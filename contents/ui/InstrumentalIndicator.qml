import QtQuick

Item {
    id: instRoot

    property int startTimeMs: 0
    property int durationMs: 5000
    property double currentPositionMs: 0
    property bool isLineActive: false
    property bool playbackActive: true

    property color activeColor: "#FFFFFF"
    property color inactiveColor: Qt.rgba(1, 1, 1, 0.35)
    property int fontSize: 20
    property bool enableShadow: true

    readonly property double progress: Math.min(1.0, Math.max(0.0, (currentPositionMs - startTimeMs) / Math.max(1, durationMs)))

    implicitWidth: row.implicitWidth
    implicitHeight: row.implicitHeight

    Row {
        id: row
        anchors.centerIn: parent
        spacing: instRoot.fontSize * 0.4

        Repeater {
            model: 3
            delegate: Item {
                id: dotContainer
                width: instRoot.fontSize * 0.7
                height: instRoot.fontSize * 0.7

                readonly property bool dotLit: instRoot.isLineActive && (instRoot.progress >= (index / 3.0))

                // Soft drop shadow behind dot (no borders)
                Rectangle {
                    anchors.centerIn: dot
                    anchors.verticalCenterOffset: 2.0
                    anchors.horizontalCenterOffset: 0.5
                    width: dot.width
                    height: dot.height
                    radius: width / 2
                    color: Qt.rgba(0, 0, 0, 0.35)
                    visible: instRoot.enableShadow
                    z: 0
                }

                Rectangle {
                    id: dot
                    anchors.centerIn: parent
                    z: 1
                    width: parent.width
                    height: parent.height
                    radius: width / 2

                    color: dotLit ? instRoot.activeColor : instRoot.inactiveColor
                    opacity: dotLit ? 1.0 : 0.35

                    scale: {
                        if (!instRoot.isLineActive) return 0.85;
                        return dotLit ? 1.15 : 0.9;
                    }

                    Behavior on color { ColorAnimation { duration: 180 } }
                    Behavior on opacity { NumberAnimation { duration: 180 } }
                    Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack } }
                }

                SequentialAnimation on scale {
                    running: instRoot.isLineActive && instRoot.playbackActive
                    loops: Animation.Infinite
                    PauseAnimation { duration: index * 180 }
                    NumberAnimation { to: 1.25; duration: 400; easing.type: Easing.InOutQuad }
                    NumberAnimation { to: 1.0; duration: 400; easing.type: Easing.InOutQuad }
                    PauseAnimation { duration: Math.max(0, (2 - index) * 180) }
                }
            }
        }
    }
}
