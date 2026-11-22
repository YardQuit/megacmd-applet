// ConfigGeneral.qml: the MEGA Plasma widget's general settings.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

// Refresh interval, the MEGA folders suggested for new syncs and backups,
// and the terminal the guided dialogs open in.
KCM.SimpleKCM {
    property alias cfg_refreshIntervalSec: refreshInterval.value
    property alias cfg_syncFolder: syncFolder.text
    property alias cfg_backupFolder: backupFolder.text
    property alias cfg_terminal: terminal.text

    Kirigami.FormLayout {
        QQC2.SpinBox {
            id: refreshInterval
            Kirigami.FormData.label: i18n("Refresh every (seconds):")
            from: 10
            to: 3600
            stepSize: 5
        }
        QQC2.TextField {
            id: syncFolder
            Kirigami.FormData.label: i18n("MEGA folder for new syncs:")
        }
        QQC2.TextField {
            id: backupFolder
            Kirigami.FormData.label: i18n("MEGA folder for backups:")
        }
        QQC2.TextField {
            id: terminal
            Kirigami.FormData.label: i18n("Terminal command:")
            placeholderText: i18n("Found automatically, e.g. konsole -e")
        }
    }
}
