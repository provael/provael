#!/usr/bin/env python3
"""Refuse to cut a release unless CHANGELOG.md documents that exact version.

WHY THIS EXISTS. 0.31.1 had to be written retroactively: a tag shipped to PyPI on 3 August with no
changelog section at all. The release workflow noticed the gap and papered over it —

    if [ ! -s release-notes.md ]; then echo "Release ${GITHUB_REF_NAME}" > release-notes.md; fi

— so the GitHub Release was cut with the body "Release v0.31.1" and the artifact went out. Nothing
failed. At 33 releases in 10 weeks that is not a one-off, it is a recurring silent downgrade of the
one document a user reads to decide whether to upgrade.

This runs BEFORE the build, so a tag with no changelog section never reaches PyPI at all. Publishing
is irreversible: a version number cannot be reused, so the check has to be a gate rather than a
warning attached to something already shipped.

THE HEADING FORMAT IS THE REPO'S, NOT KEEP-A-CHANGELOG'S. Every existing heading uses an EM DASH:

    ## [0.32.0] — 2026-08-08

Keep a Changelog writes a hyphen, and requiring one here would reject all 33 historical entries.
All three dashes are accepted so a contributor typing the ASCII one is not blocked on punctuation,
but the date must be a real ISO date — "2026-13-45" parses as a string and is not a date.

    python scripts/check_changelog.py 0.32.0
    python scripts/check_changelog.py v0.32.0     # a leading v is stripped
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys

CHANGELOG = pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md"

#: `## [1.2.3] <dash> 2026-08-09`, accepting hyphen, en dash or em dash. The version is matched
#: literally (re.escape) rather than as a pattern, so `1.2.3` cannot match `1x2x3`.
HEADING = "^##[ \t]+\\[{version}\\][ \t]*[-–—][ \t]*(\\d{{4}}-\\d{{2}}-\\d{{2}})[ \t]*$"


def find_entry(version: str, text: str) -> tuple[bool, str | None]:
    """Return (heading found, the date string it carries)."""
    match = re.search(HEADING.format(version=re.escape(version)), text, re.MULTILINE)
    return (match is not None, match.group(1) if match else None)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0] if argv else 'check_changelog.py'} <version>", file=sys.stderr)
        return 2
    version = argv[1].lstrip("vV")

    if not CHANGELOG.is_file():
        print(f"error: {CHANGELOG} does not exist", file=sys.stderr)
        return 1
    text = CHANGELOG.read_text(encoding="utf-8")

    found, date = find_entry(version, text)
    if not found:
        print(
            f"error: CHANGELOG.md has no section for {version}.\n\n"
            f"  Expected a heading of the form:\n"
            f"    ## [{version}] — {dt.date.today().isoformat()}\n\n"
            f"  This gate exists because 0.31.1 shipped to PyPI with no changelog section and had\n"
            f"  to be written retroactively. A published version cannot be unpublished, so the\n"
            f"  section has to exist BEFORE the tag, not after.",
            file=sys.stderr,
        )
        existing = re.findall(r"^##[ \t]+\[([^\]]+)\]", text, re.MULTILINE)[:6]
        if existing:
            print(f"\n  Headings currently in CHANGELOG.md: {', '.join(existing)}", file=sys.stderr)
        return 1

    assert date is not None
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        print(
            f"error: the {version} heading carries '{date}', which is not a real date.\n"
            f"  A heading that parses as text but not as a date defeats the point of dating it.",
            file=sys.stderr,
        )
        return 1

    print(f"changelog gate: CHANGELOG.md documents {version} ({date})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
