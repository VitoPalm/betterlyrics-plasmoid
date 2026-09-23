#!/usr/bin/env python3
"""Print the URL of the currently playing MPRIS player, if it has one."""

import dbus
import sys
from urllib.parse import unquote


MPRIS_PREFIX = "org.mpris.MediaPlayer2."
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"


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

def main():
    wanted_title = unquote(sys.argv[1]) if len(sys.argv) > 1 else ""
    wanted_artist = unquote(sys.argv[2]) if len(sys.argv) > 2 else ""
    try:
        bus = dbus.SessionBus()
        candidates = []
        for name in sorted(str(item) for item in bus.list_names()):
            if name.startswith(MPRIS_PREFIX):
                metadata = player_metadata(bus, name)
                if metadata is not None:
                    candidates.append(metadata)
        for metadata in candidates:
            if metadata["title"] == wanted_title and (
                    not wanted_artist or metadata["artist"] == wanted_artist):
                if metadata["url"]:
                    print(metadata["url"])
                return
        for metadata in candidates:
            if metadata["title"] == wanted_title:
                if metadata["url"]:
                    print(metadata["url"])
                return
        for metadata in candidates:
            if metadata["url"]:
                print(metadata["url"])
                return
    except dbus.DBusException:
        return

if __name__ == "__main__":
    main()
