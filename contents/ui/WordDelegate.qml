import QtQuick

Item {
    id: wordRoot

    property string wordText: ""
    property int startTimeMs: 0
    property int durationMs: 0
    property double currentPositionMs: 0
    property bool isLineActive: false

    property color activeColor: "#FFFFFF"
    property color inactiveColor: Qt.rgba(1, 1, 1, 0.35)
    property string fontFamily: "Noto Sans"
    property int fontSize: 24
    property bool fontBold: true
    property bool fontItalic: false
    property bool enableWobble: true
    property bool enableShadow: true

    // A faint, opposite-luminance edge keeps glyphs separated from both light
    // and dark details in a wallpaper. The existing shadow still supplies the
    // depth; this only closes its uncovered top and side edges.
    readonly property real textLuminance: 0.2126 * activeColor.r
                                               + 0.7152 * activeColor.g
                                               + 0.0722 * activeColor.b
    readonly property color edgeColor: textLuminance > 0.5
                                        ? Qt.rgba(0, 0, 0, 0.52)
                                        : Qt.rgba(1, 1, 1, 0.56)
    readonly property color farShadowColor: textLuminance > 0.5
                                             ? Qt.rgba(0, 0, 0, 0.28)
                                             : Qt.rgba(1, 1, 1, 0.30)

    readonly property bool isWordActive: isLineActive && durationMs > 0
                                         && currentPositionMs >= startTimeMs
                                         && currentPositionMs < startTimeMs + durationMs
    readonly property double wordProgress: {
        if (!isLineActive || currentPositionMs < startTimeMs) return 0.0;
        if (durationMs <= 0 || currentPositionMs >= startTimeMs + durationMs) return 1.0;
        return Math.max(0.0, Math.min(1.0,
                    (currentPositionMs - startTimeMs) / durationMs));
    }

    implicitWidth: content.implicitWidth
    implicitHeight: content.implicitHeight + 3

    Item {
        id: content
        width: baseLabel.implicitWidth
        height: baseLabel.implicitHeight
        implicitWidth: width
        implicitHeight: height
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter

        property double bounceScale: 1.0
        property double bounceY: 0.0

        transform: [
            Scale {
                origin.x: content.width / 2
                origin.y: content.height / 2
                xScale: content.bounceScale
                yScale: content.bounceScale
            },
            Translate { y: content.bounceY }
        ]

        // The shadows move with the glyph, rather than lagging behind its
        // animation as they did when only the foreground Text was transformed.
        Text {
            x: baseLabel.x
            y: baseLabel.y + 1.5
            visible: wordRoot.enableShadow
            text: baseLabel.text
            font: baseLabel.font
            color: wordRoot.edgeColor
            opacity: baseLabel.opacity
        }

        Text {
            x: baseLabel.x
            y: baseLabel.y + 2.8
            visible: wordRoot.enableShadow
            text: baseLabel.text
            font: baseLabel.font
            color: wordRoot.farShadowColor
            opacity: baseLabel.opacity
        }

        Text {
            id: baseLabel
            text: wordRoot.wordText
            font.family: wordRoot.fontFamily
            font.pixelSize: wordRoot.fontSize
            font.bold: wordRoot.fontBold
            font.italic: wordRoot.fontItalic
            color: wordRoot.inactiveColor
            style: wordRoot.enableShadow ? Text.Outline : Text.Normal
            styleColor: wordRoot.edgeColor
            opacity: wordRoot.isLineActive ? 0.55 : 1.0
            Behavior on opacity { NumberAnimation { duration: 140 } }
        }

        Item {
            id: highlightClip
            x: 0
            y: 0
            width: baseLabel.width * wordRoot.wordProgress
            height: baseLabel.height
            clip: true

            Text {
                width: baseLabel.width
                height: baseLabel.height
                text: baseLabel.text
                font: baseLabel.font
                color: wordRoot.activeColor
                style: wordRoot.enableShadow ? Text.Outline : Text.Normal
                styleColor: wordRoot.edgeColor
                Behavior on color { ColorAnimation { duration: 180 } }
            }
        }

        SequentialAnimation {
            id: wobbleAnim
            running: false

            ParallelAnimation {
                NumberAnimation {
                    target: content
                    property: "bounceScale"
                    to: 1.055
                    duration: 105
                    easing.type: Easing.OutQuad
                }
                NumberAnimation {
                    target: content
                    property: "bounceY"
                    to: -2.2
                    duration: 105
                    easing.type: Easing.OutQuad
                }
            }
            ParallelAnimation {
                NumberAnimation {
                    target: content
                    property: "bounceScale"
                    to: 1.0
                    duration: 330
                    easing.type: Easing.OutBack
                }
                NumberAnimation {
                    target: content
                    property: "bounceY"
                    to: 0.0
                    duration: 330
                    easing.type: Easing.OutBack
                }
            }
        }
    }

    onIsWordActiveChanged: {
        if (isWordActive && enableWobble) {
            wobbleAnim.restart();
        }
    }

    onEnableWobbleChanged: {
        if (!enableWobble) {
            wobbleAnim.stop();
            content.bounceScale = 1.0;
            content.bounceY = 0.0;
        }
    }
}
