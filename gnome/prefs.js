// prefs.js: the MEGA extension's settings window.
// SPDX-License-Identifier: GPL-3.0-or-later

import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import {ExtensionPreferences, gettext as _} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

/** Settings: refresh interval, suggested MEGA folders, the terminal command and MEGAcmd's folder. */
export default class MegaPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        const page = new Adw.PreferencesPage();
        const group = new Adw.PreferencesGroup({title: _('MEGA')});
        page.add(group);

        const refresh = Adw.SpinRow.new_with_range(10, 3600, 5);
        refresh.title = _('Refresh every (seconds)');
        refresh.subtitle = _('How often to check MEGAcmd while the menu is closed');
        settings.bind('refresh-interval', refresh, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(refresh);

        for (const [key, title] of [
            ['sync-folder', _('MEGA folder for new syncs')],
            ['backup-folder', _('MEGA folder for backups')],
            ['terminal', _('Terminal command (empty finds one)')],
            ['megacmd-dir', _('MEGAcmd folder (empty uses the PATH)')],
        ]) {
            const row = new Adw.EntryRow({title});
            settings.bind(key, row, 'text', Gio.SettingsBindFlags.DEFAULT);
            group.add(row);
        }

        window.add(page);
    }
}
