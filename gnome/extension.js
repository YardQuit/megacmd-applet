// extension.js: the MEGA extension: MEGAcmd's state and actions in the top bar.
// SPDX-License-Identifier: GPL-3.0-or-later

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import {runCore} from './core.js';
import {ItemRow, textItem} from './rows.js';

// The symbolic icon of each state the shared core names, for the badge and rows.
const STATE_ICONS = {
    stopped: 'network-offline-symbolic',
    off: 'network-offline-symbolic',
    error: 'dialog-error-symbolic',
    warning: 'dialog-warning-symbolic',
    paused: 'media-playback-pause-symbolic',
    syncing: 'view-refresh-symbolic',
    synced: 'object-select-symbolic',
};

/**
 * The top bar button: a cloud with the overall state's badge, and a menu
 * with the account, the sync folders and backups and their actions. Polls
 * the shared core every 3 seconds while the menu is open and every
 * `refresh-interval` seconds otherwise, and shows the notifications the core
 * hands it. The setting `preview-name` shows a saved state from fixtures/
 * instead; actions do nothing then.
 */
const MegaIndicator = GObject.registerClass(
class MegaIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.5, _('MEGA'));
        this._extension = extension;
        this._settings = extension.getSettings();
        this._coreDir = `${extension.path}/megacmd`;
        this._cancellable = new Gio.Cancellable();
        this._view = {kind: 'off', kindText: _('Not logged in'), syncs: [], backups: []};
        this._shownJson = '';
        this._lastError = '';
        this._actionStatus = '';
        this._shownPreview = null;
        this._pollId = 0;
        this._guidedId = 0;
        this._guidedTicks = 0;
        this._timers = new Set();
        this._source = null;

        const icon = new St.Widget({layout_manager: new Clutter.BinLayout(), y_align: Clutter.ActorAlign.CENTER});
        icon.add_child(new St.Icon({icon_name: 'weather-overcast-symbolic', style_class: 'system-status-icon'}));
        // The badge sits in the cloud's lower-right corner, a little outside it.
        this._badge = new St.Icon({
            style_class: 'megacmd-badge',
            x_align: Clutter.ActorAlign.END,
            y_align: Clutter.ActorAlign.END,
            translation_x: 2,
            translation_y: 1,
        });
        icon.add_child(this._badge);
        this.add_child(icon);

        this.menu.connect('open-state-changed', (menu, open) => {
            if (open)
                this.refresh();
            this._schedule();
        });
        this._settingsId = this._settings.connect('changed', () => {
            this._shownJson = '';
            this.refresh();
            this._schedule();
        });

        this._showView();
        this.refresh();
        this._schedule();
    }

    get _previewName() {
        return this._settings.get_string('preview-name').replace(/[^A-Za-z0-9_-]/g, '');
    }

    _schedule() {
        if (this._pollId)
            GLib.source_remove(this._pollId);
        const seconds = this.menu.isOpen ? 3 : Math.max(10, this._settings.get_int('refresh-interval'));
        this._pollId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, seconds, () => {
            this.refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    // Runs FUNCTION once after SECONDS; the timer goes with the indicator.
    _later(seconds, func) {
        const id = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, seconds, () => {
            this._timers.delete(id);
            func();
            return GLib.SOURCE_REMOVE;
        });
        this._timers.add(id);
    }

    async refresh() {
        const preview = this._previewName;
        let args = ['status', '--timeout', '20'];
        if (preview !== '') {
            // The saved states in fixtures/ are written for the home folder /home/user.
            args = ['status', '--fixture', `${this._coreDir}/fixtures/${preview}.json`, '--home', '/home/user'];
            if (this._shownPreview !== preview)
                args.push('--fresh');
        }
        this._shownPreview = preview;
        try {
            const result = await runCore(this._coreDir, args, this._cancellable);
            if (result.status !== 0) {
                this._setError(result.stderr.trim() || _('Could not read MEGA status'));
                return;
            }
            this._applyStatus(result.stdout);
        } catch (error) {
            if (!error.matches?.(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED))
                this._setError(String(error.message ?? error));
        }
    }

    _setError(text) {
        this._lastError = text;
        this._shownJson = '';
        this._showView();
    }

    _applyStatus(raw) {
        let data;
        try {
            data = JSON.parse(raw);
        } catch {
            this._setError(_('Unreadable MEGA status'));
            return;
        }
        if (!data || data.ok === false) {
            this._setError(String(data?.error || _('Could not read MEGA status')));
            return;
        }
        const notices = data.notices || [];
        delete data.notices;
        this._view = data;
        this._lastError = String(data.error || '');
        // The menu is rebuilt only when what it shows has changed, so rows
        // keep their hover and armed state between refreshes.
        const json = JSON.stringify(data) + this._lastError + this._actionStatus;
        if (json !== this._shownJson) {
            this._shownJson = json;
            this._showView();
        }
        for (const notice of notices)
            this._notify(notice);
    }

    _notify(notice) {
        if (!this._source) {
            this._source = new MessageTray.Source({title: _('MEGA'), iconName: 'folder-remote-symbolic'});
            this._source.connect('destroy', () => {
                this._source = null;
            });
            Main.messageTray.add(this._source);
        }
        const label = this._previewName !== '' ? _(' (preview)') : '';
        const notification = new MessageTray.Notification({
            source: this._source,
            title: String(notice.title) + label,
            body: String(notice.body),
            urgency: notice.urgency === 'critical' ? MessageTray.Urgency.CRITICAL : MessageTray.Urgency.NORMAL,
        });
        notification.connect('activated', () => this.menu.open());
        this._source.addNotification(notification);
    }

    // False, with a note in the menu, while a preview is shown.
    _actionsAllowed() {
        if (this._previewName === '')
            return true;
        this._showActionStatus(_('Preview: actions are off'));
        return false;
    }

    _showActionStatus(text) {
        this._actionStatus = text;
        this._shownJson = '';
        this._showView();
        this._later(4, () => {
            this._actionStatus = '';
            this._shownJson = '';
            this._showView();
        });
    }

    // Runs a core action, then refreshes twice: MEGAcmd applies changes a little later.
    async _act(args) {
        if (!this._actionsAllowed())
            return;
        try {
            const result = await runCore(this._coreDir, args, this._cancellable);
            if (result.status !== 0)
                this._showActionStatus(result.stderr.trim() || _('MEGA command failed'));
        } catch (error) {
            this._showActionStatus(String(error.message ?? error));
        }
        this.refresh();
        this._later(2, () => this.refresh());
    }

    // Opens a guided dialog in a terminal, then keeps checking for a while,
    // as it runs on its own.
    _guided(name, args = []) {
        const terminal = this._settings.get_string('terminal');
        this._act(['guided', name, ...args, ...(terminal ? ['--terminal', terminal] : [])]);
        this._guidedTicks = 0;
        if (this._guidedId)
            return;
        this._guidedId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 5, () => {
            this.refresh();
            this._guidedTicks += 1;
            if (this._guidedTicks < 60)
                return GLib.SOURCE_CONTINUE;
            this._guidedId = 0;
            return GLib.SOURCE_REMOVE;
        });
    }

    _openFolder(path) {
        if (String(path).startsWith('/') && this._actionsAllowed())
            Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(path, null), null);
    }

    _showView() {
        const view = this._view;
        const loggedIn = view.loggedIn === true;
        this._badge.icon_name = STATE_ICONS[view.kind] || STATE_ICONS.synced;
        this._badge.style_class = `megacmd-badge megacmd-${view.badgeColour || 'green'}`;

        this.menu.removeAll();
        const header = new PopupMenu.PopupMenuItem(_('MEGA'), {reactive: false, can_focus: false});
        header.label.style = 'font-weight: bold';
        this.menu.addMenuItem(header);
        this.menu.addMenuItem(textItem(view.installed === false ? _('MEGAcmd is not installed') : (view.kindText || '')));

        if (!loggedIn) {
            const stopped = view.running === false;
            const login = new PopupMenu.PopupMenuItem(stopped ? _('Start MEGAcmd') : _('Log in to MEGA'));
            login.connect('activate', () => this._guided('mega-account-login'));
            this.menu.addMenuItem(login);
        } else {
            this._addAccount(view);
            this._addSyncs(view);
            this._addBackups(view);
            this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            const web = new PopupMenu.PopupMenuItem(_('Open MEGA in the browser'));
            web.connect('activate', () => Gio.AppInfo.launch_default_for_uri('https://mega.nz/fm', null));
            this.menu.addMenuItem(web);
        }

        const note = this._actionStatus || this._lastError;
        if (note)
            this.menu.addMenuItem(textItem(note, true));
    }

    _addAccount(view) {
        if (view.email)
            this.menu.addMenuItem(textItem(view.email));
        if (view.usageText)
            this.menu.addMenuItem(textItem(_('Stored: %s').format(view.usageText), view.storageLevel > 0));
        if (view.transfersText)
            this.menu.addMenuItem(textItem(view.transfersText));
        if (view.syncs.length > 0) {
            const syncing = new PopupMenu.PopupSwitchMenuItem(_('Syncing'), view.anyRunning === true);
            syncing.connect('toggled', () => this._act(['toggle-all']));
            this.menu.addMenuItem(syncing);
        }
    }

    _addSyncs(view) {
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(_('Sync folders')));
        for (const sync of view.syncs) {
            this.menu.addMenuItem(new ItemRow({
                iconName: STATE_ICONS[sync.kind] || STATE_ICONS.synced,
                colour: sync.badgeColour,
                title: `${sync.localDisplay}  ↔  ${sync.remote}`,
                meta: sync.meta,
                actionIcon: sync.paused ? 'media-playback-start-symbolic' : 'media-playback-pause-symbolic',
                actionText: sync.paused ? _('Resume') : _('Pause'),
                onAction: () => this._act([sync.paused ? 'resume' : 'pause', sync.id]),
                onOpen: () => this._openFolder(sync.local),
                onRemove: () => this._act(['remove-sync', sync.id]),
            }));
        }
        const add = new PopupMenu.PopupMenuItem(_('Add sync…'));
        add.connect('activate', () => this._guided('mega-add-sync', [this._settings.get_string('sync-folder')]));
        this.menu.addMenuItem(add);
    }

    _addBackups(view) {
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(_('Backups')));
        for (const backup of view.backups) {
            this.menu.addMenuItem(new ItemRow({
                iconName: backup.failed ? STATE_ICONS.error : (backup.lastStatus ? STATE_ICONS.synced : 'document-save-symbolic'),
                colour: backup.failed ? 'red' : (backup.lastStatus ? 'green' : ''),
                title: `${backup.localDisplay}  →  ${backup.remote}`,
                meta: backup.meta,
                actionIcon: 'emblem-system-symbolic',
                actionText: _('Change schedule and versions'),
                onAction: () => this._guided('mega-edit-backup', [backup.tag, backup.period, String(backup.maxBackups)]),
                onOpen: () => this._openFolder(backup.local),
                onRemove: () => this._act(['remove-backup', backup.tag]),
            }));
        }
        const add = new PopupMenu.PopupMenuItem(_('Add backup…'));
        add.connect('activate', () => this._guided('mega-add-backup', [this._settings.get_string('backup-folder')]));
        this.menu.addMenuItem(add);
    }

    destroy() {
        this._cancellable.cancel();
        for (const id of [this._pollId, this._guidedId, ...this._timers]) {
            if (id)
                GLib.source_remove(id);
        }
        this._timers.clear();
        this._settings.disconnect(this._settingsId);
        this._source?.destroy();
        super.destroy();
    }
});

/** The extension: adds the MEGA button to the top bar while enabled. */
export default class MegaExtension extends Extension {
    enable() {
        this._indicator = new MegaIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
