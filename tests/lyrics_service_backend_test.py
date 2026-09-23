#!/usr/bin/env python3
import contextlib
import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contents/ui"))
import lyrics_service as service
from read_album_color import color_for_key


class LyricsBackendTests(unittest.TestCase):
    def test_shared_album_color_cache_is_optional_and_keyed(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "album-color.json"
            self.assertIsNone(color_for_key("song", cache))
            cache.write_text('{"algorithm":"raw-average-v2","records":'
                             '{"song":{"color":"#Ab12Cd"}}}')
            self.assertEqual(color_for_key("song", cache),
                             {"color": "#ab12cd", "source_key": "song"})
            self.assertIsNone(color_for_key("different-song", cache))

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
        value = {"lyrics": [{
            "startTimeMs": 1000,
            "durationMs": 1000,
            "words": "A &lt;span&gt;line&lt;/span&gt;/span>",
            "parts": [{"startTimeMs": 1000, "durationMs": 1000, "words": "line/span>"}],
        }]}
        result = service.normalize_cached_result("binimum-richsynced", value, 3000)
        self.assertEqual(result["lines"][0]["words"], "A line")
        self.assertEqual(result["lines"][0]["parts"][0]["words"], "line")

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
