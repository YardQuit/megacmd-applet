# view.py: everything an applet shows for one MEGAcmd state.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the view an applet draws: MEGAcmd's state with its meaning and texts.

build_view() adds to the collected state:

    "kind", "kindText", "badgeColour"   overall state (see model.KINDS)
    "anyRunning"                        whether "pause all" applies
    "usageText", "storageLevel"         storage line and warning level
    "transfersText"                     transfer summary, one line a direction
    "syncs"[i]: "key", "kind", "badgeColour", "meta", "paused", "localDisplay"
    "backups"[i]: "key", "failed", "meta", "localDisplay"
    "notices"                           notifications to show (see notices.py)

Applets show these fields as they are, so every desktop says the same.
"""

from . import model


def build_view(status, home="", notices=None):
    """Return STATUS with its meaning and texts; HOME shortens local paths to "~"."""
    view = dict(status)
    kind = model.overall_kind(status)
    view["kind"] = kind
    view["kindText"] = model.OVERALL_TEXT[kind]
    view["badgeColour"] = model.BADGE_COLOUR[kind]
    view["anyRunning"] = model.any_running(status.get("syncs"))
    view["usageText"] = model.usage_text(status.get("usedBytes"), status.get("totalBytes"), status.get("usagePercent"))
    view["storageLevel"] = model.storage_level(status.get("usagePercent"))
    view["transfersText"] = model.transfers_text(status.get("transfers"))
    view["syncs"] = [sync_row(sync, home) for sync in status.get("syncs") or []]
    view["backups"] = [backup_row(backup, home) for backup in status.get("backups") or []]
    view["notices"] = list(notices or [])
    return view


def sync_row(sync, home):
    """SYNC with its key, state, badge colour, second line and shortened local path."""
    kind = model.sync_kind(sync)
    return {**sync, "key": model.item_key("sync", sync), "kind": kind, "badgeColour": model.BADGE_COLOUR[kind],
            "meta": model.sync_meta(sync), "paused": model.sync_paused(sync),
            "localDisplay": model.home_path(sync.get("local"), home)}


def backup_row(backup, home):
    """BACKUP with its key, whether it failed, second line and shortened local path."""
    return {**backup, "key": model.item_key("backup", backup), "failed": model.backup_failed(backup),
            "meta": model.backup_meta(backup), "localDisplay": model.home_path(backup.get("local"), home)}
