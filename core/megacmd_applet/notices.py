# notices.py: decide which MEGA notifications are new, once per problem.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide which notifications an applet should show.

A notification goes out once per problem: a sync error, a failed backup, the
MEGAcmd engine stopping, being logged out, and storage use crossing 90% and
95%. What has been reported is kept in a small state file, shared by every
applet of the user, so two applets never report the same problem twice and
a restart does not repeat old problems.

Each notice is {"title", "body", "urgency", "icon"}: urgency "normal" or
"critical", icon "error", "off" or "cloud". Texts are plain and name no
folder.
"""

import contextlib
import fcntl
import json
import os
import pathlib

from . import model

FRESH = {"reported": [], "wasRunning": True, "wasLoggedIn": False, "storageLevel": 0}


def default_state_path():
    """The state file under $XDG_STATE_HOME (~/.local/state by default)."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return pathlib.Path(base) / "megacmd-applet" / "notices.json"


def preview_state_path():
    """The state file of previews of saved states, under $XDG_RUNTIME_DIR (or the state folder)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return pathlib.Path(runtime) / "megacmd-applet" / "preview.json"
    return default_state_path().with_name("preview.json")


def new_notices(status, state):
    """Return (notices, next state) for STATUS, given what STATE says was reported."""
    previous = {**FRESH, **(state or {})}
    reported = set(previous["reported"])
    notices = []

    current = model.problems(status)
    for problem in current:
        if problem["key"] not in reported:
            notices.append({"title": problem["title"], "body": problem["body"], "urgency": "critical", "icon": "error"})

    running = status.get("running") is not False
    logged_in = status.get("loggedIn") is True
    if previous["wasRunning"] and not running:
        notices.append({"title": "MEGAcmd stopped",
                        "body": "Syncs and backups are not running. Start it again from the MEGA panel.",
                        "urgency": "critical", "icon": "off"})
    elif previous["wasLoggedIn"] and not logged_in and running:
        notices.append({"title": "MEGA logged out",
                        "body": "Syncs and backups have stopped. Log in again from the MEGA panel.",
                        "urgency": "critical", "icon": "off"})

    percent = status.get("usagePercent")
    level = model.storage_level(percent) if logged_in else 0
    if level > previous["storageLevel"]:
        notices.append({"title": f"MEGA storage {model.js_round(model.number(percent))}% full",
                        "body": model.usage_text(status.get("usedBytes"), status.get("totalBytes"), percent),
                        "urgency": "critical" if level >= 95 else "normal", "icon": "cloud"})

    return notices, {"reported": sorted(problem["key"] for problem in current), "wasRunning": running,
                     "wasLoggedIn": logged_in, "storageLevel": level}


def read_state(handle):
    """The state in the open file HANDLE, or a fresh one when it is empty or unreadable."""
    handle.seek(0)
    try:
        data = json.loads(handle.read() or "{}")
    except json.JSONDecodeError:
        return dict(FRESH)
    return data if isinstance(data, dict) else dict(FRESH)


@contextlib.contextmanager
def locked_state(path):
    """Open the state file PATH, made if missing, locked for this process alone."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield handle


def take_notices(status, path=None, fresh=False):
    """Return the new notices for STATUS and record them in the state file PATH.

    FRESH forgets what was reported before, as for a new preview.
    """
    with locked_state(path or default_state_path()) as handle:
        state = dict(FRESH) if fresh else read_state(handle)
        notices, state = new_notices(status, state)
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(state))
    return notices
