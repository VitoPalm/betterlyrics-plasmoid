import QtQuick

Item {
    id: streamRoot

    property var lyricsList: []
    property int activeLineIndex: -1
    property bool playbackActive: true
    property double currentPositionMs: 0
    property bool allowManualScroll: false
    property bool manualBrowsing: false

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

    readonly property double targetScrollRatio: 0.37

    Flickable {
        id: flickable
        anchors.fill: parent
        contentWidth: width
        contentHeight: linesColumn.implicitHeight
        interactive: streamRoot.allowManualScroll
        clip: true
        onMovementStarted: {
            if (streamRoot.allowManualScroll) {
                streamRoot.manualBrowsing = true;
                scrollAnim.stop();
            }
        }

        NumberAnimation {
            id: scrollAnim
            target: flickable
            property: "contentY"
            duration: 650
            easing.type: Easing.OutCubic
        }

        Column {
            id: linesColumn
            width: flickable.width
            spacing: streamRoot.fontSize * 0.85

            // Top spacer so first line centers at targetScrollRatio
            Item {
                width: parent.width
                height: flickable.height * streamRoot.targetScrollRatio
            }

            Repeater {
                id: repeater
                model: streamRoot.lyricsList

                delegate: LyricLineDelegate {
                    width: linesColumn.width
                    lineIndex: index
                    startTimeMs: modelData ? (modelData.startTimeMs || 0) : 0
                    durationMs: modelData ? (modelData.durationMs || 0) : 0
                    readonly property bool swapRomanization: streamRoot.enableRomanization
                                                                && streamRoot.romanizationPrimary
                                                                && modelData
                                                                && (modelData.romanization || "").trim().length > 0
                    lineWords: modelData ? (swapRomanization
                               ? modelData.romanization : (modelData.words || "")) : ""
                    lineRomanization: modelData ? (swapRomanization
                                      ? (modelData.words || "") : (modelData.romanization || "")) : ""
                    // Provider word timings describe the original script and
                    // cannot safely be applied to transliterated word breaks.
                    lineParts: modelData ? (swapRomanization ? [] : (modelData.parts || [])) : []
                    isInstrumental: modelData ? (modelData.isInstrumental || false) : false
                    isUnsynced: modelData ? (modelData.isUnsynced || false) : false
                    // Inactive lines never fill words, so leave them out of
                    // the high-frequency position binding.
                    currentPositionMs: isLineActive ? streamRoot.currentPositionMs : 0

                    isLineActive: index === streamRoot.activeLineIndex
                    isPrevLine: index === (streamRoot.activeLineIndex - 1)
                    isNextLine: index === (streamRoot.activeLineIndex + 1)

                    activeColor: streamRoot.activeColor
                    inactiveColor: streamRoot.inactiveColor
                    fontFamily: streamRoot.fontFamily
                    fontSize: streamRoot.fontSize
                    fontBold: streamRoot.fontBold
                    fontItalic: streamRoot.fontItalic
                    enableWobble: streamRoot.enableWobble
                    playbackActive: streamRoot.playbackActive
                    enableShadow: streamRoot.enableShadow
                    enableRomanization: streamRoot.enableRomanization
                    romanizationOpacity: streamRoot.romanizationOpacity
                    showSecondary: streamRoot.showBothScripts

                    onLineClicked: function(timeMs) { streamRoot.lineClicked(timeMs); }
                }
            }

            // Bottom spacer so last line can scroll to targetScrollRatio
            Item {
                width: parent.width
                height: flickable.height * (1.0 - streamRoot.targetScrollRatio)
            }
        }
    }

    onActiveLineIndexChanged: {
        scrollToActiveLine();
    }

    onCurrentPositionMsChanged: {
        if (manualBrowsing) return;
        if (activeLineIndex < 0 || activeLineIndex >= repeater.count) return;
        var item = repeater.itemAt(activeLineIndex);
        if (!item || item.height <= flickable.height) return;
        // Let a lyric taller than the viewport travel from its first row to
        // its last during its own timing window.
        scrollAnim.stop();
        var progress = item.durationMs > 0
            ? Math.max(0, Math.min(1, (currentPositionMs - item.startTimeMs) / item.durationMs)) : 0;
        var target = item.y + (item.height - flickable.height) * progress;
        flickable.contentY = Math.max(0, Math.min(target, flickable.contentHeight - flickable.height));
    }

    function scrollToActiveLine() {
        if (manualBrowsing) return;
        if (activeLineIndex < 0 || activeLineIndex >= repeater.count) return;
        var item = repeater.itemAt(activeLineIndex);
        if (!item) return;

        var itemCenterY = item.y + item.height / 2;
        var targetY = item.height > flickable.height ? item.y
                    : itemCenterY - (flickable.height * streamRoot.targetScrollRatio);
        var maxY = Math.max(0, flickable.contentHeight - flickable.height);
        var boundedY = Math.max(0, Math.min(targetY, maxY));

        scrollAnim.to = boundedY;
        scrollAnim.restart();
    }

    onHeightChanged: {
        Qt.callLater(scrollToActiveLine);
    }

    onWidthChanged: Qt.callLater(scrollToActiveLine)
    onLyricsListChanged: Qt.callLater(scrollToActiveLine)
    onManualBrowsingChanged: {
        if (!manualBrowsing) Qt.callLater(scrollToActiveLine);
    }
    onFontSizeChanged: Qt.callLater(scrollToActiveLine)
    onFontFamilyChanged: Qt.callLater(scrollToActiveLine)
    onFontBoldChanged: Qt.callLater(scrollToActiveLine)
    onFontItalicChanged: Qt.callLater(scrollToActiveLine)
    onShowBothScriptsChanged: Qt.callLater(scrollToActiveLine)
    onRomanizationPrimaryChanged: Qt.callLater(scrollToActiveLine)
    onEnableRomanizationChanged: Qt.callLater(scrollToActiveLine)

    Component.onCompleted: Qt.callLater(scrollToActiveLine)
}
