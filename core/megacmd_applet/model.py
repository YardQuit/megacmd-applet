# model.py: overall state, problems and display texts for MEGAcmd's state.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide what MEGAcmd's state means and how an applet shows it.

Every function takes parts of the dictionary megacmd.collect() returns and
is free of side effects. Applets show the results; none of them repeats
these rules.
"""

import hashlib
import json
import math
import posixpath
import re
from decimal import ROUND_HALF_UP, Decimal

# Overall states, most serious first: MEGAcmd not installed, its state not
# readable, its engine not running, nobody logged in, then the syncs' states.
KINDS = ("missing", "unknown", "stopped", "off", "error", "warning", "paused", "syncing", "synced")

OVERALL_TEXT = {
    "missing": "MEGAcmd is not installed",
    "unknown": "Could not read MEGAcmd",
    "stopped": "MEGAcmd is not running",
    "off": "Not logged in",
    "error": "A sync needs attention",
    "warning": "Storage almost full",
    "paused": "Syncing paused",
    "syncing": "Syncing",
    "synced": "Up to date",
}
# The "warning" state's text when files are not syncing, rather than storage running out.
ISSUES_TEXT = "Some files are not syncing"

# Colour name of each overall state's badge; applets map it to their theme.
BADGE_COLOUR = {
    "missing": "orange",
    "unknown": "orange",
    "stopped": "orange",
    "off": "orange",
    "error": "red",
    "warning": "orange",
    "paused": "yellow",
    "syncing": "blue",
    "synced": "green",
}

# What an applet offers when nobody is logged in: its button text and hint.
# Both open the guided dialog mega-account-login, which starts MEGAcmd too.
OFFER_TEXT = {"login": "Log in to MEGA", "start": "Start MEGAcmd"}
OFFER_HINT = {
    "login": "Opens a terminal to log in to your MEGA account.",
    "start": "Opens a terminal that starts MEGAcmd and asks you to log in if needed.",
}

# The error MEGAcmd gives a sync with issues, e.g. "Sync Issues (2)".
SYNC_ISSUES = re.compile(r"Sync Issues \((\d+)\)")

# The ways to settle a conflict between a local and a cloud copy: button text and hint.
CHOICES = (
    ("both", "Keep both", "Renames MEGA's copy, so both copies stay in the folder."),
    ("local", "Keep this computer's", "Moves MEGA's copy to the MEGA Rubbish bin; this computer's copy is uploaded."),
    ("cloud", "Keep MEGA's", "Moves this computer's copy to the Trash; MEGA's copy is downloaded."),
)

# Sync run states that mean the sync is not running.
PAUSED_RUN_STATES = ("Disabled", "Suspended", "Paused")

# Backup run states that mean the backup did not complete.
FAILED_BACKUP = re.compile(r"INCOMPLETE|ABORTED|MISCARRIED|FAILED")

# Backup row states and their badge colours ("" for none).
BACKUP_COLOUR = {"error": "red", "synced": "green", "pending": ""}

UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
# Units of MEGAcmd's period format, e.g. "1m12d3h": "m" is months, "M" minutes.
PERIOD_UNITS = {"y": "year", "m": "month", "d": "day", "h": "hour", "M": "minute", "s": "second"}
PERIOD_PART = re.compile(r"(\d+)([ymdhMs])")
WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def number(value):
    """Return VALUE (a number or text) as a finite float, or 0.0 when it is missing or not a number."""
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def js_round(value):
    """VALUE rounded to a whole number, halves upwards, as JavaScript's Math.round does."""
    return math.floor(value + 0.5)


def fixed(value, digits):
    """VALUE with DIGITS decimals, as JavaScript's toFixed gives it.

    Like toFixed, it rounds the exact binary value, halves away from zero,
    so 1.005 gives "1.00" (it is stored as 1.00499...).
    """
    return str(Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def grouped(count):
    """COUNT as a whole number with thousands separated by commas, e.g. "1,200"."""
    return f"{js_round(number(count)):,}"


def format_bytes(count):
    """A byte count with binary units, e.g. "2.51 TB"."""
    value = number(count)
    unit = 0
    while value >= 1024 and unit < len(UNITS) - 1:
        value /= 1024
        unit += 1
    digits = 0 if unit == 0 else 0 if value >= 100 else 1 if value >= 10 else 2
    return f"{fixed(value, digits)} {UNITS[unit]}"


def storage_percent(status):
    """STATUS's storage use in percent, between 0 and 100; 0 when the total is unknown."""
    if number(status.get("totalBytes")) <= 0:
        return 0.0
    return min(max(number(status.get("usagePercent")), 0.0), 100.0)


def usage_text(status):
    """STATUS's storage use, e.g. "2.51 TB of 3.00 TB (84%)", or "" when the total is unknown."""
    total = number(status.get("totalBytes"))
    if total <= 0:
        return ""
    return f"{format_bytes(status.get('usedBytes'))} of {format_bytes(total)} ({js_round(storage_percent(status))}%)"


def sync_paused(sync):
    """True when SYNC is paused or otherwise not running."""
    return str((sync or {}).get("runState") or "") in PAUSED_RUN_STATES


def issue_count(sync):
    """The number of sync issues SYNC reports, 0 for none."""
    match = SYNC_ISSUES.fullmatch(str((sync or {}).get("error") or ""))
    return int(match.group(1)) if match else 0


def plural(count, word):
    """COUNT and WORD, with an "s" unless COUNT is 1, e.g. "2 files"."""
    return f"{grouped(count)} {word}" + ("" if count == 1 else "s")


def any_running(syncs):
    """True when at least one of SYNCS runs, so "pause all" applies; else "resume all"."""
    return any(not sync_paused(sync) for sync in syncs or [])


def item_key(kind, item):
    """Identify a sync ("sync:<id>") or backup ("backup:<tag>") across refreshes; "" without ITEM."""
    if not item:
        return ""
    return f"{kind}:{item.get('id') if kind == 'sync' else item.get('tag')}"


def sync_kind(sync):
    """One of "error", "paused", "warning" (some files not syncing), "syncing", "synced" for a sync."""
    if not sync:
        return "synced"
    if sync.get("error") and not issue_count(sync):
        return "error"
    if sync_paused(sync):
        return "paused"
    if issue_count(sync):
        return "warning"
    status = str(sync.get("status") or "")
    if status == "Synced":
        return "synced"
    if status in ("Failed", "Error"):
        return "error"
    return "syncing"


def sync_meta(sync):
    """Second line of a sync row, e.g. "Synced · 947 files · 157.51 MB"."""
    if not sync:
        return ""
    kind = sync_kind(sync)
    if kind == "error":
        parts = ["Error: " + str(sync.get("error"))]
    elif kind == "paused":
        parts = ["Paused"]
    elif kind == "warning":
        parts = [plural(issue_count(sync), "file") + " not syncing"]
    else:
        parts = [str(sync.get("status") or "Syncing")]
    parts.append(grouped(sync.get("files")) + " files")
    if sync.get("size"):
        parts.append(str(sync["size"]))
    return " · ".join(parts)


def home_path(path, home):
    """PATH with the home folder HOME shortened to "~"."""
    value = str(path or "")
    base = str(home or "")
    if base and (value == base or value.startswith(base + "/")):
        return "~" + value[len(base):]
    return value


def weekday_name(field):
    """The weekday a cron weekday FIELD names ("0" to "7" or "sun" to "sat"), or ""."""
    if field.isdigit() and int(field) <= 7:
        return WEEKDAYS[int(field) % 7]
    names = [day[:3].lower() for day in WEEKDAYS]
    return WEEKDAYS[names.index(field.lower())] if field.lower() in names else ""


def cron_text(fields):
    """A readable schedule for the six fields of a MEGAcmd cron line, or "" when it is not a simple one.

    Simple ones run hourly, daily or weekly at a fixed time; MEGAcmd reads
    cron times as UTC.
    """
    second, minute, hour, day, month, weekday = fields
    if day != "*" or month != "*" or not (second.isdigit() and minute.isdigit()):
        return ""
    if int(second) > 59 or int(minute) > 59:
        return ""
    if hour == "*":
        return f"Hourly at :{int(minute):02}" if weekday == "*" and int(second) == 0 else ""
    if not hour.isdigit() or int(hour) > 23:
        return ""
    time = f"{int(hour):02}:{int(minute):02}" + (f":{int(second):02}" if int(second) else "") + " UTC"
    if weekday == "*":
        return "Daily at " + time
    name = weekday_name(weekday)
    return f"Weekly on {name} at {time}" if name else ""


def period_text(period):
    """A readable backup schedule from MEGAcmd's period string (a time like "6h" or a cron line)."""
    value = str(period or "").strip()
    fields = value.split()
    if len(fields) == 6:
        return cron_text(fields) or value
    if not re.fullmatch(r"(?:\d+[ymdhMs])+", value):
        return value
    parts = [(int(count), PERIOD_UNITS[unit]) for count, unit in PERIOD_PART.findall(value)]
    if len(parts) == 1 and parts[0][0] == 1:
        return f"Every {parts[0][1]}"
    return "Every " + ", ".join(f"{count} {name}" + ("" if count == 1 else "s") for count, name in parts)


def backup_meta(backup):
    """Second line of a backup row, e.g. "Daily at 02:00 · keeps 14 · last complete"."""
    if not backup:
        return ""
    parts = [period_text(backup.get("period"))]
    if backup.get("maxBackups"):
        parts.append(f"keeps {backup['maxBackups']}")
    if backup.get("lastStatus"):
        parts.append("last " + str(backup["lastStatus"]).lower())
    else:
        parts.append("no backup yet")
    return " · ".join(parts)


def backup_failed(backup):
    """True when BACKUP's last run did not complete."""
    return bool(FAILED_BACKUP.search(str((backup or {}).get("lastStatus") or "")))


def backup_kind(backup):
    """One of "error" (last run failed), "synced" (last run complete) or "pending" (none yet) for a backup."""
    if backup_failed(backup):
        return "error"
    if str((backup or {}).get("lastStatus") or "") == "COMPLETE":
        return "synced"
    return "pending"


def sync_title(sync, home):
    """A sync row's title, e.g. "~/Documents ↔ /Sync/Documents"."""
    return f"{home_path(sync.get('local'), home)} ↔ {sync.get('remote') or ''}"


def backup_title(backup, home):
    """A backup row's title, e.g. "~/Pictures → /Backups"."""
    return f"{home_path(backup.get('local'), home)} → {backup.get('remote') or ''}"


def transfer_line(count, direction, done, total, percent):
    """One direction of a transfer summary, e.g. "6,838 down · 6.35 GB of 42.49 GB (15%)"."""
    return f"{grouped(count)} {direction} · {done} of {total} ({js_round(number(percent))}%)"


def transfers_text(transfers):
    """Transfer summary, one line per direction with transfers, or ""."""
    if not transfers:
        return ""
    lines = []
    if number(transfers.get("downloads")) > 0:
        lines.append(transfer_line(transfers["downloads"], "down", transfers.get("downloaded"),
                                   transfers.get("downloadTotal"), transfers.get("downloadPercent")))
    if number(transfers.get("uploads")) > 0:
        lines.append(transfer_line(transfers["uploads"], "up", transfers.get("uploaded"),
                                   transfers.get("uploadTotal"), transfers.get("uploadPercent")))
    return "\n".join(lines)


def storage_level(percent):
    """Storage warning level for a usage percentage: 0, 90 or 95."""
    value = number(percent)
    if value >= 95:
        return 95
    if value >= 90:
        return 90
    return 0


def overall_kind(status):
    """The overall state for the panel icon, most serious first (see KINDS).

    "unknown" also covers a logged-in state whose syncs could not be read.
    """
    status = status or {}
    if status.get("ok") is False:
        return "unknown"
    if status.get("installed") is False:
        return "missing"
    if status.get("running") is False:
        return "stopped"
    if not status.get("loggedIn"):
        return "off"
    syncs = status.get("syncs") or []
    transfers = status.get("transfers") or {}
    kinds = [sync_kind(sync) for sync in syncs]
    if "error" in kinds:
        return "error"
    if "syncs" in (status.get("unread") or []):
        return "unknown"
    if "warning" in kinds:
        return "warning"
    if storage_level(storage_percent(status)) > 0:
        return "warning"
    if syncs and all(kind == "paused" for kind in kinds):
        return "paused"
    if "syncing" in kinds:
        return "syncing"
    if number(transfers.get("downloads")) + number(transfers.get("uploads")) > 0:
        return "syncing"
    return "synced"


def overall_text(status, kind):
    """The text of the overall state KIND of STATUS (see overall_kind)."""
    if kind == "warning" and any(sync_kind(sync) == "warning" for sync in (status or {}).get("syncs") or []):
        return ISSUES_TEXT
    return OVERALL_TEXT[kind]


def issue_name(issue):
    """The name of the file or folder ISSUE is about, from its first path; "" without paths."""
    paths = (issue or {}).get("paths") or []
    return posixpath.basename(str(paths[0].get("path") or "").rstrip("/")) if paths else ""


def issue_conflict(issue):
    """The (local, cloud) paths of ISSUE when it is a choice between two copies of a file, else None.

    That is when it has exactly one local and one cloud path, both files of
    the same name, and MEGAcmd finds nothing wrong with either of them.
    """
    paths = (issue or {}).get("paths") or []
    local = [path for path in paths if not path.get("cloud")]
    cloud = [path for path in paths if path.get("cloud")]
    if len(paths) != 2 or len(local) != 1 or len(cloud) != 1:
        return None
    if any(path.get("problem") or not path.get("size") for path in paths):
        return None
    if posixpath.basename(local[0].get("path") or "") != posixpath.basename(cloud[0].get("path") or ""):
        return None
    return local[0], cloud[0]


def issue_version(issue):
    """A short fingerprint of ISSUE's paths, dates and sizes, which changes whenever one of them does.

    It leaves out the issue's ID, which MEGAcmd changes whenever it looks at
    its syncs again, so the same conflict keeps its fingerprint.
    """
    data = json.dumps((issue or {}).get("paths"), sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def issue_text(issue):
    """What is wrong in ISSUE, in a sentence."""
    if issue_conflict(issue):
        return "The copy on this computer and the copy on MEGA differ. Choose which to keep."
    return str((issue or {}).get("reason") or "MEGA cannot sync this.")


def copy_line(where, path, newer):
    """A line about one copy of a file, e.g. "On MEGA: 2026-11-22 13:06 · 31.36 KB · newer"."""
    parts = [str(path.get("modified") or "")[:16], str(path.get("size") or "")]
    if newer:
        parts.append("newer")
    return f"{where}: " + " · ".join(part for part in parts if part)


def issue_lines(issue, home):
    """The lines describing ISSUE's paths: each copy's date and size for a conflict, else each path."""
    conflict = issue_conflict(issue)
    if conflict:
        local, cloud = conflict
        local_date, cloud_date = str(local.get("modified") or ""), str(cloud.get("modified") or "")
        return [copy_line("On this computer", local, local_date > cloud_date),
                copy_line("On MEGA", cloud, cloud_date > local_date)]
    lines = []
    for path in (issue or {}).get("paths") or []:
        where = "On MEGA" if path.get("cloud") else "On this computer"
        shown = path.get("path") if path.get("cloud") else home_path(path.get("path"), home)
        problem = f" ({path['problem']})" if path.get("problem") else ""
        lines.append(f"{where}: {shown}{problem}")
    return lines


def issue_folder(issue, sync):
    """The local folder to open for ISSUE of SYNC: the folder its local path names or lies in, else SYNC's."""
    for path in (issue or {}).get("paths") or []:
        if not path.get("cloud"):
            local = str(path.get("path") or "")
            return local if not path.get("size") else posixpath.dirname(local)
    return str((sync or {}).get("local") or "")


def offer(status):
    """What to offer instead of the account: "start", "login" or "" (see OFFER_TEXT)."""
    kind = overall_kind(status)
    return {"stopped": "start", "off": "login"}.get(kind, "")


def problems(status):
    """Current problems worth a notification, each {kind, key, title, body}.

    KIND is "sync", "issue" or "backup"; the key identifies the problem, so the same
    problem is reported once. The texts name no folder: notification texts
    can reach other programs, and the panel a notification opens shows the
    folder.
    """
    found = []
    if not status or not status.get("loggedIn"):
        return found
    for sync in status.get("syncs") or []:
        if sync_kind(sync) != "error":
            continue
        reason = sync.get("error") or sync.get("status")
        found.append({"kind": "sync", "key": f"sync:{sync.get('id')}:{reason}", "title": "MEGA sync stopped",
                      "body": f"{reason}. Open the MEGA panel to see which folder."})
    for issue in status.get("issues") or []:
        if issue_conflict(issue):
            title, body = "MEGA: a file has two different copies", "Open the MEGA panel to choose which to keep."
        else:
            title, body = "MEGA: a file is not syncing", "Open the MEGA panel to see which file."
        found.append({"kind": "issue", "key": f"issue:{issue.get('id')}", "title": title, "body": body})
    for backup in status.get("backups") or []:
        if not backup_failed(backup):
            continue
        found.append({"kind": "backup", "key": f"backup:{backup.get('tag')}:{backup.get('lastName')}",
                      "title": "MEGA backup " + str(backup.get("lastStatus")).lower(),
                      "body": f"Last run {backup.get('lastDate')}. Open the MEGA panel to see which folder."})
    return found


def problem_group(kind, count):
    """Title and body of one notification for COUNT problems of KIND ("sync", "issue" or "backup")."""
    if kind == "issue":
        return {"title": f"MEGA: {count} files are not syncing", "body": "Open the MEGA panel to see which files."}
    title = f"MEGA: {count} syncs stopped" if kind == "sync" else f"MEGA: {count} backups did not complete"
    return {"title": title, "body": "Open the MEGA panel to see which folders."}
