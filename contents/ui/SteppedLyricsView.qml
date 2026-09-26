import QtQuick

Item {
    id: steppedRoot

    property var lyricsList: []
    property int activeLineIndex: -1
    property bool playbackActive: true
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
    property bool showBothScripts: true

    signal lineClicked(int timeMs)

    clip: true

    readonly property int displayFontSize: Math.max(8, Math.min(fontSize,
                                                Math.floor(height * (height < 65 ? 0.52 : 0.38))))
    readonly property double singleLineH: Math.round(displayFontSize * 1.35)
    readonly property double lineGap: Math.max(3, Math.round(displayFontSize * 0.22))
    property double nextTargetY: 0
    property bool pendingResizeLayout: false

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
        playbackActive: steppedRoot.playbackActive
        enableShadow: steppedRoot.enableShadow
        enableRomanization: steppedRoot.enableRomanization
        romanizationOpacity: steppedRoot.romanizationOpacity
        showSecondary: steppedRoot.showBothScripts
        currentPositionMs: 0
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
        playbackActive: steppedRoot.playbackActive
        enableShadow: steppedRoot.enableShadow
        enableRomanization: steppedRoot.enableRomanization
        romanizationOpacity: steppedRoot.romanizationOpacity
        showSecondary: steppedRoot.showBothScripts
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
        playbackActive: steppedRoot.playbackActive
        enableShadow: steppedRoot.enableShadow
        enableRomanization: steppedRoot.enableRomanization
        romanizationOpacity: steppedRoot.romanizationOpacity
        showSecondary: steppedRoot.showBothScripts
        currentPositionMs: 0

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
        onFinished: {
            if (steppedRoot.pendingResizeLayout) {
                steppedRoot.pendingResizeLayout = false;
                steppedRoot.syncActiveLine(steppedRoot.activeLineIndex, -1);
            }
        }

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
        if (!lyricsList || newIdx < 0 || newIdx >= lyricsList.length) {
            layoutGeneration++;
            prevSlideAnim.stop();
            activeSlideAnim.stop();
            nextSlideAnim.stop();
            activeDelegate.visible = false;
            nextDelegate.visible = false;
            prevDelegate.visible = false;
            return;
        }

        var advance = oldIdx >= 0 && newIdx === oldIdx + 1;
        var incomingY = nextDelegate.visible ? nextDelegate.y : steppedRoot.height;
        var outgoingY = activeDelegate.y;
        if (advance) {
            copyLineData(prevDelegate, lyricsList[oldIdx], oldIdx, true);
            prevDelegate.showSecondary = activeDelegate.showSecondary;
            prevDelegate.forceSingleLine = false;
            prevDelegate.previewFirstRow = false;
            prevDelegate.maxVisibleHeight = steppedRoot.height;
            prevDelegate.currentPositionMs = (lyricsList[oldIdx].startTimeMs || 0)
                                            + (lyricsList[oldIdx].durationMs || 0);
            prevDelegate.visible = true;
            prevSlideAnim.fromY = outgoingY;
            prevSlideAnim.restart();
        } else {
            prevSlideAnim.stop();
            activeSlideAnim.stop();
            nextSlideAnim.stop();
            prevDelegate.visible = false;
        }

        copyLineData(activeDelegate, lyricsList[newIdx], newIdx, true);
        activeDelegate.forceSingleLine = steppedRoot.height < steppedRoot.singleLineH * 1.25;
        activeDelegate.previewFirstRow = false;
        activeDelegate.showSecondary = steppedRoot.showBothScripts;
        activeDelegate.maxVisibleHeight = Math.max(1, steppedRoot.height - 4);
        activeDelegate.visible = true;

        var hasNext = newIdx + 1 < lyricsList.length;
        nextDelegate.visible = false;
        if (hasNext) {
            copyLineData(nextDelegate, lyricsList[newIdx + 1], newIdx + 1, false);
            nextDelegate.forceSingleLine = false;
            nextDelegate.previewFirstRow = false;
            nextDelegate.showSecondary = steppedRoot.showBothScripts;
            nextDelegate.maxVisibleHeight = 0;
        }

        // Repeater rows are built during the next event-loop pass. Make the
        // fit choice only after their implicit heights have settled.
        var generation = ++layoutGeneration;
        Qt.callLater(function() {
            if (generation !== layoutGeneration) return;
            var activePrimaryHeight = activeDelegate.contentHeight
                                    + activeDelegate.renderedFontSize * 0.15;
            if (activeDelegate.showRomanization
                    && activeDelegate.implicitHeight > activeDelegate.maxVisibleHeight
                    && activePrimaryHeight <= activeDelegate.maxVisibleHeight)
                activeDelegate.showSecondary = false;

            if (hasNext) {
                var available = steppedRoot.height - activeDelegate.height - steppedRoot.lineGap - 4;
                var nextPrimaryHeight = nextDelegate.contentHeight
                                      + nextDelegate.renderedFontSize * 0.15;
                if (nextDelegate.showRomanization && nextDelegate.implicitHeight > available)
                    nextDelegate.showSecondary = false;
                if (nextPrimaryHeight > available) nextDelegate.previewFirstRow = true;
            }
            Qt.callLater(function() {
                if (generation !== layoutGeneration) return;
                var available = steppedRoot.height - activeDelegate.height - steppedRoot.lineGap - 4;
                var previewFits = hasNext && available >= nextDelegate.implicitHeight
                                  && available >= steppedRoot.singleLineH * 0.65;
                var combinedHeight = activeDelegate.height
                                   + (previewFits ? steppedRoot.lineGap + nextDelegate.height : 0);
                var activeY = Math.max(2, Math.round((steppedRoot.height - combinedHeight) / 2));
                nextTargetY = activeY + activeDelegate.height + steppedRoot.lineGap;
                if (advance) {
                    activeSlideAnim.fromY = incomingY;
                    activeSlideAnim.toY = activeY;
                    activeSlideAnim.restart();
                } else {
                    activeDelegate.scale = 1.0;
                    activeDelegate.opacity = 1.0;
                    activeDelegate.y = activeY;
                }
                if (previewFits) {
                    nextDelegate.visible = true;
                    nextDelegate.scale = 0.70;
                    if (advance) nextSlideAnim.restart();
                    else {
                        nextDelegate.opacity = 0.42;
                        nextDelegate.y = nextTargetY;
                    }
                } else {
                    nextSlideAnim.stop();
                    nextDelegate.visible = false;
                    nextDelegate.opacity = 0;
                }
            });
        });
    }

    property int layoutGeneration: 0
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
        if (activeSlideAnim.running) pendingResizeLayout = true;
        else syncActiveLine(activeLineIndex, -1);
    }

    onHeightChanged: {
        if (activeSlideAnim.running) pendingResizeLayout = true;
        else syncActiveLine(activeLineIndex, -1);
    }

    onShowBothScriptsChanged: syncActiveLine(activeLineIndex, -1)
    onRomanizationPrimaryChanged: syncActiveLine(activeLineIndex, -1)
    onEnableRomanizationChanged: syncActiveLine(activeLineIndex, -1)
    onDisplayFontSizeChanged: syncActiveLine(activeLineIndex, -1)
    onFontFamilyChanged: syncActiveLine(activeLineIndex, -1)
    onFontBoldChanged: syncActiveLine(activeLineIndex, -1)
    onFontItalicChanged: syncActiveLine(activeLineIndex, -1)

    Component.onCompleted: {
        syncActiveLine(activeLineIndex, -1);
    }
}
