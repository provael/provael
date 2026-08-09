#!/usr/bin/env python3
"""Fail if any relative markdown link does not resolve CASE-EXACTLY against the git index.

WHY THE GIT INDEX AND NOT THE FILESYSTEM. macOS and Windows ship case-insensitive filesystems, so
``open("docs/TOP10.md")`` succeeds locally when the tracked file is ``docs/top10.md``. github.com
serves from a case-SENSITIVE store and returns 404. A local check therefore passes on exactly the
links that are broken for every visitor, which is the whole failure mode this script exists to
catch — and it is invisible to the author, by construction.

``git ls-files`` returns the tracked names with their real case, so comparing against that set
reproduces what github.com will do.

Directory targets (``examples/``, ``../adapters/``) are valid: GitHub renders a directory listing.
They are matched against the set of directories implied by tracked files rather than against the
files themselves.

Run:  uv run python scripts/check_links.py
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

#: ``[text](target)`` with an optional ``#anchor``. Anchors are not verified — that needs a heading
#: index per file, and a wrong anchor degrades to "lands at the top of the right page" rather than
#: a 404, which is a different severity.
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")

#: Not our problem: external URLs need the network (and rate-limit), and mailto has no path.
EXTERNAL = ("http://", "https://", "mailto:", "#")


def tracked_paths() -> tuple[set[str], set[str]]:
    """Every tracked file, and every directory those files imply, with git's exact casing."""
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split("\n")
    files = {line for line in out if line}
    dirs: set[str] = set()
    for f in files:
        parent = pathlib.PurePosixPath(f).parent
        while str(parent) not in (".", ""):
            dirs.add(str(parent))
            parent = parent.parent
    return files, dirs


def broken_links() -> list[str]:
    files, dirs = tracked_paths()
    markdown = subprocess.run(
        ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
    ).stdout.split()
    bad: list[str] = []
    for md in markdown:
        base = os.path.dirname(md)
        text = pathlib.Path(md).read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for target in LINK.findall(line):
                if target.startswith(EXTERNAL):
                    continue
                # normpath collapses "..", which PurePosixPath does NOT — without it every
                # "../top10.md" reads as a miss and the check drowns in false positives.
                resolved = os.path.normpath(os.path.join(base, target.rstrip("/")))
                if resolved in files or resolved in dirs:
                    continue
                bad.append(f"{md}:{lineno}: {target} -> {resolved}")
    return bad


def main() -> int:
    bad = broken_links()
    if not bad:
        print("link check: all relative markdown links resolve case-exactly against the git index")
        return 0
    print(f"link check: {len(bad)} broken relative link(s)\n", file=sys.stderr)
    for item in bad:
        print(f"  {item}", file=sys.stderr)
    print(
        "\nNote: a case-only mismatch passes on macOS/Windows and 404s on github.com.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
