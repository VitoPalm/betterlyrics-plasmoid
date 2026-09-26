PYTHON ?= python3
NODE ?= node
PACKAGE := dist/org.kde.plasma.betterlyrics.plasmoid

.PHONY: check test package install preview clean

check:
	$(PYTHON) -c 'import json; from pathlib import Path; data=json.loads(Path("metadata.json").read_text()); assert data["KPlugin"]["Id"] == "org.kde.plasma.betterlyrics"'
	$(PYTHON) -c 'from pathlib import Path; [compile(path.read_bytes(), str(path), "exec") for path in Path("contents/ui").glob("*.py") if path.is_file()]'

test: check
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) tests/lyrics_service_backend_test.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) tests/bridge_test.py
	$(NODE) tests/lyrics_service.test.js
	$(NODE) tests/lyric_layout.test.js

package: test
	$(PYTHON) scripts/package.py $(PACKAGE)

install: package
	@if kpackagetool6 -t Plasma/Applet --show org.kde.plasma.betterlyrics >/dev/null 2>&1; then \
		kpackagetool6 -t Plasma/Applet --upgrade $(PACKAGE); \
	else \
		kpackagetool6 -t Plasma/Applet --install $(PACKAGE); \
	fi

preview:
	plasmawindowed org.kde.plasma.betterlyrics

clean:
	rm -rf dist
