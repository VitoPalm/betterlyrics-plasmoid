#!/usr/bin/env python3
"""Read an optional shared album color cache without a project dependency."""

import json
import re
import sys
from pathlib import Path


CACHE = Path.home() / ".cache/plasma-album-color.txt"
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def color_for_key(key: str, path: Path = CACHE) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("algorithm") != "raw-average-v2":
        return None
    records = data.get("records")
    record = records.get(key) if isinstance(records, dict) else None
    value = record.get("color") if isinstance(record, dict) else None
    if isinstance(value, str) and COLOR.fullmatch(value):
        return {"color": value.lower(), "source_key": key}
    return None


if __name__ == "__main__":
    match = color_for_key(sys.argv[1]) if len(sys.argv) == 2 else None
    if match:
        print(json.dumps(match, separators=(",", ":")))
