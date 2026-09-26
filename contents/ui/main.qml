pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.plasma.private.mpris as Mpris
import org.kde.kirigami as Kirigami

import "LyricsService.js" as LyricsService

PlasmoidItem {
    id: root

    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: root.cfgEnabled ? i18n("Stop Better Lyrics") : i18n("Start Better Lyrics")
            icon.name: root.cfgEnabled ? "media-playback-stop" : "media-playback-start"
            onTriggered: Plasmoid.configuration.enabled = !root.cfgEnabled
        }
    ]

    Layout.fillWidth: true
    Layout.fillHeight: true
    Layout.minimumWidth: 200
    Layout.minimumHeight: 40

    Mpris.Mpris2Model {
        id: mpris2Model
    }

    // Robust player resolution: dynamically prioritize whichever player is actively playing
    readonly property var player: {
        const containerRole = Qt.UserRole + 1;
        for (let i = 1; i < mpris2Model.rowCount(); i++) {
            const candidate = mpris2Model.data(mpris2Model.index(i, 0), containerRole);
            if (candidate && candidate.playbackStatus === Mpris.PlaybackStatus.Playing
                    && (candidate.track || candidate.artist)) {
                return candidate;
            }
        }
        const current = mpris2Model.currentPlayer;
        if (current && (current.track || current.artist)) {
            return current;
        }
        return null;
    }

    readonly property bool isPlaying: player ? player.playbackStatus === Mpris.PlaybackStatus.Playing : false
    readonly property string trackTitle: player?.track || ""
    readonly property string trackArtist: player?.artist || ""
    readonly property string trackAlbum: player?.album || ""
    readonly property string trackArtUrl: player?.artUrl || ""
    readonly property double trackDuration: (player?.length || 0) / 1000000 // seconds
    property string trackUrl: ""

    // Configuration properties
    readonly property bool cfgEnabled: Plasmoid.configuration.enabled !== false
    readonly property string cfgFontFamily: {
        const configured = Plasmoid.configuration.fontFamily || "Noto Sans";
        const candidates = configured.split(",");
        const installed = Qt.fontFamilies();
        // Accept old CSS-like lists, but pass one real family to QML.
        for (let i = 0; i < candidates.length; i++) {
            const candidate = candidates[i].trim();
            if (installed.indexOf(candidate) >= 0) return candidate;
        }
        return "Noto Sans";
    }
    readonly property int cfgFontSize: Plasmoid.configuration.fontSize || 24
    readonly property bool cfgFontBold: Plasmoid.configuration.fontBold !== undefined ? Plasmoid.configuration.fontBold : true
    readonly property bool cfgFontItalic: Plasmoid.configuration.fontItalic || false
    readonly property bool cfgUseAlbumColor: Plasmoid.configuration.useAlbumColor !== undefined ? Plasmoid.configuration.useAlbumColor : true
    readonly property color cfgCustomFontColor: Plasmoid.configuration.customFontColor || "#FFFFFF"
    readonly property int cfgTimingOffsetMs: {
        const stored = Plasmoid.configuration.timingOffsetMs !== undefined
                     ? Plasmoid.configuration.timingOffsetMs : -150;
        return (Plasmoid.configuration.timingOffsetSemanticsVersion || 0) >= 1
             ? stored : -stored;
    }
    readonly property bool cfgEnableWobble: Plasmoid.configuration.enableWobble !== undefined ? Plasmoid.configuration.enableWobble : true
    readonly property bool cfgEnableShadow: Plasmoid.configuration.enableShadow !== undefined ? Plasmoid.configuration.enableShadow : true
    readonly property bool cfgEnableRomanization: Plasmoid.configuration.enableRomanization !== undefined
                                                   ? Plasmoid.configuration.enableRomanization : true
    readonly property real cfgRomanizationOpacity: Plasmoid.configuration.romanizationOpacity !== undefined
                                                    ? Plasmoid.configuration.romanizationOpacity : 0.72
    readonly property bool cfgRomanizationPrimary: Plasmoid.configuration.romanizationPrimary !== undefined
                                                    ? Plasmoid.configuration.romanizationPrimary : false
    readonly property bool cfgShowBothScripts: Plasmoid.configuration.showBothScripts !== false
    // Optional shared color cache, with the artwork average as fallback.
    property color sharedAlbumArtColor: Kirigami.Theme.highlightColor
    property bool sharedAlbumArtReady: false
    property int colorLookupGeneration: 0
    property int colorRetryCount: 0
    property int colorInFlightGeneration: -1

    function scheduleColorLookup() {
        colorLookupGeneration += 1;
        colorRetryCount = 0;
        colorRetryTimer.stop();
        sharedAlbumArtReady = false;
        if (cfgEnabled && isPlaying && cfgUseAlbumColor) {
            colorRetryTimer.interval = 16;
            colorRetryTimer.restart();
        }
    }

    function refreshAlbumColor() {
        if (!cfgEnabled || !isPlaying || !cfgUseAlbumColor
                || colorInFlightGeneration === colorLookupGeneration) return;
        const key = encodeURIComponent(trackTitle + "\u001f" + trackArtist
                                       + "\u001f" + trackArtUrl).replace(/'/g, "%27");
        colorInFlightGeneration = colorLookupGeneration;
        sharedColorReader.run("python3 '" + sharedColorScriptPath.replace(/'/g, "'\\''")
                              + "' '" + key + "' --generation " + colorLookupGeneration);
    }

    RunCommand {
        id: sharedColorReader
        onExited: (cmd, exitCode, exitStatus, stdout, stderr) => {
            const match = cmd.match(/ --generation (\d+)$/);
            const generation = match ? Number(match[1]) : -1;
            if (root.colorInFlightGeneration === generation) root.colorInFlightGeneration = -1;
            if (!root.cfgEnabled || generation !== root.colorLookupGeneration) return;
            try {
                const record = JSON.parse(stdout.trim());
                const expectedKey = encodeURIComponent(root.trackTitle + "\u001f"
                                                        + root.trackArtist + "\u001f"
                                                        + root.trackArtUrl).replace(/'/g, "%27");
                if (/^#[0-9a-fA-F]{6}$/.test(record.color)
                        && record.source_key === expectedKey) {
                    root.sharedAlbumArtColor = record.color;
                    root.sharedAlbumArtReady = true;
                }
            } catch (error) {
                // Missing and legacy cache files fall back to ImageColors.
            }
            // The external writer may publish a temporary background color
            // before the artwork average. Keep checking briefly after a hit.
            if (root.colorRetryCount < 8) {
                const delays = [250, 750, 1250, 1250, 1250, 1250, 1250, 1250];
                colorRetryTimer.interval = delays[root.colorRetryCount++];
                colorRetryTimer.restart();
            }
        }
    }

    Timer {
        id: colorRetryTimer
        interval: 16
        onTriggered: root.refreshAlbumColor()
    }

    Timer {
        interval: 15000
        running: root.cfgEnabled && root.isPlaying && root.cfgUseAlbumColor
        repeat: true
        onTriggered: root.refreshAlbumColor()
    }

    // Direct DBus xesam:url reader to supply videoId for Unison
    property int trackUrlLookupGeneration: 0
    property int trackUrlRetryCount: 0
    property int trackUrlInFlightGeneration: -1

    RunCommand {
        id: trackUrlReader
        onExited: (cmd, exitCode, exitStatus, stdout, stderr) => {
            const match = cmd.match(/ --generation (\d+)$/);
            const generation = match ? Number(match[1]) : -1;
            if (root.trackUrlInFlightGeneration === generation) root.trackUrlInFlightGeneration = -1;
            if (!root.cfgEnabled || generation !== root.trackUrlLookupGeneration) return;
            const val = stdout.trim();
            if (val && val !== root.trackUrl) {
                root.trackUrl = val;
            }
            if (!val && root.trackUrlRetryCount < 4) {
                const delays = [250, 500, 1000, 2000];
                trackUrlRetryTimer.interval = delays[root.trackUrlRetryCount++];
                trackUrlRetryTimer.restart();
            }
        }
    }

    function scheduleTrackUrlLookup(clearKnown) {
        trackUrlLookupGeneration += 1;
        trackUrlRetryCount = 0;
        trackUrlRetryTimer.stop();
        if (clearKnown !== false) trackUrl = "";
        if (cfgEnabled && isPlaying && trackTitle) {
            trackUrlRetryTimer.interval = 16;
            trackUrlRetryTimer.restart();
        }
    }

    function refreshTrackUrl() {
        if (!cfgEnabled || !isPlaying || !trackTitle
                || trackUrlInFlightGeneration === trackUrlLookupGeneration) return;
        const encodedTitle = encodeURIComponent(trackTitle).replace(/'/g, "%27");
        const encodedArtist = encodeURIComponent(trackArtist).replace(/'/g, "%27");
        trackUrlInFlightGeneration = trackUrlLookupGeneration;
        trackUrlReader.run("python3 '" + trackUrlScriptPath.replace(/'/g, "'\\''") + "' '"
                           + encodedTitle + "' '" + encodedArtist + "' --generation "
                           + trackUrlLookupGeneration);
    }

    Timer {
        id: trackUrlRetryTimer
        interval: 16
        onTriggered: root.refreshTrackUrl()
    }

    Timer {
        interval: 15000
        running: root.cfgEnabled && root.isPlaying && !!root.trackTitle
        repeat: true
        onTriggered: root.refreshTrackUrl()
    }

    Kirigami.ImageColors {
        id: albumColors
        // Keep the source stable while a shared-cache lookup completes. Kirigami
        // processes images asynchronously; clearing a pending source on every
        // cache hit can crash plasmashell on the next artwork change.
        source: root.cfgEnabled ? root.trackArtUrl : ""
    }

    readonly property color albumArtBaseColor: sharedAlbumArtReady
                                                ? sharedAlbumArtColor
                                                : (albumColors.average || Kirigami.Theme.highlightColor)
    readonly property var albumArtBrightness: Kirigami.ColorUtils.brightnessForColor(albumArtBaseColor)
    readonly property color readableAlbumColor: Kirigami.ColorUtils.tintWithAlpha(
                                                     albumArtBaseColor,
                                                     albumArtBrightness === Kirigami.ColorUtils.Dark ? "white" : "black",
                                                     0.36)

    // Preserve the cover hue, but move very dark/light averages far enough
    // toward contrast that they remain readable over arbitrary wallpapers.
    readonly property color activeLyricColor: {
        if (!cfgUseAlbumColor) {
            return cfgCustomFontColor;
        }
        return readableAlbumColor;
    }

    readonly property color inactiveLyricColor: {
        return Qt.rgba(activeLyricColor.r, activeLyricColor.g, activeLyricColor.b, 0.58);
    }

    // Playback state tracking
    property double currentTrackPositionMs: 0
    property double lastMprisPositionMs: 0
    property double lastUpdateTime: 0
    property double positionAnchorMs: 0
    property double positionAnchorTime: 0
    property double positionPlaybackRate: 1
    property bool positionClockInitialized: false
    property bool awaitingTrackPositionSample: false

    // Positive settings delay lyrics; negative settings advance them. This is
    // the same direction used by Better Lyrics' browser extension.
    readonly property double adjustedPositionMs: LyricsService.adjustedPositionMs(
                                                   currentTrackPositionMs, cfgTimingOffsetMs)

    // Lyrics data
    property var lyricsList: []
    property string lyricsSource: ""
    property string lyricsSyncType: ""
    property bool isLoadingLyrics: false
    property int activeLineIndex: -1
    readonly property bool activeLineHasParts: {
        if (activeLineIndex < 0 || activeLineIndex >= lyricsList.length) return false;
        const line = lyricsList[activeLineIndex];
        const swapRomanization = cfgEnableRomanization && cfgRomanizationPrimary
                                 && !!(line.romanization || "").trim();
        if (swapRomanization || !line.parts?.length) return false;
        const lastPart = line.parts[line.parts.length - 1];
        const fillEnd = Math.max(line.startTimeMs + line.durationMs,
                                 (lastPart.startTimeMs || 0) + (lastPart.durationMs || 0));
        return adjustedPositionMs >= line.startTimeMs && adjustedPositionMs < fillEnd;
    }

    property string lastLoadedTrackKey: ""
    property string lastFetchedTitle: ""
    property string lastFetchedArtist: ""
    property int requestGeneration: 0
    property int backendQuality: -1
    property int backendResultRevision: 0
    property bool legacyFallbackStarted: false

    readonly property string backendScriptPath: decodeURIComponent(
        Qt.resolvedUrl("lyrics_service.py").toString().replace(/^file:\/\//, ""))
    readonly property string trackUrlScriptPath: decodeURIComponent(
        Qt.resolvedUrl("get_track_url.py").toString().replace(/^file:\/\//, ""))
    readonly property string sharedColorScriptPath: decodeURIComponent(
        Qt.resolvedUrl("read_album_color.py").toString().replace(/^file:\/\//, ""))

    function encodedArgument(value) {
        // Percent encoding leaves only shell-safe ASCII after also escaping the
        // apostrophe which encodeURIComponent intentionally preserves.
        return encodeURIComponent(value || "").replace(/'/g, "%27");
    }

    function backendCommand(phase, token) {
        return "python3 '" + backendScriptPath.replace(/'/g, "'\\''") + "'"
            + " --phase " + phase
            + " --title '" + encodedArgument(trackTitle) + "'"
            + " --artist '" + encodedArgument(trackArtist) + "'"
            + " --album '" + encodedArgument(trackAlbum) + "'"
            + " --duration " + Math.max(0, trackDuration)
            + " --video-id '" + encodedArgument(LyricsService.extractVideoId(trackUrl)) + "'"
            + " --request-token '" + token + "'";
    }

    function applyBackendResult(payload) {
        if (!cfgEnabled || !payload || payload.requestToken !== String(requestGeneration)
                || !payload.ok || !payload.result || !payload.result.lines
                || payload.result.lines.length === 0) {
            return false;
        }
        const result = payload.result;
        const quality = Number(result.quality || 0);
        if (quality < backendQuality) return true;
        backendQuality = quality;
        backendResultRevision += 1;
        lyricsList = result.lines.slice(0);
        lyricsSource = result.source || "";
        lyricsSyncType = result.syncType || "";
        isLoadingLyrics = false;
        refreshTimeline();
        if (cfgEnableRomanization) {
            const expectedGeneration = requestGeneration;
            const expectedRevision = backendResultRevision;
            LyricsService.enrichRomanization(result, LyricsService.extractVideoId(trackUrl), function(err, enriched) {
                if (!err && expectedGeneration === requestGeneration
                        && backendResultRevision === expectedRevision && enriched?.lines) {
                    lyricsList = enriched.lines.slice(0);
                    refreshTimeline();
                }
            });
        }
        return true;
    }

    function startLegacyFallback(token) {
        if (!cfgEnabled || legacyFallbackStarted || backendQuality >= 0
                || token !== String(requestGeneration)) return;
        legacyFallbackStarted = true;
        const expectedGeneration = requestGeneration;
        const expectedKey = lastLoadedTrackKey;
        LyricsService.fetchLyrics(trackTitle, trackArtist, trackAlbum, trackDuration,
                                  trackUrl, cfgEnableRomanization, function(err, result) {
            if (expectedGeneration !== requestGeneration || expectedKey !== lastLoadedTrackKey) return;
            isLoadingLyrics = false;
            if (!err && result?.lines?.length && backendQuality < 0) {
                lyricsList = result.lines.slice(0);
                lyricsSource = result.source || "";
                lyricsSyncType = result.syncType || "";
                refreshTimeline();
            } else if (backendQuality < 0 && (err || !result?.lines?.length)) {
                lyricsList = [];
            }
        });
    }

    RunCommand {
        id: fastLyricsReader
        onExited: (cmd, exitCode, exitStatus, stdout, stderr) => {
            let payload = null;
            try { payload = JSON.parse(stdout.trim()); } catch (error) {}
            const tokenMatch = cmd.match(/--request-token '([^']+)'/);
            const token = payload?.requestToken || (tokenMatch ? tokenMatch[1] : "");
            if (!root.applyBackendResult(payload) && (!payload || payload.error)) {
                root.startLegacyFallback(token);
            }
        }
    }

    RunCommand {
        id: richLyricsReader
        onExited: (cmd, exitCode, exitStatus, stdout, stderr) => {
            try { root.applyBackendResult(JSON.parse(stdout.trim())); } catch (error) {}
        }
    }

    RunCommand {
        id: youtubeLyricsReader
        onExited: (cmd, exitCode, exitStatus, stdout, stderr) => {
            try { root.applyBackendResult(JSON.parse(stdout.trim())); } catch (error) {}
        }
    }

    RunCommand {
        id: browserBridgeReader
        onExited: (cmd, exitCode, exitStatus, stdout, stderr) => {
            try { root.applyBackendResult(JSON.parse(stdout.trim())); } catch (error) {}
        }
    }

    // Disappear completely if song is paused OR if lyrics weren't found
    readonly property bool shouldBeVisible: root.cfgEnabled && root.isPlaying && root.lyricsList.length > 0

    // Smooth karaoke locally; querying DBus every frame is expensive and can
    // stall Plasma when a remote MPRIS player is slow.
    function resetPositionClock(positionMs, now) {
        const safePosition = Math.max(0, Number(positionMs) || 0);
        positionAnchorMs = safePosition;
        positionAnchorTime = now;
        currentTrackPositionMs = safePosition;
        lastMprisPositionMs = safePosition;
        lastUpdateTime = now;
        positionPlaybackRate = Math.max(0.1, Number(player?.rate || 1));
        positionClockInitialized = true;
        awaitingTrackPositionSample = false;
    }

    function projectPositionAt(now) {
        if (!positionClockInitialized) return 0;
        const projected = positionAnchorMs + Math.max(0, now - positionAnchorTime) * positionPlaybackRate;
        return trackDuration > 0 ? Math.min(projected, trackDuration * 1000) : projected;
    }

    function reanchorForTrack() {
        if (!cfgEnabled || !isPlaying) return;
        resetPositionClock((player?.position || 0) / 1000.0, Date.now());
        awaitingTrackPositionSample = true;
        player?.updatePosition();
    }

    function updatePositionClock(now, force) {
        const sample = Math.max(0, Number(root.player?.position || 0) / 1000.0);
        if (force || !positionClockInitialized) {
            resetPositionClock(sample, now);
            return;
        }

        const projected = projectPositionAt(now);
        if (sample !== lastMprisPositionMs) {
            const corrected = LyricsService.reconcilePositionMs(projected, sample, 45, 1200);
            positionAnchorMs = corrected;
            positionAnchorTime = now;
            currentTrackPositionMs = corrected;
            lastMprisPositionMs = sample;
            lastUpdateTime = now;
        } else {
            currentTrackPositionMs = projected;
        }
    }

    function scheduleTimelineWake() {
        timelineWakeTimer.stop();
        if (!cfgEnabled || !isPlaying || lyricsList.length === 0 || activeLineHasParts) return;

        const now = Date.now();
        const position = LyricsService.adjustedPositionMs(projectPositionAt(now), cfgTimingOffsetMs);
        const delay = LyricsService.nextTimelineDelayMs(lyricsList, activeLineIndex,
                                                        position, player?.rate || 1);
        if (delay > 0) {
            timelineWakeTimer.interval = delay;
            timelineWakeTimer.start();
        }
    }

    function refreshTimeline() {
        if (!cfgEnabled || !isPlaying || lyricsList.length === 0) {
            timelineWakeTimer.stop();
            if (lyricsList.length === 0) activeLineIndex = -1;
            return;
        }
        const now = Date.now();
        if (!positionClockInitialized) {
            resetPositionClock((player?.position || 0) / 1000.0, now);
        } else {
            updatePositionClock(now, false);
        }
        updateActiveLine();
        scheduleTimelineWake();
    }

    Timer {
        id: positionTimer
        interval: 33
        running: root.cfgEnabled && root.isPlaying && root.activeLineHasParts
        repeat: true
        onTriggered: {
            root.updatePositionClock(Date.now(), false);
            root.updateActiveLine();
        }
    }

    Timer {
        id: positionProbeTimer
        interval: 250
        running: root.cfgEnabled && root.isPlaying && root.lyricsList.length > 0
        repeat: true
        onTriggered: {
            root.player?.updatePosition();
            root.refreshTimeline();
        }
    }

    Timer {
        id: timelineWakeTimer
        interval: 1000
        onTriggered: root.refreshTimeline()
    }

    Connections {
        target: root.player
        ignoreUnknownSignals: true
        function onMetadataChanged() {
            root.reanchorForTrack();
            root.scheduleTrackUrlLookup(false);
            root.refreshTimeline();
        }
        function onPositionChanged() {
            if (!root.cfgEnabled || !root.isPlaying) return;
            if (root.awaitingTrackPositionSample) {
                root.resetPositionClock((root.player?.position || 0) / 1000.0, Date.now());
            } else if (root.lyricsList.length === 0) {
                root.updatePositionClock(Date.now(), false);
            }
            if (root.lyricsList.length > 0) root.refreshTimeline();
        }
        function onRateChanged() {
            if (!root.cfgEnabled || !root.isPlaying) return;
            const now = Date.now();
            const projected = root.projectPositionAt(now);
            root.positionAnchorMs = projected;
            root.positionAnchorTime = now;
            root.positionPlaybackRate = Math.max(0.1, Number(root.player?.rate || 1));
            root.currentTrackPositionMs = projected;
            root.player?.updatePosition();
            root.refreshTimeline();
        }
    }

    onActiveLineIndexChanged: scheduleTimelineWake()
    onActiveLineHasPartsChanged: scheduleTimelineWake()
    onLyricsListChanged: refreshTimeline()

    // Debounce timer to allow MPRIS metadata to fully settle across async DBus events
    Timer {
        id: songDebounceTimer
        interval: 300
        repeat: false
        onTriggered: {
            root.executeSongFetch();
        }
    }

    function triggerSongChange(clearExisting) {
        if (!cfgEnabled) return;
        requestGeneration += 1;
        if (clearExisting) {
            root.lyricsList = [];
            root.activeLineIndex = -1;
        }
        if (isPlaying) songDebounceTimer.restart();
        else songDebounceTimer.stop();
    }

    onTrackTitleChanged: {
        reanchorForTrack();
        scheduleColorLookup();
        scheduleTrackUrlLookup();
        triggerSongChange(true);
    }
    onTrackArtistChanged: {
        reanchorForTrack();
        scheduleColorLookup();
        scheduleTrackUrlLookup();
        triggerSongChange(true);
    }
    onTrackUrlChanged: triggerSongChange(false)
    onTrackDurationChanged: {
        reanchorForTrack();
        scheduleTrackUrlLookup(false);
        triggerSongChange(true);
    }
    onPlayerChanged: {
        reanchorForTrack();
        scheduleColorLookup();
        scheduleTrackUrlLookup();
        triggerSongChange(true);
    }
    onTrackArtUrlChanged: scheduleColorLookup()
    onCfgUseAlbumColorChanged: scheduleColorLookup()
    onCfgEnabledChanged: {
        requestGeneration += 1;
        songDebounceTimer.stop();
        lastLoadedTrackKey = "";
        isLoadingLyrics = false;
        if (cfgEnabled) {
            if (isPlaying) {
                resetPositionClock((player?.position || 0) / 1000.0, Date.now());
                scheduleTrackUrlLookup();
                scheduleColorLookup();
                triggerSongChange(true);
            }
        } else {
            trackUrlLookupGeneration += 1;
            colorLookupGeneration += 1;
            trackUrlRetryTimer.stop();
            colorRetryTimer.stop();
            lyricsList = [];
            activeLineIndex = -1;
            trackUrl = "";
            positionClockInitialized = false;
            sharedAlbumArtReady = false;
        }
    }
    onIsPlayingChanged: {
        if (!cfgEnabled) return;
        if (isPlaying) {
            resetPositionClock((player?.position || 0) / 1000.0, Date.now());
            const key = (trackTitle + "---" + trackArtist + "---"
                         + Math.round(trackDuration) + "---" + trackUrl).toLowerCase();
            if (lyricsList.length === 0 || key !== lastLoadedTrackKey) {
                triggerSongChange(true);
            } else {
                refreshTimeline();
            }
            if (!trackUrl) scheduleTrackUrlLookup();
            if (!sharedAlbumArtReady) scheduleColorLookup();
        } else {
            songDebounceTimer.stop();
            trackUrlLookupGeneration += 1;
            colorLookupGeneration += 1;
            trackUrlRetryTimer.stop();
            colorRetryTimer.stop();
            isLoadingLyrics = false;
            positionClockInitialized = false;
        }
    }

    function executeSongFetch() {
        if (!cfgEnabled || !isPlaying || !trackTitle) {
            lyricsList = [];
            lastLoadedTrackKey = "";
            isLoadingLyrics = false;
            return;
        }

        var key = (trackTitle + "---" + trackArtist + "---" + Math.round(trackDuration) + "---" + trackUrl).toLowerCase();
        if (key === lastLoadedTrackKey && lyricsList.length > 0) return;
        lastLoadedTrackKey = key;
        lastFetchedTitle = trackTitle;
        lastFetchedArtist = trackArtist;

        lyricsList = [];
        activeLineIndex = -1;
        isLoadingLyrics = true;
        backendQuality = -1;
        legacyFallbackStarted = false;
        const token = String(requestGeneration);
        // Each lookup can render while the others continue looking for a better result.
        fastLyricsReader.run(backendCommand("fast", token));
        richLyricsReader.run(backendCommand("rich", token));
        if (LyricsService.extractVideoId(trackUrl)) {
            youtubeLyricsReader.run(backendCommand("youtube", token));
            browserBridgeReader.run(backendCommand("bridge", token));
        }
    }

    function updateActiveLine() {
        if (!lyricsList || lyricsList.length === 0) {
            activeLineIndex = -1;
            return;
        }
        var pos = adjustedPositionMs;
        if (pos < lyricsList[0].startTimeMs) {
            activeLineIndex = 0;
            return;
        }
        var found = 0;

        for (var i = 0; i < lyricsList.length; i++) {
            var line = lyricsList[i];
            var start = line.startTimeMs;
            var end = start + line.durationMs;
            if (pos >= start && pos < end) {
                found = i;
                break;
            } else if (pos >= start) {
                found = i;
            }
        }
        if (found !== activeLineIndex) {
            activeLineIndex = found;
        }
    }

    function handleLineClick(timeMs) {
        if (root.player) {
            root.player.position = timeMs * 1000;
            resetPositionClock(timeMs, Date.now());
            refreshTimeline();
        }
    }

    onCfgTimingOffsetMsChanged: refreshTimeline()

    // Inner container: controls visibility & smooth fade without suspending PlasmoidItem in Corona
    Item {
        id: contentContainer
        anchors.fill: parent

        opacity: root.shouldBeVisible ? 1.0 : 0.0
        visible: opacity > 0.001

        Behavior on opacity {
            NumberAnimation { duration: 250; easing.type: Easing.InOutQuad }
        }

        Loader {
            anchors.fill: parent
            active: root.lyricsList.length > 0
            sourceComponent: root.height < 220 ? steppedViewComponent : streamViewComponent
        }
    }

    Component {
        id: steppedViewComponent
        SteppedLyricsView {
            lyricsList: root.lyricsList
            activeLineIndex: root.activeLineIndex
            playbackActive: root.isPlaying
            currentPositionMs: root.adjustedPositionMs
            activeColor: root.activeLyricColor
            inactiveColor: root.inactiveLyricColor
            fontFamily: root.cfgFontFamily
            fontSize: root.cfgFontSize
            fontBold: root.cfgFontBold
            fontItalic: root.cfgFontItalic
            enableWobble: root.cfgEnableWobble
            enableShadow: root.cfgEnableShadow
            enableRomanization: root.cfgEnableRomanization
            romanizationOpacity: root.cfgRomanizationOpacity
            romanizationPrimary: root.cfgRomanizationPrimary
            showBothScripts: root.cfgShowBothScripts
            onLineClicked: function(timeMs) { root.handleLineClick(timeMs); }
        }
    }

    Component {
        id: streamViewComponent
        LyricsStreamView {
            lyricsList: root.lyricsList
            activeLineIndex: root.activeLineIndex
            playbackActive: root.isPlaying
            currentPositionMs: root.adjustedPositionMs
            activeColor: root.activeLyricColor
            inactiveColor: root.inactiveLyricColor
            fontFamily: root.cfgFontFamily
            fontSize: root.cfgFontSize
            fontBold: root.cfgFontBold
            fontItalic: root.cfgFontItalic
            enableWobble: root.cfgEnableWobble
            enableShadow: root.cfgEnableShadow
            enableRomanization: root.cfgEnableRomanization
            romanizationOpacity: root.cfgRomanizationOpacity
            romanizationPrimary: root.cfgRomanizationPrimary
            showBothScripts: root.cfgShowBothScripts
            onLineClicked: function(timeMs) { root.handleLineClick(timeMs); }
        }
    }

    Component.onCompleted: {
        if ((Plasmoid.configuration.timingOffsetSemanticsVersion || 0) < 1) {
            // Versions through 1.1.0 added the setting to playback position,
            // so negative meant later. Preserve the actual timing while
            // adopting the extension's positive-means-later convention.
            const legacyOffset = Plasmoid.configuration.timingOffsetMs !== undefined
                               ? Plasmoid.configuration.timingOffsetMs : -150;
            Plasmoid.configuration.timingOffsetMs = -legacyOffset;
            Plasmoid.configuration.timingOffsetSemanticsVersion = 1;
        }
        if (cfgEnabled && isPlaying) {
            scheduleTrackUrlLookup();
            scheduleColorLookup();
        }
        if (cfgEnabled) triggerSongChange(true);
    }
}
