# actions.py: change MEGA syncs and backups, open folders and the guided dialogs.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run what an applet's panel asks for: pause, resume and remove syncs,
remove backups, pause or resume all syncing, open a local folder in the file
manager, and open the guided dialogs (log in, add a sync or backup, change a
backup) in a terminal.

Sync IDs, backup tags and the dialogs' arguments are checked before they
reach a command line, so a value can never pass for an option. Commands run
without a shell.
"""

import os
import pathlib
import re
import shlex
import shutil
import subprocess

from . import megacmd, model

BACKUP_TAG = re.compile(r"[0-9]+")
# A MEGAcmd backup period: a time such as "1m12d3h" or a cron line with seconds.
PERIOD = re.compile(r"(?:[0-9]+[ymdhMs])+|(?:[0-9A-Za-z*,/?-]+ ){5}[0-9A-Za-z*,/?-]+")
KEEP = re.compile(r"[0-9]*")
BIN = pathlib.Path(__file__).resolve().parent.parent.parent / "bin"
# Terminals tried in turn when none is set, each with the arguments that make
# it run the program after them: the freedesktop launcher first, then the
# desktops' own terminals.
TERMINALS = (("xdg-terminal-exec", []), ("ptyxis", ["--"]), ("kgx", ["--"]), ("gnome-terminal", ["--"]),
             ("konsole", ["-e"]), ("cosmic-term", ["-e"]), ("kitty", []), ("foot", []), ("alacritty", ["-e"]))
GUIDED = ("mega-account-login", "mega-add-sync", "mega-add-backup", "mega-edit-backup")
# The mega-sync option of each sync action.
SYNC_FLAGS = {"pause": "--pause", "resume": "--enable", "remove-sync": "--delete"}


class ActionError(Exception):
    """An action could not be done; the message says why, for the panel."""


def check_sync_id(sync_id):
    """Return SYNC_ID when it is a valid MEGAcmd sync ID, else raise ActionError."""
    if not megacmd.SYNC_ID.fullmatch(str(sync_id)):
        raise ActionError(f"Not a sync ID: {sync_id}")
    return str(sync_id)


def check_backup_tag(tag):
    """Return TAG when it is a valid MEGAcmd backup tag, else raise ActionError."""
    if not BACKUP_TAG.fullmatch(str(tag)):
        raise ActionError(f"Not a backup tag: {tag}")
    return str(tag)


def run_all(commands, timeout=60):
    """Run each mega-* command of COMMANDS in turn; raise ActionError at the first failure."""
    for command in commands:
        code, output = megacmd.run(command, timeout)
        if code == megacmd.TIMED_OUT:
            raise ActionError("MEGAcmd did not answer in time")
        if code == megacmd.NOT_FOUND:
            raise ActionError("MEGAcmd is not installed")
        if code != 0 or megacmd.is_error(output):
            raise ActionError(megacmd.error_text(output))


def sync_commands(action, sync_id):
    """The command that pauses, resumes or removes (ACTION, see SYNC_FLAGS) the sync SYNC_ID."""
    return [["mega-sync", SYNC_FLAGS[action], check_sync_id(sync_id)]]


def all_commands(paused, syncs):
    """The commands that pause (PAUSED true) or resume every sync of SYNCS not already so."""
    flag = SYNC_FLAGS["pause" if paused else "resume"]
    return [["mega-sync", flag, check_sync_id(sync["id"])] for sync in syncs if model.sync_paused(sync) != paused]


def read_syncs_for_action(timeout):
    """The syncs, read for an action on all of them; raises ActionError when they cannot be read.

    Asks only who is logged in and the sync list.
    """
    if shutil.which("mega-whoami") is None:
        raise ActionError("MEGAcmd is not installed")
    if not megacmd.engine_running():
        raise ActionError("MEGAcmd is not running")
    logged_in, _, reason = megacmd.read_account(timeout)
    if logged_in is None:
        raise ActionError(reason)
    if not logged_in:
        raise ActionError("Not logged in to MEGA")
    found = megacmd.read_syncs(timeout)
    if found is None:
        raise ActionError("Could not read the syncs from MEGAcmd")
    return found[0]


def set_all_paused(paused, timeout=20):
    """Pause or resume every sync; with PAUSED None, pause while any runs, else resume."""
    syncs = read_syncs_for_action(timeout)
    if paused is None:
        paused = model.any_running(syncs)
    run_all(all_commands(paused, syncs))


def remove_backup(tag):
    """Remove the backup TAG; its files stay where they are."""
    run_all([["mega-backup", "-d", check_backup_tag(tag)]])


def use_megacmd_dir(folder):
    """Search FOLDER for MEGAcmd's mega-* commands before the PATH.

    Applies to this process and every program it starts. Raises ActionError
    unless FOLDER is the absolute path of a folder whose name can go on the
    PATH (no ":").
    """
    if os.pathsep in folder:
        raise ActionError(f"A folder name with \"{os.pathsep}\" cannot go on the PATH: {folder}")
    if not os.path.isabs(folder) or not os.path.isdir(folder):
        raise ActionError(f"Not a folder: {folder}")
    current = os.environ.get("PATH")
    os.environ["PATH"] = folder + os.pathsep + current if current else folder


def detach(command):
    """Start COMMAND on its own, without waiting for it; raises ActionError when it cannot start."""
    try:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as error:
        raise ActionError(f"Could not start {command[0]}: {error.strerror or error}") from error


def open_folder(path):
    """Open the local folder PATH in the file manager, without waiting.

    Raises ActionError unless PATH is the absolute path of an existing
    folder, so no file can be opened (and perhaps run) this way.
    """
    if not os.path.isabs(path) or not os.path.isdir(path):
        raise ActionError(f"Not a folder: {path}")
    opener = shutil.which("xdg-open")
    if opener is None:
        raise ActionError("xdg-open is not installed")
    detach([opener, path])


def terminal_command(setting=None):
    """The command that runs a program in a terminal.

    SETTING when given, else the first of TERMINALS on the PATH, else
    $TERMINAL with -e. Raises ActionError when none is found or SETTING
    cannot be split into words.
    """
    if setting:
        try:
            words = shlex.split(setting)
        except ValueError as error:
            raise ActionError(f"Not a terminal command: {setting}") from error
        if words:
            return words
    for name, args in TERMINALS:
        if shutil.which(name):
            return [name] + args
    terminal = os.environ.get("TERMINAL")
    if terminal and shutil.which(terminal):
        return [terminal, "-e"]
    raise ActionError("No terminal found; set one in the applet's settings")


def guided_args(name, args):
    """ARGS checked for the guided dialog NAME, as the dialog takes them; raises ActionError when wrong.

    mega-account-login takes none. mega-add-sync and mega-add-backup take
    an optional suggested MEGA folder, absolute or empty. mega-edit-backup
    takes TAG [PERIOD [KEEP]]: PERIOD that is not a MEGAcmd period becomes
    "" (the dialog then asks for a new one), and KEEP empty or 0 becomes ""
    (the dialog's default).
    """
    args = [str(arg) for arg in args]
    if name == "mega-account-login":
        if args:
            raise ActionError("mega-account-login takes no arguments")
        return []
    if name in ("mega-add-sync", "mega-add-backup"):
        if len(args) > 1:
            raise ActionError(f"{name} takes one MEGA folder")
        if args and args[0] and not args[0].startswith("/"):
            raise ActionError(f"Not a MEGA folder: {args[0]}")
        return [arg for arg in args if arg]
    if len(args) > 3:
        raise ActionError("mega-edit-backup takes a backup tag, period and number to keep")
    tag, period, keep = (args + ["", "", ""])[:3]
    if not KEEP.fullmatch(keep):
        raise ActionError(f"Not a number of backups: {keep}")
    period = period.strip()
    return [check_backup_tag(tag), period if PERIOD.fullmatch(period) else "", keep.lstrip("0")]


def guided_command(name, args, terminal=None, path=None):
    """The command that opens the guided dialog NAME with ARGS (see guided_args) in a terminal.

    With PATH the dialog gets that command search path; it is passed through
    env, as some terminals start programs from a server process that does
    not inherit this one's environment. Raises ActionError for an unknown
    dialog, wrong arguments or no terminal.
    """
    if name not in GUIDED:
        raise ActionError(f"No such dialog: {name}")
    checked = guided_args(name, args)
    env = ["env", f"PATH={path}"] if path else []
    return terminal_command(terminal) + env + [str(BIN / name)] + checked


def open_guided(name, args, terminal=None, path=None):
    """Open the guided dialog NAME in a terminal, without waiting for it; see guided_command."""
    detach(guided_command(name, args, terminal, path))
