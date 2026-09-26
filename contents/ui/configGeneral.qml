import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts

import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    // Hidden state still belongs to the KCM contract. Independent instances
    // use enabled; following instances keep it for a later opt-out.
    property bool cfg_enabled: true
    property bool cfg_enabledDefault: true
    // Plasma's panel layout adds these keys to the same configuration map.
    property bool cfg_expanding: false
    property int cfg_length: 280
    property alias cfg_followGlobalEnabled: followGlobalCheckBox.checked
    property bool cfg_followGlobalEnabledDefault
    property alias cfg_panelWidth: panelWidthSpinBox.value
    property int cfg_panelWidthDefault
    property alias cfg_fontFamily: fontFamilyField.text
    property string cfg_fontFamilyDefault
    property alias cfg_fontSize: fontSizeSpinBox.value
    property int cfg_fontSizeDefault
    property alias cfg_fontBold: fontBoldCheckBox.checked
    property bool cfg_fontBoldDefault
    property alias cfg_fontItalic: fontItalicCheckBox.checked
    property bool cfg_fontItalicDefault
    property alias cfg_useAlbumColor: useAlbumColorCheckBox.checked
    property bool cfg_useAlbumColorDefault
    property alias cfg_customFontColor: customFontColorField.text
    property string cfg_customFontColorDefault
    property alias cfg_timingOffsetMs: timingOffsetSpinBox.value
    property int cfg_timingOffsetMsDefault
    // Internal migration marker: it must participate in the KCM contract so
    // opening and accepting settings never drops it back to the legacy mode.
    property int cfg_timingOffsetSemanticsVersion: 1
    property int cfg_timingOffsetSemanticsVersionDefault: 1
    property alias cfg_enableWobble: enableWobbleCheckBox.checked
    property bool cfg_enableWobbleDefault
    property alias cfg_enableShadow: enableShadowCheckBox.checked
    property bool cfg_enableShadowDefault
    property alias cfg_enableRomanization: enableRomanizationCheckBox.checked
    property bool cfg_enableRomanizationDefault
    property alias cfg_romanizationOpacity: romanizationOpacitySlider.value
    property real cfg_romanizationOpacityDefault
    property alias cfg_romanizationPrimary: romanizationPrimaryCheckBox.checked
    property bool cfg_romanizationPrimaryDefault
    property alias cfg_showBothScripts: showBothScriptsCheckBox.checked
    property bool cfg_showBothScriptsDefault

    Component.onCompleted: {
        // The schema retains the old sign/default solely so main.qml can
        // identify pre-1.2.0 installations. Inside the new settings UI,
        // Defaults must always mean a 150 ms delay under the new convention.
        cfg_timingOffsetMsDefault = 150;
        cfg_timingOffsetSemanticsVersion = 1;
        cfg_timingOffsetSemanticsVersionDefault = 1;
    }

    Kirigami.FormLayout {
        QQC2.CheckBox {
            id: followGlobalCheckBox
            Kirigami.FormData.label: i18n("Playback control:")
            text: i18n("Follow global Start/Stop")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("Turn off to start and stop only this widget")
        }

        QQC2.SpinBox {
            id: panelWidthSpinBox
            from: 80
            to: 800
            stepSize: 20
            Kirigami.FormData.label: i18n("Panel lyric width:")
        }

        QQC2.TextField {
            id: fontFamilyField
            Kirigami.FormData.label: i18n("Font family:")
        }

        QQC2.SpinBox {
            id: fontSizeSpinBox
            from: 8
            to: 72
            Kirigami.FormData.label: i18n("Font size:")
        }

        QQC2.CheckBox {
            id: fontBoldCheckBox
            Kirigami.FormData.label: i18n("Bold text:")
        }

        QQC2.CheckBox {
            id: fontItalicCheckBox
            Kirigami.FormData.label: i18n("Italic text:")
        }

        QQC2.CheckBox {
            id: useAlbumColorCheckBox
            Kirigami.FormData.label: i18n("Color from album art:")
        }

        QQC2.TextField {
            id: customFontColorField
            visible: !cfg_useAlbumColor
            Kirigami.FormData.label: i18n("Custom text color:")
        }

        QQC2.CheckBox {
            id: enableWobbleCheckBox
            Kirigami.FormData.label: i18n("Syllable wobble animation:")
        }

        QQC2.CheckBox {
            id: enableShadowCheckBox
            Kirigami.FormData.label: i18n("Drop shadows:")
        }

        QQC2.CheckBox {
            id: enableRomanizationCheckBox
            Kirigami.FormData.label: i18n("Romanize non-Latin lyrics:")
        }

        QQC2.Slider {
            id: romanizationOpacitySlider
            visible: enableRomanizationCheckBox.checked
            from: 0.30
            to: 1.0
            stepSize: 0.05
            Kirigami.FormData.label: i18n("Romanization opacity:")
        }

        QQC2.CheckBox {
            id: romanizationPrimaryCheckBox
            visible: enableRomanizationCheckBox.checked
            Kirigami.FormData.label: i18n("Romanization as primary text:")
        }

        QQC2.CheckBox {
            id: showBothScriptsCheckBox
            visible: enableRomanizationCheckBox.checked
            Kirigami.FormData.label: i18n("Show both scripts:")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: romanizationPrimaryCheckBox.checked
                ? i18n("Turn off to show only romanized lyrics")
                : i18n("Turn off to show only original lyrics")
        }

        QQC2.SpinBox {
            id: timingOffsetSpinBox
            from: -2000
            to: 2000
            stepSize: 50
            editable: true
            Kirigami.FormData.label: i18n("Lyrics delay (ms):")
            Accessible.description: i18n("Positive values show lyrics later; negative values show them earlier")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("Positive = later · Negative = earlier")
        }
    }
}
