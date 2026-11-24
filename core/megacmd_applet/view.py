# view.py: everything an applet shows for one MEGAcmd state.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the view an applet draws: MEGAcmd's state with its meaning and texts.

build_view() fills in every field of the collected state (see megacmd.py)
and adds:

    "kind", "kindText", "badgeColour"   overall state (see model.KINDS)
    "offer", "offerText", "offerHint"   what to offer when not logged in:
                                        "start", "login" or "" (nothing)
    "anyRunning"                        whether "pause all" applies
    "usageText", "storageLevel"         storage line and warning level
    "transfersText"                     transfer summary, one line a direction
    "syncs"[i]: "key", "title", "kind", "badgeColour", "meta", "paused",
                "localDisplay"
    "issues"[i]: "key", "title", "text", "lines", "syncTitle", "actions"
                                        the first sync issues: the file's
                                        name, what is wrong, one line per
                                        copy or path, the sync's title, and
                                        buttons, each {"label", "hint",
                                        "args"}: the core command line to
                                        run when it is pressed
    "issuesMoreText"                    how many more files are not syncing,
                                        or ""
    "backups"[i]: "key", "title", "kind", "badgeColour", "failed", "meta",
                  "localDisplay"
    "notices"                           notifications to show (see notices.py)

When "ok" is false the state could not be read: "kind" is "unknown",
"kindText" and "error" say why, "loggedIn" is false and "offer" is "".
Otherwise "error" is a note to show under the state, or "".

Applets show these fields as they are, so every desktop says the same.
"""

from . import megacmd, model

# Most sync issues the view shows; the rest are counted in "issuesMoreText".
ISSUES_SHOWN = 5


def build_view(status, home="", notices=None):
    """Return STATUS with its meaning and texts; HOME shortens local paths to "~"."""
    view = {**megacmd.blank_status(), **status}
    kind = model.overall_kind(view)
    if not view["ok"]:
        view["loggedIn"] = False
        view["error"] = view["error"] or model.OVERALL_TEXT["unknown"]
    view["kind"] = kind
    view["kindText"] = view["error"] if not view["ok"] else model.overall_text(view, kind)
    view["badgeColour"] = model.BADGE_COLOUR[kind]
    view["offer"] = model.offer(view)
    view["offerText"] = model.OFFER_TEXT.get(view["offer"], "")
    view["offerHint"] = model.OFFER_HINT.get(view["offer"], "")
    view["anyRunning"] = model.any_running(view["syncs"])
    view["usageText"] = model.usage_text(view)
    view["storageLevel"] = model.storage_level(model.storage_percent(view))
    view["transfersText"] = model.transfers_text(view["transfers"])
    issues = view["issues"] or []
    view["issues"] = [issue_row(issue, view["syncs"], home) for issue in issues[:ISSUES_SHOWN]]
    view["issuesMoreText"] = issues_more_text(view["syncs"], len(issues), len(view["issues"]))
    view["syncs"] = [sync_row(sync, home) for sync in view["syncs"] or []]
    view["backups"] = [backup_row(backup, home) for backup in view["backups"] or []]
    view["notices"] = list(notices or [])
    return view


def sync_row(sync, home):
    """SYNC with its key, title, state, badge colour, second line and shortened local path."""
    kind = model.sync_kind(sync)
    return {**sync, "key": model.item_key("sync", sync), "title": model.sync_title(sync, home), "kind": kind,
            "badgeColour": model.BADGE_COLOUR[kind], "meta": model.sync_meta(sync), "paused": model.sync_paused(sync),
            "localDisplay": model.home_path(sync.get("local"), home)}


def backup_row(backup, home):
    """BACKUP with its key, title, state, badge colour, whether it failed, second line and shortened local path."""
    kind = model.backup_kind(backup)
    return {**backup, "key": model.item_key("backup", backup), "title": model.backup_title(backup, home),
            "kind": kind, "badgeColour": model.BACKUP_COLOUR[kind], "failed": model.backup_failed(backup),
            "meta": model.backup_meta(backup), "localDisplay": model.home_path(backup.get("local"), home)}


def issue_row(issue, syncs, home):
    """ISSUE with its key, title, text, lines, its sync's title and the buttons that settle it.

    A conflict between two copies gets one button for each of model.CHOICES,
    which runs `resolve ID CHOICE VERSION`; any other issue gets one that
    opens its folder.
    """
    sync = next((sync for sync in syncs or [] if sync.get("id") == issue.get("syncId")), None)
    if model.issue_conflict(issue):
        version = model.issue_version(issue)
        actions = [{"label": label, "hint": hint, "args": ["resolve", str(issue.get("id")), choice, version]}
                   for choice, label, hint in model.CHOICES]
    else:
        folder = model.issue_folder(issue, sync)
        actions = [{"label": "Open folder", "hint": "Opens the folder in the file manager.",
                    "args": ["open-folder", folder]}] if folder else []
    return {**issue, "key": f"issue:{issue.get('id')}", "title": model.issue_name(issue) or "Unnamed item",
            "text": model.issue_text(issue), "lines": model.issue_lines(issue, home),
            "syncTitle": model.sync_title(sync, home) if sync else "", "actions": actions}


def issues_more_text(syncs, listed, shown):
    """How many more files are not syncing than the SHOWN of the LISTED issues, or "" for none."""
    total = max(sum(model.issue_count(sync) for sync in syncs or []), listed)
    if total <= shown:
        return ""
    return model.plural(total - shown, "more file") + " not syncing; list them with mega-sync-issues in a terminal."
