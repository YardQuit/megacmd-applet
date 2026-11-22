# megacmd.py: read the MEGAcmd account, sync, backup and transfer state.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect MEGAcmd's state.

Runs the mega-* client commands, which talk to the running MEGAcmd engine,
and returns one dictionary:

    {"ok", "installed", "running", "loggedIn", "email", "usedBytes",
     "totalBytes", "usagePercent", "syncs": [...], "backups": [...],
     "transfers": {...}, "unread": [...], "error"}

When the MEGAcmd engine (mega-cmd-server) is not running, "running" is false
and no mega-* command runs: each of them would start the engine again.

"ok" is false when it cannot be told whether anyone is logged in (MEGAcmd
busy or failing); "error" then says why. When logged in, "unread" names the
parts ("storage", "syncs", "backups", "transfers") whose command failed or
timed out, and "error" carries a note about them; those parts are left empty
and must not be taken for "nothing there".
"""

import json
import os
import re
import shutil
import signal
import subprocess

from .model import number

SYNC_COLUMNS = ["ID", "LOCALPATH", "REMOTEPATH", "RUN_STATE", "STATUS", "ERROR", "SIZE", "FILES", "DIRS"]
# Column separator for the sync table: the ASCII unit separator, which a
# folder name cannot contain, unlike "|".
SEPARATOR = "\x1f"
# A MEGAcmd sync ID; it never starts with "-", so it cannot pass for an option.
SYNC_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*")
WIDE_PATHS = "--path-display-size=4096"
ROW_SPLIT = re.compile(r"\s{2,}")
BACKUP_ROW = re.compile(r"(\d+)\s+(/.*\S)\s{2,}(/.*\S)\s{2,}(\S+)\s*")
HISTORY_ROW = re.compile(r"\s+(.*\S)\s{2,}(\w{3}, .*?\d{4} \d\d:\d\d:\d\d [+-]\d{4})\s+(\S+).*")
# The start of a MEGAcmd error message, e.g. "[API:err: 10:00:00]" or "[10:00:00 ERR".
MEGA_ERROR = re.compile(r"\[[^\]]*\bERR\b", re.IGNORECASE)
NOT_LOGGED_IN = re.compile(r"not logged in", re.IGNORECASE)

# Exit statuses run() reports for a command that timed out or could not start.
TIMED_OUT = 124
NOT_FOUND = 127


def run(args, timeout):
    """Run the command ARGS without a shell and return (exit status, output).

    The output is standard output followed by standard error, decoded as
    UTF-8 with undecodable bytes replaced. The command runs in a process
    group of its own; when it takes longer than TIMEOUT seconds the whole
    group is killed and the status is TIMED_OUT. A command that cannot be
    started gives NOT_FOUND.
    """
    try:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except OSError:
        return NOT_FOUND, ""
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.stdout.close()
        process.stderr.close()
        process.wait()
        return TIMED_OUT, ""
    return process.returncode, (out + err).decode("utf-8", "replace")


def error_text(output):
    """MEGAcmd's error message in OUTPUT, without its "[... ERR" prefix and brackets.

    Handles both "[API:10:00:00 ERR message]" and "[API:err: 10:00:00]
    message"; gives "MEGA command failed" when nothing is left.
    """
    text = output.strip()
    match = MEGA_ERROR.match(text)
    if match:
        inside, _, after = text[match.end():].partition("]")
        text = (after.strip() or inside).strip(" :")
    return text or "MEGA command failed"


def is_error(output):
    """True when OUTPUT starts with a MEGAcmd error message."""
    return bool(MEGA_ERROR.match(output.strip()))


def failed(code, output):
    """True when a listing command with exit status CODE and OUTPUT did not answer.

    That is when it timed out, could not start, or exited non-zero with a
    MEGAcmd error or nothing at all; a non-zero status with a plain message
    (such as "No backup configured.") still counts as an answer.
    """
    if code in (TIMED_OUT, NOT_FOUND):
        return True
    return code != 0 and (is_error(output) or not output.strip())


def engine_running():
    """True when this user's MEGAcmd engine is running; checked without starting it."""
    code, _ = run(["pgrep", "-u", str(os.getuid()), "-x", "mega-cmd-server"], 10)
    return code in (0, NOT_FOUND)


def parse_storage(text):
    """Return (used, total, percent) in bytes from `mega-df` output; zeroes without a storage line.

    The exact used byte count is taken when mega-df prints it whole, else it
    is worked out from the percentage.
    """
    match = re.search(r"USED STORAGE:\s*(\S+)\s+(\d+(?:\.\d+)?)%\s+of\s+(\d+)", text)
    if not match:
        return 0, 0, 0.0
    percent = number(match.group(2))
    total = int(match.group(3))
    used = int(match.group(1)) if match.group(1).isdigit() else int(total * percent / 100)
    return used, total, percent


def parse_syncs(text):
    """Return (syncs, unreadable) from `mega-sync` output separated by SEPARATOR.

    A line is a sync only when it has every column, a valid sync ID and an
    absolute local path; any other line except the header and blank lines is
    counted as unreadable. A folder name containing a line break therefore
    cannot pose as a sync of its own.
    """
    syncs = []
    unreadable = 0
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(SEPARATOR)]
        if not line.strip() or parts[0] == "ID":
            continue
        if len(parts) != len(SYNC_COLUMNS) or not SYNC_ID.fullmatch(parts[0]) or not parts[1].startswith("/"):
            unreadable += 1
            continue
        row = dict(zip(SYNC_COLUMNS, parts, strict=True))
        syncs.append({
            "id": row["ID"],
            "local": row["LOCALPATH"],
            "remote": row["REMOTEPATH"],
            "runState": row["RUN_STATE"],
            "status": row["STATUS"],
            "error": "" if row["ERROR"] in ("", "NO") else row["ERROR"],
            "size": re.sub(r"\s+", " ", row["SIZE"]),
            "files": int(number(row["FILES"])),
            "dirs": int(number(row["DIRS"])),
        })
    return syncs, unreadable


def split_backup_row(line):
    """Split a backup table row (TAG LOCALPATH REMOTEPARENTPATH STATUS); None for other lines."""
    match = BACKUP_ROW.fullmatch(line)
    if not match:
        return None
    return {"tag": match.group(1), "local": match.group(2), "remote": match.group(3), "state": match.group(4)}


def parse_backups(text):
    """Return the backups in `mega-backup -l -h` output, each with its newest history entry.

    The output lists each backup as a table row followed by its details and
    its history of backups, oldest first.
    """
    backups = {}
    order = []
    current = None
    in_history = False
    for line in text.splitlines():
        row = split_backup_row(line)
        if row:
            current = backups.get(row["tag"])
            if current is None:
                row.update({"maxBackups": 0, "period": "", "next": "", "lastName": "", "lastDate": "", "lastStatus": ""})
                current = backups[row["tag"]] = row
                order.append(row["tag"])
            in_history = False
            continue
        if current is None:
            continue
        stripped = line.strip()
        if "HISTORY OF BACKUPS" in line:
            in_history = True
        elif in_history:
            entry = HISTORY_ROW.fullmatch(line)
            if entry and not stripped.startswith("NAME"):
                current["lastName"], current["lastDate"], current["lastStatus"] = entry.groups()
        elif stripped.startswith("Max Backups:"):
            current["maxBackups"] = int(number(stripped.split(":", 1)[1]))
        elif stripped.startswith("Period:"):
            current["period"] = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("Next backup scheduled for:"):
            current["next"] = stripped.split(":", 1)[1].strip()

    return [backups[tag] for tag in order]


def parse_transfers(text):
    """Return download and upload counts and progress from `mega-transfers --summary`."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or "NUM DOWNLOADS" not in lines[0]:
        return {"downloads": 0, "uploads": 0, "downloaded": "", "downloadTotal": "", "uploaded": "", "uploadTotal": "",
                "downloadPercent": 0.0, "uploadPercent": 0.0}
    # NUM, DONE, TOTAL, % for downloads, then the same for uploads.
    values = [re.sub(r"\s+", " ", v) for v in ROW_SPLIT.split(lines[1].strip())]
    values += [""] * (8 - len(values))
    return {
        "downloads": int(number(values[0])), "downloaded": values[1], "downloadTotal": values[2],
        "downloadPercent": number(values[3].rstrip("%")),
        "uploads": int(number(values[4])), "uploaded": values[5], "uploadTotal": values[6],
        "uploadPercent": number(values[7].rstrip("%")),
    }


def load_fixture(path):
    """Return the saved state in PATH, after checking it is a JSON object."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a JSON object")
    return data


def blank_status():
    """A state with every field and nothing in it: installed, running, not logged in."""
    return {"ok": True, "installed": True, "running": True, "loggedIn": False, "email": "",
            "usedBytes": 0, "totalBytes": 0, "usagePercent": 0.0,
            "syncs": [], "backups": [], "transfers": parse_transfers(""), "unread": [], "error": ""}


def unreadable_status(reason):
    """A state that could not be read, for REASON: "ok" false and "error" REASON."""
    return {**blank_status(), "ok": False, "error": reason}


def read_account(timeout):
    """Ask MEGAcmd who is logged in; return (logged in, e-mail, reason).

    "logged in" is True, False, or None when MEGAcmd's answer does not tell
    (busy, failing, or saying something unexpected); REASON then says why.
    """
    code, out = run(["mega-whoami"], timeout)
    match = re.search(r"Account e-mail:\s*(\S+)", out)
    if match:
        return True, match.group(1), ""
    if code == TIMED_OUT:
        return None, "", "MEGAcmd is busy"
    if NOT_LOGGED_IN.search(out):
        return False, "", ""
    if code == NOT_FOUND:
        return None, "", "MEGAcmd is not installed"
    detail = error_text(out) if out.strip() else ""
    return None, "", "Could not read the MEGA account" + (f": {detail}" if detail else "")


def read_syncs(timeout):
    """Return (syncs, unreadable lines) from mega-sync, or None when it did not answer (see failed)."""
    code, out = run(["mega-sync", "--col-separator=" + SEPARATOR, "--output-cols=" + ",".join(SYNC_COLUMNS)], timeout)
    if failed(code, out):
        return None
    return parse_syncs(out)


def unread_note(parts):
    """A note saying which of PARTS could not be read, or "" for none."""
    if not parts:
        return ""
    names = list(parts)
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"Could not read the {listed} from MEGAcmd."


def collect(timeout=20):
    """Return MEGAcmd's current state; each mega-* command gets TIMEOUT seconds."""
    status = blank_status()
    status["installed"] = shutil.which("mega-whoami") is not None
    if not status["installed"]:
        return status
    if not engine_running():
        status["running"] = False
        return status

    logged_in, email, reason = read_account(timeout)
    if logged_in is None:
        return unreadable_status(reason)
    if not logged_in:
        return status
    status["loggedIn"] = True
    status["email"] = email
    unread = []
    notes = []

    code, out = run(["mega-df"], timeout)
    used, total, percent = parse_storage(out)
    if failed(code, out) or total <= 0:
        unread.append("storage")
    else:
        status["usedBytes"], status["totalBytes"], status["usagePercent"] = used, total, percent

    found = read_syncs(timeout)
    if found is None:
        unread.append("syncs")
    else:
        status["syncs"], unreadable = found
        if unreadable:
            notes.append("Some syncs could not be read; list them with mega-sync in a terminal.")

    code, out = run(["mega-backup", "-l", "-h", WIDE_PATHS], timeout)
    if failed(code, out):
        unread.append("backups")
    else:
        status["backups"] = parse_backups(out)

    code, out = run(["mega-transfers", "--summary"], timeout)
    if failed(code, out):
        unread.append("transfers")
    else:
        status["transfers"] = parse_transfers(out)

    status["unread"] = unread
    status["error"] = " ".join(note for note in [unread_note(unread)] + notes if note)
    return status
