#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Fail when a commit in a range lacks a ``Signed-off-by`` trailer.

WHY THIS EXISTS. CONTRIBUTING.md has asked for the Developer Certificate of Origin sign-off since
the repository opened, and nothing enforced it: 69 of the 438 commits up to 19 September 2026
carried the trailer. Contribution terms that are not checked are not terms. This is the check;
`.github/workflows/ci.yml` runs it on every pull request over ``base..head``, and
``scripts/hooks/prepare-commit-msg`` (installed by ``make hooks``) adds the trailer locally so the
check is rarely the thing that tells you.

Bots are exempt by author e-mail (dependabot, github-actions): their commits are produced by
workflows in this repository and carry no human authorship to certify. Merge commits are skipped
because ``main`` requires linear history and a merge commit's parents are checked on their own.

Usage::

    python scripts/check_dco.py --range origin/main..HEAD
    python scripts/check_dco.py --range <base-sha>..<head-sha>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

TRAILER = "Signed-off-by:"
BOT_EMAIL_SUFFIXES = (
    "dependabot[bot]@users.noreply.github.com",
    "github-actions[bot]@users.noreply.github.com",
)
_SEP = "\x1e"  # record separator: safe inside commit messages, which never contain it


@dataclass(frozen=True)
class Commit:
    sha: str
    author_email: str
    parents: int
    body: str

    @property
    def is_bot(self) -> bool:
        return self.author_email.endswith(BOT_EMAIL_SUFFIXES)

    @property
    def is_merge(self) -> bool:
        return self.parents > 1

    @property
    def signed_off(self) -> bool:
        return any(line.strip().startswith(TRAILER) for line in self.body.splitlines())


def commits_in(rev_range: str) -> list[Commit]:
    fmt = f"%H%x00%ae%x00%P%x00%B{_SEP}"
    out = subprocess.run(
        ["git", "log", "--reverse", f"--format={fmt}", rev_range],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    commits: list[Commit] = []
    for record in out.split(_SEP):
        if not record.strip():
            continue
        sha, email, parents, body = record.lstrip("\n").split("\x00", 3)
        commits.append(Commit(sha, email, len(parents.split()) if parents else 0, body))
    return commits


def unsigned(commits: list[Commit]) -> list[Commit]:
    return [c for c in commits if not (c.is_bot or c.is_merge or c.signed_off)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check DCO sign-off on a commit range.")
    ap.add_argument("--range", required=True, help="git revision range, e.g. origin/main..HEAD")
    args = ap.parse_args(argv)

    commits = commits_in(args.range)
    missing = unsigned(commits)
    if missing:
        print(f"{len(missing)} commit(s) without a '{TRAILER}' trailer:", file=sys.stderr)
        for c in missing:
            subject = c.body.splitlines()[0] if c.body.strip() else "(no message)"
            print(f"  {c.sha[:10]}  {c.author_email}  {subject}", file=sys.stderr)
        print(
            "\nSign off every commit (Developer Certificate of Origin, see CONTRIBUTING.md):\n"
            "  the last commit:  git commit --amend -s --no-edit\n"
            "  a whole branch:   git rebase --signoff <base>\n"
            "  from now on:      make hooks   (installs scripts/hooks/prepare-commit-msg)",
            file=sys.stderr,
        )
        return 1
    print(f"every commit in {args.range} is signed off ({len(commits)} checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
