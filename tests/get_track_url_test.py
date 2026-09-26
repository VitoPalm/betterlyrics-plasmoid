#!/usr/bin/env python3
"""URL lookup must not mix different MPRIS players."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "get_track_url", Path(__file__).resolve().parents[1] / "contents/ui/get_track_url.py"
)
lookup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lookup)


class FakeBus:
    names = ["org.mpris.MediaPlayer2.alpha", "org.mpris.MediaPlayer2.beta"]
    pids = {names[0]: 100, names[1]: 200}

    def list_names(self):
        return self.names

class TrackUrlTests(unittest.TestCase):
    def test_same_title_uses_selected_process(self):
        values = {
            FakeBus.names[0]: {"title": "Song", "artist": "Singer", "url": "https://example/first"},
            FakeBus.names[1]: {"title": "Song", "artist": "Singer", "url": "https://example/second"},
        }
        with patch.object(lookup, "player_metadata", side_effect=lambda bus, name: values[name]), \
             patch.object(lookup, "service_pid", side_effect=lambda bus, name: FakeBus.pids[name]):
            self.assertEqual(lookup.matching_url(FakeBus(), "Song", "Singer", 200), "https://example/second")
            self.assertEqual(lookup.matching_url(FakeBus(), "Song", "Singer", 300), "")
            self.assertEqual(lookup.matching_url(FakeBus(), "Song", "Other"), "")

    def test_no_metadata_match_does_not_borrow_url(self):
        with patch.object(lookup, "player_metadata", return_value={
                "title": "Other song", "artist": "Other", "url": "https://example/wrong"}):
            self.assertEqual(lookup.matching_url(FakeBus(), "Song", "Singer"), "")


if __name__ == "__main__":
    unittest.main()
