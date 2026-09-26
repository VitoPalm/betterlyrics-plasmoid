pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Item {
    id: popup
    property bool serviceEnabled: false
    property bool playing: false
    property bool loading: false
    property var lyricsList: []
    property int activeLineIndex: -1
    property double positionMs: 0
    property string title: ""
    property string artist: ""
    property string sourceName: ""
    property string syncType: ""
    property color lyricColor: Kirigami.Theme.textColor
    property string fontFamily: "Noto Sans"
    property int fontSize: 20
    property bool fontBold: true
    property bool fontItalic: false
    property bool romanizationEnabled: true
    property bool romanizationPrimary: false
    property bool showBothScripts: true
    property real romanizationOpacity: 0.72
    property bool manuallyBrowsing: false
    signal retryRequested()
    signal seekRequested(int timeMs)
    signal startRequested()
    signal returnToCurrentLyric()

    onVisibleChanged: {
        if (!visible) manuallyBrowsing = false;
    }
    onLyricsListChanged: manuallyBrowsing = false

    readonly property bool untimed: lyricsList.length > 0 && lyricsList[0].isUnsynced

    Layout.minimumWidth: 280
    Layout.minimumHeight: 220
    Layout.preferredWidth: 480
    Layout.preferredHeight: 420

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.smallSpacing * 2
        spacing: Kirigami.Units.smallSpacing

        QQC2.Label {
            Layout.fillWidth: true
            text: popup.title || i18n("No player")
            font.bold: true
            elide: Text.ElideRight
        }
        QQC2.Label {
            Layout.fillWidth: true
            text: popup.artist
            visible: !!popup.artist
            elide: Text.ElideRight
            opacity: 0.7
        }
        QQC2.Label {
            Layout.fillWidth: true
            text: !popup.serviceEnabled ? i18n("Better Lyrics is stopped")
                : !popup.playing && popup.title ? i18n("Paused")
                : popup.sourceName ? popup.sourceName + (popup.untimed ? i18n(" · Unsynced") : "")
                : popup.loading ? i18n("Loading lyrics…") : ""
            visible: !!text
            opacity: 0.7
        }

        Loader {
            id: lyricsLoader
            Layout.fillWidth: true
            Layout.fillHeight: true
            active: popup.visible && popup.serviceEnabled && popup.lyricsList.length > 0
            sourceComponent: popup.untimed ? plainComponent : timedComponent
        }

        QQC2.Button {
            text: i18n("Return to current lyric")
            visible: popup.visible && !popup.untimed && popup.manuallyBrowsing
            onClicked: popup.returnToCurrentLyric()
        }

        QQC2.Label {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: popup.serviceEnabled && popup.lyricsList.length === 0
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: popup.loading ? i18n("Looking for lyrics…")
                : popup.playing ? i18n("No lyrics found") : i18n("Play music to see lyrics")
        }

        QQC2.Button {
            text: i18n("Retry")
            visible: popup.serviceEnabled && popup.playing && !popup.loading && popup.lyricsList.length === 0
            onClicked: popup.retryRequested()
        }
        QQC2.Button {
            text: i18n("Start Better Lyrics")
            visible: !popup.serviceEnabled
            onClicked: popup.startRequested()
        }
    }

    Component {
        id: timedComponent
        LyricsStreamView {
            id: timedView
            allowManualScroll: true
            onManualBrowsingChanged: popup.manuallyBrowsing = manualBrowsing
            Connections {
                target: popup
                function onReturnToCurrentLyric() { timedView.manualBrowsing = false; }
            }
            lyricsList: popup.lyricsList
            activeLineIndex: popup.activeLineIndex
            playbackActive: popup.playing
            currentPositionMs: popup.positionMs
            activeColor: popup.lyricColor
            inactiveColor: Qt.rgba(popup.lyricColor.r, popup.lyricColor.g, popup.lyricColor.b, 0.58)
            fontFamily: popup.fontFamily
            fontSize: popup.fontSize
            fontBold: popup.fontBold
            fontItalic: popup.fontItalic
            enableWobble: false
            enableShadow: false
            enableRomanization: popup.romanizationEnabled
            romanizationOpacity: popup.romanizationOpacity
            romanizationPrimary: popup.romanizationPrimary
            showBothScripts: popup.showBothScripts
            onLineClicked: function(timeMs) { popup.seekRequested(timeMs); }
        }
    }

    Component {
        id: plainComponent
        Flickable {
            contentWidth: width
            contentHeight: transcript.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: transcript
                width: parent.width
                spacing: Kirigami.Units.largeSpacing
                Repeater {
                    model: popup.lyricsList
                    delegate: QQC2.Label {
                        width: transcript.width
                        text: modelData.words || ""
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        font.family: popup.fontFamily
                        font.pixelSize: popup.fontSize
                        color: Kirigami.Theme.textColor
                    }
                }
            }
        }
    }
}
