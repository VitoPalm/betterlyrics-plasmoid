# Energy efficiency plan

## Goal and constraints

Reduce wakeups, process starts, network traffic, and QML work during playback
without changing lyric availability, source preference, word timing, seek
behavior, colors, animation, or the visual transition between compact and tall
layouts. Keep the fast and rich lookup phases independent so a rich lookup does
not delay the first visible result.

## Baseline from the current code

While enabled and playing, `main.qml` schedules a 33 ms position timer, a
250 ms MPRIS probe, a 1 s track URL process, and (with album color enabled) a
1.25 s color-cache process. These imply approximately 30 position callbacks,
4 D-Bus position requests, and 1.8 Python starts per second. This is a code
count, not measured power consumption. Both lyric layouts are instantiated,
and the tall layout constructs every line and propagates each position update
to every line.

## Implementation stages

1. **Remove steady helper polling.** Fetch the MPRIS URL immediately on a
   settled player/track change, retry briefly while metadata arrives, and use
   a much slower reconciliation check for players that change the URL without
   changing the exposed title or artist. Read the shared color cache on
   artwork/track change, retry briefly while the cache is being populated,
   and likewise retain a slow reconciliation check. Reject helper responses
   from older tracks. Keep the image-color fallback available immediately.
2. **Suspend idle timing work.** Run the 33 ms position clock only when there
   are visible, timed word or syllable fills. For line-synced lyrics, wake at
   the next line boundary; keep the existing 250 ms MPRIS correction cadence
   while lyrics are visible to preserve seek responsiveness with players that
   omit seek signals.
   Re-evaluate the schedule on pause/resume, seek, rate change, new lyrics,
   and timing-offset change. Keep the 33 ms cadence for active karaoke.
3. **Limit QML work to visible content.** Instantiate only the selected layout.
   In the tall layout, send high-frequency position changes only to the active
   line. Investigate `ListView` virtualization and mutually exclusive word
   branches after profiling; these need visual verification of variable-height
   line positioning and transitions.
4. **Reduce repeated fetches.** Reuse lyrics across pause/resume for the same
   track. Then evaluate bounded positive/negative caching and reuse of Zen
   cache reads across the two backend phases. Preserve source priority and
   progressive rich upgrades.

## Verification gates

- `make test`, QML syntax/lint, and a clean package build.
- Manual playback checks: line sync, word sync, instrumental break, seek,
  pause/resume, player switch, missing lyrics, late `xesam:url`, and resizing
  across the 220 px layout threshold.
- Compare equivalent before/after playback sessions for helper process starts,
  D-Bus calls, plasmashell CPU time, QML binding work, frame pacing, network
  requests, and battery/energy counters where available. Do not claim a watt
  or battery-life reduction from event counts alone.

## Acceptance

The first lyric should appear no later than the current fetch path under the
same provider conditions. Active syllable fill and seeks should remain smooth
and accurate. Paused, lyricless, and static-line states should have no 33 ms
application timer. During stable playback, helper starts should fall from
roughly 1.8 per second to occasional reconciliation checks.

## Progress

- Stages 1 and 2 are implemented. Stable URL checks now run at 15-second
  intervals. Color checks continue at 15-second intervals, with short checks
  during the first seconds of a track so a late artwork average replaces the
  shared cache's temporary neutral color.
- Stage 3 is implemented for layout loading and active-line position binding.
  `ListView` virtualization and conditional word-layout construction remain
  candidates for a measured second pass.
- Stage 4 reuses the displayed result across pause/resume of the same track.
  Cross-track caching and backend consolidation remain candidates for a
  measured second pass because they could affect rich upgrades or freshness.
- Automated tests, lint syntax checks, package build, a synthetic QML layout
  switch, a compact-view render, and an isolated live-playback load have passed.
  The first installed build exposed a Plasma crash on song changes in
  Kirigami's asynchronous `ImageColors` handler. Restoring the prior package
  stopped the crash. The color source is now kept stable while a shared-cache
  lookup finishes. Live tracing found that the shared writer initially saves
  `#202326` for a new track, then replaces it with the actual artwork color.
  The reader now leaves that temporary value to the image fallback, and the
  lookup continues through the early update. A live track changed from
  `#202326` to `#747d24` during the checks. Three consecutive MPRIS track
  changes completed with no new crash. Interactive seek and player-switch
  checks, visual color confirmation, and before/after energy measurements
  remain before claiming a battery-life improvement.
