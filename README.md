# Better Lyrics for Plasma 6

A centered, responsive lyrics plasmoid with line, word, and syllable timing;
album-derived colors; compact stepped and tall stream layouts; instrumental
breaks; MPRIS seeking; a local Firefox-cache reader; concurrent fallback
providers; and progressive rich-sync upgrades.

This directory is the independent source project for the Plasma widget. It
does not require the Better Lyrics browser extension repository to build or
test. The installed widget is a copy of the package produced here.

## Quick start

Requires Plasma 6, Python 3, Node.js for the JavaScript tests, and `make`.
From this directory:

```sh
make test       # validate metadata, Python, and JavaScript behavior
make package    # create dist/org.kde.plasma.betterlyrics.plasmoid
make install    # test, package, and install for this user
make preview    # open the installed widget in plasmawindowed
```

After installing, reload a running panel if needed with
`systemctl --user restart plasma-plasmashell.service`. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the editing workflow. This repository
is local; add your own Git remote when you want to publish or sync it.

Right-click the widget and choose **Stop Better Lyrics** to suspend lyric
fetching and playback polling. Choose **Start Better Lyrics** from the same
menu to resume. The choice is saved for that widget instance.

## Lyrics pipeline

`contents/ui/lyrics_service.py` runs two generation-guarded lookups for each
track. The fast phase reads an existing Better Lyrics cache entry or races
Unison, BiniLyrics, and LRCLIB. The rich phase independently checks cached
word/syllable results and, when Zen has a current Better Lyrics JWT, consumes
the authenticated Unified SSE stream for GoLyrics, BiniLyrics, Portato, and
Musixmatch. A richer result replaces an already-visible fallback without
blanking the widget. The original QML JavaScript cascade remains the automatic
fallback if the helper is unavailable.

The cache is opened read-only with SQLite immutable mode. The JWT is checked
locally for expiry, used only in the request body, and never printed or copied
into the plasmoid's own storage.

## Project structure

```text
betterlyrics-plasmoid/
├── metadata.json                   Plasma package identity and version
├── README.md                       Operator and contributor entry point
├── CONTRIBUTING.md                 Development workflow
├── LICENSE                         GPL-3.0 license text
├── Makefile                        Test, package, install, and preview commands
├── scripts/package.py              Clean reproducible package builder
├── contents/
│   ├── config/
│   │   ├── config.qml              Registers the General settings page
│   │   └── main.xml                Persistent configuration schema/defaults
│   └── ui/
│       ├── main.qml                MPRIS selection, orchestration, timing, color
│       ├── lyrics_service.py       Cache, network providers, SSE, text parsers
│       ├── LyricsService.js        QML fallback providers and romanization
│       ├── get_track_url.py        Playing-player URL/video-ID lookup over D-Bus
│       ├── read_album_color.py     Optional shared artwork color cache reader
│       ├── RunCommand.qml          Plasma executable-engine adapter
│       ├── SteppedLyricsView.qml   Compact two-line animated layout
│       ├── LyricsStreamView.qml    Tall scrolling layout
│       ├── LyricLineDelegate.qml   Wrapping, original/romanized line rendering
│       ├── WordDelegate.qml        Timed word fill and wobble animation
│       ├── InstrumentalIndicator.qml Instrumental-break presentation
│       └── configGeneral.qml       Settings controls
└── tests/
    ├── lyrics_service.test.js      JavaScript parser regressions
    └── lyrics_service_backend_test.py Python parser/cache/CLI tests
```

Generated `__pycache__` directories are runtime artifacts and are not part of
the package design.

## Runtime architecture

1. `main.qml` selects the first actively playing MPRIS player and tracks its
   metadata and interpolated position.
2. `get_track_url.py` retrieves `xesam:url`; YouTube-style URLs supply the
   video ID used for cache keys, Unison, and Unified providers.
3. A track change starts separate `fast` and `rich` backend processes.
   Responses include a request token, so results from an earlier track are
   discarded.
4. The fast process checks Zen's cache and otherwise queries the three public
   fallback providers concurrently. The rich process checks high-resolution
   cache entries and optionally consumes the authenticated SSE stream.
5. `main.qml` applies results according to the Better Lyrics provider order.
   Equal or better timing may replace the visible fallback; lower-quality data
   cannot downgrade it.
6. `LyricsService.js` progressively adds romanization. It also provides the
   complete legacy fetch path if the Python helper fails or is unavailable.
7. The active layout is `SteppedLyricsView.qml` below 220 px height and
   `LyricsStreamView.qml` at 220 px or above. Clicking a timed line seeks the
   active MPRIS player.

The Python service does not maintain application data. Its only project-specific
local read is the Zen extension cache; `libsnappy` is loaded from the system.
Python tooling may generate `__pycache__` bytecode. The QML package stores user
settings through Plasma's configuration system.

## Requirements

- KDE Plasma 6 with the private MPRIS and Plasma 5 Support QML modules used by
  the stock media widgets.
- Python 3 with its standard SQLite, `ctypes`, networking, and XML modules,
  plus Python D-Bus bindings for MPRIS URL lookup.
- System `libsnappy` when reading Firefox IndexedDB cache entries.
- An MPRIS-compatible player. Zen/Firefox and the Better Lyrics extension are
  optional: without them, public providers and the JavaScript fallback remain
  available.
- Network access for uncached lyrics and romanization.

Node.js and `make` are needed only for development. No daemon or build step is
required at runtime.

## Configuration

The General settings page exposes font family, size, weight/style, album-art or
custom text color, lyric delay, syllable wobble, drop shadows, romanization,
romanization opacity, and whether romanization becomes the primary line.
Lyric delay follows the browser extension's convention: positive values show
lyrics later and negative values show them earlier. Defaults and persistent key
types live in `contents/config/main.xml`.

## Development and verification

Run `make test` from the project root. `make package` creates a clean
installable archive under `dist/`.

Optional package preview:

```sh
plasmawindowed org.kde.plasma.betterlyrics
```

The Python cache test reads local Zen storage when present but does not print
tokens, lyric text, or track metadata.

## Deployment and rollback

Your clone is the editing source. The active package is usually
`~/.local/share/plasma/plasmoids/org.kde.plasma.betterlyrics`.

Use `make install` to upgrade the active package from a tested archive. Then
reload Plasma if needed with:

```sh
systemctl --user restart plasma-plasmashell.service
```

For rollback, check out the earlier Git commit and run `make install` again.

## Privacy and security

- Firefox databases are opened read-only using SQLite immutable mode.
- Cached transient values are ignored after their recorded expiry.
- JWTs are decoded only to validate expiration, never logged, returned to QML,
  or persisted by this project.
- Shell arguments are percent-encoded before the Plasma executable engine
  invokes helpers, and results are generation-checked before display.
- Provider failures are isolated: they produce no lyrics result and do not
  interrupt playback or mutate browser data.

## Current limitations

- Unified SSE requires an unexpired token already issued to the Better Lyrics
  browser extension. This plasmoid does not automate Turnstile or renew tokens.
- The Firefox decoder intentionally supports only JSON-like structured-clone
  values used by extension storage. Unsupported future cache formats are
  ignored and fall back to network providers.
- Provider availability and response formats are external dependencies.
- The live authenticated SSE path depends on a valid browser-issued token and
  may be unavailable during local testing.

## Tests

`tests/lyrics_service.test.js` covers the JavaScript fallback parsers.
`tests/lyrics_service_backend_test.py` covers the Python parsers, CLI contract,
optional color cache, and installed Zen cache decoder without exposing cached
lyric contents or credentials.
