import QtQuick

Item {
    id: steppedRoot

    property var lyricsList: []
    property int activeLineIndex: -1
    property double currentPositionMs: 0

    property color activeColor: "#FFFFFF"
    property color inactiveColor: Qt.rgba(1, 1, 1, 0.35)
    property string fontFamily: "Noto Sans"
    property int fontSize: 24
    property bool fontBold: true
    property bool fontItalic: false
    property bool enableWobble: true
    property bool enableShadow: true
    property bool enableRomanization: true
    property real romanizationOpacity: 0.72
    property bool romanizationPrimary: false

    signal lineClicked(int timeMs)

    clip: true

    readonly property int displayFontSize: Math.max(8, Math.min(fontSize,
                                                Math.floor(height * (height < 65 ? 0.52 : 0.38))))
    readonly property double singleLineH: Math.round(displayFontSize * 1.35)
    readonly property double lineGap: Math.max(3, Math.round(displayFontSize * 0.22))
    readonly property bool canWrapActive: height >= singleLineH * 1.9
    readonly property bool canShowPreview: height >= singleLineH * 2.15

    function computeActiveTargetY(isWrapped, hasRomanization) {
        if (steppedRoot.height < 65) {
            return Math.max(0, Math.round((steppedRoot.height - singleLineH) / 2));
        }
        var romanizationH = hasRomanization ? Math.round(displayFontSize * 0.66) : 0;
        if (isWrapped) {
            var wrappedH = Math.round(singleLineH * 2 + lineGap + romanizationH);
            return Math.max(2, Math.round((steppedRoot.height - wrappedH) / 2));
        }
        if (hasRomanization) {
            return Math.max(2, Math.round((steppedRoot.height - singleLineH - romanizationH) / 2));
        }
        // Push active line higher when a next preview line will be displayed below it
        return Math.max(2, Math.round(steppedRoot.height * 0.08));
    }

    readonly property double nextTargetY: {
        var actY = computeActiveTargetY(false, false);
        return actY + singleLineH + lineGap;
    }

    TextMetrics {
        id: measureMetrics
        font.family: steppedRoot.fontFamily
        font.pixelSize: steppedRoot.displayFontSize
        font.bold: steppedRoot.fontBold
        font.italic: steppedRoot.fontItalic
    }

    function checkLineWillWrap(lineData) {
        if (!lineData || lineData.isInstrumental) return false;
        if (!steppedRoot.canWrapActive) return false;
        if (steppedRoot.width <= 120) return false;
        var swap = steppedRoot.enableRomanization && steppedRoot.romanizationPrimary
                && (lineData.romanization || "").trim().length > 0;
        var words = (swap ? lineData.romanization : (lineData.words || "")).trim();
        if (!words) return false;
        measureMetrics.text = words;
        var maxW = Math.max(24, steppedRoot.width - 24);
        if (measureMetrics.width <= maxW) return false;
        if (!swap && lineData.parts && lineData.parts.length >= 2) return true;
        var w = words.split(/\s+/);
        return w.length >= 2;
    }

    // 1. Outgoing line (slides up and fades out)
    LyricLineDelegate {
        id: prevDelegate
        width: steppedRoot.width
        anchors.horizontalCenter: steppedRoot.horizontalCenter
        customTransforms: true
        visible: false
        z: 0

        activeColor: steppedRoot.activeColor
        inactiveColor: steppedRoot.inactiveColor
        fontFamily: steppedRoot.fontFamily
        fontSize: steppedRoot.displayFontSize
        fontBold: steppedRoot.fontBold
        fontItalic: steppedRoot.fontItalic
        enableWobble: false
        enableShadow: steppedRoot.enableShadow
        enableRomanization: steppedRoot.enableRomanization
        romanizationOpacity: steppedRoot.romanizationOpacity
        currentPositionMs: steppedRoot.currentPositionMs
    }

    // 2. Active line (main singing lyric, syllable-synced / karaoke)
    LyricLineDelegate {
        id: activeDelegate
        width: steppedRoot.width
        anchors.horizontalCenter: steppedRoot.horizontalCenter
        customTransforms: true
        visible: false
        z: 2

        activeColor: steppedRoot.activeColor
        inactiveColor: steppedRoot.inactiveColor
        fontFamily: steppedRoot.fontFamily
        fontSize: steppedRoot.displayFontSize
        fontBold: steppedRoot.fontBold
        fontItalic: steppedRoot.fontItalic
        enableWobble: steppedRoot.enableWobble
        enableShadow: steppedRoot.enableShadow
        enableRomanization: steppedRoot.enableRomanization
        romanizationOpacity: steppedRoot.romanizationOpacity
        currentPositionMs: steppedRoot.currentPositionMs

        onLineClicked: function(timeMs) {
            steppedRoot.lineClicked(timeMs);
        }
    }

    // 3. Next line (preview: smaller, lower opacity, hidden when active line wraps)
    LyricLineDelegate {
        id: nextDelegate
        width: steppedRoot.width
        anchors.horizontalCenter: steppedRoot.horizontalCenter
        customTransforms: true
        visible: false
        z: 1

        activeColor: steppedRoot.activeColor
        inactiveColor: steppedRoot.inactiveColor
        fontFamily: steppedRoot.fontFamily
        fontSize: steppedRoot.displayFontSize
        fontBold: steppedRoot.fontBold
        fontItalic: steppedRoot.fontItalic
        enableWobble: false
        enableShadow: steppedRoot.enableShadow
        enableRomanization: steppedRoot.enableRomanization
        romanizationOpacity: steppedRoot.romanizationOpacity
        currentPositionMs: steppedRoot.currentPositionMs

        onLineClicked: function(timeMs) {
            steppedRoot.lineClicked(timeMs);
        }
    }

    // Slide-up and fade-out animation for previous active line
    ParallelAnimation {
        id: prevSlideAnim
        property double fromY: 0

        NumberAnimation {
            target: prevDelegate
            property: "y"
            from: prevSlideAnim.fromY
            to: -Math.max(40, steppedRoot.displayFontSize * 1.6)
            duration: 340
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: prevDelegate
            property: "scale"
            from: 1.0
            to: 0.70
            duration: 340
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: prevDelegate
            property: "opacity"
            from: 1.0
            to: 0.0
            duration: 280
            easing.type: Easing.InQuad
        }
        onFinished: {
            prevDelegate.visible = false;
        }
    }

    // Slide-up and expand animation for active line
    ParallelAnimation {
        id: activeSlideAnim
        property double fromY: 0
        property double toY: 0

        NumberAnimation {
            target: activeDelegate
            property: "y"
            from: activeSlideAnim.fromY
            to: activeSlideAnim.toY
            duration: 360
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: activeDelegate
            property: "scale"
            from: 0.70
            to: 1.0
            duration: 360
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: activeDelegate
            property: "opacity"
            from: 0.42
            to: 1.0
            duration: 320
            easing.type: Easing.OutCubic
        }
    }

    // Slide-up and fade-in animation for incoming next line preview
    ParallelAnimation {
        id: nextSlideAnim

        NumberAnimation {
            target: nextDelegate
            property: "y"
            from: steppedRoot.nextTargetY + 16
            to: steppedRoot.nextTargetY
            duration: 360
            easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: nextDelegate
            property: "opacity"
            from: 0.0
            to: 0.42
            duration: 320
            easing.type: Easing.OutCubic
        }
    }

    function copyLineData(target, lineData, idx, isActive) {
        if (!target) return;
        var swap = steppedRoot.enableRomanization && steppedRoot.romanizationPrimary
                && lineData && (lineData.romanization || "").trim().length > 0;
        target.lineIndex = idx;
        target.startTimeMs = lineData ? (lineData.startTimeMs || 0) : 0;
        target.durationMs = lineData ? (lineData.durationMs || 0) : 0;
        target.lineWords = lineData ? (swap ? lineData.romanization : (lineData.words || "")) : "";
        target.lineRomanization = lineData ? (swap ? (lineData.words || "")
                                                   : (lineData.romanization || "")) : "";
        target.lineParts = lineData ? (swap ? [] : (lineData.parts || [])) : [];
        target.isInstrumental = lineData ? (lineData.isInstrumental || false) : false;
        target.isUnsynced = lineData ? (lineData.isUnsynced || false) : false;
        target.isLineActive = isActive;
        target.isNextLine = !isActive;
        target.isPrevLine = false;
    }

    function syncActiveLine(newIdx, oldIdx) {
        if (!lyricsList || lyricsList.length === 0 || newIdx < 0 || newIdx >= lyricsList.length) {
            activeDelegate.visible = false;
            nextDelegate.visible = false;
            prevDelegate.visible = false;
            return;
        }

        var isAdvance = (oldIdx >= 0 && newIdx === oldIdx + 1);
        var activeData = lyricsList[newIdx];
        var willWrap = checkLineWillWrap(activeData);
        var hasRomanization = steppedRoot.enableRomanization && activeData
                && (activeData.romanization || "").trim().length > 0;
        var hasNext = (newIdx + 1 < lyricsList.length);
        var nextData = hasNext ? lyricsList[newIdx + 1] : null;

        if (isAdvance) {
            // 1. Outgoing line: slide up and fade out
            var oldData = lyricsList[oldIdx];
            // Keep the completed line lit during its short exit instead of
            // snapping it to the inactive color before the motion begins.
            copyLineData(prevDelegate, oldData, oldIdx, true);
            prevDelegate.forceSingleLine = false;
            prevDelegate.visible = true;
            prevSlideAnim.fromY = activeDelegate.y;
            prevSlideAnim.restart();

            // 2. Incoming active line: starts from next line position/scale and expands
            copyLineData(activeDelegate, activeData, newIdx, true);
            activeDelegate.forceSingleLine = !steppedRoot.canWrapActive;
            activeDelegate.visible = true;

            activeSlideAnim.fromY = nextTargetY;
            activeSlideAnim.toY = computeActiveTargetY(willWrap, hasRomanization);
            activeSlideAnim.restart();

            // 3. Next line preview: only shown if active line is NOT wrapped
            if (hasNext && !willWrap && !hasRomanization && steppedRoot.canShowPreview) {
                copyLineData(nextDelegate, nextData, newIdx + 1, false);
                nextDelegate.forceSingleLine = true;
                nextDelegate.visible = true;
                nextDelegate.scale = 0.70;
                nextSlideAnim.restart();
            } else {
                nextSlideAnim.stop();
                nextDelegate.visible = false;
                nextDelegate.opacity = 0.0;
            }
        } else {
            // Non-consecutive change (song change, seek, initial load)
            prevSlideAnim.stop();
            activeSlideAnim.stop();
            nextSlideAnim.stop();
            prevDelegate.visible = false;

            copyLineData(activeDelegate, activeData, newIdx, true);
            activeDelegate.forceSingleLine = !steppedRoot.canWrapActive;
            activeDelegate.visible = true;
            activeDelegate.scale = 1.0;
            activeDelegate.opacity = 1.0;
            activeDelegate.y = computeActiveTargetY(willWrap, hasRomanization);

            if (hasNext && !willWrap && !hasRomanization && steppedRoot.canShowPreview) {
                copyLineData(nextDelegate, nextData, newIdx + 1, false);
                nextDelegate.forceSingleLine = true;
                nextDelegate.visible = true;
                nextDelegate.scale = 0.70;
                nextDelegate.opacity = 0.42;
                nextDelegate.y = nextTargetY;
            } else {
                nextDelegate.visible = false;
                nextDelegate.opacity = 0.0;
            }
        }
    }

    property int lastActiveIndex: -1

    onActiveLineIndexChanged: {
        var old = lastActiveIndex;
        lastActiveIndex = activeLineIndex;
        syncActiveLine(activeLineIndex, old);
    }

    onLyricsListChanged: {
        lastActiveIndex = -1;
        syncActiveLine(activeLineIndex, -1);
    }

    onWidthChanged: {
        if (!activeSlideAnim.running) syncActiveLine(activeLineIndex, -1);
    }

    onHeightChanged: {
        if (!activeSlideAnim.running) syncActiveLine(activeLineIndex, -1);
    }

    Component.onCompleted: {
        syncActiveLine(activeLineIndex, -1);
    }
}
