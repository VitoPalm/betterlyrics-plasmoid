#!/usr/bin/env python3
"""Register the optional Better Lyrics native messaging host for Zen Flatpak."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


HOST_NAME = "org.betterlyrics.plasmoid"
EXTENSION_ID = "betterlyrics@boidu.dev"


def install_zen():
    home = Path.home()
    flatpak_home = home / ".var/app/app.zen_browser.zen"
    zen_home = flatpak_home / ".zen"
    if not zen_home.exists():
        raise SystemExit("Zen Flatpak profile not found")
    script = zen_home / "betterlyrics-plasmoid-bridge-host.py"
    shutil.copyfile(Path(__file__).with_name("native_host.py"), script)
    os.chmod(script, 0o700)
    manifest = {
        "name": HOST_NAME,
        "description": "Better Lyrics Plasma widget session bridge",
        "path": str(home / ".zen/betterlyrics-plasmoid-bridge-host.py"),
        "type": "stdio",
        "allowed_extensions": [EXTENSION_ID],
    }
    manifest_paths = []
    for config in (".mozilla", ".zen"):
        manifests = flatpak_home / config / "native-messaging-hosts"
        manifests.mkdir(parents=True, exist_ok=True)
        manifest_path = manifests / f"{HOST_NAME}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        os.chmod(manifest_path, 0o600)
        manifest_paths.append(manifest_path)
    return manifest_paths


def uninstall_zen():
    flatpak_home = Path.home() / ".var/app/app.zen_browser.zen"
    for config in (".mozilla", ".zen"):
        (flatpak_home / config / "native-messaging-hosts" / f"{HOST_NAME}.json").unlink(missing_ok=True)
    (flatpak_home / ".zen/betterlyrics-plasmoid-bridge-host.py").unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    if args.uninstall:
        uninstall_zen()
        print("Removed Better Lyrics native host registration")
    else:
        print("Installed native host registrations:")
        for path in install_zen():
            print(path)


if __name__ == "__main__":
    main()
