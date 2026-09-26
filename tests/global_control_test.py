#!/usr/bin/env python3
"""Shared Start/Stop persistence and migration regressions."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "global_control", Path(__file__).resolve().parents[1] / "contents/ui/global_control.py"
)
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class GlobalControlTests(unittest.TestCase):
    def test_search_is_shared_and_cached_for_same_track(self):
        calls = []
        delivered = []
        callbacks = {}
        coordinator = control.SearchCoordinator(
            dispatch=lambda request, phase, done: (calls.append(phase), callbacks.__setitem__(phase, done)))
        request = {"key": "track-1", "video_id": "", "title": "Song"}
        publish = lambda key, payload: delivered.append((key, payload))
        first = coordinator.lookup(request, publish)
        second = coordinator.lookup(request, publish)
        self.assertEqual(first, {"key": "track-1", "expected": 2, "results": []})
        self.assertEqual(second, first)
        self.assertEqual(calls, ["fast", "rich"])
        callbacks["fast"]({"phase": "fast", "ok": True})
        self.assertEqual(len(delivered), 1)
        self.assertEqual(len(coordinator.lookup(request, publish)["results"]), 1)
        callbacks["rich"]({"phase": "rich", "ok": False})
        self.assertEqual(len(coordinator.lookup(request, publish)["results"]), 2)
        self.assertEqual(calls, ["fast", "rich"])

    def test_search_cache_expires(self):
        now = [0]
        calls = []
        coordinator = control.SearchCoordinator(
            dispatch=lambda request, phase, done: (calls.append(phase), done({"phase": phase})),
            clock=lambda: now[0])
        request = {"key": "track-1", "video_id": ""}
        coordinator.lookup(request, lambda key, payload: None)
        coordinator.lookup(request, lambda key, payload: None)
        self.assertEqual(len(calls), 2)
        now[0] = control.SEARCH_TTL_SECONDS + 1
        coordinator.lookup(request, lambda key, payload: None)
        self.assertEqual(len(calls), 4)

    def test_stop_and_start_are_persistent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            self.assertEqual(control.transact(), (True, 0, False))
            self.assertEqual(control.transact(False), (False, 1, True))
            self.assertEqual(control.transact(False), (False, 1, False))
            self.assertEqual(control.transact(), (False, 1, False))
            self.assertEqual(control.transact(True), (True, 2, True))
            self.assertEqual(json.loads(control.state_path().read_text())["revision"], 2)

    def test_disabled_legacy_instance_wins_migration(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            config = Path(directory) / "plasma-org.kde.plasma.desktop-appletsrc"
            config.write_text(
                "[Containments][1][Applets][11]\nplugin=org.kde.plasma.betterlyrics\n"
                "[Containments][1][Applets][11][Configuration][General]\nenabled=true\n"
                "[Containments][2][Applets][12]\nplugin=org.kde.plasma.betterlyrics\n"
                "[Containments][2][Applets][12][Configuration][General]\nenabled=false\n"
            )
            self.assertEqual(control.transact(), (False, 0, False))
            self.assertEqual(control.transact(True), (True, 1, True))
            self.assertEqual(control.transact(), (True, 1, False))

    def test_independent_instance_does_not_set_migrated_global_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"XDG_CONFIG_HOME": directory}):
            config = Path(directory) / "plasma-org.kde.plasma.desktop-appletsrc"
            config.write_text(
                "[Containments][1][Applets][11]\nplugin=org.kde.plasma.betterlyrics\n"
                "[Containments][1][Applets][11][Configuration][General]\n"
                "enabled=false\nfollowGlobalEnabled=false\n"
            )
            self.assertEqual(control.transact(), (True, 0, False))


if __name__ == "__main__":
    unittest.main()
