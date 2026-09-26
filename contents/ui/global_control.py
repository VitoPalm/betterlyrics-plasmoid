#!/usr/bin/env python3
"""Share Start/Stop state and in-flight lyric searches across widgets."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import quote, unquote


INTERFACE = "org.kde.plasma.BetterLyrics.Control"
SERVICE = "org.kde.plasma.BetterLyrics.Control"
PATH = "/org/kde/plasma/BetterLyrics/Control"
SEARCH_TTL_SECONDS = 45
SEARCH_MAX_ENTRIES = 24


class SearchCoordinator:
    """One phase cascade per key; completed results live only in this process."""

    def __init__(self, dispatch=None, clock=time.monotonic):
        self.entries = {}
        self.dispatch = dispatch or self._dispatch
        self.clock = clock

    def lookup(self, request, publish):
        key = request["key"]
        if not isinstance(key, str) or not key or len(key) > 4096:
            raise ValueError("invalid search key")
        now = self.clock()
        entry = self.entries.get(key)
        if entry and entry["finished_at"] is not None and now - entry["finished_at"] > SEARCH_TTL_SECONDS:
            del self.entries[key]
            entry = None
        if entry is None:
            phases = ("fast", "rich", "youtube", "bridge") if request.get("video_id") else ("fast", "rich")
            entry = {"results": {}, "phases": phases, "finished_at": None, "started_at": now}
            self.entries[key] = entry
            for phase in phases:
                self.dispatch(request, phase, lambda payload, key=key, phase=phase:
                              self.complete(key, phase, payload, publish))
        self._evict()
        return {"key": key, "expected": len(entry["phases"]),
                "results": list(entry["results"].values())}

    def complete(self, key, phase, payload, publish):
        entry = self.entries.get(key)
        if entry is None or phase in entry["results"]:
            return False
        entry["results"][phase] = payload
        if len(entry["results"]) == len(entry["phases"]):
            entry["finished_at"] = self.clock()
        publish(key, payload)
        return False  # GLib.idle_add must run this callback only once.

    def _evict(self):
        if len(self.entries) <= SEARCH_MAX_ENTRIES:
            return
        completed = sorted(((key, value) for key, value in self.entries.items()
                            if value["finished_at"] is not None),
                           key=lambda item: item[1]["finished_at"])
        for key, _ in completed[:max(0, len(self.entries) - SEARCH_MAX_ENTRIES)]:
            del self.entries[key]

    def _dispatch(self, request, phase, done):
        from gi.repository import GLib

        def worker():
            command = [sys.executable, str(Path(__file__).with_name("lyrics_service.py")),
                       "--phase", phase, "--title", quote(request["title"], safe=""),
                       "--artist", quote(request["artist"], safe=""),
                       "--album", quote(request["album"], safe=""),
                       "--duration", str(request["duration"]),
                       "--video-id", quote(request["video_id"], safe=""),
                       "--request-token", "shared"]
            try:
                process = subprocess.run(command, capture_output=True, text=True,
                                         timeout=75 if phase == "bridge" else 40)
                payload = json.loads(process.stdout.strip()) if process.returncode == 0 else None
                if not isinstance(payload, dict) or payload.get("phase") != phase:
                    raise ValueError("invalid backend response")
            except (OSError, ValueError, subprocess.TimeoutExpired):
                payload = {"ok": False, "phase": phase, "error": "BackendUnavailable"}
            GLib.idle_add(done, payload)

        threading.Thread(target=worker, daemon=True).start()


def state_path():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "betterlyrics-plasmoid" / "state.json"


def legacy_enabled():
    """A disabled legacy instance wins the one-time user-wide migration."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "plasma-org.kde.plasma.desktop-appletsrc"
    try:
        source = config.read_text(encoding="utf-8")
    except OSError:
        return True
    sections = {}
    current = None
    for raw in source.splitlines():
        if raw.startswith("[") and raw.endswith("]"):
            current = raw
            sections[current] = {}
        elif current and "=" in raw:
            key, value = raw.split("=", 1)
            sections[current][key] = value
    applets = set()
    for section, values in sections.items():
        if values.get("plugin") == "org.kde.plasma.betterlyrics":
            applets.add(section.rstrip("]"))
    for prefix in applets:
        general = prefix + "][Configuration][General]"
        settings = sections.get(general, {})
        if (settings.get("followGlobalEnabled", "true").lower() != "false"
                and settings.get("enabled", "true").lower() == "false"):
            return False
    return True


def transact(value=None):
    path = state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            enabled = state["enabled"]
            revision = int(state["revision"])
            if not isinstance(enabled, bool) or revision < 0:
                raise ValueError("invalid state")
        except (OSError, ValueError, KeyError, TypeError):
            enabled = legacy_enabled()
            revision = 0
        changed = value is not None and enabled != value
        if changed:
            enabled = value
            revision += 1
        if not path.exists() or changed:
            temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            temporary.write_text(json.dumps({"enabled": enabled, "revision": revision}), encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
    return enabled, revision, changed


def serve():
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    try:
        name = dbus.service.BusName(SERVICE, bus=bus, do_not_queue=True)
    except dbus.DBusException:
        return  # Another instance won the startup race.

    class Control(dbus.service.Object):
        searches = SearchCoordinator()

        @dbus.service.method(INTERFACE, in_signature="", out_signature="s")
        def GetState(self):
            enabled, revision, _ = transact()
            return json.dumps({"enabled": enabled, "revision": revision})

        @dbus.service.method(INTERFACE, in_signature="b", out_signature="s")
        def SetEnabled(self, value):
            enabled, revision, changed = transact(bool(value))
            if changed:
                self.StateChanged(enabled, revision)
            return json.dumps({"enabled": enabled, "revision": revision})

        @dbus.service.signal(INTERFACE, signature="bx")
        def StateChanged(self, enabled, revision):
            pass

        @dbus.service.method(INTERFACE, in_signature="s", out_signature="s")
        def Lookup(self, request_json):
            request = json.loads(request_json)
            if not isinstance(request, dict):
                raise ValueError("invalid lookup request")
            for field in ("key", "title", "artist", "album", "video_id"):
                if not isinstance(request.get(field), str) or len(request[field]) > 4096:
                    raise ValueError("invalid lookup field")
            if not isinstance(request.get("duration"), (float, int)):
                raise ValueError("invalid duration")
            return json.dumps(self.searches.lookup(request, self.publish_result))

        @dbus.service.signal(INTERFACE, signature="ss")
        def LyricsReady(self, key, payload_json):
            pass

        def publish_result(self, key, payload):
            self.LyricsReady(key, json.dumps(payload))

    control = Control(bus, PATH)
    loop = GLib.MainLoop()
    loop.run()
    return 0


def service_interface():
    import dbus
    bus = dbus.SessionBus()
    if not bus.name_has_owner(SERVICE):
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--daemon"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(80):
            if bus.name_has_owner(SERVICE):
                break
            time.sleep(0.025)
        else:
            raise RuntimeError("Better Lyrics global control service did not start")
    return dbus.Interface(bus.get_object(SERVICE, PATH), INTERFACE)


def call_service(value=None):
    remote = service_interface()
    return str(remote.GetState() if value is None else remote.SetEnabled(value))


def call_lookup(args):
    request = {"key": unquote(args.key), "title": unquote(args.title),
               "artist": unquote(args.artist), "album": unquote(args.album),
               "duration": args.duration, "video_id": unquote(args.video_id)}
    return str(service_interface().Lookup(json.dumps(request)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=("true", "false"))
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--lookup", action="store_true")
    parser.add_argument("--key", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--artist", default="")
    parser.add_argument("--album", default="")
    parser.add_argument("--duration", type=float, default=0)
    parser.add_argument("--video-id", default="")
    args = parser.parse_args()
    if args.daemon:
        return serve()
    print(call_lookup(args) if args.lookup else
          call_service(None if args.set is None else args.set == "true"))


if __name__ == "__main__":
    main()
