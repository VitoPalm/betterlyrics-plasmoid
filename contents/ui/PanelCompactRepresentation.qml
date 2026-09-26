import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: compact
    property bool horizontal: true
    property bool serviceEnabled: false
    property bool playing: false
    property bool loading: false
    property var activeLine: null
    property var previousLine: null
    property var nextLine: null
    property string title: ""
    property string artist: ""
    property bool romanizationPrimary: false
    property int preferredWidth: 280
    signal activated()

    function textForLine(line) {
        if (!line) return "";
        if (line.isInstrumental) return i18n("Instrumental");
        if (line.isUnsynced) return i18n("Lyrics available");
        return romanizationPrimary && line.romanization
            ? line.romanization : (line.words || "");
    }
    readonly property string lyricText: textForLine(activeLine)
    readonly property bool instrumentalWithPrevious: serviceEnabled && playing && activeLine
        && activeLine.isInstrumental && previousLine
    readonly property bool wrappedPrevious: instrumentalWithPrevious && twoRowsFit
        && previousMetrics.width > width - 12
    readonly property string displayText: wrappedPrevious ? textForLine(previousLine)
        : !serviceEnabled ? ""
        : !title ? i18n("No player")
        : !playing ? title
        : lyricText || (loading ? i18n("Loading lyrics") : title)
    readonly property string secondaryText: {
        if (!serviceEnabled || !title) return "";
        if (wrappedPrevious) return "";
        if (playing && activeLine && activeLine.isInstrumental)
            return previousLine ? textForLine(previousLine) : title;
        if (playing && activeLine && !activeLine.isUnsynced && nextLine)
            return textForLine(nextLine);
        return displayText === title ? artist : title;
    }
    readonly property bool twoRowsFit: horizontal && height >= 30
    readonly property int primaryFontSize: twoRowsFit
        ? Math.max(12, Math.min(18, Math.floor(height * 0.42)))
        : Math.max(11, Math.min(18, Math.floor(height * 0.52)))
    readonly property int secondaryFontSize: Math.max(10, Math.round(primaryFontSize * 0.82))
    readonly property bool wrapCurrent: twoRowsFit && currentMetrics.width > width - 12

    Layout.minimumWidth: horizontal ? 32 : 24
    Layout.preferredWidth: horizontal ? Math.max(80, Math.min(800, preferredWidth)) : 32
    Layout.maximumWidth: horizontal ? 800 : 64
    Layout.minimumHeight: 24
    Layout.preferredHeight: horizontal ? 32 : Math.max(24, width)
    Layout.maximumHeight: horizontal ? 128 : Math.max(24, width)
    Layout.fillHeight: horizontal
    clip: true
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: wrappedPrevious ? i18n("Instrumental: %1", displayText)
        : secondaryText ? displayText + ", " + secondaryText : displayText
    Accessible.description: i18n("Open Better Lyrics")
    Keys.onReturnPressed: compact.activated()
    Keys.onSpacePressed: compact.activated()

    TextMetrics {
        id: currentMetrics
        font.family: Kirigami.Theme.defaultFont.family
        font.pixelSize: compact.wrappedPrevious ? compact.secondaryFontSize : compact.primaryFontSize
        font.bold: !compact.wrappedPrevious
        text: compact.displayText
    }

    TextMetrics {
        id: previousMetrics
        font.family: Kirigami.Theme.defaultFont.family
        font.pixelSize: compact.secondaryFontSize
        text: compact.textForLine(compact.previousLine)
    }

    Column {
        visible: compact.horizontal
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 6
        anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0

        Text {
            width: parent.width
            text: compact.displayText
            textFormat: Text.PlainText
            wrapMode: compact.wrapCurrent ? Text.WrapAtWordBoundaryOrAnywhere : Text.NoWrap
            maximumLineCount: compact.wrapCurrent ? 2 : 1
            elide: Text.ElideRight
            font.family: Kirigami.Theme.defaultFont.family
            font.pixelSize: compact.wrappedPrevious ? compact.secondaryFontSize : compact.primaryFontSize
            font.bold: !compact.wrappedPrevious
            color: Kirigami.Theme.textColor
            opacity: compact.wrappedPrevious ? 0.62 : 1.0
        }

        Text {
            visible: compact.twoRowsFit && !compact.wrapCurrent && !!compact.secondaryText
            width: parent.width
            text: compact.secondaryText
            textFormat: Text.PlainText
            elide: Text.ElideRight
            maximumLineCount: 1
            font.family: Kirigami.Theme.defaultFont.family
            font.pixelSize: compact.secondaryFontSize
            color: Kirigami.Theme.textColor
            opacity: 0.62
        }
    }

    Kirigami.Icon {
        visible: !compact.horizontal
        anchors.centerIn: parent
        width: Math.min(parent.width, parent.height) - 6
        height: width
        source: compact.serviceEnabled ? "view-media-lyrics" : "media-playback-stop"
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onClicked: compact.activated()
    }
}
