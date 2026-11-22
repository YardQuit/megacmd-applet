// rows.js: sync folder and backup rows of the MEGA extension's menu.
// SPDX-License-Identifier: GPL-3.0-or-later

import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

/**
 * A menu row for one sync folder or backup: a status icon, the folder pair
 * and its second line, and buttons for the row's main action, opening its
 * local folder and removing it. Removing asks twice: the first click arms
 * the button for a few seconds.
 *
 * Construct with {iconName, colour, title, meta, actionIcon, actionText}
 * and the callbacks {onAction, onOpen, onRemove}; COLOUR is a badge colour
 * name the shared core gives, or empty for the text colour.
 */
export const ItemRow = GObject.registerClass(
class ItemRow extends PopupMenu.PopupBaseMenuItem {
    _init(row) {
        super._init({reactive: true, can_focus: true});
        this._row = row;
        this._disarmId = 0;

        const colour = row.colour ? ` megacmd-${row.colour}` : '';
        this.add_child(new St.Icon({icon_name: row.iconName, style_class: `popup-menu-icon${colour}`}));
        const text = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
        text.add_child(new St.Label({text: row.title}));
        text.add_child(new St.Label({text: row.meta, style_class: 'megacmd-meta'}));
        this.add_child(text);

        this.add_child(this._button(row.actionIcon, row.actionText, () => row.onAction()));
        this.add_child(this._button('folder-open-symbolic', _('Open folder'), () => row.onOpen()));
        this._removeButton = this._button('user-trash-symbolic', _('Remove (files stay)'), () => this._remove());
        this.add_child(this._removeButton);
    }

    _button(iconName, text, callback) {
        const button = new St.Button({
            style_class: 'megacmd-row-button',
            child: new St.Icon({icon_name: iconName, icon_size: 16}),
            accessible_name: text,
            y_align: Clutter.ActorAlign.CENTER,
        });
        button.connect('clicked', () => callback());
        return button;
    }

    _remove() {
        if (this._disarmId) {
            this._disarm();
            this._row.onRemove();
            return;
        }
        this._removeButton.child.icon_name = 'object-select-symbolic';
        this._removeButton.accessible_name = _('Remove?');
        this._disarmId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 4, () => {
            this._disarm();
            return GLib.SOURCE_REMOVE;
        });
    }

    _disarm() {
        if (this._disarmId)
            GLib.source_remove(this._disarmId);
        this._disarmId = 0;
        this._removeButton.child.icon_name = 'user-trash-symbolic';
        this._removeButton.accessible_name = _('Remove (files stay)');
    }

    destroy() {
        if (this._disarmId)
            GLib.source_remove(this._disarmId);
        this._disarmId = 0;
        super.destroy();
    }

    activate(event) {
        this._row.onAction();
        super.activate(event);
    }
});

/**
 * A menu row of text only, such as the storage line; ERROR shows it in the
 * warning colour.
 */
export function textItem(text, error = false) {
    const item = new PopupMenu.PopupMenuItem(text, {reactive: false, can_focus: false});
    if (error)
        item.label.add_style_class_name('megacmd-warning-text');
    item.label.clutter_text.line_wrap = true;
    return item;
}
