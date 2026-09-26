#!/usr/bin/env python3
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contents/ui"))
import lyrics_service as service
from read_album_color import color_for_key


class LyricsBackendTests(unittest.TestCase):
    def test_shared_album_color_cache_is_optional_and_keyed(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "album-color.json"
            self.assertIsNone(color_for_key("song", cache))
            cache.write_text('{"algorithm":"raw-average-v2","records":'
                             '{"song":{"color":"#Ab12Cd"}}}')
            self.assertEqual(color_for_key("song", cache),
                             {"color": "#ab12cd", "source_key": "song"})
            self.assertIsNone(color_for_key("different-song", cache))
            cache.write_text('{"algorithm":"raw-average-v2","records":'
                             '{"song":{"color":"#202326"}}}')
            self.assertIsNone(color_for_key("song", cache))

    def test_color_reader_accepts_generation_argument(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / ".cache/plasma-album-color.txt"
            cache.parent.mkdir()
            cache.write_text('{"algorithm":"raw-average-v2","records":'
                             '{"song":{"color":"#Ab12Cd"}}}')
            env = dict(os.environ, HOME=temporary)
            result = subprocess.run(
                [sys.executable, str(ROOT / "contents/ui/read_album_color.py"),
                 "song", "--generation", "7"],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertEqual(json.loads(result.stdout),
                             {"color": "#ab12cd", "source_key": "song"})

    def test_lrc_repeated_timestamps_and_words(self):
        lines = service.parse_lrc(
            "[offset:+100]\n[00:01.00][00:03.00]<00:01.00>Hello <00:01.50>world",
            6000,
        )
        self.assertEqual([item["startTimeMs"] for item in lines], [1100, 3100])
        self.assertEqual(lines[1]["parts"][1]["startTimeMs"], 3600)

    def test_ttml_entities_and_word_timing(self):
        lines = service.parse_ttml(
            '<tt><body><p begin="1s" end="2s"><span begin="1s" end="1.5s">A &amp; </span>'
            '<span begin="1.5s" end="2s">B &#x1f3b5;</span></p></body></tt>',
            3000,
        )
        self.assertEqual(lines[0]["words"], "A & B 🎵")
        self.assertEqual(len(lines[0]["parts"]), 2)

    def test_nested_background_spans_never_leak_markup(self):
        lines = service.parse_ttml(
            '<tt xmlns:ttm="urn:ttm"><body><p begin="1s" end="3s">Lead '
            '<span ttm:role="x-bg"><span begin="1.5s" end="2s">(back,</span> '
            '<span begin="2s" end="2.5s">ground)</span></span></p></body></tt>',
            4000,
        )
        self.assertEqual(lines[0]["words"], "Lead (back, ground)")
        self.assertEqual([part["isBackground"] for part in lines[0]["parts"]], [True, True])
        self.assertNotIn("span", lines[0]["words"])

    def test_cached_markup_is_sanitized_at_result_boundary(self):
        value = {"version": service.LYRIC_CACHE_VERSION, "lyrics": [{
            "startTimeMs": 1000,
            "durationMs": 1000,
            "words": "A &lt;span&gt;line&lt;/span&gt;/span>",
            "parts": [{"startTimeMs": 1000, "durationMs": 1000, "words": "line/span>"}],
        }]}
        result = service.normalize_cached_result("binimum-richsynced", value, 3000)
        self.assertEqual(result["lines"][0]["words"], "A line")
        self.assertEqual(result["lines"][0]["parts"][0]["words"], "line")

    def test_cache_requires_matching_version_and_preserves_word_timing(self):
        value = {"version": service.LYRIC_CACHE_VERSION, "lyrics": [
            {"startTimeMs": 0, "durationMs": 1000, "words": "Hello",
             "parts": [{"startTimeMs": 0, "durationMs": 1000, "words": "Hello"}]},
        ]}
        self.assertIsNone(service.normalize_cached_result("unison-wordsynced", {**value, "version": "1"}, 1000))
        normalized = service.normalize_cached_result("unison-wordsynced", value, 1000)
        self.assertEqual(normalized["syncType"], "word")

    def test_extension_provider_order_and_disabled_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "profile"
            idb = profile / "storage/default/moz-extension+++example/idb"
            idb.mkdir(parents=True)
            sync = profile / "storage-sync-v2.sqlite"
            with contextlib.closing(sqlite3.connect(sync)) as db:
                db.execute("CREATE TABLE storage_sync_data (ext_id TEXT, data TEXT, sync_change_counter INTEGER)")
                db.execute("INSERT INTO storage_sync_data VALUES (?, ?, 0)", (
                    service.EXTENSION_ID,
                    json.dumps({"preferredProviderList": ["lrclib-synced", "d_unison-richsynced"]}),
                ))
                db.commit()
            service.preferred_provider_order.cache_clear()
            try:
                with mock.patch.object(service, "zen_database_paths", return_value=[idb / service.EXTENSION_DB_NAME]):
                    order = service.preferred_provider_order()
                self.assertEqual(order[0], "lrclib-synced")
                self.assertNotIn("unison-richsynced", order)
                self.assertIsNone(service.result("Unison", "unison-richsynced", [service.line(0, 1000, "One")]))
                self.assertEqual(service.result("LRCLib", "lrclib-synced", [service.line(0, 1000, "One")])["quality"], 100)
            finally:
                service.preferred_provider_order.cache_clear()

    def test_unison_lrc_richsync_uses_word_provider_and_album(self):
        meta = type("Meta", (), {"video_id": "dQw4w9WgXcQ", "title": "Song", "artist": "Artist",
                                 "album": "Album", "duration": 120, "duration_ms": 120000})()
        payload = {"data": {"format": "lrc", "syncType": "richsync",
                            "lyrics": "[00:01.00]<00:01.00>Hello"}}
        with mock.patch.object(service, "request", return_value=json.dumps(payload)) as http, \
             mock.patch.object(service, "extension_key_id", return_value="key"):
            value = service.unison(meta)
        self.assertEqual(value["provider"], "unison-wordsynced")
        self.assertEqual(value["syncType"], "word")
        self.assertIn("album=Album", http.call_args.args[0])
        self.assertEqual(http.call_args.kwargs["headers"]["x-key-id"], "key")

    def test_unified_maps_every_stream_provider(self):
        meta = type("Meta", (), {"duration_ms": 4000})()
        cases = [
            ("musixmatch", {"wordByWord": "[00:01.00]One", "synced": "[00:01.00]One"},
             {"musixmatch-richsync", "musixmatch-synced"}),
            ("lrclib", {"synced": "[00:01.00]One", "plain": "One"},
             {"lrclib-synced", "lrclib-plain"}),
            ("kugou", {"lyrics": json.dumps({"lyrics": "[00:01.00]One"})}, {"legato-synced"}),
            ("qq", {"lyrics": json.dumps({"lyrics": "[1000,1000]One (1000,1000)"})},
             {"portato-richsynced"}),
            ("golyrics", {"lyrics": '<tt><body><p begin="1s" end="2s">One</p></body></tt>'},
             {"bLyrics-synced"}),
            ("binimum", {"lyrics": '<tt><body><p begin="1s" end="2s">One</p></body></tt>',
                          "timingType": "line"}, {"binimum-synced"}),
        ]
        for provider, payload, expected in cases:
            with self.subTest(provider=provider):
                actual = {item["provider"] for item in service.unified_results(provider, payload, meta)}
                self.assertEqual(actual, expected)

    def test_metadata_event_updates_later_provider_duration(self):
        meta = type("Meta", (), {"title": "Old", "artist": "Old", "album": "",
                                 "duration": 0, "duration_ms": 0})()
        self.assertEqual(service.process_sse_event("metadata", [json.dumps({
            "song": "New", "artist": "Singer", "duration": 123,
        })], meta), [])
        self.assertEqual((meta.title, meta.artist, meta.duration_ms), ("New", "Singer", 123000))

    def test_cached_extension_metadata_corrects_track_query(self):
        args = type("Args", (), {"title": "Old", "artist": "Old", "album": "",
                                "duration": 0, "video_id": "dQw4w9WgXcQ"})()
        with mock.patch.object(service, "cached_metadata", return_value={
            "song": "Correct", "artist": "Singer", "album": "Album", "duration": 123,
        }):
            meta = service.Metadata(args)
        self.assertEqual((meta.title, meta.artist, meta.album, meta.duration_ms),
                         ("Correct", "Singer", "Album", 123000))

    def test_mpris_title_and_topic_artist_are_cleaned(self):
        args = type("Args", (), {"title": "Song (Official Music Video) | YouTube Music",
                                "artist": "Singer - Topic", "album": "", "duration": 120,
                                "video_id": ""})()
        meta = service.Metadata(args)
        self.assertEqual((meta.title, meta.artist), ("Song", "Singer"))

    def test_fast_phase_compares_cached_and_live_priority(self):
        meta = type("Meta", (), {"video_id": "dQw4w9WgXcQ", "duration_ms": 2000})()
        cached = service.result("LRCLib", "lrclib-synced", [service.line(0, 1000, "One")])
        live = service.result("Unison", "unison-richsynced", [service.line(0, 1000, "One")])
        with mock.patch.object(service, "cached_lyrics", return_value=cached), \
             mock.patch.object(service, "unison", return_value=live), \
             mock.patch.object(service, "binimum", return_value=None), \
             mock.patch.object(service, "lrclib", return_value=None), \
             mock.patch.object(service, "yt_music_lyrics", return_value=None), \
             mock.patch.object(service, "yt_captions", return_value=None):
            self.assertEqual(service.fast_phase(meta)["provider"], "unison-richsynced")

    def test_youtube_music_lyrics_from_next_and_browse(self):
        meta = type("Meta", (), {"video_id": "dQw4w9WgXcQ", "duration_ms": 4000})()
        page = '<script>ytcfg.set({"INNERTUBE_API_KEY":"key","INNERTUBE_CONTEXT":' \
               '{"client":{"clientName":"WEB_REMIX"}}});</script>'
        next_data = {"contents": {"singleColumnMusicWatchNextResultsRenderer": {"tabbedRenderer": {
            "watchNextTabbedResultsRenderer": {"tabs": [{}, {"tabRenderer": {
                "endpoint": {"browseEndpoint": {"browseId": "lyrics"}}}}]}}}}}
        browse_data = {"contents": {"sectionListRenderer": {"contents": [{
            "musicDescriptionShelfRenderer": {"description": {"runs": [{"text": "One\nTwo"}]},
                                              "footer": {"runs": [{"text": "Source: Provider"}]}}
        }]}}}
        with mock.patch.object(service, "youtube_page", return_value=page), \
             mock.patch.object(service, "youtube_api", side_effect=[next_data, browse_data]) as api:
            value = service.yt_music_lyrics(meta)
        self.assertEqual(value["provider"], "yt-lyrics")
        self.assertEqual(value["syncType"], "none")
        self.assertEqual([item["words"] for item in value["lines"]], ["One", "Two"])
        self.assertEqual([call.args[0] for call in api.call_args_list], ["next", "browse"])

    def test_youtube_caption_parser_uses_authored_text(self):
        data = {"events": [{"tStartMs": 1000, "dDurationMs": 500,
                            "segs": [{"utf8": "♪ HELLO\nWORLD ♪"}]},
                           {"tStartMs": 1500, "dDurationMs": 500,
                            "segs": [{"utf8": "GOODBYE"}]}]}
        self.assertEqual([item["words"] for item in service.parse_youtube_captions(data)],
                         ["Hello world", "Goodbye"])
        self.assertEqual(service.parse_youtube_captions({"events": [{"tStartMs": 0}]}), [])

    def test_youtube_captions_select_manual_track_matching_auto_language(self):
        meta = type("Meta", (), {"video_id": "dQw4w9WgXcQ"})()
        tracks = [{"kind": "asr", "languageCode": "en", "baseUrl": "https://www.youtube.com/auto"},
                  {"languageCode": "en-US", "baseUrl": "https://www.youtube.com/manual?x=1"},
                  {"languageCode": "fr", "baseUrl": "https://www.youtube.com/french"}]
        page = "ytInitialPlayerResponse = " + json.dumps({"captions": {
            "playerCaptionsTracklistRenderer": {"captionTracks": tracks}}})
        caption_data = json.dumps({"events": [{"tStartMs": 1000, "dDurationMs": 500,
                                                "segs": [{"utf8": "Hello"}]}]}).encode()
        with mock.patch.object(service, "youtube_page", return_value=page), \
             mock.patch.object(service.urllib.request, "urlopen", return_value=io.BytesIO(caption_data)) as http:
            value = service.yt_captions(meta)
        self.assertEqual(value["provider"], "yt-captions")
        self.assertIn("/manual", http.call_args.args[0].full_url)
        self.assertIn("fmt=json3", http.call_args.args[0].full_url)
        with mock.patch.object(service, "youtube_page", return_value=page.replace(
                json.dumps(tracks), json.dumps(tracks[:1]))), \
             mock.patch.object(service.urllib.request, "urlopen") as http:
            self.assertIsNone(service.yt_captions(meta))
        http.assert_not_called()

    def test_rich_phase_keeps_best_stream_result_and_cached_fallback(self):
        meta = type("Meta", (), {"video_id": "dQw4w9WgXcQ", "title": "Song", "artist": "Artist",
                                 "album": "", "duration": 10, "duration_ms": 10000})()
        cached = service.result("LRCLib", "lrclib-synced", [service.line(0, 1000, "One")])
        stream = io.BytesIO(
            b'event: provider\ndata: {"provider":"musixmatch","results":{"synced":"[00:01.00]One"}}\n\n'
            b'event: provider\ndata: {"provider":"golyrics","results":{"lyrics":"<tt><body>'
            b'<p begin=\\"1s\\" end=\\"2s\\">One</p></body></tt>"}}\n\n'
        )
        with mock.patch.object(service, "cached_lyrics", return_value=cached), \
             mock.patch.object(service, "read_zen_storage", return_value={"jwtToken": "token"}), \
             mock.patch.object(service, "jwt_expiry", return_value=10**12), \
             mock.patch.object(service.urllib.request, "urlopen", return_value=stream):
            self.assertEqual(service.rich_phase(meta)["provider"], "bLyrics-synced")
        with mock.patch.object(service, "cached_lyrics", return_value=cached), \
             mock.patch.object(service, "read_zen_storage", return_value={}):
            self.assertEqual(service.rich_phase(meta)["provider"], "lrclib-synced")

    def test_bridge_result_uses_browser_selection_and_segment_map(self):
        meta = type("Meta", (), {"video_id": "dQw4w9WgXcQ", "duration_ms": 5000})()
        value = {"playbackVideoId": meta.video_id, "provider": "unison-wordsynced",
                 "source": "Unison", "segmentMap": {"segment": [{
                     "counterpartVideoStartTimeMilliseconds": 1000,
                     "primaryVideoStartTimeMilliseconds": 1500,
                     "durationMilliseconds": 2000,
                 }]}, "lyrics": [{"startTimeMs": 1000, "durationMs": 1000, "words": "One",
                                 "parts": [{"startTimeMs": 1000, "durationMs": 500, "words": "One"}]}]}
        result = service.normalize_bridge_result(value, meta)
        self.assertEqual((result["provider"], result["quality"], result["syncType"]),
                         ("unison-wordsynced", 1000, "word"))
        self.assertEqual(result["lines"][0]["startTimeMs"], 1500)
        self.assertEqual(result["lines"][0]["parts"][0]["startTimeMs"], 1500)
        self.assertIsNone(service.normalize_bridge_result({**value, "playbackVideoId": "other"}, meta))

    def test_qrc_word_timing(self):
        lines = service.parse_qrc('[1000,2000]Hello (1000,800)world(1800,1200)', 4000)
        self.assertEqual(lines[0]["words"], "Hello world")
        self.assertEqual([part["startTimeMs"] for part in lines[0]["parts"]], [1000, 1800])

    def test_local_firefox_cache_decoder(self):
        paths = service.zen_database_paths()
        if not paths:
            self.skipTest("Zen Better Lyrics cache is not installed")
        # Find a rich cache key without exposing track data or token contents.
        chosen = None
        for path in paths:
            with contextlib.closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
                for raw_key, in connection.execute("SELECT key FROM object_data"):
                    key = service.decode_idb_key(bytes(raw_key))
                    if key and any(key.endswith("_" + provider) for provider in service.RICH_KEYS):
                        chosen = key
                        break
            if chosen:
                break
        if not chosen:
            self.skipTest("No rich lyrics cache entry is available")
        video_id = chosen[len("blyrics_"):].split("_", 1)[0]
        value = service.cached_lyrics(video_id, 300_000, rich_only=True)
        # Negative/expired entries are valid; direct structured-clone decoding
        # still has to retrieve a well-formed storage value.
        stored = service.read_zen_storage({chosen})
        self.assertIn(chosen, stored)
        self.assertIsInstance(stored[chosen], dict)
        if value:
            self.assertTrue(value["lines"])
            self.assertIn(value["provider"], service.RICH_KEYS)

    def test_cli_contract_on_cache_miss(self):
        # The rich phase must fail closed without a video ID and never include
        # credentials or provider internals in its response.
        self.assertIsNone(service.rich_phase(type("Meta", (), {"video_id": "", "duration_ms": 0})()))


if __name__ == "__main__":
    unittest.main()
