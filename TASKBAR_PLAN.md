# Taskbar / panel version plan

Status: initial panel implementation installed on 2026-09-26. The detailed
verification matrix below includes scenarios that still need live panel QA.

## 1. Scope and proposed defaults

Interpret “taskbar version” as a Better Lyrics applet placed alongside the task
manager in a Plasma panel. It does not require modifying Plasma's task manager.
Keep the existing package identity and add placement-aware presentations, so
desktop and panel instances use the same providers, timing, and fixes.

Proposed first-release behavior:

- Horizontal panel: a stable-width lyric strip with no leading icon or progress
  bar. The current lyric wraps onto two rows when needed; a short current lyric
  can show the next line below it. During an instrumental break, the last sung
  lyric appears muted, retaining two rows if it wraps. Start with a preferred width of 280 logical
  pixels; clamp to available space. Width is a setting, never a function of the
  current lyric's length.
- Vertical panel: an upright, icon-sized button with the same tooltip and popup.
  Do not rotate lyrics or grow the panel to accommodate them.
- Left click or keyboard activation opens/closes a native Plasma popup. Panel
  clicks never seek. Right click retains Plasma's context menu and Start/Stop.
- **Start/Stop Better Lyrics is global by default.** Stopping from a following
  desktop or panel instance stops every following instance; starting resumes
  them all. Persist this shared state across shell restarts. Each instance may
  turn off “Follow global Start/Stop” and then uses independent Start/Stop.
- Popup: track and artist, playback state, source and synchronization label,
  lyrics, and a retry action when appropriate. Use a preferred size around
  480 × 420 logical pixels, constrained to the available screen area.
- Desktop: retain the current transparent presentation, pause/no-lyrics fade,
  font defaults, and stepped/stream switch at 220 px.
- Panel default color follows the Plasma theme. Album color is opt-in for the
  strip, with contrast protection against the panel theme. Keep desktop color
  behavior independent.
- Panel default motion is a short line transition; no perpetual marquee or
  syllable wobble. Word fill can remain enabled for supported timed scripts.
- Paused, stopped, missing-lyrics, and disabled states remain discoverable.
  Keep the configured horizontal allocation stable and display a concise
  status or track label. Offer explicit icon-only mode, rather than automatic
  width collapse whenever playback pauses.

These are proposed product decisions, not existing capabilities. A separately
named applet can be considered later if independent distribution is desired;
forking the provider/controller code is unnecessary.

## 2. Desktop behavior to preserve

“Present” below means found in source, not that every combination has been
verified interactively. Existing tests are strongest around parsers, backend
selection, and layout helpers; QML lifecycle behavior needs additional coverage.

| Area | Existing handling and evidence | Panel requirement |
| --- | --- | --- |
| Playback selection | `main.qml` prioritizes playing players with metadata, then the model's current player | Retain automatic selection, strengthen identity consistency as described below |
| Metadata arriving in pieces | 300 ms song debounce; URL retries at 250/500/1000/2000 ms; 15 s reconciliation | Reuse the controller; layout changes must not restart this process |
| Stale work | Request generation checks; separate URL/color generations; romanization revision checks | Preserve guards across popup destruction, Stop, player changes, and retries |
| Provider fallback | Independent fast/rich phases, conditional YouTube/bridge phases, JavaScript fallback on helper failure | Reuse the pipeline and never make the popup own a lookup |
| Source preference | Python honors extension priority and disabled sources; bridge selection has precedence | A later lower-ranked result cannot replace the current winner; “rich” does not automatically mean preferred |
| Progressive improvement | Accepted results replace lyrics and refresh the timeline; enrichment checks result revision | Recompute active line by time, not previous array index; avoid replaying normal line-advance animation |
| Browser/cache failures | Read-only cache access, version/expiry checks, optional JWT and bridge, fallback providers | Missing browser, token, decoder dependency, or bridge must remain nonfatal |
| Provider formats | LRC repeated timestamps/offsets, enhanced LRC, TTML entities/background spans, QRC, captions, plain lyrics | Keep parser behavior and markup sanitization; treat provider text as plain text everywhere |
| Bridge timing | Matching video ID and segment-map adjustment are tested | Preserve corrected line/part timing; reject results for another playing video |
| Position | Local interpolation, duration clamp, drift reconciliation, large-seek correction, rate handling | One shared clock for strip and popup; fresh position sample on reveal/resume |
| Delay migration | Positive means later; old configuration is migrated once | Do not migrate again or apply delay to both controller and view |
| Pause/resume | Reuses loaded lyrics for the same existing key; hides desktop; stops playback clocks | Panel can show a frozen state without fetching again |
| Rendering | Width-based wrapping, preserved timing-bearing parts, next-line fit decisions, tall-line travel | Reuse the full view where appropriate; give the strip its own width/overflow policy |
| Resize races | Deferred stepped-layout work is generation-guarded; resize during transition is handled | Extend protection to representation switches, display-scale changes, and destruction |
| Romanization | Optional enrichment, primary/secondary swap, duplicate suppression; original word timing is removed when romanization is primary | Keep that safeguard; the compact strip uses only the selected primary script, while the popup can show both |
| Font compatibility | Old comma-separated font lists resolve to an installed family | Preserve migration/fallback; test missing glyphs and changed system fonts |
| Color races | Artwork-keyed shared cache, retries for provisional color, stale result rejection | Keep color controller stable across popup open/close |
| Plasma crash mitigation | `ImageColors.source` remains stable when a shared-cache result arrives | Do not unload/recreate artwork processing on every representation change |
| Energy work | 33 ms clock only during active parts; boundary wakes otherwise; 250 ms position probes; lazy selection of desktop layout | Add actual presentation demand to clock/animation decisions |
| Privacy | Encoded shell arguments; no JWT persistence/logging; private bridge socket | New tooltips, status text, and diagnostics must not expose credentials or raw helper output |

Relevant existing tests: `tests/lyrics_service.test.js`,
`tests/lyrics_service_backend_test.py`, `tests/lyric_layout.test.js`, and
`tests/bridge_test.py`. `ENERGY_PLAN.md` also documents the artwork crash and
remaining interactive/performance verification; its original baseline is not
the current timer configuration.

## 3. Existing gaps to address deliberately

These are source-review findings or risks to reproduce, not claims of newly
observed runtime failures.

1. **Selected player and URL can disagree.** `get_track_url.py` searches all
   playing players and eventually accepts any URL. Two players with matching
   metadata can also be ambiguous. Pass the selected D-Bus service identity
   through the lookup and validate the response against it. Do not borrow
   another player's URL when the selected player has none.
2. **Track keys are not strong identities.** Current keys lowercase title,
   artist, rounded duration, and URL, omit the player and MPRIS track ID, and
   concatenate with a delimiter. Video IDs/URLs can be case-sensitive. Use a
   structured identity containing player service/owner generation, track ID,
   exact URL/video ID, and metadata fallback fields. Preserve case for IDs.
   Treat late URL/duration as refinement when demonstrably the same track.
3. **A refinement may erase useful lyrics.** `triggerSongChange(false)` keeps
   lyrics initially, but `executeSongFetch()` subsequently clears them when
   its key changes. Keep existing lyrics during a verified same-track upgrade;
   clear immediately on a real track/player change.
4. **Loading completion is incomplete.** Valid empty responses from all Python
   phases do not necessarily clear `isLoadingLyrics`. Track each launched phase
   and fallback to a terminal state, including unavailable, empty, failure,
   timeout, and cancellation. A slow bridge must not prevent displaying a
   usable result already obtained.
5. **Cancellation is not established.** Generation guards prevent stale UI
   writes but do not prove old subprocesses stop. `RunCommand.terminate()`
   disconnects an executable-engine source; verify its actual process semantics
   before relying on it. Bound phase lifetimes and obsolete concurrency.
6. **Seeking has no explicit capability check.** The root writes position when
   a player exists. Gate by player seek capability, valid timed content, and
   unchanged identity; clamp targets. Unsynced lyrics must not invent a seek
   target from estimated timing.
7. **Plain lyrics have estimated timings.** `parse_plain()` distributes lines
   over duration (or estimates duration). In the panel, show “Lyrics available”
   or track metadata; show a manually scrollable, labeled unsynced transcript
   in the popup. Do not present estimates as karaoke synchronization.
8. **Overlapping intervals need a declared winner.** `updateActiveLine()` stops
   at the first interval containing the position. Choose the latest started
   eligible line for the strip; define a stable tie-break for equal starts.
   Preserve secondary/background text in the popup. Add fixtures before
   changing shared selection so desktop consequences are explicit.
9. **Unicode wrapping is not grapheme-aware.** `Array.from()` prevents splitting
   surrogate pairs, but may split combining sequences or emoji clusters. Timed
   parts can also individually exceed the viewport. Use Qt text shaping/elision
   where possible and test graphemes before considering a custom segmenter.
10. **Visibility does not fully control work.** Current clocks depend on playback
    and lyrics; instrumental pulses can run continuously while active. A hidden
    popup or panel must not retain animation demand merely because data exists.
11. **Paused metadata and configuration changes need characterization.** Album
    changes do not directly trigger a fetch, and enabling romanization after a
    result loaded without it has no obvious enrichment trigger. Define which
    changes update presentation, enrich data, refine a request, or replace it;
    avoid unnecessary full refetches.

## 4. Shared architecture

Keep one controller per applet instance, outside all representation loaders.
Opening the popup adds a view, not another player model, provider cascade,
artwork reader, or timing loop.

Proposed responsibilities/files (names may be adjusted during implementation):

| Component | Responsibility |
| --- | --- |
| `main.qml` | Thin `PlasmoidItem` shell; form factor, representations, actions, configuration migration |
| `LyricsController.qml` | Selected player, structured track identity, request generations, phase completion, result arbitration, enrichment, playback clock |
| `AlbumColorController.qml` | Stable image-color object and existing optional shared-cache lookup lifecycle |
| `DesktopLyricsView.qml` | Existing desktop fade and stepped/stream selection |
| `PanelCompactRepresentation.qml` | Stable layout, icon fallback, tooltip, activation, accessibility |
| `PanelLyricLine.qml` | One-row timed rendering and overflow policy without seeking |
| `LyricsPopup.qml` | Metadata/status, timed lyrics or unsynced transcript, retry, constrained popup sizing |
| Small pure JS helpers | Track identity, request/state reduction, timeline selection where extraction improves testability |

Expose data state separately from presentation state: selected identity,
playback status, fetch status, pending phases, accepted source/sync type,
result revision, lyrics, raw/adjusted position, active index, and capabilities.
For example, “playing + usable fallback + enrichment pending” is valid and must
not be forced into a single “loading” state.

Views request actions through the controller. A seek carries the identity and
result revision used to render its target; ignore it if the track changed before
activation. Seek to the raw lyric timestamp; the display offset remains a clock
adjustment, preserving current semantics.

Use Plasma 6 `PlasmoidItem` representation properties. Prefer compact in panels
and full on the desktop; do not infer panel placement from height alone. The
popup uses the full representation with normal Plasma framing, while desktop
retains its background policy. KDE documents the property ownership in its
[Plasma 6 porting guide](https://develop.kde.org/docs/plasma/widget/porting_kf6/).
Check the supported Plasma version's actual sizing/visibility APIs during the
first implementation stage; no stock media-controller source was available at
the standard local path during this review.

## 5. State and interaction contract

| State | Horizontal strip | Popup / behavior |
| --- | --- | --- |
| Globally disabled | Blank horizontal strip on following instances | Start action resumes all following instances; independent instances retain their local state |
| No player | Icon + “No player” | Explain that an MPRIS player is needed; no retry loop |
| Playing, metadata incomplete | Icon + waiting status | Wait for bounded metadata settling; never show another track's lyrics |
| First lookup pending | Track title or “Loading lyrics” | Status; show each accepted result immediately |
| Timed lyrics | Current primary-script line | Full timed lyrics, source, click-to-seek when supported |
| Before first lyric | Upcoming line with preview styling | No premature word fill; retain any explicit instrumental intro |
| Instrumental segment | Small indicator / “Instrumental” | Distinguish a timed break from unavailable lyrics |
| Unsynced only | “Lyrics available” / track title | Labeled, manually scrollable transcript; no timed seeking |
| Paused | Pause indicator + last line or title | Frozen timed state; cached lyrics retained; no fill animation |
| Playback stopped | Track title or idle label | Retain useful transcript for the same identity; no advancing timeline |
| All phases empty | “No lyrics” | Terminal empty state; explicit retry |
| All phases failed | “Lyrics unavailable” | Sanitized explanation and retry; distinguish from a genuine empty result |
| Better result arrives | Replace at current position | Keep popup open; do not jump to first line |
| After final timed line | Last line static until stop/track change | No invented loop or animation; repeat seeks reselect correctly |

Additional interaction rules:

- Enter/Space activates the strip; Escape dismisses the popup and restores
  focus appropriately. Do not steal focus when lyrics or provider results change.
- Tooltip gives full unelided line, track, artist, and meaningful state. Render
  plain text and suppress tooltip clutter while the popup is open.
- Wheel over the strip does not seek or change volume. Wheel/touch scrolling
  inside the popup navigates lyrics.
- Timed popup lyrics may be manually browsed. User scrolling suspends follow
  mode until “Return to current lyric” or popup reopen. Do not fight the user
  with auto-scroll every 250 ms. Untimed lyrics never enter follow mode.
- Right click and panel edit/drag gestures retain standard applet behavior.
  Opening/closing must be handled once, avoiding competing click handlers.
- Pause keeps an open popup available. Explicit Stop stops Better Lyrics work
  in all following instances, or only the independent instance where invoked,
  without stopping the media player's playback. Starting
  globally while the player is paused shows state without starting the player.

## 6. Layout, text, color, and motion

Use panel thickness to derive font size with theme-aware padding and a readable
minimum. If the allocation is too small for readable text, use the icon. Never
enforce the desktop's 200 × 40 minimum on a panel representation. A taller panel
uses the same two-row policy with a larger readable font.

For long timed lines, use a bounded viewport that follows the active word/part
only as necessary. For line-only text, use native elision with complete text in
the tooltip/popup. Do not shrink arbitrarily long lyrics into illegibility.
If a timed part itself cannot fit, clip/elide safely and keep its timing intact;
do not split its timing among invented fragments. Reduced-motion mode freezes
viewport travel and uses an elided line. Test that word-follow does not reset
on every clock tick or fight right-to-left shaping.

Render logical text order through Qt's shaping engine. For scripts where the
existing separate-word delegate cannot preserve joining, or where directional
fill is unreliable, fall back to a correctly shaped line highlight. Correct
Arabic/Indic/bidirectional text is more important than approximate word fill.
No provider markup may become clickable HTML.

The strip uses the configured primary script only. A missing romanization
falls back to the original. Late enrichment updates in place without width
changes or fake original-script word timings. Popup preserves the existing
both-scripts preference and opacity controls.

Panel colors must remain readable in light/dark/translucent/floating panels,
with a theme-text fallback when artwork or custom colors are unsuitable.
Re-evaluate on theme change. Preserve the artwork crash mitigation; do not
clear an in-flight image source to switch to a shared-cache color.

Honor reduced animation preferences where available and provide an explicit
panel motion setting. Accessible names update at line/state boundaries, never
per word frame; avoid unsolicited screen-reader announcements on every line.
Include visible keyboard focus and adequately sized touch targets.

## 7. Lifecycle, performance, and additional edge cases

| Scenario | Required handling / verification |
| --- | --- |
| Auto-hidden panel, closed popup, icon-only mode | No invisible karaoke or instrumental animation. Verify which visibility signal reflects actual exposure; do not assume `visible` alone proves on-screen visibility |
| Popup and strip visible together | One position probe stream and provider cascade; each view renders its own presentation without duplicate fetches |
| Reveal after hidden playback | Sample current position and select the current line immediately; do not replay every missed transition |
| Hidden track changes | Retain bounded acquisition for the current track so reveal is useful; coalesce rapid changes and prevent obsolete helper buildup |
| Suspend/resume or wall-clock jump | Reanchor rather than projecting a large elapsed `Date.now()` interval; use a monotonic source if supported, otherwise detect discontinuities |
| Seek backward / repeat-one / external seek | Reset selection and word fill; do not interpret backward seek as an outgoing-next-line transition |
| Rate changes, bad position/duration | Validate finite values; cover 0.5×/1×/2×, zero/unknown duration, stale samples, invalid rates, and track-end corrections |
| Two simultaneously playing players | Deterministic selection; selected service supplies metadata, URL, position, and seek target; characterize current behavior before changing selection policy |
| Player closes or restarts | Invalidate old owner identity; discard pending seek/results; safely select the next eligible player |
| Same title/artist, different recording | Distinguish URLs/track IDs; album-only and duration refinements must not silently reuse another recording |
| Ads, live streams, podcasts | Incomplete/unknown-duration metadata remains safe; never reuse a previous song solely because title is blank |
| Rapid track skips / very long SSE / lost network | Generation guards plus bounded timeouts/concurrency; terminal loading state; retries are explicit or bounded, never triggered by popup opening |
| Empty result while richer work remains | Show waiting state honestly; once useful lyrics exist, failures of remaining phases cannot blank them |
| Equal-priority duplicate results | Stable arbitration; avoid pointless revision churn and visual resets for identical content |
| Invalid/massive provider payload | Validate types, finite timestamps, line/part counts and response size; reject unusable data without blocking the shell |
| Reordered/duplicate/overlapping times | Deterministic active-line selection, no zero-delay wake loop, no negative interval or division by zero |
| Long strings, emoji, combining marks, RTL/CJK | Safe elision/wrapping and glyph fallback; correct text order; test mixed scripts and punctuation |
| Multiple widgets / multiple monitors | Shared global Start/Stop state; independent presentation settings and request generations. Measure duplicate acquisition across instances |
| Panel moved / rotated / resized during popup | Recompute presentation, close/reanchor popup if necessary, retain controller state; no lookup solely due to geometry |
| Fractional scale / monitor removed / screen edge | Recompute font metrics and constrain popup; no off-screen content or retained device-pixel assumptions |
| Edit mode, locked widgets, zero-size startup | Always leave a discoverable handle/icon; no minimum-size loops or fetch storms during construction |
| Widget removed / shell shutdown | Invalidate callbacks and clean up supported resources; an obsolete result cannot revive a destroyed view |
| Old configuration / restore backup | Preserve desktop settings and one-time offset migration; validate new enums and clamp invalid sizes |

Timing demand is aggregated per instance: fast updates only when an exposed
view needs word fill or deliberate viewport motion; line boundaries otherwise.
Keep the existing 250 ms correction cadence when timed lyrics are exposed.
Icon-only and hidden views should not need that cadence. Metadata monitoring
continues, with fresh sampling on exposure. If reliable panel-exposure detection
is unavailable, document the limitation rather than claiming zero hidden work.

Cross-instance fetch deduplication is a later optimization unless measurements
show it is required for acceptable desktop-plus-panel usage. It would need
reference-counted subscribers and keys including provider preferences; do not
introduce an unbounded global cache or a background daemon as part of v1.

### Required global Start/Stop coordination

Global control is a v1 requirement, independent of optional fetch deduplication.
Following the global state is the default. An instance with “Follow global
Start/Stop” disabled uses its own persisted `enabled` setting and does not
change or respond to the global control.
Use one authoritative, persisted enabled state for the current user, with
event-driven notification to every live instance. Verify an appropriate Plasma/
KConfig or session-bus mechanism in Stage 1; a per-instance configuration flag,
a process-local JavaScript singleton, or repeated polling is insufficient.
Independent hosts must also read the persisted state before starting work.

- Stop from a following instance updates all following contextual actions to
  Start Better Lyrics and gives following panel instances the stopped
  presentation; desktops retain their
  existing hidden-when-disabled presentation.
- Each controller invalidates lyric, URL, artwork, and enrichment generations;
  stops debounce/retry/reconciliation/position timers and animations; and cancels
  in-flight work where supported. Late results cannot restore lyrics, restart
  timers, or overwrite the global stopped state. Verify actual helper
  termination rather than treating callback disconnection as cancellation.
- Keep only the coordination needed to observe Start and maintain controls.
  Document any unavoidable residual in-flight work with bounded completion;
  do not claim global stopping is complete while obsolete helpers run unbounded.
- Global Start broadcasts one state transition. Each following instance reanchors to current
  playback and follows its normal bounded acquisition path. Duplicate state
  notifications must not launch duplicate requests.
- Serialize concurrent Start/Stop writes through the chosen authority and use
  an ordered revision so delayed notifications cannot reverse a newer action.
  A newly added instance or a restarted shell must honor a persisted Stop.
- Migrate existing per-instance `enabled` values once. If no global value exists,
  choose stopped if any existing following instance is disabled; otherwise choose enabled.
  Read the complete relevant configuration before committing that decision so
  initialization order cannot decide the result. Once created, the global value
  takes precedence and obsolete instance flags cannot overwrite it.

The coordination mechanism must be validated before committing to the no-new-
dependency assumption; global control must not depend on the optional browser
bridge being installed or connected.

## 8. Configuration and compatibility

Add panel-specific keys without overwriting existing desktop font/color/motion
preferences. Proposed initial controls: strip versus icon mode, preferred strip
width, panel font size override (automatic by default), panel color mode, and
motion preference. Keep timing offset, romanization, and source behavior
consistent within each instance. Desktop and panel placements retain separate
presentation configuration, but enabled state is shared globally. Explain in
settings and documentation that Start/Stop affects every Better Lyrics instance.

Use automatic form-factor detection; do not add a setting users must toggle
after moving the applet. Preserve package ID, existing configuration names,
bridge protocol, and installation flow unless a separately reviewed issue
requires a change. No new runtime dependency is planned.

## 9. Ordered implementation stages and exit criteria

### Stage 1 — Characterize the baseline and confirm Plasma integration

Record desktop behavior with representative synthetic tracks; confirm the
supported Plasma version's representation, popup, form-factor, visibility, and
MPRIS identity/capability APIs. Validate the global-state persistence,
notification, ordering, and migration mechanism. Reproduce the identified loading/identity risks.
Capture reference images at compact/tall sizes and existing timing behavior.

Exit: agreed contracts for state, identity, seeking, and panel exposure; test
fixtures distinguish existing behavior from intended changes. Do not change
desktop behavior opportunistically during extraction.

### Stage 2 — Extract the controller without presentation changes

Move orchestration and color ownership out of the root visual tree; wrap the
existing desktop presentation. Keep provider ordering, migrations, and clock
behavior intact. Add an injectable MPRIS/phase runner for deterministic tests.

Exit: desktop fixtures and existing suite pass; equivalent fetch/probe counts;
same active line, accepted provider, artwork behavior, and pause/resume reuse.

### Stage 3 — Harden shared state and requests

Implement structured identity, selected-service URL lookup, explicit phase
completion/deadlines, same-track refinement, seek validation, deterministic
result arbitration, configuration-triggered enrichment, and global Start/Stop
coordination with one-time configuration migration. Investigate actual
subprocess cancellation separately from callback invalidation.

Exit: stale responses never win; all-empty and all-failed requests terminate;
same-track upgrades remain visible; rapid skipping has bounded resource use.
Stopping from any following instance stops all following instances, including across distinct hosts;
restart/new-instance initialization preserves Stop, and global Start resumes
without duplicate requests from repeated notifications.
Shared desktop changes are documented and covered by regression tests.

### Stage 4 — Build panel shell and popup states

Add compact/full representations, horizontal/vertical layout contracts,
stable width, icon fallback, native popup, tooltips, accessible activation,
and all non-lyric states. Initially use simple fixture text to isolate layout.

Exit: actual Plasma panel accepts the applet at all four edges, neighboring
items stay still across state changes, and opening the popup starts no fetch.

### Stage 5 — Integrate lyrics and interaction

Add compact timing/overflow behavior, script handling, popup timed/untimed
views, capability-aware seeking, manual browsing/follow mode, theme colors,
and motion preferences. Verify provider upgrades while popup and strip coexist.

Exit: complete text is accessible; no accidental panel seek; no false timed
presentation for plain lyrics; long/mixed-script content remains usable.

### Stage 6 — Visibility scheduling and lifecycle

Aggregate view demand, gate clocks/animations, reanchor on reveal/resume, and
handle geometry, destruction, player restart, and display changes. Profile
one panel instance and desktop-plus-panel together using the same tracks.

Exit: popup opening does not duplicate backend or probe work; hidden static
states have no unnecessary 33 ms loop; no animation accumulates off-screen.
Report measured process starts, D-Bus calls, CPU/frame pacing, and limitations;
do not infer battery savings from timer counts alone.

### Stage 7 — Release verification and documentation

Run existing and new tests, QML syntax/lint checks with the actual imports, and
a clean package build. Test in an isolated Plasma session before installing in
a daily-use panel. Update README with placement, behavior, configuration, and
known limitations. Keep a previous package available for rollback.

Exit: the regression matrix below passes on declared supported environments,
or limitations are explicitly recorded; no change is shipped solely on the
basis of a `plasmawindowed` preview.

## 10. Verification matrix and definition of done

Automated coverage should focus on behavior rather than duplicating bindings:

- Pure state/timeline tests: structured IDs, track refinements, phase settlement,
  quality/bridge precedence, stale results/enrichment, rate/offset/seek/overlap,
  repeat-one, unknown duration, bad timestamps, and wake scheduling.
- Helper/backend tests: selected service and disappearing D-Bus owner; no
  wrong-player URL fallback; timeout/empty/failure classification; malformed
  payload limits; existing provider/cache/bridge parser regressions.
- QML integration fixtures: popup recreation, both views observing one
  controller, Stop mid-request, font/theme/script changes, capability changes,
  resize during transition, and identity-checked seek.

Manual matrix, using pairwise combinations plus the named high-risk cases:

| Dimension | Cases |
| --- | --- |
| Placement | Desktop, top/bottom panel, left/right panel, icon-only, edit mode |
| Geometry | 24/32/48/64 logical-pixel panel thickness; narrow allocations; preferred 280 px; small popup work area |
| Displays | 100/125/150/200% scale, mixed-scale monitors, hot-unplug, relocation |
| Panel behavior | Fixed, floating, auto-hide, translucent, opaque |
| Playback | Playing/paused/stopped, no player, two players, player restart, seek without signal, repeat, suspend/resume |
| Lyrics | Line/word/syllable, instrumental, plain, absent, malformed, long lines/parts, RTL/CJK/emoji, romanization late/missing |
| Providers | Cache hit/miss, offline, helper missing, bridge absent/late, expired JWT, fallback then preferred upgrade, all-empty/all-failed |
| Input and access | Mouse, keyboard, touch, focus restoration, context menu, manual scroll, reduced motion, screen-reader names |
| Coexistence | Desktop plus panel; two panel instances; remove one during lookup; global Stop/Start from each placement and distinct hosts |
| Global control | Stop during fetch/enrichment; new instance while stopped; shell restart while stopped; simultaneous conflicting actions; delayed/duplicate notifications; migration of mixed legacy enabled flags |

High-risk combined scenarios: two players with identical titles while a late
URL arrives; rapid skips while bridge and romanization are pending; popup close
during enrichment followed by monitor relocation; Stop followed by a late
success; artwork cache hit during rapid song changes; auto-hidden panel revealed
after suspend and a seek; provider replacement with different line counts while
the user is browsing the popup.

Done means global Start/Stop reliably controls following instances while independent instances retain local control, stable panel geometry, correct source/player/timeline identity,
finite loading states, reachable controls in every state, preserved desktop
behavior except explicitly tested shared fixes, and no duplicate work from
representation changes. Retain this matrix for verification and follow-up work.
