# actions.py: change MEGA syncs and backups, and open the guided dialogs.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run what an applet's panel asks for: pause, resume and remove syncs,
remove backups, pause or resume all syncing, and open the guided dialogs
(log in, add a sync or backup, change a backup) in a terminal.

Sync IDs and backup tags are checked before they reach a command line, so a
value can never pass for an option. Commands run without a shell.
"""

import os
import pathlib
import re
import shlex
import shutil
import subprocess

from . import megacmd, model

BACKUP_TAG = re.compile(r"^[0-9]+$")
MEGA_ERROR = re.compile(r"\bERR\b")
BIN = pathlib.Path(__file__).resolve().parent.parent.parent / "bin"
# Terminals tried in turn when none is set, each with the arguments that make
# it run the program after them: the freedesktop launcher first, then the
# desktops' own terminals.
TERMINALS = (("xdg-terminal-exec", []), ("ptyxis", ["--"]), ("kgx", ["--"]), ("gnome-terminal", ["--"]),
             ("konsole", ["-e"]), ("cosmic-term", ["-e"]), ("kitty", []), ("foot", []), ("alacritty", ["-e"]))
GUIDED = ("mega-account-login", "mega-add-sync", "mega-add-backup", "mega-edit-backup")


class ActionError(Exception):
    """An action could not be done; the message says why, for the panel."""


def check_sync_id(sync_id):
    """Return SYNC_ID when it is a valid MEGAcmd sync ID, else raise ActionError."""
    if not megacmd.SYNC_ID.match(str(sync_id)):
        raise ActionError(f"Not a sync ID: {sync_id}")
    return str(sync_id)


def check_backup_tag(tag):
    """Return TAG when it is a valid MEGAcmd backup tag, else raise ActionError."""
    if not BACKUP_TAG.match(str(tag)):
        raise ActionError(f"Not a backup tag: {tag}")
    return str(tag)


def error_text(output):
    """MEGAcmd's error message in OUTPUT without its "[... ERR" prefix and closing bracket."""
    text = re.sub(r"^\[[^\]]*ERR\s*", "", output.strip())
    return re.sub(r"\]$", "", text) or "MEGA command failed"


def run_all(commands, timeout=60):
    """Run each mega-* command of COMMANDS in turn; raise ActionError at the first failure."""
    for command in commands:
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise ActionError("MEGAcmd did not answer in time") from error
        except FileNotFoundError as error:
            raise ActionError("MEGAcmd is not installed") from error
        output = ((done.stdout or "") + (done.stderr or "")).strip()
        if done.returncode != 0 or MEGA_ERROR.search(output):
            raise ActionError(error_text(output))


def sync_commands(action, sync_id):
    """The command that pauses, resumes or removes the sync SYNC_ID."""
    flags = {"pause": "--pause", "resume": "--enable", "remove-sync": "--delete"}
    return [["mega-sync", flags[action], check_sync_id(sync_id)]]


def all_commands(paused, syncs):
    """The commands that pause (PAUSED true) or resume every sync of SYNCS not already so."""
    flag = "--pause" if paused else "--enable"
    return [["mega-sync", flag, check_sync_id(sync["id"])] for sync in syncs if model.sync_paused(sync) != paused]


def set_all_paused(paused, timeout=20):
    """Pause or resume every sync; with PAUSED None, pause while any runs, else resume."""
    status = megacmd.collect(timeout)
    if not status["running"]:
        raise ActionError("MEGAcmd is not running")
    syncs = status["syncs"]
    if paused is None:
        paused = model.any_running(syncs)
    run_all(all_commands(paused, syncs))


def remove_backup(tag):
    """Remove the backup TAG; its files stay where they are."""
    run_all([["mega-backup", "-d", check_backup_tag(tag)]])


def terminal_command(setting=None):
    """The command that runs a program in a terminal.

    SETTING when given, else the first of TERMINALS on the PATH, else
    $TERMINAL with -e.
    """
    if setting:
        return shlex.split(setting)
    for name, args in TERMINALS:
        if shutil.which(name):
            return [name] + args
    terminal = os.environ.get("TERMINAL")
    if terminal and shutil.which(terminal):
        return [terminal, "-e"]
    raise ActionError("No terminal found; set one in the applet's settings")


def guided_command(name, args, terminal=None):
    """The command that opens the guided dialog NAME with ARGS in a terminal."""
    if name not in GUIDED:
        raise ActionError(f"No such dialog: {name}")
    if name == "mega-edit-backup":
        tag, period, keep = (list(args) + ["", "", ""])[:3]
        if not re.fullmatch(r"[0-9]*", str(keep)):
            raise ActionError(f"Not a number of backups: {keep}")
        args = [check_backup_tag(tag), str(period), str(int(keep or 0))]
    return terminal_command(terminal) + [str(BIN / name)] + [str(arg) for arg in args]


def open_guided(name, args, terminal=None):
    """Open the guided dialog NAME in a terminal, without waiting for it."""
    subprocess.Popen(guided_command(name, args, terminal), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
