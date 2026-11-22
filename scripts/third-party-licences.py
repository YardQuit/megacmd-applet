#!/usr/bin/env python3
# third-party-licences.py: write the licence texts of the crates built into the COSMIC applet.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Print the licences of every crate linked into the COSMIC applet.

Usage: scripts/third-party-licences.py [--summary] [CARGO_TOML]

Asks cargo which crates the applet in CARGO_TOML (default cosmic/Cargo.toml)
links into its program on this machine's target: normal dependencies only,
without procedural macros and build or development dependencies, which run
while building but are not linked in. It prints, for the file installed
beside the applet, a list of these crates with their versions, licences and
sources, then each distinct licence text once with the crates that ship it.

A crate that ships no licence file gets the standard text of its licence
from scripts/licence-texts/, with the crate's authors as copyright holders;
for a choice of licences, the first one with a standard text is used.

With --summary it prints instead one SPDX expression for the applet and all
these crates together, for the licence tags of the packages, and names on
standard error the crates left out of it because they state no licence.

Crate sources must already be fetched (cargo build or cargo fetch does that);
cargo runs offline. Exits with status 1 and a message when cargo fails or a
crate's licence cannot be given.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

LICENCE_PREFIXES = ("license", "licence", "copying", "notice", "copyright")
STANDARD_TEXTS = pathlib.Path(__file__).resolve().parent / "licence-texts"
HOLDERS = "<copyright holders>"


class LicenceError(Exception):
    """The licences cannot be listed; the message says why."""


def run(command):
    """The standard output of COMMAND, a list of arguments.

    Raises LicenceError with the command's own error output when it cannot
    be started or fails.
    """
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", check=False)
    except OSError as error:
        raise LicenceError(f"cannot run {command[0]}: {error.strerror}") from error
    if done.returncode != 0:
        raise LicenceError(f"{' '.join(command[:2])} failed:\n{done.stderr.rstrip()}")
    return done.stdout


def host_target():
    """The target triple of this machine, as rustc names it."""
    return run(["rustc", "--print", "host-tuple"]).strip()


def metadata(manifest, target):
    """Cargo's metadata for MANIFEST on TARGET, without the network."""
    return json.loads(run(["cargo", "metadata", "--format-version", "1", "--locked", "--offline",
                           "--manifest-path", str(manifest), "--filter-platform", target]))


def tree_key(package):
    """PACKAGE as `cargo tree` names it: name, version and, unless from crates.io, its source."""
    name = f"{package['name']} v{package['version']}"
    origin = package.get("source") or ""
    if origin.startswith("registry+"):
        return name
    if origin.startswith("git+"):
        url, _, revision = origin[len("git+"):].rpartition("#")
        return f"{name} ({url}#{revision[:8]})"
    return f"{name} ({pathlib.Path(package['manifest_path']).parent})"


def linked_packages(manifest, meta, target):
    """The packages linked into the program of MANIFEST on TARGET, sorted by name and version.

    META is cargo's metadata for MANIFEST; `cargo tree` decides which of its
    packages are linked in, as it resolves features and platforms the way a
    build does.
    """
    tree = run(["cargo", "tree", "--locked", "--offline", "--manifest-path", str(manifest),
                "--edges", "normal,no-proc-macro", "--target", target,
                "--prefix", "none", "--no-dedupe", "--format", "{p}"])
    linked = set(tree.splitlines())
    root = meta["resolve"]["root"]
    packages = [package for package in meta["packages"]
                if package["id"] != root and tree_key(package) in linked]
    return sorted(packages, key=lambda p: (p["name"], p["version"]))


def files_in(folder):
    """The licence files directly in FOLDER, sorted by name."""
    return sorted((path for path in folder.iterdir()
                   if path.is_file() and path.name.lower().startswith(LICENCE_PREFIXES)),
                  key=lambda path: path.name)


def licence_files(package):
    """The licence files of PACKAGE, sorted by name.

    Those in its source folder, with the file its manifest names; for a crate
    from git with none there, those at the top of its repository checkout.
    """
    folder = pathlib.Path(package["manifest_path"]).parent
    files = files_in(folder)
    if package.get("license_file"):
        extra = folder / package["license_file"]
        if extra.is_file() and extra not in files:
            files.append(extra)
    if not files and (package.get("source") or "").startswith("git+"):
        for parent in folder.parents:
            if (parent / ".git").exists() or (parent / ".cargo-ok").exists():
                return files_in(parent)
    return files


def parse_expression(text):
    """The SPDX licence expression TEXT as a tree.

    A leaf is a tuple of licence identifiers that apply together (a licence
    and its exception); an inner node is ("AND", [...]) or ("OR", [...]).
    The old cargo form "MIT/Apache-2.0" is read as "MIT OR Apache-2.0".
    Raises LicenceError when TEXT is not a valid expression.
    """
    tokens = re.findall(r"[()]|[^\s()/]+|/", text)
    tokens = ["OR" if token == "/" else token for token in tokens]
    position = 0

    def take():
        nonlocal position
        if position == len(tokens):
            raise LicenceError(f"incomplete licence expression: {text}")
        position += 1
        return tokens[position - 1]

    def peek():
        return tokens[position] if position < len(tokens) else None

    def operand():
        token = take()
        if token == "(":
            node = either()
            if take() != ")":
                raise LicenceError(f"unbalanced licence expression: {text}")
            return node
        if token in ("AND", "OR", "WITH", ")"):
            raise LicenceError(f"unexpected {token} in licence expression: {text}")
        if peek() == "WITH":
            take()
            return (token, take())
        return (token,)

    def joined(operator, part):
        nodes = [part()]
        while peek() == operator:
            take()
            nodes.append(part())
        return nodes[0] if len(nodes) == 1 else (operator, nodes)

    def both():
        return joined("AND", operand)

    def either():
        return joined("OR", both)

    tree = either()
    if position != len(tokens):
        raise LicenceError(f"unexpected {tokens[position]} in licence expression: {text}")
    return tree


def needed_licences(tree):
    """The identifiers whose standard texts cover TREE, or None when some text is missing."""
    if tree[0] == "AND":
        parts = [needed_licences(node) for node in tree[1]]
        return None if None in parts else [name for part in parts for name in part]
    if tree[0] == "OR":
        return next((part for part in map(needed_licences, tree[1]) if part is not None), None)
    return list(tree) if all((STANDARD_TEXTS / f"{name}.txt").is_file() for name in tree) else None


def standard_texts(package):
    """The standard licence texts for PACKAGE, which ships no licence file of its own.

    Copyright lines name the crate's authors, or its authors in general when
    the manifest lists none. Raises LicenceError when the crate states no
    licence or no standard text covers it.
    """
    name = f"{package['name']} {package['version']}"
    if not package.get("license"):
        raise LicenceError(f"{name} ships no licence file and states no licence")
    names = needed_licences(parse_expression(package["license"]))
    if names is None:
        raise LicenceError(f"{name} ships no licence file, and scripts/licence-texts/ has no "
                           f"standard text for its licence {package['license']}")
    authors = [re.sub(r"\s*<[^>]*>", "", author) for author in package.get("authors") or []]
    holders = ", ".join(authors) or f"the {package['name']} authors"
    return [(STANDARD_TEXTS / f"{licence}.txt").read_text(encoding="utf-8").replace(HOLDERS, holders)
            for licence in names]


def source(package):
    """Where PACKAGE's source is published: crates.io or its git repository and revision."""
    origin = package.get("source") or ""
    if origin.startswith("git+"):
        return origin[len("git+"):].replace("#", " revision ")
    return f"https://crates.io/crates/{package['name']}/{package['version']}"


def report(packages, lock, target):
    """The text of the licence file for PACKAGES, resolved from the lock file LOCK for TARGET."""
    lines = ["Third-party licences of the MEGA applet for COSMIC",
             f"Generated by scripts/third-party-licences.py from {lock} for {target}.",
             "",
             "The applet's program includes the Rust crates below, each under its own",
             "licence. Their sources are published where each entry says. Crates marked",
             "\"standard text\" ship no licence file; the standard text of their licence",
             "is given instead.",
             "", "Crates", "======", ""]
    texts = {}
    for package in packages:
        name = f"{package['name']} {package['version']}"
        files = licence_files(package)
        found = [path.read_text(encoding="utf-8", errors="replace") for path in files]
        note = "" if found else " (standard text)"
        lines.append(f"{name}: {package.get('license') or 'licence not stated'}{note}; {source(package)}")
        for text in found or standard_texts(package):
            texts.setdefault(text, []).append(name)
    lines += ["", "Licence texts", "=============", ""]
    for text, names in texts.items():
        lines += ["-" * 78, "Used by: " + ", ".join(names), "-" * 78, "", text.rstrip(), ""]
    return "\n".join(lines) + "\n"


def render(tree, nested=False):
    """TREE as SPDX text: duplicates dropped, parts sorted, inner groups bracketed when NESTED."""
    if tree[0] in ("AND", "OR"):
        nodes = [inner for node in tree[1] for inner in (node[1] if node[0] == tree[0] else [node])]
        parts = sorted({render(node, True) for node in nodes})
        text = f" {tree[0]} ".join(parts)
        return f"({text})" if nested and len(parts) > 1 else text
    return " WITH ".join(tree)


def summary(packages):
    """One SPDX expression for PACKAGES together, and the names of those left out.

    Crates that state no licence are left out of the expression; their
    licence files must be read to complete it by hand.
    """
    stated = [parse_expression(p["license"]) for p in packages if p.get("license")]
    unstated = [f"{p['name']} {p['version']}" for p in packages if not p.get("license")]
    return render(("AND", stated)), unstated


def main(argv):
    """Print the licence report or summary for the manifest named in ARGV."""
    parser = argparse.ArgumentParser(description="Print the licences of the crates linked into "
                                                 "the COSMIC applet.")
    parser.add_argument("--summary", action="store_true",
                        help="print one SPDX expression for the applet and its crates")
    parser.add_argument("manifest", nargs="?", default="cosmic/Cargo.toml", type=pathlib.Path,
                        help="the applet's Cargo.toml (default: cosmic/Cargo.toml)")
    args = parser.parse_args(argv[1:])
    try:
        target = host_target()
        meta = metadata(args.manifest, target)
        packages = linked_packages(args.manifest, meta, target)
        if args.summary:
            root = next(p for p in meta["packages"] if p["id"] == meta["resolve"]["root"])
            expression, unstated = summary([root] + packages)
            print(expression)
            if unstated:
                print("third-party-licences.py: left out, as they state no licence: "
                      + ", ".join(unstated), file=sys.stderr)
        else:
            lock = os.path.relpath(pathlib.Path(meta["workspace_root"]) / "Cargo.lock")
            sys.stdout.write(report(packages, lock, target))
    except LicenceError as error:
        print(f"third-party-licences.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
