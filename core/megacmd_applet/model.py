# model.py: overall state, problems and display texts for MEGAcmd's state.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide what MEGAcmd's state means and how an applet shows it.

Every function takes parts of the dictionary megacmd.collect() returns and
is free of side effects. Applets show the results; none of them repeats
these rules.
"""

import math
import re
from decimal import ROUND_HALF_UP, Decimal

# Overall states, most serious first.
KINDS = ("stopped", "off", "error", "warning", "paused", "syncing", "synced")

OVERALL_TEXT = {
    "stopped": "MEGAcmd is not running",
    "off": "Not logged in",
    "error": "A sync needs attention",
    "warning": "Storage almost full",
    "paused": "Syncing paused",
    "syncing": "Syncing",
    "synced": "Up to date",
}

# Colour name of each overall state's badge; applets map it to their theme.
BADGE_COLOUR = {
    "stopped": "orange",
    "off": "orange",
    "error": "red",
    "warning": "orange",
    "paused": "yellow",
    "syncing": "blue",
    "synced": "green",
}

# Backup run states that mean the backup did not complete.
FAILED_BACKUP = re.compile(r"INCOMPLETE|ABORTED|MISCARRIED|FAILED")

UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
PERIOD_UNITS = {"d": "day", "h": "hour", "m": "minute", "s": "second"}


def number(value):
    """Return VALUE as a float, or 0.0 when it is missing or not a number."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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


def usage_text(used, total, percent):
    """"2.51 TB of 3.00 TB (84%)", or "" when the total is unknown."""
    if not number(total):
        return ""
    return f"{format_bytes(used)} of {format_bytes(total)} ({js_round(number(percent))}%)"


def sync_paused(sync):
    """True when SYNC is paused or otherwise not running."""
    return str((sync or {}).get("runState") or "") in ("Disabled", "Suspended")


def any_running(syncs):
    """True when at least one of SYNCS runs, so "pause all" applies; else "resume all"."""
    return any(not sync_paused(sync) for sync in syncs or [])


def item_key(kind, item):
    """Identify a sync ("sync:<id>") or backup ("backup:<tag>") across refreshes; "" without ITEM."""
    if not item:
        return ""
    return f"{kind}:{item.get('id') if kind == 'sync' else item.get('tag')}"


def sync_kind(sync):
    """One of "error", "paused", "syncing", "synced" for a sync."""
    if not sync:
        return "synced"
    if sync.get("error"):
        return "error"
    if sync_paused(sync):
        return "paused"
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


def period_text(period):
    """A readable backup schedule from MEGAcmd's period string."""
    value = str(period or "").strip()
    cron = value.split()
    if len(cron) == 6:
        time = cron[2].rjust(2, "0")[-2:] + ":" + cron[1].rjust(2, "0")[-2:]
        if cron[3] == "*" and cron[4] == "*" and cron[5] == "*":
            return "Daily at " + time
        if cron[3] == "*" and cron[4] == "*":
            return "Weekly at " + time
        return value
    match = re.fullmatch(r"(\d+)([dhms])", value)
    if match:
        count = int(match.group(1))
        name = PERIOD_UNITS[match.group(2)]
        return f"Every {name}" if count == 1 else f"Every {count} {name}s"
    return value


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
    """The overall state for the panel icon, most serious first (see KINDS)."""
    if status and status.get("running") is False:
        return "stopped"
    if not status or not status.get("loggedIn"):
        return "off"
    syncs = status.get("syncs") or []
    transfers = status.get("transfers") or {}
    kinds = [sync_kind(sync) for sync in syncs]
    if "error" in kinds:
        return "error"
    if storage_level(status.get("usagePercent")) > 0:
        return "warning"
    if syncs and all(kind == "paused" for kind in kinds):
        return "paused"
    if "syncing" in kinds:
        return "syncing"
    if number(transfers.get("downloads")) + number(transfers.get("uploads")) > 0:
        return "syncing"
    return "synced"


def problems(status):
    """Current problems worth a notification, each {key, title, body}.

    The key identifies the problem, so the same problem is reported once.
    The texts name no folder: notification texts can reach other programs,
    and the panel a notification opens shows the folder.
    """
    found = []
    if not status or not status.get("loggedIn"):
        return found
    for sync in status.get("syncs") or []:
        if sync_kind(sync) != "error":
            continue
        reason = sync.get("error") or sync.get("status")
        found.append({"key": f"sync:{sync.get('id')}:{reason}", "title": "MEGA sync stopped",
                      "body": f"{reason}. Open the MEGA panel to see which folder."})
    for backup in status.get("backups") or []:
        if not backup_failed(backup):
            continue
        found.append({"key": f"backup:{backup.get('tag')}:{backup.get('lastName')}",
                      "title": "MEGA backup " + str(backup.get("lastStatus")).lower(),
                      "body": f"Last run {backup.get('lastDate')}. Open the MEGA panel to see which folder."})
    return found
