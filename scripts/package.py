#!/usr/bin/env python3
"""Build a deterministic Plasma package from the runtime tree only."""

import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    output = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "dist/org.kde.plasma.betterlyrics.plasmoid")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / "metadata.json", ROOT / "LICENSE"] + sorted(
        path for path in (ROOT / "contents").rglob("*")
        if path.is_file()
        and not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(ROOT).parts)
        and path.suffix.lower() in {".qml", ".js", ".py", ".xml", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp"}
    )
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as package:
        for path in files:
            info = ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o755 if path.suffix == ".py" else 0o644) << 16
            package.writestr(info, path.read_bytes())
    print(f"Built {output} ({len(files)} files)")


if __name__ == "__main__":
    main()
