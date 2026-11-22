# notices.py: decide which MEGA notifications are new, once per problem.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide which notifications an applet should show.

A notification goes out once per problem: a sync error, a failed backup, the
MEGAcmd engine stopping, being logged out, and storage use crossing 90% and
95%. Several new problems of one kind at once (say three stopped syncs) give
one notification for all of them. What has been reported is kept in a small
state file, shared by every applet of the user, so two applets never report
the same problem twice and a restart does not repeat old problems.

A part of the state that was not read (MEGAcmd stopped, nobody logged in, or
a command that failed; see megacmd.py) keeps what was recorded for it, so
its problems are neither forgotten nor reported again once it reads again.

Each notice is {"title", "body", "urgency", "icon"}: urgency "normal" or
"critical", icon "error", "off" or "cloud". Texts are plain and name no
folder.
"""

import contextlib
import fcntl
import json
import os
import pathlib
import tempfile

from . import model

FRESH = {"reported": [], "wasRunning": True, "wasLoggedIn": False, "storageLevel": 0}
# The part of the state (see megacmd.py "unread") each kind of problem comes from.
PROBLEM_PART = {"sync": "syncs", "backup": "backups"}
ALL_PARTS = {"storage", "syncs", "backups"}


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


def problem_notices(found):
    """The notices for the new problems FOUND: one each, or one for all of a kind when there are several."""
    kinds = {}
    for problem in found:
        kinds.setdefault(problem["kind"], []).append(problem)
    result = []
    for kind, group in kinds.items():
        texts = group[0] if len(group) == 1 else model.problem_group(kind, len(group))
        result.append({"title": texts["title"], "body": texts["body"], "urgency": "critical", "icon": "error"})
    return result


def new_notices(status, state):
    """Return (notices, next state) for STATUS, given what STATE says was reported."""
    previous = clean_state(state)
    installed = status.get("installed") is not False
    running = status.get("running") is not False
    logged_in = installed and running and status.get("loggedIn") is True
    unread = set(status.get("unread") or []) if logged_in else set(ALL_PARTS)

    reported = set(previous["reported"])
    current = model.problems(status)
    notices = problem_notices([problem for problem in current if problem["key"] not in reported])
    kept = {key for key in reported if PROBLEM_PART.get(key.split(":", 1)[0]) in unread}

    if not installed:
        running, logged_in = previous["wasRunning"], previous["wasLoggedIn"]
    elif previous["wasRunning"] and not running:
        notices.append({"title": "MEGAcmd stopped",
                        "body": "Syncs and backups are not running. Start it again from the MEGA panel.",
                        "urgency": "critical", "icon": "off"})
    elif previous["wasLoggedIn"] and not logged_in and running:
        notices.append({"title": "MEGA logged out",
                        "body": "Syncs and backups have stopped. Log in again from the MEGA panel.",
                        "urgency": "critical", "icon": "off"})

    if "storage" in unread:
        level = previous["storageLevel"]
    else:
        percent = model.storage_percent(status)
        level = model.storage_level(percent)
        if level > previous["storageLevel"]:
            notices.append({"title": f"MEGA storage {model.js_round(percent)}% full",
                            "body": model.usage_text(status),
                            "urgency": "critical" if level >= 95 else "normal", "icon": "cloud"})

    return notices, {"reported": sorted(kept | {problem["key"] for problem in current}), "wasRunning": running,
                     "wasLoggedIn": logged_in, "storageLevel": level}


def clean_state(data):
    """DATA as a state with every field of FRESH, each of the right type; wrong or missing ones are fresh.

    A "preview" text, naming the saved state the notices are for, is kept.
    """
    data = data if isinstance(data, dict) else {}
    state = dict(FRESH)
    reported = data.get("reported")
    if isinstance(reported, list):
        state["reported"] = [key for key in reported if isinstance(key, str)]
    for name in ("wasRunning", "wasLoggedIn"):
        if isinstance(data.get(name), bool):
            state[name] = data[name]
    level = data.get("storageLevel")
    if type(level) is int and level in (0, 90, 95):
        state["storageLevel"] = level
    if isinstance(data.get("preview"), str):
        state["preview"] = data["preview"]
    return state


def read_state(path):
    """The state in the file PATH, or a fresh one when it is missing, empty or unreadable."""
    try:
        text = pathlib.Path(path).read_bytes().decode("utf-8", "replace")
        return clean_state(json.loads(text))
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(FRESH)


def write_state(path, state):
    """Replace the state file PATH by STATE at once, readable by this user only."""
    path = pathlib.Path(path)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state))
        os.replace(temporary, path)
    except OSError:
        os.unlink(temporary)
        raise


@contextlib.contextmanager
def locked(path):
    """Hold the lock that guards the state file PATH (PATH.lock, made if missing) for this process alone."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def take_notices(status, path=None, fresh=False, preview=None):
    """Return the new notices for STATUS and record them in the state file PATH.

    FRESH forgets what was reported before. PREVIEW names the saved state
    shown; the state starts fresh whenever it differs from the one recorded
    last. Raises OSError when the state file cannot be read or written.
    """
    path = path or default_state_path()
    with locked(path):
        state = read_state(path)
        if fresh or (preview is not None and state.get("preview") != preview):
            state = dict(FRESH)
        notices, state = new_notices(status, state)
        if preview is not None:
            state["preview"] = preview
        write_state(path, state)
    return notices
