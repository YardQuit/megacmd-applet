// rows.js: sync folder, backup and sync issue rows of the MEGA extension's menu.
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
 * Lets LABEL wrap at word (or, for long words, character) boundaries over as
 * many lines as it needs, instead of asking for more width.
 *
 * @param {St.Label} label - the label to change
 * @returns {St.Label} LABEL
 */
function wrapped(label) {
    label.clutter_text.line_wrap = true;
    label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
    label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return label;
}

/**
 * A secondary-text label that shortens itself with an ellipsis where
 * ELLIPSIZE says, or wraps to the menu's width when that is NONE.
 *
 * @param {string} text - the label's text, never read as markup
 * @param {Pango.EllipsizeMode} ellipsize - where to shorten it
 * @returns {St.Label} the label
 */
function dimLabel(text, ellipsize) {
    const label = plainLabel(text, ellipsize);
    if (ellipsize === Pango.EllipsizeMode.NONE)
        wrapped(label);
    label.add_style_class_name('megacmd-meta');
    label.opacity = DIM_OPACITY;
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
        text.add_child(dimLabel(meta, Pango.EllipsizeMode.END));
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
    wrapped(item.label);
    return item;
}

// Space between the buttons of a ButtonFlow, across and down, in pixels.
const BUTTON_SPACING = 6;

/**
 * A row of buttons that wraps onto further lines at the width it is given.
 * Each line holds as many buttons as fit, at their natural widths, from the
 * left; it never asks for more width than its widest button.
 */
const ButtonFlow = GObject.registerClass(
class ButtonFlow extends St.Widget {
    /**
     * The visible children in lines that fit WIDTH, each child with its
     * natural width and height.
     *
     * @param {number} width - the width available, in pixels
     * @returns {Array<Array<{child: Clutter.Actor, width: number, height: number}>>} the lines
     */
    _lines(width) {
        const lines = [];
        let line = [];
        let used = 0;
        for (const child of this.get_children()) {
            if (!child.visible)
                continue;
            const [, childWidth] = child.get_preferred_width(-1);
            const [, childHeight] = child.get_preferred_height(childWidth);
            if (line.length > 0 && used + BUTTON_SPACING + childWidth > width) {
                lines.push(line);
                line = [];
                used = 0;
            }
            used += (line.length > 0 ? BUTTON_SPACING : 0) + childWidth;
            line.push({child, width: childWidth, height: childHeight});
        }
        if (line.length > 0)
            lines.push(line);
        return lines;
    }

    vfunc_get_preferred_width(forHeight) {
        let minimum = 0;
        let natural = 0;
        for (const child of this.get_children()) {
            if (!child.visible)
                continue;
            const [childMinimum, childNatural] = child.get_preferred_width(-1);
            minimum = Math.max(minimum, childMinimum);
            natural = Math.max(natural, childNatural);
        }
        return this.get_theme_node().adjust_preferred_width(minimum, natural);
    }

    vfunc_get_preferred_height(forWidth) {
        const theme = this.get_theme_node();
        const width = forWidth < 0 ? Infinity : theme.adjust_for_width(forWidth);
        const height = this._lines(width).reduce((sum, line, index) =>
            sum + (index > 0 ? BUTTON_SPACING : 0) + Math.max(...line.map(item => item.height)), 0);
        return theme.adjust_preferred_height(height, height);
    }

    vfunc_allocate(box) {
        this.set_allocation(box);
        const content = this.get_theme_node().get_content_box(box);
        let y = content.y1;
        for (const line of this._lines(content.get_width())) {
            let x = content.x1;
            for (const item of line) {
                item.child.allocate(Clutter.ActorBox.new(x, y, x + item.width, y + item.height));
                x += item.width + BUTTON_SPACING;
            }
            y += Math.max(...line.map(item => item.height)) + BUTTON_SPACING;
        }
    }
});

/**
 * A menu row for one file that is not syncing: its name, its sync, what is
 * wrong with it, and a button for each way the core offers to deal with it.
 *
 * Construct with {title, syncTitle, text, lines, actions} and the callback
 * {onAction}. ACTIONS are the core's `{label, hint, args}` buttons; pressing
 * one calls onAction with its ARGS. Long names are shortened in the middle,
 * and the buttons wrap onto further lines rather than widen the menu.
 */
export const IssueItem = GObject.registerClass(
class IssueItem extends PopupMenu.PopupBaseMenuItem {
    _init({title, syncTitle, text, lines, actions, onAction}) {
        super._init({activate: false, can_focus: false});

        const box = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
        box.add_child(plainLabel(title, Pango.EllipsizeMode.MIDDLE));
        box.add_child(dimLabel(syncTitle, Pango.EllipsizeMode.MIDDLE));
        for (const line of [text, ...lines])
            box.add_child(dimLabel(line, Pango.EllipsizeMode.NONE));

        const buttons = new ButtonFlow({style_class: 'megacmd-issue-buttons', x_expand: true});
        for (const action of actions) {
            const button = new St.Button({
                style_class: 'megacmd-issue-button',
                label: action.label,
                accessible_name: action.hint,
                can_focus: true,
            });
            button.connect('clicked', () => onAction(action.args));
            buttons.add_child(button);
        }
        box.add_child(buttons);
        this.add_child(box);
    }
});
