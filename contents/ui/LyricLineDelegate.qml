import QtQuick
import "LyricLayout.js" as LyricLayout

Item {
    id: lineRoot

    property int lineIndex: 0
    property int startTimeMs: 0
    property int durationMs: 0
    property string lineWords: ""
    property string lineRomanization: ""
    property var lineParts: []
    property bool isInstrumental: false
    property bool isUnsynced: false
    property double currentPositionMs: 0
    property bool isLineActive: false
    property bool isPrevLine: false
    property bool isNextLine: false
    property bool forceSingleLine: false
    property bool previewFirstRow: false
    property bool showSecondary: true
    property real maxVisibleHeight: 0
    property bool playbackActive: true

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

    // Use a subtle edge opposite the lyric color. Unlike a one-directional
    // shadow, it remains useful when a detailed wallpaper changes brightness
    // several times across the same glyph.
    readonly property real textLuminance: 0.2126 * activeColor.r
                                               + 0.7152 * activeColor.g
                                               + 0.0722 * activeColor.b
    readonly property color edgeColor: textLuminance > 0.5
                                        ? Qt.rgba(0, 0, 0, 0.52)
                                        : Qt.rgba(1, 1, 1, 0.56)
    readonly property color farShadowColor: textLuminance > 0.5
                                             ? Qt.rgba(0, 0, 0, 0.28)
                                             : Qt.rgba(1, 1, 1, 0.30)

    signal lineClicked(int timeMs)

    readonly property bool hasParts: lineParts && lineParts.length > 0

    TextMetrics {
        id: lineMetrics
        font.family: lineRoot.fontFamily
        font.pixelSize: lineRoot.fontSize
        font.bold: lineRoot.fontBold
        font.italic: lineRoot.fontItalic
        text: lineRoot.lineWords
    }

    FontMetrics {
        id: splitMetrics
        font.family: lineRoot.fontFamily
        font.pixelSize: lineRoot.fontSize
        font.bold: lineRoot.fontBold
        font.italic: lineRoot.fontItalic
    }

    function textWidth(text) {
        // FontMetrics and TextMetrics can disagree on the window's device
        // scale. Calibrate with the complete line rendered by TextMetrics.
        var measuredFull = splitMetrics.advanceWidth(lineWords || "");
        var ratio = measuredFull > 0 ? lineMetrics.width / measuredFull : 1;
        return splitMetrics.advanceWidth(text || "") * ratio;
    }

    function partsText(parts, from, to) {
        var result = "";
        for (var i = from; i < to; i++) {
            result += parts[i] ? (parts[i].words || "") : "";
        }
        return result;
    }

    readonly property double maxAvailableWidth: Math.max(24, lineRoot.width - 24)

    readonly property var textRows: LyricLayout.textRows(lineWords, maxAvailableWidth, textWidth)
    readonly property var partRows: LyricLayout.partRows(lineParts, maxAvailableWidth, textWidth)
    readonly property var visibleTextRows: previewFirstRow ? textRows.slice(0, 1) : textRows
    readonly property var visiblePartRows: previewFirstRow ? partRows.slice(0, 1) : partRows

    readonly property bool shouldWrap: {
        if (forceSingleLine || isInstrumental) return false;
        return hasParts ? partRows.length > 1 : textRows.length > 1;
    }

    readonly property bool isWrapped: shouldWrap

    readonly property double widestRenderedLine: {
        if (!shouldWrap) return lineMetrics.width;
        var widest = 0;
        if (hasParts) {
            for (var i = 0; i < visiblePartRows.length; i++)
                widest = Math.max(widest, textWidth(partsText(visiblePartRows[i], 0, visiblePartRows[i].length)));
        } else {
            for (var j = 0; j < visibleTextRows.length; j++)
                widest = Math.max(widest, textWidth(visibleTextRows[j]));
        }
        return widest;
    }
    readonly property int renderedFontSize: {
        if (widestRenderedLine <= maxAvailableWidth || widestRenderedLine <= 0) return fontSize;
        return Math.max(6, Math.floor(fontSize * maxAvailableWidth / widestRenderedLine));
    }
    readonly property bool requiresElide: widestRenderedLine * renderedFontSize
                                           / Math.max(1, fontSize) > maxAvailableWidth

    property bool customTransforms: false

    scale: customTransforms ? 1.0 : (isLineActive ? 1.04 : (isNextLine ? 0.95 : (isPrevLine ? 0.92 : 0.88)))
    opacity: {
        if (customTransforms) return 1.0;
        if (isLineActive) return 1.0;
        if (isNextLine) return isUnsynced ? 0.65 : 0.45;
        if (isPrevLine) return isUnsynced ? 0.50 : 0.28;
        return 0.15;
    }

    Behavior on scale {
        enabled: !lineRoot.customTransforms
        NumberAnimation { duration: 320; easing.type: Easing.OutCubic }
    }
    Behavior on opacity {
        enabled: !lineRoot.customTransforms
        NumberAnimation { duration: 320; easing.type: Easing.OutCubic }
    }

    implicitWidth: contentLoader.implicitWidth
    readonly property real contentHeight: contentLoader.height
    readonly property bool showRomanization: showSecondary && enableRomanization && !isInstrumental
                                                && lineRomanization.trim().length > 0
                                                && lineRomanization.trim().toLowerCase()
                                                   !== lineWords.trim().toLowerCase()
    implicitHeight: contentLoader.implicitHeight
                    + (showRomanization ? romanizationLabel.implicitHeight
                       + Math.max(1, renderedFontSize * 0.08) : renderedFontSize * 0.15)
    height: maxVisibleHeight > 0 ? Math.min(implicitHeight, maxVisibleHeight) : implicitHeight
    clip: maxVisibleHeight > 0 && implicitHeight > height
    readonly property real scrollOverflow: Math.max(0, implicitHeight - height)
    readonly property real timeProgress: durationMs > 0
        ? Math.max(0, Math.min(1, (currentPositionMs - startTimeMs) / durationMs)) : 0

    transformOrigin: Item.Center

    Item {
        id: contentLoader
        width: parent.width
        anchors.horizontalCenter: parent.horizontalCenter
        height: {
            if (lineRoot.isInstrumental) return instItem.implicitHeight;
            if (lineRoot.hasParts) {
                return lineRoot.shouldWrap ? syllablesWrappedColumn.implicitHeight : flowItem.implicitHeight;
            }
            return lineRoot.shouldWrap ? plainTextWrappedColumn.implicitHeight : singleTextContainer.implicitHeight;
        }
        implicitHeight: height
        y: lineRoot.scrollOverflow > 0 && lineRoot.isLineActive
           ? -lineRoot.scrollOverflow * lineRoot.timeProgress : 0

        // 1. Instrumental break
        InstrumentalIndicator {
            id: instItem
            visible: lineRoot.isInstrumental
            anchors.centerIn: parent
            startTimeMs: lineRoot.startTimeMs
            durationMs: lineRoot.durationMs
            currentPositionMs: lineRoot.currentPositionMs
            isLineActive: lineRoot.isLineActive
            playbackActive: lineRoot.playbackActive
            activeColor: lineRoot.activeColor
            inactiveColor: lineRoot.inactiveColor
            fontSize: lineRoot.renderedFontSize
            enableShadow: lineRoot.enableShadow
        }

        // 2. Syllable/word-synced flow: Single Row (strictly horizontally centered)
        Item {
            id: flowItem
            visible: !lineRoot.isInstrumental && lineRoot.hasParts && !lineRoot.shouldWrap
            width: parent.width
            height: singleWordsRow.implicitHeight
            implicitHeight: singleWordsRow.implicitHeight

            Row {
                id: singleWordsRow
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 0
                scale: Math.min(1.0, lineRoot.maxAvailableWidth / Math.max(1, implicitWidth))
                transformOrigin: Item.Center

                Repeater {
                    model: lineRoot.lineParts
                    delegate: WordDelegate {
                        wordText: modelData ? (modelData.words || "") : ""
                        startTimeMs: modelData ? (modelData.startTimeMs || 0) : 0
                        durationMs: modelData ? (modelData.durationMs || 0) : 0
                        currentPositionMs: lineRoot.currentPositionMs
                        isLineActive: lineRoot.isLineActive
                        activeColor: lineRoot.activeColor
                        inactiveColor: lineRoot.inactiveColor
                        fontFamily: lineRoot.fontFamily
                        fontSize: lineRoot.renderedFontSize
                        fontBold: lineRoot.fontBold
                        fontItalic: lineRoot.fontItalic
                        enableWobble: lineRoot.enableWobble
                        enableShadow: lineRoot.enableShadow
                    }
                }
            }
        }

        // 3. Syllable/word-synced flow: as many timed rows as the width needs.
        Column {
            id: syllablesWrappedColumn
            visible: !lineRoot.isInstrumental && lineRoot.hasParts && lineRoot.shouldWrap
            width: parent.width
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Math.round(lineRoot.renderedFontSize * 0.15)

            Repeater {
                model: lineRoot.visiblePartRows
                delegate: Item {
                    required property var modelData
                    width: syllablesWrappedColumn.width
                    height: wordsRow.implicitHeight
                    Row {
                        id: wordsRow
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 0
                        scale: Math.min(1.0, lineRoot.maxAvailableWidth / Math.max(1, implicitWidth))
                        transformOrigin: Item.Center
                        Repeater {
                            model: modelData
                            delegate: WordDelegate {
                                wordText: modelData ? (modelData.words || "") : ""
                                startTimeMs: modelData ? (modelData.startTimeMs || 0) : 0
                                durationMs: modelData ? (modelData.durationMs || 0) : 0
                                currentPositionMs: lineRoot.currentPositionMs
                                isLineActive: lineRoot.isLineActive
                                activeColor: lineRoot.activeColor
                                inactiveColor: lineRoot.inactiveColor
                                fontFamily: lineRoot.fontFamily
                                fontSize: lineRoot.renderedFontSize
                                fontBold: lineRoot.fontBold
                                fontItalic: lineRoot.fontItalic
                                enableWobble: lineRoot.enableWobble
                                enableShadow: lineRoot.enableShadow
                            }
                        }
                    }
                }
            }
        }

        // 4. Line-synced standard text: Single Row (with soft vertical drop shadows)
        Item {
            id: singleTextContainer
            visible: !lineRoot.isInstrumental && !lineRoot.hasParts && !lineRoot.shouldWrap
            width: parent.width
            height: singleText.implicitHeight
            implicitHeight: singleText.implicitHeight

            // Ambient / soft shadow layer 1
            Text {
                width: parent.width
                text: lineRoot.lineWords
                elide: lineRoot.forceSingleLine || lineRoot.requiresElide ? Text.ElideRight : Text.ElideNone
                horizontalAlignment: Text.AlignHCenter

                font.family: lineRoot.fontFamily
                font.pixelSize: lineRoot.renderedFontSize
                font.bold: lineRoot.fontBold
                font.italic: lineRoot.fontItalic
                style: Text.Normal

                color: lineRoot.edgeColor
                y: 1.5
                x: 0
                visible: lineRoot.enableShadow
                z: 0
            }

            // Ambient / soft shadow layer 2
            Text {
                width: parent.width
                text: lineRoot.lineWords
                elide: lineRoot.forceSingleLine || lineRoot.requiresElide ? Text.ElideRight : Text.ElideNone
                horizontalAlignment: Text.AlignHCenter

                font.family: lineRoot.fontFamily
                font.pixelSize: lineRoot.renderedFontSize
                font.bold: lineRoot.fontBold
                font.italic: lineRoot.fontItalic
                style: Text.Normal

                color: lineRoot.farShadowColor
                y: 2.8
                x: 0
                visible: lineRoot.enableShadow
                z: -1
            }

            // Foreground Text
            Text {
                id: singleText
                width: parent.width
                z: 1
                text: lineRoot.lineWords
                elide: lineRoot.forceSingleLine || lineRoot.requiresElide ? Text.ElideRight : Text.ElideNone
                horizontalAlignment: Text.AlignHCenter

                font.family: lineRoot.fontFamily
                font.pixelSize: lineRoot.renderedFontSize
                font.bold: lineRoot.fontBold
                font.italic: lineRoot.fontItalic

                style: lineRoot.enableShadow ? Text.Outline : Text.Normal
                styleColor: lineRoot.edgeColor
                color: lineRoot.isLineActive ? lineRoot.activeColor : lineRoot.inactiveColor

                Behavior on color {
                    ColorAnimation { duration: 200 }
                }
            }
        }

        // 5. Line-synced text: each rendered row stays centered.
        Column {
            id: plainTextWrappedColumn
            visible: !lineRoot.isInstrumental && !lineRoot.hasParts && lineRoot.shouldWrap
            width: parent.width
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Math.round(lineRoot.renderedFontSize * 0.15)

            Repeater {
                model: lineRoot.visibleTextRows
                delegate: Item {
                    required property string modelData
                    width: plainTextWrappedColumn.width
                    height: foreground.implicitHeight
                    Text {
                        width: parent.width
                        text: modelData
                        elide: lineRoot.requiresElide ? Text.ElideRight : Text.ElideNone
                        horizontalAlignment: Text.AlignHCenter
                        font.family: lineRoot.fontFamily
                        font.pixelSize: lineRoot.renderedFontSize
                        font.bold: lineRoot.fontBold
                        font.italic: lineRoot.fontItalic
                        color: lineRoot.edgeColor
                        y: 1.5
                        visible: lineRoot.enableShadow
                    }
                    Text {
                        width: parent.width
                        text: modelData
                        elide: lineRoot.requiresElide ? Text.ElideRight : Text.ElideNone
                        horizontalAlignment: Text.AlignHCenter
                        font.family: lineRoot.fontFamily
                        font.pixelSize: lineRoot.renderedFontSize
                        font.bold: lineRoot.fontBold
                        font.italic: lineRoot.fontItalic
                        color: lineRoot.farShadowColor
                        y: 2.8
                        visible: lineRoot.enableShadow
                    }
                    Text {
                        id: foreground
                        width: parent.width
                        text: modelData
                        elide: lineRoot.requiresElide ? Text.ElideRight : Text.ElideNone
                        horizontalAlignment: Text.AlignHCenter
                        font.family: lineRoot.fontFamily
                        font.pixelSize: lineRoot.renderedFontSize
                        font.bold: lineRoot.fontBold
                        font.italic: lineRoot.fontItalic
                        style: lineRoot.enableShadow ? Text.Outline : Text.Normal
                        styleColor: lineRoot.edgeColor
                        color: lineRoot.isLineActive ? lineRoot.activeColor : lineRoot.inactiveColor
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }
                }
            }
        }
    }

    Text {
        id: romanizationLabel
        visible: lineRoot.showRomanization
        anchors.top: contentLoader.bottom
        anchors.topMargin: Math.max(1, lineRoot.renderedFontSize * 0.08)
        width: parent.width
        text: lineRoot.lineRomanization
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        font.family: lineRoot.fontFamily
        font.pixelSize: Math.max(7, Math.round(lineRoot.renderedFontSize * 0.52))
        font.weight: Font.Medium
        font.italic: lineRoot.fontItalic
        color: lineRoot.isLineActive ? lineRoot.activeColor : lineRoot.inactiveColor
        opacity: lineRoot.romanizationOpacity
        style: lineRoot.enableShadow ? Text.Outline : Text.Normal
        styleColor: lineRoot.edgeColor

        Behavior on opacity { NumberAnimation { duration: 180 } }
        Behavior on color { ColorAnimation { duration: 200 } }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            lineRoot.lineClicked(lineRoot.startTimeMs);
        }
    }
}
