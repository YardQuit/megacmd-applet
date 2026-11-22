// notifications.js: the MEGA extension's notifications in the message tray.
// SPDX-License-Identifier: GPL-3.0-or-later

import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as MessageTray from 'resource:///org/gnome/shell/ui/messageTray.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

// The symbolic icon of each notice icon the shared core names.
const NOTICE_ICONS = {
    error: 'dialog-error-symbolic',
    off: 'network-offline-symbolic',
    cloud: 'weather-overcast-symbolic',
};

/**
 * Shows the shared core's notices in the message tray, under one source
 * that is made when the first notice arrives and goes away with its last
 * notification.
 */
export class Notifier {
    /**
     * @param {Function} onActivated - called when a notification is clicked
     */
    constructor(onActivated) {
        this._onActivated = onActivated;
        this._source = null;
    }

    /**
     * Shows one notice, its title and body as plain text.
     *
     * @param {{title: string, body: string, urgency: string, icon: string}} notice -
     *   a notice from the core's view
     * @param {boolean} preview - whether the notice comes from a preview, which
     *   its title then says
     */
    show(notice, preview) {
        const title = String(notice.title);
        const notification = new MessageTray.Notification({
            source: this._ensureSource(),
            title: preview ? _('%s (preview)').format(title) : title,
            body: String(notice.body),
            gicon: new Gio.ThemedIcon({name: NOTICE_ICONS[notice.icon] ?? NOTICE_ICONS.error}),
            urgency: notice.urgency === 'critical' ? MessageTray.Urgency.CRITICAL : MessageTray.Urgency.NORMAL,
        });
        notification.connect('activated', () => this._onActivated());
        this._source.addNotification(notification);
    }

    _ensureSource() {
        if (!this._source) {
            this._source = new MessageTray.Source({title: _('MEGA'), iconName: 'folder-remote-symbolic'});
            this._source.connect('destroy', () => {
                this._source = null;
            });
            Main.messageTray.add(this._source);
        }
        return this._source;
    }

    /** Removes the source and its notifications from the message tray. */
    destroy() {
        this._source?.destroy();
    }
}
