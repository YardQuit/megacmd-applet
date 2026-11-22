// rows.js: sync folder and backup rows of the MEGA extension's menu.
// SPDX-License-Identifier: GPL-3.0-or-later

import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

// Opacity of secondary text, so it follows the theme's text colour.
const DIM_OPACITY = 180;

/**
 * A plain-text label that shortens itself with an ellipsis where ELLIPSIZE
 * says when it gets less room than its text needs.
 *
 * @param {string} text - the label's text, never read as markup
 * @param {Pango.EllipsizeMode} ellipsize - where to shorten it
 * @returns {St.Label} the label
 */
function plainLabel(text, ellipsize) {
    const label = new St.Label({text, x_expand: true});
    label.clutter_text.ellipsize = ellipsize;
    return label;
}

/**
 * A round icon button with the accessible name TEXT that calls CALLBACK.
 *
 * @param {string} iconName - the symbolic icon shown
 * @param {string} text - what the button does
 * @param {Function} callback - called on click
 * @returns {St.Button} the button
 */
function iconButton(iconName, text, callback) {
    const button = new St.Button({
        style_class: 'megacmd-row-button',
        child: new St.Icon({icon_name: iconName, icon_size: 16}),
        accessible_name: text,
        can_focus: true,
        y_align: Clutter.ActorAlign.CENTER,
    });
    button.connect('clicked', () => callback());
    return button;
}

/**
 * A menu row for one sync folder or backup: a status icon, the folder pair
 * and its second line, and buttons for the row's main action, opening its
 * local folder and removing it. Clicking the row itself does nothing.
 *
 * Construct with {iconName, colour, title, meta, actionIcon, actionText,
 * armed} and the callbacks {onAction, onOpen, onRemove}. COLOUR is a badge
 * colour name the shared core gives, or empty for the text colour; ARMED
 * shows the remove button asking for confirmation. Titles longer than the
 * menu's width are shortened in the middle.
 */
export const ItemRow = GObject.registerClass(
class ItemRow extends PopupMenu.PopupBaseMenuItem {
    _init({iconName, colour, title, meta, actionIcon, actionText, armed, onAction, onOpen, onRemove}) {
        super._init({activate: false, can_focus: false});

        const iconClass = colour ? `popup-menu-icon megacmd-${colour}` : 'popup-menu-icon';
        this.add_child(new St.Icon({icon_name: iconName, style_class: iconClass}));
        const text = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
        text.add_child(plainLabel(title, Pango.EllipsizeMode.MIDDLE));
        const metaLabel = plainLabel(meta, Pango.EllipsizeMode.END);
        metaLabel.add_style_class_name('megacmd-meta');
        metaLabel.opacity = DIM_OPACITY;
        text.add_child(metaLabel);
        this.add_child(text);

        this.add_child(iconButton(actionIcon, actionText, onAction));
        this.add_child(iconButton('folder-open-symbolic', _('Open folder'), onOpen));

        this._removeIcon = new St.Icon({icon_size: 16});
        this._removeLabel = new St.Label({text: _('Remove?'), y_align: Clutter.ActorAlign.CENTER});
        const removeBox = new St.BoxLayout({style_class: 'megacmd-button-box'});
        removeBox.add_child(this._removeIcon);
        removeBox.add_child(this._removeLabel);
        this._removeButton = new St.Button({
            style_class: 'megacmd-row-button',
            child: removeBox,
            can_focus: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._removeButton.connect('clicked', () => onRemove());
        this.add_child(this._removeButton);
        this.setArmed(armed);
    }

    /**
     * Shows the remove button as asking for confirmation, or as it normally is.
     *
     * @param {boolean} armed - whether the next press removes the item
     */
    setArmed(armed) {
        this._removeIcon.icon_name = armed ? 'object-select-symbolic' : 'user-trash-symbolic';
        this._removeLabel.visible = armed;
        this._removeButton.accessible_name = armed ? _('Remove?') : _('Remove (files stay)');
    }
});

/**
 * A menu row of plain text only, such as the storage line, wrapped to the
 * menu's width.
 *
 * @param {string} text - the row's text, never read as markup
 * @param {object} [options]
 * @param {boolean} [options.warning] - shows it in the warning colour
 * @param {boolean} [options.dim] - shows it as secondary text
 * @returns {PopupMenu.PopupMenuItem} the row
 */
export function textItem(text, {warning = false, dim = false} = {}) {
    const item = new PopupMenu.PopupMenuItem(text, {reactive: false, can_focus: false});
    if (warning)
        item.label.add_style_class_name('megacmd-warning-text');
    if (dim)
        item.label.opacity = DIM_OPACITY;
    item.label.clutter_text.line_wrap = true;
    item.label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
    item.label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return item;
}
