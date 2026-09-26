#!/usr/bin/env python3
"""Print the URL of the currently playing MPRIS player, if it has one."""

import dbus
import sys
import argparse
from urllib.parse import unquote


MPRIS_PREFIX = "org.mpris.MediaPlayer2."
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"


def service_pid(bus, name):
    daemon = bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
    return int(dbus.Interface(daemon, "org.freedesktop.DBus").GetConnectionUnixProcessID(name))


def player_metadata(bus, service_name):
    try:
        obj = bus.get_object(service_name, "/org/mpris/MediaPlayer2")
        props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        if str(props.Get(PLAYER_INTERFACE, "PlaybackStatus")) != "Playing":
            return None
        metadata = props.Get(PLAYER_INTERFACE, "Metadata")
        artists = metadata.get("xesam:artist") or []
        return {
            "title": str(metadata.get("xesam:title") or ""),
            "artist": ", ".join(str(item) for item in artists),
            "url": str(metadata.get("xesam:url") or ""),
        }
    except dbus.DBusException:
        # Players can disappear between ListNames and Get; keep looking.
        return None


def matching_url(bus, wanted_title, wanted_artist, wanted_pid=0):
    candidates = []
    for name in sorted(str(item) for item in bus.list_names()):
        if not name.startswith(MPRIS_PREFIX):
            continue
        if wanted_pid > 0:
            try:
                if service_pid(bus, name) != wanted_pid:
                    continue
            except dbus.DBusException:
                continue
        metadata = player_metadata(bus, name)
        if metadata is not None:
            candidates.append(metadata)
    for metadata in candidates:
        if metadata["title"] == wanted_title and (
                not wanted_artist or metadata["artist"] == wanted_artist):
            return metadata["url"]
    if not wanted_artist:
        for metadata in candidates:
            if metadata["title"] == wanted_title:
                return metadata["url"]
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("title", nargs="?", default="")
    parser.add_argument("artist", nargs="?", default="")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--generation", type=int, default=0)
    args = parser.parse_args()
    wanted_title = unquote(args.title)
    wanted_artist = unquote(args.artist)
    try:
        bus = dbus.SessionBus()
        url = matching_url(bus, wanted_title, wanted_artist, args.pid)
        if url:
            print(url)
    except dbus.DBusException:
        return

if __name__ == "__main__":
    main()
