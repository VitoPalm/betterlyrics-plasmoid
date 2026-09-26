#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Vito Palmieri
# SPDX-License-Identifier: GPL-3.0-only
"""Lyrics provider backend for the Better Lyrics Plasma widget.

The command has two intentionally independent phases. ``fast`` checks the
Firefox extension cache and races the public fallback providers. ``rich``
checks the cache for word/syllable data, then consumes Better Lyrics' Unified
SSE stream when Zen has a still-valid token.  Each invocation prints exactly
one JSON object so Plasma's executable data engine can safely consume it.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import contextlib
import ctypes
import ctypes.util
import gzip
import html
import json
import os
import re
import sqlite3
import socket
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path


USER_AGENT = "BetterLyrics-Plasma/2.0"
YOUTUBE_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
LYRIC_CACHE_VERSION = "2.1.0"
UNISON_URL = "https://unison.betterlyrics.org/lyrics"
BINIMUM_URL = "https://lyrics-api.binimum.org/"
LRCLIB_GET_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
UNIFIED_URL = "https://lyrics.api.dacubeking.com/v2/lyrics"
EXTENSION_DB_NAME = "3647222921wleabcEoxlt-eengsairo.sqlite"
FRAME_HEADER = b"\xff\x06\x00\x00sNaPpY"
COMPRESSED_PREFIX = "__COMPRESSED__"

# Better Lyrics' configured provider order. Lower is better.
PROVIDER_PRIORITY = {
    "bLyrics-richsynced": 0,
    "unison-richsynced": 1,
    "binimum-richsynced": 2,
    "unison-wordsynced": 3,
    "portato-richsynced": 4,
    "musixmatch-richsync": 5,
    "bLyrics-synced": 6,
    "unison-synced": 7,
    "yt-captions": 8,
    "binimum-synced": 9,
    "lrclib-synced": 10,
    "legato-synced": 11,
    "musixmatch-synced": 12,
    "yt-lyrics": 13,
    "unison-plain": 14,
    "lrclib-plain": 15,
}
RICH_KEYS = {key for key in PROVIDER_PRIORITY if "rich" in key or "word" in key or "portato" in key}
UNIFIED_KEYS = {
    "bLyrics-richsynced", "bLyrics-synced", "binimum-richsynced", "binimum-synced",
    "portato-richsynced", "musixmatch-richsync", "musixmatch-synced",
    "lrclib-synced", "lrclib-plain", "legato-synced",
}
EXTENSION_ID = "betterlyrics@boidu.dev"


@lru_cache(maxsize=1)
def preferred_provider_order():
    """Match the extension's merged storage.sync order, including d_ disables."""
    defaults = list(PROVIDER_PRIORITY)
    stored = None
    for database in zen_database_paths():
        sync_database = database.parents[4] / "storage-sync-v2.sqlite"
        if not sync_database.exists():
            continue
        try:
            with contextlib.closing(sqlite3.connect(sync_database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
                row = db.execute("SELECT data FROM storage_sync_data WHERE ext_id = ?", (EXTENSION_ID,)).fetchone()
                if row:
                    document = json.loads(row[0])
                    value = document.get("preferredProviderList") if isinstance(document, dict) else None
                    if isinstance(value, list):
                        stored = [item for item in value if isinstance(item, str)]
                        break
        except (OSError, sqlite3.Error, ValueError):
            continue
    if stored is None:
        return defaults
    merged = stored[:]
    def index_of(key):
        return next((i for i, item in enumerate(merged) if item.removeprefix("d_") == key), -1)
    for default_index, key in enumerate(defaults):
        if index_of(key) >= 0:
            continue
        insert_at = -1
        for before in range(default_index - 1, -1, -1):
            predecessor = index_of(defaults[before])
            if predecessor >= 0:
                insert_at = predecessor + 1
                break
        if insert_at < 0:
            for after in range(default_index + 1, len(defaults)):
                successor = index_of(defaults[after])
                if successor >= 0:
                    insert_at = successor
                    break
        if insert_at < 0:
            insert_at = len(merged)
        merged.insert(insert_at, key)
    return [key for key in merged if key in PROVIDER_PRIORITY]


def provider_rank(provider: str):
    try:
        return preferred_provider_order().index(provider)
    except ValueError:
        return None


def request(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 8.0):
    values = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    values.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=values, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def get_json(url: str, timeout: float = 7.0):
    return json.loads(request(url, timeout=timeout))


def clean_lyric_text(value, *, collapse=False):
    """Return provider text without XML/HTML presentation markup.

    Some otherwise-valid TTML feeds contain nested background-vocal spans.
    Tolerant/regex parsers can expose a malformed closing fragment such as
    ``/span>`` as text, so remove both complete tags and those fragments after
    decoding entities. Lyrics are always rendered as plain text by QML.
    """
    text = html.unescape(str(value or ""))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"(?i)/(?:span|p|div|body|tt)\s*>", "", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip() if collapse else text


def line(start: int, duration: int, words: str, parts=None, *, unsynced=False):
    cleaned_parts = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        cleaned = clean_lyric_text(part.get("words", ""))
        if cleaned:
            cleaned_parts.append({**part, "words": cleaned})
    return {
        "startTimeMs": max(0, round(start)),
        "durationMs": max(0, round(duration)),
        "words": clean_lyric_text(words, collapse=True),
        "parts": cleaned_parts,
        "isInstrumental": False,
        "isUnsynced": unsynced,
    }


def time_ms(value: str) -> int:
    value = (value or "").strip()
    match = re.fullmatch(r"([\d.]+)(h|m|s|ms)", value)
    if match:
        scale = {"h": 3_600_000, "m": 60_000, "s": 1_000, "ms": 1}[match.group(2)]
        return round(float(match.group(1)) * scale)
    pieces = value.split(":")
    try:
        if len(pieces) == 2:
            return round(float(pieces[0]) * 60_000 + float(pieces[1]) * 1_000)
        if len(pieces) == 3:
            return round(float(pieces[0]) * 3_600_000 + float(pieces[1]) * 60_000 + float(pieces[2]) * 1_000)
        return round(float(value) * 1_000)
    except ValueError:
        return 0


def finish_durations(lines: list[dict], duration_ms: int):
    lines.sort(key=lambda item: item["startTimeMs"])
    for index, item in enumerate(lines):
        if item["durationMs"] <= 0:
            end = lines[index + 1]["startTimeMs"] if index + 1 < len(lines) else duration_ms
            item["durationMs"] = max(500, end - item["startTimeMs"]) if end > item["startTimeMs"] else 4000
        parts = item.get("parts") or []
        for part_index, part in enumerate(parts):
            if part.get("durationMs", 0) <= 0:
                end = parts[part_index + 1]["startTimeMs"] if part_index + 1 < len(parts) else item["startTimeMs"] + item["durationMs"]
                part["durationMs"] = max(50, end - part["startTimeMs"])
    return lines


def parse_plain(value: str, duration_ms: int):
    values = [item.strip() for item in value.splitlines() if item.strip() and not re.match(r"^\[(ar|ti|al|by|offset|length|re|ve):", item, re.I)]
    if not values:
        return []
    step = (duration_ms or len(values) * 4000) / len(values)
    return [line(index * step, step, value, unsynced=True) for index, value in enumerate(values)]


def parse_lrc(value: str, duration_ms: int):
    offset_match = re.search(r"^\s*\[offset:([+-]?\d+)\]\s*$", value, re.I | re.M)
    offset = int(offset_match.group(1)) if offset_match else 0
    result = []
    for raw in value.splitlines():
        stamps = re.findall(r"\[(\d+:\d+(?:\.\d+)?)\]", raw)
        if not stamps:
            continue
        content = re.sub(r"\[\d+:\d+(?:\.\d+)?\]", "", raw).strip()
        if not content:
            continue
        word_matches = list(re.finditer(r"<(\d+:\d+(?:\.\d+)?)>([^<]*)", content))
        parts = []
        for match in word_matches:
            parts.append({"startTimeMs": max(0, time_ms(match.group(1)) + offset), "durationMs": 0,
                          "words": match.group(2), "isBackground": False})
        words = re.sub(r"<\d+:\d+(?:\.\d+)?>", "", content).strip()
        first = max(0, time_ms(stamps[0]) + offset)
        for stamp in stamps:
            start = max(0, time_ms(stamp) + offset)
            delta = start - first
            shifted = [{**part, "startTimeMs": max(0, part["startTimeMs"] + delta)} for part in parts]
            result.append(line(start, 0, words, shifted))
    return finish_durations(result, duration_ms) if result else parse_plain(value, duration_ms)


def _xml_attribute(element, name):
    for key, value in element.attrib.items():
        if key.rsplit("}", 1)[-1].rsplit(":", 1)[-1] == name:
            return value
    return None


def _xml_local_name(element):
    return element.tag.rsplit("}", 1)[-1].lower()


def _parse_ttml_xml(value: str, duration_ms: int):
    root = ET.fromstring(value)
    result = []
    for paragraph in root.iter():
        if _xml_local_name(paragraph) != "p":
            continue
        begin = _xml_attribute(paragraph, "begin")
        if not begin:
            continue
        start = time_ms(begin)
        end = _xml_attribute(paragraph, "end")
        stop = time_ms(end) if end else 0
        full, parts = [], []
        pending = ""

        def append_text(text):
            nonlocal pending
            text = clean_lyric_text(text)
            if not text:
                return
            full.append(text)
            if parts:
                parts[-1]["words"] += text
            else:
                pending += text

        def visit(container, inherited_background=False):
            nonlocal pending
            append_text(container.text)
            for child in container:
                role = (_xml_attribute(child, "role") or "").lower()
                background = inherited_background or role == "x-bg"
                child_begin = _xml_attribute(child, "begin")
                child_end = _xml_attribute(child, "end")
                if _xml_local_name(child) == "span" and child_begin and child_end:
                    text = clean_lyric_text("".join(child.itertext()))
                    if text:
                        full.append(text)
                        part_start, part_end = time_ms(child_begin), time_ms(child_end)
                        parts.append({
                            "startTimeMs": part_start,
                            "durationMs": max(50, part_end - part_start),
                            "words": pending + text,
                            "isBackground": background,
                        })
                        pending = ""
                else:
                    visit(child, background)
                append_text(child.tail)

        visit(paragraph, (_xml_attribute(paragraph, "role") or "").lower() == "x-bg")
        words = clean_lyric_text("".join(full), collapse=True)
        if words:
            result.append(line(start, max(0, stop - start), words, parts))
    return finish_durations(result, duration_ms)


def _parse_ttml_regex(value: str, duration_ms: int):
    result = []
    for match in re.finditer(r"<p\b([^>]*)>([\s\S]*?)</p>", value, re.I):
        attrs, body = match.groups()
        begin = re.search(r"\bbegin=[\"']([^\"']+)", attrs, re.I)
        if not begin:
            continue
        end = re.search(r"\bend=[\"']([^\"']+)", attrs, re.I)
        start = time_ms(begin.group(1))
        stop = time_ms(end.group(1)) if end else 0
        parts = []
        full = []
        for token in re.finditer(r"<span\b([^>]*)>([\s\S]*?)</span>|([^<]+)", body, re.I):
            if token.group(3) is not None:
                text = clean_lyric_text(token.group(3))
                full.append(text)
                if parts:
                    parts[-1]["words"] += text
                continue
            span_attrs, span_body = token.group(1), token.group(2)
            text = clean_lyric_text(span_body)
            full.append(text)
            span_begin = re.search(r"\bbegin=[\"']([^\"']+)", span_attrs, re.I)
            span_end = re.search(r"\bend=[\"']([^\"']+)", span_attrs, re.I)
            if text and span_begin and span_end:
                part_start, part_end = time_ms(span_begin.group(1)), time_ms(span_end.group(1))
                parts.append({"startTimeMs": part_start, "durationMs": max(50, part_end - part_start),
                              "words": text, "isBackground": "x-bg" in span_attrs})
        words = clean_lyric_text("".join(full), collapse=True)
        if words:
            result.append(line(start, max(0, stop - start), words, parts))
    return finish_durations(result, duration_ms)


def parse_ttml(value: str, duration_ms: int):
    try:
        return _parse_ttml_xml(value, duration_ms)
    except (ET.ParseError, ValueError, TypeError):
        # A few community submissions are intentionally XML-like rather than
        # well-formed XML. Keep the tolerant parser, then rely on line()'s
        # shared sanitation so presentation tags still cannot reach QML.
        return _parse_ttml_regex(value, duration_ms)


def parse_qrc(value: str, duration_ms: int):
    match = re.search(r"LyricContent=[\"']([\s\S]*?)[\"'](?:\s|/?>)", value, re.I)
    content = html.unescape(match.group(1)) if match else value
    result = []
    for raw in content.splitlines():
        timing = re.search(r"\[(\d+),(\d+)\]", raw)
        if not timing:
            continue
        start, duration = int(timing.group(1)), int(timing.group(2))
        body = raw[timing.end():]
        parts = []
        words = []
        cursor = 0
        for part in re.finditer(r"([^()]*)\((\d+),(\d+)\)", body):
            text = part.group(1)
            if part.start() > cursor and not text:
                text = body[cursor:part.start()]
            cursor = part.end()
            words.append(text)
            parts.append({"startTimeMs": int(part.group(2)), "durationMs": int(part.group(3)),
                          "words": text, "isBackground": False})
        cleaned = "".join(words).strip() or re.sub(r"\(\d+,\d+\)", "", body).strip()
        if cleaned:
            result.append(line(start, duration, cleaned, parts))
    return finish_durations(result, duration_ms)


def normalize_cached_result(provider: str, value: dict, duration_ms: int):
    rank = provider_rank(provider)
    if rank is None or not isinstance(value, dict) or value.get("version") != LYRIC_CACHE_VERSION:
        return None
    lyrics = value.get("lyrics")
    if not isinstance(lyrics, list) or not lyrics:
        return None
    normalized = []
    for item in lyrics:
        if not isinstance(item, dict) or not isinstance(item.get("words"), str):
            continue
        normalized.append(line(item.get("startTimeMs", 0), item.get("durationMs", 0), item["words"], item.get("parts"),
                               unsynced=provider.endswith("plain") or provider == "yt-lyrics"))
    if not normalized:
        return None
    finish_durations(normalized, duration_ms)
    sync_type = provider_sync_type(provider, normalized)
    return {"source": value.get("source") or provider, "provider": provider, "syncType": sync_type,
            "quality": 100 - rank, "lines": normalized, "cache": "zen"}


def provider_sync_type(provider: str, lines: list[dict]):
    if provider in ("unison-wordsynced", "portato-richsynced", "musixmatch-richsync"):
        return "word"
    if provider.endswith("plain") or provider == "yt-lyrics":
        return "none"
    return "syllable" if any(item.get("parts") for item in lines) else "line"


class CloneDecoder:
    """Small Firefox structured-clone reader for extension storage values.

    It intentionally supports only the JSON-like types used by
    ``browser.storage.local``. The format constants come from Mozilla's public
    structured-clone format. Google dfIndexedDB's parser was used as an
    interoperability reference during development.
    """

    HEADER, NULL, UNDEFINED, BOOLEAN, INT32, STRING = 0xFFF10000, 0xFFFF0000, 0xFFFF0001, 0xFFFF0002, 0xFFFF0003, 0xFFFF0004
    ARRAY, OBJECT, END = 0xFFFF0007, 0xFFFF0008, 0xFFFF0013

    def __init__(self, raw: bytes):
        self.raw = raw
        self.pos = 0

    def pair(self):
        if self.pos + 8 > len(self.raw):
            raise ValueError("truncated structured clone")
        data, tag = struct.unpack_from("<II", self.raw, self.pos)
        self.pos += 8
        return tag, data

    def align(self):
        self.pos = (self.pos + 7) & ~7

    def read_value(self):
        tag, data = self.pair()
        if tag == self.NULL:
            value = None
        elif tag == self.UNDEFINED:
            value = None
        elif tag == self.BOOLEAN:
            value = bool(data)
        elif tag == self.INT32:
            value = data if data < 0x80000000 else data - 0x100000000
        elif tag == self.STRING:
            length, latin = data & 0x7FFFFFFF, data & 0x80000000
            size = length if latin else length * 2
            chunk = self.raw[self.pos:self.pos + size]
            self.pos += size
            value = chunk.decode("latin-1" if latin else "utf-16-le")
        elif tag == self.OBJECT:
            value = {}
            self.align()
            while True:
                next_tag = struct.unpack_from("<I", self.raw, self.pos + 4)[0]
                if next_tag == self.END:
                    self.pair()
                    break
                key = self.read_value()
                self.align()
                value[key] = self.read_value()
                self.align()
        elif tag == self.ARRAY:
            value = [None] * data
            self.align()
            while True:
                next_tag = struct.unpack_from("<I", self.raw, self.pos + 4)[0]
                if next_tag == self.END:
                    self.pair()
                    break
                key = self.read_value()
                self.align()
                item = self.read_value()
                self.align()
                if isinstance(key, int) and 0 <= key < len(value):
                    value[key] = item
        elif tag < 0xFFF00000:
            value = struct.unpack("<d", struct.pack("<II", data, tag))[0]
        else:
            raise ValueError(f"unsupported clone tag {tag:#x}")
        self.align()
        return value

    @classmethod
    def decode(cls, raw: bytes):
        unpacked = snappy_uncompress(raw)
        decoder = cls(unpacked)
        tag, _ = decoder.pair()
        if tag != cls.HEADER:
            raise ValueError("structured-clone header missing")
        return decoder.read_value()


def snappy_uncompress(raw: bytes) -> bytes:
    library = ctypes.util.find_library("snappy")
    if not library:
        raise RuntimeError("libsnappy is unavailable")
    snappy = ctypes.CDLL(library)
    length = ctypes.c_size_t()
    source = ctypes.create_string_buffer(raw)
    if snappy.snappy_uncompressed_length(source, len(raw), ctypes.byref(length)) != 0:
        raise ValueError("invalid Snappy data")
    destination = ctypes.create_string_buffer(length.value)
    if snappy.snappy_uncompress(source, len(raw), destination, ctypes.byref(length)) != 0:
        raise ValueError("Snappy decompression failed")
    return destination.raw[:length.value]


def decode_idb_key(raw: bytes):
    if not raw or raw[0] != 0x30:
        return None
    return bytes((value - 1) & 0xFF for value in raw[1:]).decode("utf-8", "replace")


def zen_database_paths():
    roots = [Path.home() / ".var/app/app.zen_browser.zen/.zen", Path.home() / ".zen"]
    found = []
    for root in roots:
        if root.exists():
            found.extend(root.glob(f"*/storage/default/moz-extension+++*/idb/{EXTENSION_DB_NAME}"))
    return sorted(found, key=lambda item: item.stat().st_mtime, reverse=True)


def read_zen_storage(keys: set[str]):
    remaining, values = set(keys), {}
    for database in zen_database_paths():
        if not remaining:
            break
        try:
            uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
            with contextlib.closing(sqlite3.connect(uri, uri=True)) as connection:
                for raw_key, raw_value in connection.execute("SELECT key, data FROM object_data"):
                    key = decode_idb_key(bytes(raw_key))
                    if key in remaining:
                        try:
                            values[key] = CloneDecoder.decode(bytes(raw_value))
                            remaining.remove(key)
                        except (ValueError, RuntimeError):
                            pass
        except (OSError, sqlite3.Error):
            continue
    return values


def decode_transient(item):
    if not isinstance(item, dict) or item.get("expiry", 0) and item["expiry"] <= time.time() * 1000:
        return None
    value = item.get("value")
    if not isinstance(value, str):
        return None
    try:
        if value.startswith(COMPRESSED_PREFIX):
            value = gzip.decompress(base64.b64decode(value[len(COMPRESSED_PREFIX):])).decode("utf-8")
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) and parsed.get("missing") is not True else None
    except (ValueError, OSError):
        return None


def cached_lyrics(video_id: str, duration_ms: int, rich_only=False, providers=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        return None
    selected = [key for key in PROVIDER_PRIORITY if (not rich_only or key in RICH_KEYS)
                and (providers is None or key in providers)]
    keys = {f"blyrics_{video_id}_{provider}" for provider in selected}
    stored = read_zen_storage(keys)
    candidates = []
    for provider in selected:
        value = decode_transient(stored.get(f"blyrics_{video_id}_{provider}"))
        result = normalize_cached_result(provider, value, duration_ms) if value else None
        if result:
            candidates.append(result)
    return best_result(*candidates)


def cached_metadata(video_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        return None
    key = f"blyrics_{video_id}_metadata"
    data = decode_transient(read_zen_storage({key}).get(key))
    return data if data and data.get("version") == LYRIC_CACHE_VERSION else None


def best_result(*items):
    candidates = [item for item in items if item and provider_rank(item["provider"]) is not None]
    return min(candidates, key=lambda item: provider_rank(item["provider"])) if candidates else None


def extension_key_id():
    identity = read_zen_storage({"userIdentity"}).get("userIdentity")
    if isinstance(identity, dict) and isinstance(identity.get("keyId"), str):
        return identity["keyId"]
    return "better-lyrics-default"


def unison(meta):
    if not meta.video_id:
        return None
    query = {"v": meta.video_id, "song": meta.title, "artist": meta.artist, "duration": meta.duration}
    if meta.album:
        query["album"] = meta.album
    data = json.loads(request(f"{UNISON_URL}?{urllib.parse.urlencode(query)}",
                              headers={"x-key-id": extension_key_id()}, timeout=10))
    payload = data.get("data", data)
    lyrics = payload.get("lyrics") if isinstance(payload, dict) else None
    if not lyrics:
        return None
    format_name = payload.get("format")
    if format_name == "ttml" or "<tt" in lyrics:
        lines = parse_ttml(lyrics, meta.duration_ms)
    elif format_name == "plain":
        lines = parse_plain(lyrics, meta.duration_ms)
    else:
        lines = parse_lrc(lyrics, meta.duration_ms)
    if format_name == "plain":
        provider = "unison-plain"
    elif format_name == "lrc":
        provider = "unison-wordsynced" if payload.get("syncType") == "richsync" else "unison-synced"
    else:
        provider = "unison-richsynced" if any(item.get("parts") for item in lines) else "unison-synced"
    return result("Unison", provider, lines)


def binimum(meta):
    queries = []
    if meta.duration:
        full = {"track": meta.title, "artist": meta.artist, "duration": meta.duration}
        if meta.album:
            full["album"] = meta.album
        queries.append(full)
    stripped = re.sub(r"\s*[\[(](?:feat\.?|ft\.?|featuring)\b.*?[\])]", "", meta.title, flags=re.I).strip()
    queries.append({"track": stripped or meta.title, "artist": meta.artist.replace("，", ",")})
    for query in queries:
        try:
            data = get_json(f"{BINIMUM_URL}?{urllib.parse.urlencode(query)}")
            entries = data.get("results", []) if isinstance(data, dict) else []
            if not entries or not entries[0].get("lyricsUrl"):
                continue
            lines = parse_ttml(request(entries[0]["lyricsUrl"]), meta.duration_ms)
            if lines:
                rich = any(item.get("parts") for item in lines)
                return result("BiniLyrics", "binimum-richsynced" if rich else "binimum-synced", lines)
        except (urllib.error.URLError, ValueError, OSError):
            continue
    return None


def match_score(item, meta):
    normalize = lambda value: re.sub(r"[^\w]+", " ", (value or "").casefold()).strip()
    title, artist = normalize(meta.title), normalize(meta.artist)
    candidate_title, candidate_artist = normalize(item.get("trackName") or item.get("name")), normalize(item.get("artistName"))
    score = 80 if title and title == candidate_title else (30 if candidate_title and title and (title in candidate_title or candidate_title in title) else 0)
    score += 50 if artist and artist == candidate_artist else (20 if candidate_artist and artist and (artist in candidate_artist or candidate_artist in artist) else 0)
    if meta.duration and item.get("duration"):
        score += max(-50, 35 - abs(float(item["duration"]) - meta.duration) * 3)
    return score


def lrclib(meta):
    exact_query = {"track_name": meta.title, "artist_name": meta.artist}
    if meta.album:
        exact_query["album_name"] = meta.album
    if meta.duration:
        exact_query["duration"] = meta.duration
    plain = None
    try:
        data = get_json(f"{LRCLIB_GET_URL}?{urllib.parse.urlencode(exact_query)}")
        if isinstance(data, dict):
            if data.get("syncedLyrics"):
                synced = result("LRCLIB", "lrclib-synced", parse_lrc(data["syncedLyrics"], meta.duration_ms))
                if synced:
                    return synced
            if data.get("plainLyrics"):
                plain = result("LRCLIB", "lrclib-plain", parse_plain(data["plainLyrics"], meta.duration_ms))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        pass
    stripped = re.sub(r"\s*[\[(](?:feat\.?|ft\.?)\b.*?[\])]", "", meta.title, flags=re.I).strip() or meta.title
    artist = re.sub(r"[·•]", " ", meta.artist).strip()
    searches = (
        {"track_name": stripped, "artist_name": artist},
        {"q": f"{stripped} {artist}".strip()},
    )
    for query in searches:
        try:
            entries = get_json(f"{LRCLIB_SEARCH_URL}?{urllib.parse.urlencode(query)}")
        except (urllib.error.URLError, ValueError):
            continue
        if not isinstance(entries, list):
            continue
        entries = sorted((item for item in entries if isinstance(item, dict)),
                         key=lambda item: match_score(item, meta), reverse=True)
        for item in entries:
            if item.get("syncedLyrics"):
                lines = parse_lrc(item["syncedLyrics"], meta.duration_ms)
                if lines:
                    synced = result("LRCLIB", "lrclib-synced", lines)
                    if synced:
                        return synced
        for item in entries:
            if item.get("plainLyrics") and not plain:
                plain = result("LRCLIB", "lrclib-plain", parse_plain(item["plainLyrics"], meta.duration_ms))
    return plain


def embedded_json(page: str, marker: str):
    match = re.search(marker + r"\s*[:=]\s*", page)
    if not match:
        return None
    try:
        return json.JSONDecoder().raw_decode(page[match.end():])[0]
    except ValueError:
        return None


def youtube_page(video_id: str, *, music=False):
    host = "music.youtube.com" if music else "www.youtube.com"
    url = f"https://{host}/watch?v={urllib.parse.quote(video_id)}"
    req = urllib.request.Request(url, headers={"User-Agent": YOUTUBE_USER_AGENT,
                                               "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read(3_000_000).decode("utf-8", "replace")


def youtube_api(endpoint: str, api_key: str, context: dict, payload: dict, video_id: str):
    url = f"https://music.youtube.com/youtubei/v1/{endpoint}?key={urllib.parse.quote(api_key)}"
    body = json.dumps({"context": context, **payload}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": YOUTUBE_USER_AGENT, "Content-Type": "application/json",
        "Origin": "https://music.youtube.com",
        "Referer": f"https://music.youtube.com/watch?v={video_id}",
    })
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def nested(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def yt_music_lyrics(meta):
    if not meta.video_id:
        return None
    page = youtube_page(meta.video_id, music=True)
    api_key = embedded_json(page, r'"INNERTUBE_API_KEY"')
    context = embedded_json(page, r'"INNERTUBE_CONTEXT"')
    if not isinstance(api_key, str) or not isinstance(context, dict):
        return None
    next_data = youtube_api("next", api_key, context, {"videoId": meta.video_id}, meta.video_id)
    tabs = nested(next_data, "contents", "singleColumnMusicWatchNextResultsRenderer", "tabbedRenderer",
                  "watchNextTabbedResultsRenderer", "tabs") or []
    if len(tabs) < 2:
        return None
    tab = tabs[1].get("tabRenderer", {})
    if tab.get("unselectable"):
        return None
    browse_id = nested(tab, "endpoint", "browseEndpoint", "browseId")
    if not browse_id:
        return None
    data = youtube_api("browse", api_key, context, {"browseId": browse_id}, meta.video_id)
    shelf = nested(data, "contents", "sectionListRenderer", "contents") or []
    if not shelf:
        return None
    shelf = shelf[0].get("musicDescriptionShelfRenderer", {})
    text_runs = nested(shelf, "description", "runs") or []
    source_runs = nested(shelf, "footer", "runs") or []
    if not text_runs or not source_runs:
        return None
    lyrics = text_runs[0].get("text", "")
    source_text = source_runs[0].get("text", "")
    if not lyrics or not source_text:
        return None
    source = source_text[8:] + " (via YT)"
    return result(source, "yt-lyrics", parse_plain(lyrics, meta.duration_ms))


def parse_youtube_captions(data):
    if not isinstance(data, dict):
        return []
    lines = []
    for event in data.get("events", []):
        if not isinstance(event, dict) or not isinstance(event.get("segs"), list):
            continue
        words = "".join(segment.get("utf8", "") for segment in event["segs"] if isinstance(segment, dict))
        words = words.replace("\n", " ").strip(" \t♪𝅘𝅥𝅮𝅘𝅥𝅯𝅘𝅥𝅰𝅘𝅥𝅱𝅘𝅥𝅲")
        if words:
            lines.append(line(event.get("tStartMs", 0), event.get("dDurationMs", 0), words))
    if lines and all(item["words"].upper() == item["words"] for item in lines):
        for item in lines:
            item["words"] = item["words"][:1].upper() + item["words"][1:].lower()
    return lines


def yt_captions(meta):
    if not meta.video_id:
        return None
    page = youtube_page(meta.video_id)
    player = embedded_json(page, r"ytInitialPlayerResponse")
    tracks = nested(player, "captions", "playerCaptionsTracklistRenderer", "captionTracks") or []
    if not tracks:
        return None
    if len(tracks) == 1:
        lang = tracks[0].get("languageCode")
    else:
        auto = next((track for track in tracks if track.get("kind") == "asr"), None)
        lang = auto.get("languageCode") if auto else None
    if not lang:
        return None
    selected = next((track for track in tracks if track.get("kind") != "asr"
                     and track.get("languageCode", "").split("-")[0] == lang.split("-")[0]), None)
    if not selected or not selected.get("baseUrl"):
        return None
    parsed_url = urllib.parse.urlparse(selected["baseUrl"])
    query = urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "fmt"] + [("fmt", "json3")]
    url = urllib.parse.urlunparse(parsed_url._replace(query=urllib.parse.urlencode(query)))
    req = urllib.request.Request(url, headers={"User-Agent": YOUTUBE_USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as response:
        lines = parse_youtube_captions(json.load(response))
    return result("YouTube Captions", "yt-captions", lines)


def result(source, provider, lines):
    rank = provider_rank(provider)
    if not lines or rank is None:
        return None
    return {"source": source, "provider": provider,
            "syncType": provider_sync_type(provider, lines),
            "quality": 100 - rank, "lines": lines}


def fast_phase(meta):
    cached = cached_lyrics(meta.video_id, meta.duration_ms)
    if cached and provider_rank(cached["provider"]) == 0:
        return cached
    candidates = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(provider, meta) for provider in
                   (unison, binimum, lrclib)]
        for future in concurrent.futures.as_completed(futures):
            try:
                value = future.result()
                if value:
                    candidates.append(value)
            except (urllib.error.URLError, TimeoutError, ValueError, TypeError, KeyError, OSError):
                pass
    return best_result(cached, *candidates)


def youtube_phase(meta):
    if not meta.video_id:
        return None
    candidates = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(provider, meta) for provider in (yt_music_lyrics, yt_captions)]
        for future in concurrent.futures.as_completed(futures):
            try:
                candidates.append(future.result())
            except (urllib.error.URLError, TimeoutError, ValueError, TypeError, KeyError, OSError):
                pass
    return best_result(*candidates)


def bridge_socket_path():
    override = os.environ.get("BETTERLYRICS_BRIDGE_SOCKET")
    if override:
        return Path(override)
    return (Path.home() / ".var/app/app.zen_browser.zen/cache/"
            "betterlyrics-plasmoid-bridge/bridge.sock")


def segment_shift(segment_map, time_ms):
    shift = 0
    if not isinstance(segment_map, dict):
        return shift
    for segment in segment_map.get("segment", []):
        if not isinstance(segment, dict):
            continue
        counterpart = segment.get("counterpartVideoStartTimeMilliseconds")
        primary = segment.get("primaryVideoStartTimeMilliseconds")
        duration = segment.get("durationMilliseconds")
        if not all(isinstance(value, (int, float)) for value in (counterpart, primary, duration)):
            continue
        if time_ms >= counterpart:
            shift = primary - counterpart
            if time_ms <= counterpart + duration:
                break
    return shift


def normalize_bridge_result(value, meta):
    if not isinstance(value, dict) or value.get("playbackVideoId") != meta.video_id:
        return None
    provider = value.get("provider")
    if provider not in PROVIDER_PRIORITY or not isinstance(value.get("lyrics"), list):
        return None
    normalized = []
    for item in value["lyrics"]:
        if not isinstance(item, dict) or not isinstance(item.get("words"), str):
            continue
        try:
            lyric = line(item.get("startTimeMs", 0), item.get("durationMs", 0), item["words"], item.get("parts"),
                         unsynced=provider.endswith("plain") or provider == "yt-lyrics")
        except (TypeError, ValueError):
            continue
        lyric["isInstrumental"] = item.get("isInstrumental") is True
        if isinstance(item.get("romanization"), str):
            lyric["romanization"] = item["romanization"]
        if value.get("segmentMap") and not lyric["isUnsynced"]:
            lyric["startTimeMs"] += segment_shift(value["segmentMap"], lyric["startTimeMs"])
            for part in lyric["parts"]:
                part["startTimeMs"] += segment_shift(value["segmentMap"], part["startTimeMs"])
        normalized.append(lyric)
    if not normalized:
        return None
    finish_durations(normalized, meta.duration_ms)
    return {"source": value.get("source") or provider, "provider": provider,
            "syncType": provider_sync_type(provider, normalized), "quality": 1000,
            "lines": normalized, "bridge": True}


def bridge_phase(meta):
    path = bridge_socket_path()
    if not meta.video_id or not path.is_socket():
        return None
    request_value = {"videoId": meta.video_id, "title": meta.title, "artist": meta.artist,
                     "album": meta.album, "duration": meta.duration}
    try:
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(62)
            connection.connect(str(path))
            connection.sendall(json.dumps(request_value, separators=(",", ":")).encode() + b"\n")
            with connection.makefile("rb") as stream:
                raw = stream.readline(1_000_001)
        if not raw or len(raw) > 1_000_000:
            return None
        response = json.loads(raw)
        if response.get("ok") is not True:
            return None
        return normalize_bridge_result(response.get("result"), meta)
    except (OSError, ValueError, TypeError):
        return None


def jwt_expiry(token: str):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (ValueError, KeyError, IndexError, json.JSONDecodeError):
        return 0


def unified_results(provider, results, meta):
    """Map every provider event to the extension's source keys."""
    if not isinstance(results, dict):
        return []
    found = []
    try:
        if provider == "musixmatch":
            if results.get("wordByWord"):
                found.append(result("Musixmatch", "musixmatch-richsync",
                                    parse_lrc(results["wordByWord"], meta.duration_ms)))
            if results.get("synced"):
                found.append(result("Musixmatch", "musixmatch-synced",
                                    parse_lrc(results["synced"], meta.duration_ms)))
        elif provider == "lrclib":
            if results.get("synced"):
                found.append(result("LRCLib", "lrclib-synced", parse_lrc(results["synced"], meta.duration_ms)))
            if results.get("plain"):
                found.append(result("LRCLib", "lrclib-plain", parse_plain(results["plain"], meta.duration_ms)))
        elif provider == "kugou" and results.get("lyrics"):
            payload = json.loads(results["lyrics"]) if isinstance(results["lyrics"], str) else results["lyrics"]
            found.append(result("Better Lyrics Legato", "legato-synced",
                                parse_lrc(payload.get("lyrics", ""), meta.duration_ms)))
        elif provider == "qq" and results.get("lyrics"):
            payload = json.loads(results["lyrics"]) if isinstance(results["lyrics"], str) else results["lyrics"]
            found.append(result("Better Lyrics Portato", "portato-richsynced",
                                parse_qrc(payload.get("lyrics", ""), meta.duration_ms)))
        elif provider == "golyrics" and results.get("lyrics"):
            lyrics = results["lyrics"]
            try:
                parsed = json.loads(lyrics)
                if isinstance(parsed, dict):
                    lyrics = parsed.get("ttml", lyrics)
            except (ValueError, TypeError):
                pass
            lines = parse_ttml(lyrics, meta.duration_ms)
            key = "bLyrics-richsynced" if any(item.get("parts") for item in lines) else "bLyrics-synced"
            found.append(result("betterlyrics.org", key, lines))
        elif provider == "binimum" and results.get("lyrics"):
            lines = parse_ttml(results["lyrics"], meta.duration_ms)
            timing = results.get("timingType")
            rich = timing == "syllable" or (timing != "line" and any(item.get("parts") for item in lines))
            found.append(result("BiniLyrics", "binimum-richsynced" if rich else "binimum-synced", lines))
    except (ValueError, TypeError, AttributeError):
        return []
    return [item for item in found if item]


def process_sse_event(event, data_lines, meta):
    if not data_lines:
        return []
    try:
        payload = json.loads("".join(data_lines))
    except (ValueError, TypeError):
        return []
    if event == "metadata" and isinstance(payload, dict):
        for key, attribute in (("song", "title"), ("artist", "artist"), ("album", "album")):
            if payload.get(key):
                setattr(meta, attribute, payload[key])
        try:
            if float(payload.get("duration") or 0) > 0:
                meta.duration = round(float(payload["duration"]))
                meta.duration_ms = meta.duration * 1000
        except (ValueError, TypeError):
            pass
    if event == "provider" and isinstance(payload, dict):
        return unified_results(payload.get("provider"), payload.get("results"), meta)
    return []


def clean_track_title(value: str):
    value = re.sub(r"\s*\|\s*YouTube Music$", "", value, flags=re.I)
    value = re.sub(r"\s*[\[(](?:Official\s+)?(?:Music\s+)?(?:Video|Audio|Lyric\s+Video|Visualizer)[\])]",
                   "", value, flags=re.I)
    return value.strip()


def clean_track_artist(value: str):
    return re.sub(r"\s*-\s*Topic$", "", value, flags=re.I).strip()


def rich_phase(meta):
    cached = cached_lyrics(meta.video_id, meta.duration_ms, providers=UNIFIED_KEYS | RICH_KEYS)
    if cached and provider_rank(cached["provider"]) == 0:
        return cached
    if not meta.video_id:
        return cached
    stored = read_zen_storage({"jwtToken"})
    token = stored.get("jwtToken")
    if not isinstance(token, str) or jwt_expiry(token) <= time.time() + 15:
        return cached
    body_values = {"videoId": meta.video_id, "alwaysFetchMetadata": "false", "token": token}
    if meta.title:
        body_values["song"] = meta.title
    if meta.artist:
        body_values["artist"] = meta.artist
    if meta.album:
        body_values["album"] = meta.album
    if meta.duration:
        body_values["duration"] = meta.duration
    body = urllib.parse.urlencode(body_values).encode()
    req = urllib.request.Request(UNIFIED_URL, data=body, method="POST", headers={
        "User-Agent": USER_AGENT, "Accept": "text/event-stream",
        "Content-Type": "application/x-www-form-urlencoded", "Origin": "https://betterlyrics.org",
    })
    candidates = [cached] if cached else []
    try:
        with urllib.request.urlopen(req, timeout=22) as response:
            event, data_lines = "", []
            for raw in response:
                text = raw.decode("utf-8", "replace").rstrip("\r\n")
                if not text:
                    candidates.extend(process_sse_event(event, data_lines, meta))
                    event, data_lines = "", []
                elif text.startswith("event:"):
                    event = text[6:].strip()
                elif text.startswith("data:"):
                    data_lines.append(text[5:].strip())
            candidates.extend(process_sse_event(event, data_lines, meta))
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    return best_result(*candidates)


class Metadata:
    def __init__(self, args):
        decode = lambda value: urllib.parse.unquote(value or "")
        self.title = clean_track_title(decode(args.title))
        self.artist = clean_track_artist(decode(args.artist))
        self.album = decode(args.album).strip()
        self.video_id = decode(args.video_id).strip()
        self.duration = max(0, round(args.duration or 0))
        self.duration_ms = self.duration * 1000
        metadata = cached_metadata(self.video_id)
        if metadata:
            for key, attribute in (("song", "title"), ("artist", "artist"), ("album", "album")):
                if isinstance(metadata.get(key), str) and metadata[key].strip():
                    setattr(self, attribute, metadata[key].strip())
            try:
                if float(metadata.get("duration") or 0) > 0:
                    self.duration = round(float(metadata["duration"]))
                    self.duration_ms = self.duration * 1000
            except (ValueError, TypeError):
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("fast", "rich", "youtube", "bridge"), required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", default="")
    parser.add_argument("--album", default="")
    parser.add_argument("--duration", type=float, default=0)
    parser.add_argument("--video-id", default="")
    parser.add_argument("--request-token", default="")
    args = parser.parse_args()
    meta = Metadata(args)
    try:
        output = {"fast": fast_phase, "rich": rich_phase, "youtube": youtube_phase,
                  "bridge": bridge_phase}[args.phase](meta)
        print(json.dumps({"ok": bool(output), "phase": args.phase, "requestToken": args.request_token,
                          "result": output}, ensure_ascii=False, separators=(",", ":")))
    except Exception as error:  # Network errors can contain the JWT-bearing request URL.
        print(json.dumps({"ok": False, "phase": args.phase, "requestToken": args.request_token,
                          "error": type(error).__name__}, separators=(",", ":")))


if __name__ == "__main__":
    main()
