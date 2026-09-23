import QtQuick

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
        return splitMetrics.advanceWidth(text || "");
    }

    function partsText(parts, from, to) {
        var result = "";
        for (var i = from; i < to; i++) {
            result += parts[i] ? (parts[i].words || "") : "";
        }
        return result;
    }

    readonly property double maxAvailableWidth: Math.max(24, lineRoot.width - 24)

    // Wrap into 2 balanced lines when text exceeds available widget width
    readonly property bool shouldWrap: {
        if (forceSingleLine || isInstrumental) return false;
        if (lineRoot.width <= 120) return false;
        if (lineMetrics.width <= maxAvailableWidth) return false;
        if (hasParts) {
            return lineParts.length >= 2;
        }
        var w = lineWords.trim().split(/\s+/);
        return w.length >= 2;
    }

    readonly property bool isWrapped: shouldWrap

    // Split by rendered width. Character counts are badly wrong for mixed
    // scripts, punctuation, bold fonts, and narrow/wide Latin glyphs.
    readonly property var balancedText: {
        if (!shouldWrap || hasParts) {
            return { line1: lineWords, line2: "" };
        }
        var words = lineWords.trim().split(/\s+/);
        if (words.length <= 1) {
            return { line1: lineWords, line2: "" };
        }
        var bestK = 1;
        var bestScore = Number.POSITIVE_INFINITY;
        for (var k = 1; k < words.length; k++) {
            var first = words.slice(0, k).join(" ");
            var second = words.slice(k).join(" ");
            var firstWidth = textWidth(first);
            var secondWidth = textWidth(second);
            var overflow = Math.max(0, firstWidth - maxAvailableWidth)
                         + Math.max(0, secondWidth - maxAvailableWidth);
            var score = overflow * 8 + Math.max(firstWidth, secondWidth)
                      + Math.abs(firstWidth - secondWidth) * 0.35;
            if (score < bestScore) {
                bestScore = score;
                bestK = k;
            }
        }
        return {
            line1: words.slice(0, bestK).join(" "),
            line2: words.slice(bestK).join(" ")
        };
    }

    // Balanced 2-line syllable split for karaoke
    readonly property var balancedParts: {
        if (!shouldWrap || !hasParts) {
            return { parts1: lineParts || [], parts2: [] };
        }
        var bestK = 1;
        var bestScore = Number.POSITIVE_INFINITY;
        for (var k = 1; k < lineParts.length; k++) {
            var firstWidth = textWidth(partsText(lineParts, 0, k));
            var secondWidth = textWidth(partsText(lineParts, k, lineParts.length));
            var overflow = Math.max(0, firstWidth - maxAvailableWidth)
                         + Math.max(0, secondWidth - maxAvailableWidth);
            var score = overflow * 8 + Math.max(firstWidth, secondWidth)
                      + Math.abs(firstWidth - secondWidth) * 0.35;
            if (score < bestScore) {
                bestScore = score;
                bestK = k;
            }
        }
        return {
            parts1: lineParts.slice(0, bestK),
            parts2: lineParts.slice(bestK)
        };
    }

    readonly property double widestRenderedLine: {
        if (!shouldWrap) return lineMetrics.width;
        if (hasParts) {
            return Math.max(textWidth(partsText(balancedParts.parts1, 0, balancedParts.parts1.length)),
                            textWidth(partsText(balancedParts.parts2, 0, balancedParts.parts2.length)));
        }
        return Math.max(textWidth(balancedText.line1), textWidth(balancedText.line2));
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
    readonly property bool showRomanization: enableRomanization && !isInstrumental
                                                && lineRomanization.trim().length > 0
                                                && lineRomanization.trim().toLowerCase()
                                                   !== lineWords.trim().toLowerCase()
    implicitHeight: contentLoader.implicitHeight
                    + (showRomanization ? romanizationLabel.implicitHeight
                       + Math.max(1, renderedFontSize * 0.08) : renderedFontSize * 0.15)
    height: implicitHeight

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

        // 3. Syllable/word-synced flow: Balanced 2 Rows (both strictly horizontally centered)
        Column {
            id: syllablesWrappedColumn
            visible: !lineRoot.isInstrumental && lineRoot.hasParts && lineRoot.shouldWrap
            width: parent.width
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Math.round(lineRoot.renderedFontSize * 0.15)

            Item {
                id: row1PartsItem
                width: parent.width
                height: row1.implicitHeight
                implicitHeight: row1.implicitHeight

                Row {
                    id: row1
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 0
                    scale: Math.min(1.0, lineRoot.maxAvailableWidth / Math.max(1, implicitWidth))
                    transformOrigin: Item.Center

                    Repeater {
                        model: lineRoot.balancedParts.parts1
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

            Item {
                id: row2PartsItem
                width: parent.width
                height: row2.implicitHeight
                implicitHeight: row2.implicitHeight

                Row {
                    id: row2
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 0
                    scale: Math.min(1.0, lineRoot.maxAvailableWidth / Math.max(1, implicitWidth))
                    transformOrigin: Item.Center

                    Repeater {
                        model: lineRoot.balancedParts.parts2
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

        // 5. Line-synced standard text: Balanced 2 Rows (both strictly horizontally centered)
        Column {
            id: plainTextWrappedColumn
            visible: !lineRoot.isInstrumental && !lineRoot.hasParts && lineRoot.shouldWrap
            width: parent.width
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: Math.round(lineRoot.renderedFontSize * 0.15)

            Item {
                id: row1TextItem
                width: parent.width
                height: textRow1.implicitHeight
                implicitHeight: textRow1.implicitHeight

                Text {
                    width: parent.width
                    text: lineRoot.balancedText.line1
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
                    text: lineRoot.balancedText.line1
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
                    id: textRow1
                    width: parent.width
                    text: lineRoot.balancedText.line1
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

            Item {
                id: row2TextItem
                width: parent.width
                height: textRow2.implicitHeight
                implicitHeight: textRow2.implicitHeight

                Text {
                    width: parent.width
                    text: lineRoot.balancedText.line2
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
                    text: lineRoot.balancedText.line2
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
                    id: textRow2
                    width: parent.width
                    text: lineRoot.balancedText.line2
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

    Text {
        id: romanizationLabel
        visible: lineRoot.showRomanization
        anchors.top: contentLoader.bottom
        anchors.topMargin: Math.max(1, lineRoot.renderedFontSize * 0.08)
        width: parent.width
        text: lineRoot.lineRomanization
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        maximumLineCount: 1
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
