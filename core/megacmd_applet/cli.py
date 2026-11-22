# cli.py: the megacmd-applet command line, which every desktop's applet calls.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line of the shared core.

    megacmd-applet status [--timeout S] [--home PATH] [--fixture FILE]
                          [--state FILE] [--fresh] [--no-notices]
        Print the view (see view.py) as one JSON object. Notices are taken
        from the state file, so each is printed once; a --fixture preview
        keeps its own file, apart from the live one. --state names another
        file, --fresh forgets what it recorded and --no-notices leaves it
        alone.

    megacmd-applet pause|resume|remove-sync SYNC_ID
    megacmd-applet remove-backup TAG
    megacmd-applet pause-all|resume-all|toggle-all
        Change syncs and backups. Exit status 1 with the reason on standard
        error when MEGAcmd refuses.

    megacmd-applet guided NAME [ARG...] [--terminal COMMAND]
        Open a guided dialog (mega-account-login, mega-add-sync,
        mega-add-backup, mega-edit-backup) in a terminal: COMMAND, else
        the first known terminal found (see actions.TERMINALS).
"""

import argparse
import json
import os
import sys

from . import actions, megacmd, notices, view


def status_command(args):
    """Print the view of MEGAcmd's state, or of the saved state in --fixture."""
    if args.fixture:
        try:
            status = megacmd.load_fixture(args.fixture)
        except (OSError, ValueError) as error:
            print(json.dumps({"ok": False, "error": str(error)}))
            return 0
    else:
        status = megacmd.collect(args.timeout)
    state = args.state or (notices.preview_state_path() if args.fixture else None)
    found = [] if args.no_notices else notices.take_notices(status, state, args.fresh)
    print(json.dumps(view.build_view(status, args.home, found)))
    return 0


def parser():
    """The argument parser for every subcommand."""
    top = argparse.ArgumentParser(prog="megacmd-applet", description="MEGAcmd state and actions for desktop applets.")
    commands = top.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="print the state as JSON")
    status.add_argument("--timeout", type=float, default=20, help="seconds each mega-* command may take")
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

    guided = commands.add_parser("guided", help="open a guided dialog in a terminal")
    guided.add_argument("name", choices=actions.GUIDED)
    guided.add_argument("args", nargs="*")
    guided.add_argument("--terminal", help="command that runs a program in a terminal")
    return top


def main(argv=None):
    """Run the command line; return the exit status."""
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            return status_command(args)
        if args.command in ("pause", "resume", "remove-sync"):
            actions.run_all(actions.sync_commands(args.command, args.sync_id))
        elif args.command == "remove-backup":
            actions.remove_backup(args.tag)
        elif args.command in ("pause-all", "resume-all", "toggle-all"):
            actions.set_all_paused({"pause-all": True, "resume-all": False, "toggle-all": None}[args.command])
        elif args.command == "guided":
            actions.open_guided(args.name, args.args, args.terminal)
    except actions.ActionError as error:
        print(error, file=sys.stderr)
        return 1
    return 0
