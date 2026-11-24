// extension.js: the MEGA extension: MEGAcmd's state and actions in the top bar.
// SPDX-License-Identifier: GPL-3.0-or-later

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

import {isCancelled, runCore} from './core.js';
import {Notifier} from './notifications.js';
import {IssueItem, ItemRow, textItem} from './rows.js';

// The symbolic icon of each state the shared core names, for the badge and rows.
const STATE_ICONS = {
    missing: 'action-unavailable-symbolic',
    unknown: 'dialog-question-symbolic',
    stopped: 'network-offline-symbolic',
    off: 'network-offline-symbolic',
    error: 'dialog-error-symbolic',
    warning: 'dialog-warning-symbolic',
    paused: 'media-playback-pause-symbolic',
    syncing: 'view-refresh-symbolic',
    synced: 'object-select-symbolic',
    pending: 'document-save-symbolic',
};

// Timings shared with the other desktops, in seconds.
const OPEN_POLL_SECONDS = 3;
const MIN_POLL_SECONDS = 10;
const SETTLE_SECONDS = 2;
const ARM_SECONDS = 4;
const NOTE_SECONDS = 4;
const GUIDED_SECONDS = 5;
const GUIDED_CHECKS = 60;
const SETTINGS_SECONDS = 1;

// Settings that change what the status shows or how often it is read.
const STATUS_SETTINGS = ['refresh-interval', 'megacmd-dir', 'preview-name'];

// Shown until the first status arrives: nothing known yet, nothing offered.
const START_VIEW = {ok: false, kind: 'unknown', kindText: '', badgeColour: '', offer: '', syncs: [], backups: []};

/**
 * The view shown when the core itself could not run or printed no view.
 *
 * @param {string} text - why the state is unknown
 * @returns {object} a view of kind "unknown" saying TEXT
 */
function failedView(text) {
    return {...START_VIEW, kindText: text, badgeColour: 'orange'};
}

/**
 * Reads the view from a finished `status` run.
 *
 * @param {{status: number, stdout: string, stderr: string}} result - how it ended
 * @returns {object} the core's view, or a failed view when there is none
 */
function readView(result) {
    if (result.status !== 0)
        return failedView(result.stderr.trim() || _('Could not read MEGA status'));
    try {
        return JSON.parse(result.stdout);
    } catch {
        return failedView(_('Unreadable MEGA status'));
    }
}

/**
 * The top bar button: a cloud with the overall state's badge, and a menu
 * with the account, the sync folders and backups and their actions. Polls
 * the shared core every 3 seconds while the menu is open and every
 * `refresh-interval` seconds otherwise, and passes the notices the core
 * hands it to a Notifier. The setting `preview-name` shows a saved state
 * instead; actions are refused then.
 */
const MegaIndicator = GObject.registerClass(
class MegaIndicator extends PanelMenu.Button {
    _init(extension, notifier) {
        super._init(0.5, _('MEGA'));
        this._settings = extension.getSettings();
        this._coreDir = `${extension.path}/megacmd`;
        this._notifier = notifier;
        this._cancellable = new Gio.Cancellable();
        this._destroyed = false;
        this._view = START_VIEW;
        this._note = '';
        this._shown = '';
        this._armedKey = '';
        this._rows = new Map();
        this._syncSwitch = null;
        this._statusRunning = false;
        this._statusPending = false;
        this._guidedChecks = 0;
        this._timers = new Map();

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
        this.menu.box.add_style_class_name('megacmd-menu');

        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open)
                this.refresh();
            this._schedule();
        });
        this._settingsIds = STATUS_SETTINGS.map(key => this._settings.connect(`changed::${key}`, () => {
            this._after('settings', SETTINGS_SECONDS, () => {
                this.refresh();
                this._schedule();
            });
        }));

        this._showView();
        this.refresh();
        this._schedule();
    }

    get _previewName() {
        return this._settings.get_string('preview-name');
    }

    // Runs FUNC once after SECONDS under NAME, replacing a timer of that name.
    _after(name, seconds, func) {
        this._cancelTimer(name);
        if (this._destroyed)
            return;
        const id = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, seconds, () => {
            this._timers.delete(name);
            func();
            return GLib.SOURCE_REMOVE;
        });
        this._timers.set(name, id);
    }

    _cancelTimer(name) {
        const id = this._timers.get(name);
        if (id) {
            GLib.source_remove(id);
            this._timers.delete(name);
        }
    }

    _schedule() {
        const seconds = this.menu.isOpen
            ? OPEN_POLL_SECONDS
            : Math.max(MIN_POLL_SECONDS, this._settings.get_int('refresh-interval'));
        this._after('poll', seconds, () => {
            this.refresh();
            this._schedule();
        });
    }

    /**
     * Reads the state from the core and shows it. One run at a time: a
     * refresh asked for meanwhile runs once when it ends, and a result for
     * a preview setting no longer in effect is not shown, though its
     * notices are.
     */
    async refresh() {
        if (this._destroyed)
            return;
        if (this._statusRunning) {
            this._statusPending = true;
            return;
        }
        this._statusRunning = true;
        const preview = this._previewName;
        const args = ['status', '--timeout', '20'];
        if (preview !== '')
            args.push(`--preview=${preview}`);
        let view;
        try {
            view = readView(await this._runCore(args));
        } catch (error) {
            if (isCancelled(error))
                return;
            view = failedView(String(error.message ?? error));
        }
        this._statusRunning = false;
        if (this._destroyed)
            return;

        const notices = view.notices ?? [];
        delete view.notices;
        if (preview === this._previewName) {
            this._view = view;
            this._showView();
        }
        for (const notice of notices)
            this._notifier.show(notice, preview !== '');
        if (this._statusPending) {
            this._statusPending = false;
            this.refresh();
        }
    }

    // False, with a note in the menu, while a preview is shown.
    _actionsAllowed() {
        if (this._previewName === '')
            return true;
        this._showNote(_('Preview: actions are off'));
        return false;
    }

    _showNote(text) {
        this._note = text;
        this._showView();
        this._after('note', NOTE_SECONDS, () => {
            this._note = '';
            this._showView();
        });
    }

    // Runs the core's command line with ARGS, with the MEGAcmd folder set.
    _runCore(args) {
        const megacmdDir = this._settings.get_string('megacmd-dir');
        return runCore(this._coreDir, args, {megacmdDir, cancellable: this._cancellable});
    }

    // Runs a core action unless a preview is shown.
    _act(args) {
        if (this._actionsAllowed())
            this._run(args, true);
    }

    // Runs a core action and shows why it failed. SETTLE refreshes at once
    // and again a little later, as MEGAcmd applies changes after a moment.
    async _run(args, settle) {
        let failure = '';
        try {
            const result = await this._runCore(args);
            if (result.status !== 0)
                failure = result.stderr.trim() || _('MEGA command failed');
        } catch (error) {
            if (isCancelled(error))
                return;
            failure = String(error.message ?? error);
        }
        if (this._destroyed)
            return;
        if (failure)
            this._showNote(failure);
        if (settle) {
            this.refresh();
            this._after('settle', SETTLE_SECONDS, () => this.refresh());
        }
    }

    // Opens a guided dialog in a terminal, then keeps checking for a while,
    // as it runs on its own.
    _guided(name, args = []) {
        if (!this._actionsAllowed())
            return;
        const terminal = this._settings.get_string('terminal');
        const options = terminal ? [`--terminal=${terminal}`] : [];
        this._run(['guided', ...options, name, '--', ...args], true);
        this._guidedChecks = GUIDED_CHECKS;
        this._after('guided', GUIDED_SECONDS, () => this._guidedCheck());
    }

    _guidedCheck() {
        this.refresh();
        this._guidedChecks -= 1;
        if (this._guidedChecks > 0)
            this._after('guided', GUIDED_SECONDS, () => this._guidedCheck());
    }

    // The first press arms the item KEY's remove button for a few seconds;
    // a second press while armed runs the core action ARGS.
    _remove(key, args) {
        if (this._armedKey === key) {
            this._disarm();
            this._act(args);
            return;
        }
        this._disarm();
        this._armedKey = key;
        this._rows.get(key)?.setArmed(true);
        this._after('arm', ARM_SECONDS, () => this._disarm());
    }

    _disarm() {
        this._cancelTimer('arm');
        this._rows.get(this._armedKey)?.setArmed(false);
        this._armedKey = '';
    }

    _openFolder(path) {
        if (this._actionsAllowed())
            this._run(['open-folder', path], false);
    }

    _openWeb() {
        Gio.AppInfo.launch_default_for_uri_async('https://mega.nz/fm', null, this._cancellable, (_source, result) => {
            try {
                Gio.AppInfo.launch_default_for_uri_finish(result);
            } catch (error) {
                if (!isCancelled(error))
                    this._showNote(error.message);
            }
        });
    }

    // Rebuilds the menu when what it shows has changed, so rows keep their
    // hover between refreshes.
    _showView() {
        if (this._destroyed)
            return;
        const view = this._view;
        const shown = JSON.stringify([view, this._note]);
        if (shown === this._shown) {
            this._syncSwitch?.setToggleState(view.anyRunning === true);
            return;
        }
        this._shown = shown;

        this._badge.icon_name = STATE_ICONS[view.kind] ?? STATE_ICONS.unknown;
        this._badge.style_class = view.badgeColour ? `megacmd-badge megacmd-${view.badgeColour}` : 'megacmd-badge';

        this.menu.removeAll();
        this._rows.clear();
        this._syncSwitch = null;
        const header = new PopupMenu.PopupMenuItem(_('MEGA'), {reactive: false, can_focus: false});
        header.label.add_style_class_name('megacmd-heading');
        this.menu.addMenuItem(header);
        this.menu.addMenuItem(textItem(view.kindText ?? ''));

        if (view.ok && view.loggedIn) {
            this._addAccount(view);
            this._addIssues(view);
            this._addSyncs(view);
            this._addBackups(view);
            this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            const web = new PopupMenu.PopupMenuItem(_('Open MEGA in the browser'));
            web.connect('activate', () => this._openWeb());
            this.menu.addMenuItem(web);
        } else if (view.offer) {
            const offer = new PopupMenu.PopupMenuItem(view.offerText);
            offer.connect('activate', () => this._guided('mega-account-login'));
            this.menu.addMenuItem(offer);
            this.menu.addMenuItem(textItem(view.offerHint ?? '', {dim: true}));
        }

        if (view.ok && view.error)
            this.menu.addMenuItem(textItem(view.error, {warning: true}));
        if (this._note)
            this.menu.addMenuItem(textItem(this._note, {warning: true}));
    }

    _addAccount(view) {
        if (view.email)
            this.menu.addMenuItem(textItem(view.email));
        if (view.usageText)
            this.menu.addMenuItem(textItem(_('Stored: %s').format(view.usageText), {warning: view.storageLevel > 0}));
        if (view.transfersText)
            this.menu.addMenuItem(textItem(view.transfersText));
        if (view.syncs.length > 0) {
            this._syncSwitch = new PopupMenu.PopupSwitchMenuItem(_('Syncing'), view.anyRunning === true);
            this._syncSwitch.connect('toggled', () => this._act(['toggle-all']));
            this.menu.addMenuItem(this._syncSwitch);
        }
    }

    // Adds the row for ITEM, a sync or backup of the view; REMOVE is the
    // core action that removes it.
    _addRow(item, {actionIcon, actionText, onAction, remove}) {
        const row = new ItemRow({
            iconName: STATE_ICONS[item.kind] ?? STATE_ICONS.unknown,
            colour: item.badgeColour,
            title: item.title,
            meta: item.meta,
            armed: item.key === this._armedKey,
            actionIcon,
            actionText,
            onAction,
            onOpen: () => this._openFolder(item.local),
            onRemove: () => this._remove(item.key, remove),
        });
        this._rows.set(item.key, row);
        this.menu.addMenuItem(row);
    }

    // The files that are not syncing, each with the core's buttons for it.
    _addIssues(view) {
        const issues = view.issues ?? [];
        if (issues.length === 0)
            return;
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(_('Not syncing')));
        for (const issue of issues)
            this.menu.addMenuItem(new IssueItem({...issue, onAction: args => this._act(args)}));
        if (view.issuesMoreText)
            this.menu.addMenuItem(textItem(view.issuesMoreText, {dim: true}));
    }

    _addSyncs(view) {
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(_('Sync folders')));
        for (const sync of view.syncs) {
            this._addRow(sync, {
                actionIcon: sync.paused ? 'media-playback-start-symbolic' : 'media-playback-pause-symbolic',
                actionText: sync.paused ? _('Resume') : _('Pause'),
                onAction: () => this._act([sync.paused ? 'resume' : 'pause', '--', sync.id]),
                remove: ['remove-sync', '--', sync.id],
            });
        }
        const add = new PopupMenu.PopupMenuItem(_('Add sync…'));
        add.connect('activate', () => this._guided('mega-add-sync', [this._settings.get_string('sync-folder')]));
        this.menu.addMenuItem(add);
    }

    _addBackups(view) {
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(_('Backups')));
        for (const backup of view.backups) {
            const kept = backup.maxBackups ? String(backup.maxBackups) : '';
            this._addRow(backup, {
                actionIcon: 'emblem-system-symbolic',
                actionText: _('Change schedule and versions'),
                onAction: () => this._guided('mega-edit-backup', [backup.tag, backup.period, kept]),
                remove: ['remove-backup', '--', backup.tag],
            });
        }
        const add = new PopupMenu.PopupMenuItem(_('Add backup…'));
        add.connect('activate', () => this._guided('mega-add-backup', [this._settings.get_string('backup-folder')]));
        this.menu.addMenuItem(add);
    }

    /** Stops every timer and kills the core processes still running. */
    destroy() {
        this._destroyed = true;
        this._cancellable.cancel();
        for (const id of this._timers.values())
            GLib.source_remove(id);
        this._timers.clear();
        for (const id of this._settingsIds)
            this._settings.disconnect(id);
        super.destroy();
    }
});

/**
 * The extension: adds the MEGA button to the top bar while enabled. Its
 * notifications stay in the message tray while the screen is locked.
 */
export default class MegaExtension extends Extension {
    enable() {
        this._notifier ??= new Notifier(() => this._indicator?.menu.open());
        this._indicator = new MegaIndicator(this, this._notifier);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator.destroy();
        this._indicator = null;
        if (!Main.sessionMode.isLocked) {
            this._notifier.destroy();
            this._notifier = null;
        }
    }
}
