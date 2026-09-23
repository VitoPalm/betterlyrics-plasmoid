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
import re
import sqlite3
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


USER_AGENT = "BetterLyrics-Plasma/2.0"
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
    "binimum-synced": 9,
    "lrclib-synced": 10,
    "legato-synced": 11,
    "musixmatch-synced": 12,
    "unison-plain": 14,
    "lrclib-plain": 15,
}
RICH_KEYS = {key for key in PROVIDER_PRIORITY if "rich" in key or "word" in key or "portato" in key}


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
    lyrics = value.get("lyrics")
    if not isinstance(lyrics, list) or not lyrics:
        return None
    normalized = []
    for item in lyrics:
        if not isinstance(item, dict) or not isinstance(item.get("words"), str):
            continue
        normalized.append(line(item.get("startTimeMs", 0), item.get("durationMs", 0), item["words"], item.get("parts"),
                               unsynced=provider.endswith("plain")))
    if not normalized:
        return None
    finish_durations(normalized, duration_ms)
    sync_type = "syllable" if any(item.get("parts") for item in normalized) else ("none" if provider.endswith("plain") else "line")
    return {"source": value.get("source") or provider, "provider": provider, "syncType": sync_type,
            "quality": 100 - PROVIDER_PRIORITY.get(provider, 99), "lines": normalized, "cache": "zen"}


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
        return None if parsed.get("missing") is True else parsed
    except (ValueError, OSError, json.JSONDecodeError):
        return None


def cached_lyrics(video_id: str, duration_ms: int, rich_only=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
        return None
    providers = [key for key in PROVIDER_PRIORITY if not rich_only or key in RICH_KEYS]
    keys = {f"blyrics_{video_id}_{provider}" for provider in providers}
    stored = read_zen_storage(keys)
    candidates = []
    for provider in providers:
        value = decode_transient(stored.get(f"blyrics_{video_id}_{provider}"))
        result = normalize_cached_result(provider, value, duration_ms) if value else None
        if result:
            candidates.append(result)
    return min(candidates, key=lambda item: PROVIDER_PRIORITY[item["provider"]]) if candidates else None


def unison(meta):
    if not meta.video_id:
        return None
    query = urllib.parse.urlencode({"v": meta.video_id, "song": meta.title, "artist": meta.artist, "duration": meta.duration})
    data = get_json(f"{UNISON_URL}?{query}")
    payload = data.get("data", data)
    lyrics = payload.get("lyrics") if isinstance(payload, dict) else None
    if not lyrics:
        return None
    if payload.get("format") == "ttml" or "<tt" in lyrics:
        lines = parse_ttml(lyrics, meta.duration_ms)
    elif payload.get("format") == "plain":
        lines = parse_plain(lyrics, meta.duration_ms)
    else:
        lines = parse_lrc(lyrics, meta.duration_ms)
    rich = payload.get("syncType") == "richsync" or any(item.get("parts") for item in lines)
    provider = "unison-richsynced" if rich else ("unison-plain" if lines and lines[0]["isUnsynced"] else "unison-synced")
    return result("Unison", provider, lines)


def binimum(meta):
    query = urllib.parse.urlencode({"track": meta.title, "artist": meta.artist, "album": meta.album, "duration": meta.duration})
    data = get_json(f"{BINIMUM_URL}?{query}")
    entries = data.get("results", []) if isinstance(data, dict) else []
    if not entries or not entries[0].get("lyricsUrl"):
        return None
    lyrics = request(entries[0]["lyricsUrl"])
    lines = parse_ttml(lyrics, meta.duration_ms)
    rich = any(item.get("parts") for item in lines)
    return result("BiniLyrics", "binimum-richsynced" if rich else "binimum-synced", lines)


def match_score(item, meta):
    normalize = lambda value: re.sub(r"[^\w]+", " ", (value or "").casefold()).strip()
    title, artist = normalize(meta.title), normalize(meta.artist)
    candidate_title, candidate_artist = normalize(item.get("trackName") or item.get("name")), normalize(item.get("artistName"))
    score = 80 if title == candidate_title else (30 if title in candidate_title or candidate_title in title else 0)
    score += 50 if artist == candidate_artist else (20 if artist in candidate_artist or candidate_artist in artist else 0)
    if meta.duration and item.get("duration"):
        score += max(-50, 35 - abs(float(item["duration"]) - meta.duration) * 3)
    return score


def lrclib(meta):
    exact = urllib.parse.urlencode({"track_name": meta.title, "artist_name": meta.artist, "album_name": meta.album, "duration": meta.duration})
    try:
        data = get_json(f"{LRCLIB_GET_URL}?{exact}")
        entries = [data]
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        query = urllib.parse.urlencode({"track_name": meta.title, "artist_name": meta.artist})
        entries = get_json(f"{LRCLIB_SEARCH_URL}?{query}")
    if not isinstance(entries, list):
        return None
    entries.sort(key=lambda item: match_score(item, meta), reverse=True)
    for item in entries:
        if item.get("syncedLyrics"):
            return result("LRCLIB", "lrclib-synced", parse_lrc(item["syncedLyrics"], meta.duration_ms))
    for item in entries:
        if item.get("plainLyrics"):
            return result("LRCLIB", "lrclib-plain", parse_plain(item["plainLyrics"], meta.duration_ms))
    return None


def result(source, provider, lines):
    if not lines:
        return None
    return {"source": source, "provider": provider,
            "syncType": "syllable" if any(item.get("parts") for item in lines) else ("none" if lines[0].get("isUnsynced") else "line"),
            "quality": 100 - PROVIDER_PRIORITY.get(provider, 99), "lines": lines}


def fast_phase(meta):
    cached = cached_lyrics(meta.video_id, meta.duration_ms)
    if cached:
        return cached
    candidates = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(provider, meta) for provider in (unison, binimum, lrclib)]
        for future in concurrent.futures.as_completed(futures):
            try:
                value = future.result()
                if value:
                    candidates.append(value)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
                pass
    return max(candidates, key=lambda item: item["quality"]) if candidates else None


def jwt_expiry(token: str):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (ValueError, KeyError, IndexError, json.JSONDecodeError):
        return 0


def unified_result(provider, results, meta):
    try:
        if provider == "musixmatch" and results.get("wordByWord"):
            return result("Musixmatch", "musixmatch-richsync", parse_lrc(results["wordByWord"], meta.duration_ms))
        if provider == "qq" and results.get("lyrics"):
            payload = json.loads(results["lyrics"])
            return result("Better Lyrics Portato", "portato-richsynced", parse_qrc(payload.get("lyrics", ""), meta.duration_ms))
        if provider == "golyrics" and results.get("lyrics"):
            lyrics = results["lyrics"]
            try:
                lyrics = json.loads(lyrics).get("ttml", lyrics)
            except (ValueError, AttributeError):
                pass
            lines = parse_ttml(lyrics, meta.duration_ms)
            return result("betterlyrics.org", "bLyrics-richsynced" if any(item.get("parts") for item in lines) else "bLyrics-synced", lines)
        if provider == "binimum" and results.get("lyrics"):
            lines = parse_ttml(results["lyrics"], meta.duration_ms)
            rich = results.get("timingType") == "syllable" or any(item.get("parts") for item in lines)
            return result("BiniLyrics", "binimum-richsynced" if rich else "binimum-synced", lines)
    except (ValueError, TypeError, AttributeError):
        return None
    return None


def rich_phase(meta):
    cached = cached_lyrics(meta.video_id, meta.duration_ms, rich_only=True)
    if cached:
        return cached
    if not meta.video_id:
        return None
    stored = read_zen_storage({"jwtToken"})
    token = stored.get("jwtToken")
    if not isinstance(token, str) or jwt_expiry(token) <= time.time() + 15:
        return None
    body = urllib.parse.urlencode({"videoId": meta.video_id, "song": meta.title, "artist": meta.artist,
                                   "album": meta.album, "duration": meta.duration,
                                   "alwaysFetchMetadata": "false", "token": token}).encode()
    req = urllib.request.Request(UNIFIED_URL, data=body, method="POST", headers={
        "User-Agent": USER_AGENT, "Accept": "text/event-stream",
        "Content-Type": "application/x-www-form-urlencoded", "Origin": "https://betterlyrics.org",
    })
    candidates = []
    with urllib.request.urlopen(req, timeout=22) as response:
        event, data_lines = "", []
        for raw in response:
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not text:
                if data_lines:
                    try:
                        payload = json.loads("".join(data_lines))
                        if event == "provider":
                            candidate = unified_result(payload.get("provider"), payload.get("results") or {}, meta)
                            if candidate:
                                candidates.append(candidate)
                    except json.JSONDecodeError:
                        pass
                event, data_lines = "", []
            elif text.startswith("event:"):
                event = text[6:].strip()
            elif text.startswith("data:"):
                data_lines.append(text[5:].strip())
    return max(candidates, key=lambda item: item["quality"]) if candidates else None


class Metadata:
    def __init__(self, args):
        decode = lambda value: urllib.parse.unquote(value or "")
        self.title = decode(args.title).strip()
        self.artist = decode(args.artist).strip()
        self.album = decode(args.album).strip()
        self.video_id = decode(args.video_id).strip()
        self.duration = max(0, round(args.duration or 0))
        self.duration_ms = self.duration * 1000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("fast", "rich"), required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", default="")
    parser.add_argument("--album", default="")
    parser.add_argument("--duration", type=float, default=0)
    parser.add_argument("--video-id", default="")
    parser.add_argument("--request-token", default="")
    args = parser.parse_args()
    meta = Metadata(args)
    try:
        output = fast_phase(meta) if args.phase == "fast" else rich_phase(meta)
        print(json.dumps({"ok": bool(output), "phase": args.phase, "requestToken": args.request_token,
                          "result": output}, ensure_ascii=False, separators=(",", ":")))
    except Exception as error:  # Keep errors out of Plasma's process and away from tokens.
        print(json.dumps({"ok": False, "phase": args.phase, "requestToken": args.request_token,
                          "error": f"{type(error).__name__}: {error}"}, separators=(",", ":")))


if __name__ == "__main__":
    main()
