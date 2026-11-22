# cli.py: the megacmd-applet command line, which every desktop's applet calls.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the shared core.

    megacmd-applet [--megacmd-dir=DIR] COMMAND ...
        --megacmd-dir searches DIR for MEGAcmd's mega-* commands before the
        PATH; it must be an absolute folder whose name has no ":".

    megacmd-applet status [--timeout S] [--preview NAME]
                          [--home PATH] [--fixture FILE]
                          [--state FILE] [--fresh] [--no-notices]
        Print the view (see view.py) as one JSON object and exit 0, also
        when MEGAcmd, the MEGAcmd folder or the saved state cannot be read
        ("ok" is false then). --preview shows the saved state
        fixtures/NAME.json (NAME of letters, digits, "-" and "_") for the
        home folder /home/user. Notices are taken from the state file, so
        each is printed once; previews keep their own file, apart from the
        live one, and start it afresh when a different NAME is shown.
        For tests: --fixture shows a saved state from any file, --home sets
        the home folder shortened to "~", --state names another state file,
        --fresh forgets what it recorded and --no-notices leaves it alone.

    megacmd-applet pause|resume|remove-sync SYNC_ID
    megacmd-applet remove-backup TAG
    megacmd-applet pause-all|resume-all|toggle-all
        Change syncs and backups. The "all" commands fail when nobody is
        logged in or the syncs cannot be read.

    megacmd-applet open-folder PATH
        Open the local folder PATH (absolute, existing) in the file manager.

    megacmd-applet guided [--terminal COMMAND] NAME -- [ARG...]
        Open a guided dialog (mega-account-login, mega-add-sync,
        mega-add-backup, mega-edit-backup) in a terminal: COMMAND, else
        the first known terminal found (see actions.TERMINALS). Options go
        before NAME and "--" before the dialog's arguments, which are
        checked (see actions.guided_args).

    Every command but status exits 1 with the reason on standard error when
    it is refused or fails.
"""

import argparse
import json
import os
import pathlib
import re
import sys

from . import actions, megacmd, notices, view

FIXTURES = pathlib.Path(__file__).resolve().parent.parent.parent / "fixtures"
PREVIEW_NAME = re.compile(r"[A-Za-z0-9_-]+")
# The home folder the saved states in FIXTURES are written for.
PREVIEW_HOME = "/home/user"


def preview_path(name):
    """The saved state fixtures/NAME.json; raises ValueError for a bad or unknown NAME."""
    path = FIXTURES / f"{name}.json"
    if not PREVIEW_NAME.fullmatch(name) or not path.is_file():
        raise ValueError(f"No saved state named {name}")
    return path


def read_status(args):
    """Return (state, home folder) for the status command's ARGS; the state has "ok" false when unreadable."""
    try:
        if args.preview is not None:
            return megacmd.load_fixture(preview_path(args.preview)), PREVIEW_HOME
        if args.fixture:
            return megacmd.load_fixture(args.fixture), args.home
        if args.megacmd_dir:
            actions.use_megacmd_dir(args.megacmd_dir)
        return megacmd.collect(args.timeout), args.home
    except (actions.ActionError, OSError, ValueError) as error:
        return megacmd.unreadable_status(str(error)), args.home


def status_command(args):
    """Print the view of MEGAcmd's state, or of a saved state; always exits 0."""
    status, home = read_status(args)
    found = []
    if status.get("ok") is not False and not args.no_notices:
        previewing = args.preview is not None or args.fixture
        path = args.state or (notices.preview_state_path() if previewing else None)
        try:
            found = notices.take_notices(status, path, args.fresh, args.preview)
        except OSError as error:
            note = f"Could not keep the notification state: {error.strerror or error}"
            status["error"] = " ".join(text for text in (status.get("error"), note) if text)
    print(json.dumps(view.build_view(status, home, found)))
    return 0


def parser():
    """The argument parser for every subcommand."""
    top = argparse.ArgumentParser(prog="megacmd-applet", description="MEGAcmd state and actions for desktop applets.")
    top.add_argument("--megacmd-dir", help="folder holding MEGAcmd's mega-* commands, searched before the PATH")
    commands = top.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="print the state as JSON")
    status.add_argument("--timeout", type=float, default=20, help="seconds each mega-* command may take")
    status.add_argument("--preview", metavar="NAME", help="show the saved state fixtures/NAME.json")
    status.add_argument("--home", default=os.path.expanduser("~"), help="home folder shortened to ~")
    status.add_argument("--fixture", help="print this saved state instead of MEGAcmd's")
    status.add_argument("--state", help="notification state file")
    status.add_argument("--fresh", action="store_true", help="forget the notifications recorded so far")
    status.add_argument("--no-notices", action="store_true", help="take no notifications")

    for name in ("pause", "resume", "remove-sync"):
        commands.add_parser(name, help=f"{name.replace('-', ' ')} a sync").add_argument("sync_id")
    commands.add_parser("remove-backup", help="remove a backup").add_argument("tag")
    for name in ("pause-all", "resume-all", "toggle-all"):
        commands.add_parser(name, help=f"{name.replace('-', ' ')} syncing")
    commands.add_parser("open-folder", help="open a local folder in the file manager").add_argument("path")

    guided = commands.add_parser("guided", help="open a guided dialog in a terminal")
    guided.add_argument("--terminal", help="command that runs a program in a terminal")
    guided.add_argument("name", choices=actions.GUIDED)
    guided.add_argument("args", nargs="*", help="the dialog's arguments, after --")
    return top


def follows_dashes(words, argv):
    """True when WORDS are exactly what follows the first "--" in ARGV, or WORDS is empty."""
    return not words or ("--" in argv and argv[argv.index("--") + 1:] == words)


def run_action(args, argv):
    """Run the action command in ARGS, parsed from ARGV; raises actions.ActionError when refused."""
    if args.megacmd_dir:
        actions.use_megacmd_dir(args.megacmd_dir)
    if args.command in actions.SYNC_FLAGS:
        actions.run_all(actions.sync_commands(args.command, args.sync_id))
    elif args.command == "remove-backup":
        actions.remove_backup(args.tag)
    elif args.command in ("pause-all", "resume-all", "toggle-all"):
        actions.set_all_paused({"pause-all": True, "resume-all": False, "toggle-all": None}[args.command])
    elif args.command == "open-folder":
        actions.open_folder(args.path)
    elif args.command == "guided":
        if not follows_dashes(args.args, argv):
            raise actions.ActionError("Put -- before the dialog's arguments")
        actions.open_guided(args.name, args.args, args.terminal, os.environ["PATH"] if args.megacmd_dir else None)


def main(argv=None):
    """Run the command line; return the exit status."""
    argv = sys.argv[1:] if argv is None else list(argv)
    args = parser().parse_args(argv)
    if args.command == "status":
        return status_command(args)
    try:
        run_action(args, argv)
    except actions.ActionError as error:
        print(error, file=sys.stderr)
        return 1
    return 0
