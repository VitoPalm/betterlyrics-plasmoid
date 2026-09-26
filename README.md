# Better Lyrics for Plasma 6

A centered, responsive lyrics plasmoid with line, word, and syllable timing;
album-derived colors; compact stepped and tall stream layouts; instrumental
breaks; MPRIS seeking; a local Firefox-cache reader; concurrent fallback
providers; YouTube Music lyrics and captions; and progressive rich-sync upgrades.

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

By default, right-clicking any widget and choosing **Stop Better Lyrics**
suspends lyric fetching and playback polling in every widget that follows the
global control. **Start Better Lyrics** resumes all those widgets. The shared
choice persists across Plasma restarts. In General settings, turn off **Follow
global Start/Stop** for a widget that should start and stop independently;
its context-menu action then affects only that instance. Existing following
instances migrate to the shared state; if any was stopped, the first migrated
state is stopped.

Place the same widget in a Plasma panel for a compact lyric strip. Horizontal
panels use the full fixed-width allocation for lyrics: the current line wraps
onto two rows when needed, or the next line previews below a short current
line. When stopped, the horizontal strip is blank. Vertical panels show an icon.
During an instrumental break, the strip shows the last sung line in the
smaller, muted row. If that line needs both rows, it stays wrapped and muted;
an instrumental intro shows the track title instead.
Click to open a lyrics popup. The strip width is configurable under General.
The popup shows an unsynced transcript without timed seeking when only plain
lyrics are available. Desktop and panel instances keep separate display
settings while sharing Start/Stop by default.

## Lyrics pipeline

The session service runs one in-flight lyric search per track for all widget
instances, broadcasting each result as it arrives. Completed results stay in
memory for 45 seconds so a newly opened instance can reuse them. A widget
falls back to its own lookup if the service is unavailable. This sharing also
applies to instances with independent Start/Stop settings.

`contents/ui/lyrics_service.py` runs four phases for each track with a YouTube
Music video ID. The fast phase compares versioned Better Lyrics cache entries with
Unison, BiniLyrics, and LRCLIB. The YouTube phase requests Music's plain lyrics
and human-authored captions. The rich phase checks cached sources and, when Zen
has a current Better Lyrics JWT, consumes the authenticated Unified SSE stream
for GoLyrics, BiniLyrics, Portato, Musixmatch, LRCLIB, and Legato. Sources are
selected in the extension's configured provider order, including disabled
sources. The bridge phase requests the result chosen by a locally built Better
Lyrics browser extension, including session-only lyrics and renewed credentials.
Its result takes precedence over the standalone lookups. Better results replace
an already-visible fallback without blanking the widget. The QML JavaScript
cascade runs if the helper fails.

The lyric cache is opened read-only with SQLite immutable mode; provider
preferences are read from Zen's sync database in read-only mode. The JWT is
checked locally for expiry, used only in the request body, and never printed or
copied into the plasmoid's own storage.

## Browser bridge for exact source selection

The standalone lookups cannot always reproduce the browser result: YouTube
captions and refreshed provider credentials may exist only in the live browser
session. For the same result and provider choice as Better Lyrics on YouTube
Music, use the companion changes in the Better Lyrics extension source. The
browser must be playing the same video ID reported by MPRIS. The widget still
uses its standalone providers while the browser result is pending or when the
bridge is unavailable.

For the Zen Flatpak on this machine, including a persistent local extension:

1. Build the companion extension from the `better-lyrics` source worktree with
   `npm ci` and `npm run build:plasmoid-bridge`. A stock Better Lyrics add-on
   does not contain the bridge.
2. Back up the installed signed add-on XPI from the Zen profile's `extensions/`
   directory. In Zen's `about:config`, set `xpinstall.signatures.required` to
   `false`. This allows unsigned add-ons throughout this Zen profile. Open
   `about:addons`, choose **Install Add-on From File** from the gear menu, and
   select `dist/better-lyrics-firefox-bridge.xpi`. Remove an earlier temporary
   copy from `about:debugging` if present. In the extension's Details page,
   set **Allow automatic updates** to **Off** so a stock release does not
   replace the bridge. Restart Zen to confirm the extension remains enabled.
3. Run `python3 bridge/install.py` from this project. This registers the
   extension-scoped native messaging host inside Zen's Flatpak profile.
4. Run `make install` and reload the Plasma panel if needed. Play a track in
   YouTube Music and check that its MPRIS URL contains the same video ID.

For a session-only development install, load the generated ZIP from
`about:debugging` instead of changing the signature preference. To return to
the signed add-on, remove the local build, reinstall the signed XPI or the
published add-on, and reset `xpinstall.signatures.required` to `true`.

The extension opens the native host when its background page starts. The host
accepts widget requests on a private Unix socket, forwards only the video ID
and display metadata to the extension, and returns the extension's selected
provider and timed lyric lines. Tokens and lyric responses are not persisted by
the bridge. The socket is removed when the extension disconnects. Run
`python3 bridge/install.py --uninstall` to remove the native host registration.

## Project structure

```text
betterlyrics-plasmoid/
├── metadata.json                   Plasma package identity and version
├── README.md                       Operator and contributor entry point
├── CONTRIBUTING.md                 Development workflow
├── LICENSE                         GPL-3.0 license text
├── Makefile                        Test, package, install, and preview commands
├── bridge/                         Zen native host and registration helper
├── scripts/package.py              Clean reproducible package builder
├── contents/
│   ├── config/
│   │   ├── config.qml              Registers the General settings page
│   │   └── main.xml                Persistent configuration schema/defaults
│   └── ui/
│       ├── main.qml                MPRIS selection, orchestration, timing, color
│       ├── global_control.py       Shared Start/Stop session service
│       ├── PanelCompactRepresentation.qml Panel lyric strip and vertical icon
│       ├── PanelPopup.qml          Panel popup and untimed transcript
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
    ├── bridge_test.py              Native host protocol test
    └── lyrics_service_backend_test.py Python parser/cache/CLI tests
```

Generated `__pycache__` directories are runtime artifacts and are not part of
the package design.

## Runtime architecture

1. `main.qml` selects the first actively playing MPRIS player and tracks its
   metadata and interpolated position.
2. `get_track_url.py` retrieves `xesam:url`; YouTube-style URLs supply the
   video ID used for cache keys, Unison, and Unified providers.
3. A track change starts separate `fast`, `youtube`, `rich`, and `bridge` backend processes.
   Responses include a request token, so results from an earlier track are
   discarded.
4. The fast process compares Zen's cache with the three public fallback
   providers concurrently. The YouTube process requests Music lyrics and
   captions. The rich process checks cache entries and optionally consumes
   the authenticated SSE stream.
5. `main.qml` applies standalone results according to the Better Lyrics provider
   order. The extension's final bridge result takes precedence when available.
6. `LyricsService.js` progressively adds romanization. It also provides the
   complete legacy fetch path if the Python helper fails or is unavailable.
7. On the desktop, the active layout is `SteppedLyricsView.qml` below 220 px
   height and `LyricsStreamView.qml` at 220 px or above. In a panel, the compact
   representation shows a lyric strip or icon and opens a full lyric popup.
   Clicking a timed popup line seeks the active MPRIS player when it can seek.

The widget checks the track URL and shared album-color cache on player or
artwork changes, with short retries for late metadata and a 15-second
reconciliation check. The 33 ms lyric clock runs only while an active timed
line is filling; line-only transitions are scheduled at their next boundary.
MPRIS position corrections retain the original 250 ms cadence while lyrics
are visible, preserving seek responsiveness even with players that omit seek
signals. The unused lyric layout is not instantiated.

The Python service does not maintain application data. Its only project-specific
local read is the Zen extension cache; `libsnappy` is loaded from the system.
Python tooling may generate `__pycache__` bytecode. The QML package stores user
settings through Plasma's configuration system.

## Requirements

- KDE Plasma 6 with the private MPRIS, Plasma 5 Support, and Plasma Workspace
  D-Bus QML modules.
- Python 3 with its standard SQLite, `ctypes`, networking, and XML modules,
  Python D-Bus bindings, and PyGObject/GLib for shared Start/Stop control and
  lyric lookup coordination.
- System `libsnappy` when reading Firefox IndexedDB cache entries.
- An MPRIS-compatible player. Zen/Firefox and the Better Lyrics extension are
  optional: without them, public providers and the JavaScript fallback remain
  available.
- Network access for uncached lyrics and romanization.

Node.js and `make` are needed only for development. The optional bridge runs
only while the companion browser extension is active.
The session service starts when any widget requests lyric results or shared
Start/Stop state.

## Configuration

The General settings page exposes font family, size, weight/style, album-art or
custom text color, lyric delay, syllable wobble, drop shadows, romanization,
romanization opacity, and whether romanization becomes the primary line.
"Show both scripts" can be disabled to show only the selected primary script.
Lyrics wrap across the rows available at the current width; compact windows
show an upcoming line when it fits, including a first-row preview for longer
lines. If an active line exceeds the window height, its rows move through the
viewport during that line's timing window.
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

- Firefox databases are opened read-only; the IndexedDB cache uses SQLite
  immutable mode.
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
- YouTube's caption URLs can return empty data outside the browser session;
  caption availability therefore depends on YouTube's response to the desktop
  request. Music lyrics are queried through the same `next` and `browse` API
  paths the extension observes, but account-only lyrics may require the
  browser's logged-in session.
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
