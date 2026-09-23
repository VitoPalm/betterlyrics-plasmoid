# Contributing

Edit your clone of this repository. The installed Plasma
package under `~/.local/share/plasma/plasmoids/` is a deployment copy; edits
there can be overwritten by the next install.

## Local workflow

1. Make a branch for the change: `git switch -c my-change`.
2. Edit files in `contents/`. Keep runtime dependencies limited to what the
   package and Plasma provide.
3. Run `make test` after parser or service changes. For visual changes, also
   use `make install` and `make preview` with an MPRIS player.
4. Check `git status` before committing so generated files stay out of Git.

`make package` creates `dist/org.kde.plasma.betterlyrics.plasmoid` from only
`metadata.json` and `contents/`. The archive excludes docs, tests, caches, and
local editor files. `make install` installs or upgrades that archive for the
current user. A running Plasma panel may need `systemctl --user restart
plasma-plasmashell.service` to reload QML. Save any panel state before doing so.

The Better Lyrics browser extension was used as a research reference. Its
source is not required to build, test, package, or edit this plasmoid.

## Reporting changes

Describe the behavior, the test commands run, and any UI or provider behavior
that could not be exercised locally. Keep credentials, cached lyrics, and
browser profile files out of issues and commits.
