#!/usr/bin/env python3
"""Refuse a pull request that changes published behaviour without a changelog line.

WHY THIS EXISTS, AND IT IS A DIFFERENT GAP FROM `check_changelog.py`. That script gates a
RELEASE: it refuses to cut a tag `CHANGELOG.md` does not document. It cannot see the window
where the damage actually happens — between merge and release, when the entry that should have
been written is already forgotten.

#157 and #158 both merged with no changelog line at all. #157 is the one that makes this a gate
rather than a nicety: it corrected a confidence interval that had been published on two READMEs
for 21 days, and disagreed with the project's own website the whole time. A correction of a
published number that leaves no record is close to the worst failure mode available to a project
whose entire pitch is evidence you can check. The release gate would not have caught it either —
`[Unreleased]` was non-empty, so `check_changelog.py` was satisfied by two entries about a
different change.

WHAT COUNTS AS PUBLISHED BEHAVIOUR. `src/` (the tool), `results/` (committed real-model run
artifacts — the substrate `coverage.py` and the evidence manifest read) and `README.md` (the most
quoted surface in the project). Deliberately NOT `docs/`, `tests/` or `.github/`: a docs edit is
usually its own record, and requiring a changelog line for every test would train contributors to
write filler, which is worse than silence because it hides the real entries.

THE SKIP LABEL IS NARROW ON PURPOSE. `no-changelog` exists for a change that genuinely publishes
nothing — a pure refactor, a typo in a docstring, a test-only touch inside `src/`. It is a label
rather than a commit-message token so that applying it is a visible, attributable act on the PR
rather than something buried in a squashed subject.

Worth stating plainly, because the motivating example does not need it: the bot refreshes
(`chore(watch): refresh the measurement-freshness badge …`) never reach this check at all. They
push directly to `main` rather than opening a PR, they carry a CI-skip marker in the subject, and
they touch only `watch/`, which is not a watched path. Three independent reasons. The label is for
humans.

DO NOT SPELL THAT MARKER OUT HERE, OR IN A COMMIT MESSAGE. The literal token is written once, in
`.github/workflows/freshness.yml`, where it does a job. Describing it in prose costs a release:
the commit that first added this file explained the bot refreshes and quoted the token verbatim,
the squash-merge carried that text into the merge commit's body, and GitHub honoured it — the push
to `main` produced zero workflow runs, and every `v0.38.1` tag pointing at that commit was skipped
too, three pushes in a row, while the workflow sat there `active` and correctly configured.

This class cannot be guarded from CI, which is the whole trouble: a check cannot run on the commit
that switches checks off. The only defence is not writing the token where it can be copied.

    python scripts/check_changelog_entry.py --changed-files changed.txt --labels "bug,no-changelog"
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

#: Path prefixes whose change is a change to something the project publishes.
WATCHED_PREFIXES = ("src/", "results/")

#: Exact paths that count for the same reason, without their whole directory counting.
WATCHED_FILES = ("README.md",)

#: The file that must move alongside them.
CHANGELOG = "CHANGELOG.md"

#: Applying this to a PR is an explicit statement that the change publishes nothing.
SKIP_LABEL = "no-changelog"


def watched(paths: Iterable[str]) -> list[str]:
    """Return the changed paths that represent published behaviour."""
    return sorted(
        p
        for p in paths
        if p.startswith(WATCHED_PREFIXES) or p in WATCHED_FILES
    )


def decide(changed: Iterable[str], labels: Iterable[str]) -> tuple[bool, str]:
    """Return ``(ok, message)`` for one pull request.

    Pure so it can be tested without a checkout, a network call, or a GitHub event — the same
    reason the Action's gate logic lives in ``scripts/action/`` rather than inside ``action.yml``.
    """
    changed = list(changed)
    labels = {str(label).strip() for label in labels if str(label).strip()}
    triggering = watched(changed)

    if not triggering:
        return True, "No change under src/, results/ or README.md — no changelog entry required."

    if CHANGELOG in changed:
        return True, f"{CHANGELOG} changed alongside {len(triggering)} published path(s)."

    if SKIP_LABEL in labels:
        return True, (
            f"{len(triggering)} published path(s) changed with no {CHANGELOG} entry, "
            f"allowed by the '{SKIP_LABEL}' label."
        )

    listed = "\n".join(f"    {p}" for p in triggering[:20])
    more = f"\n    … and {len(triggering) - 20} more" if len(triggering) > 20 else ""
    return False, (
        f"This PR changes {len(triggering)} path(s) that the project publishes, and does not "
        f"touch {CHANGELOG}:\n{listed}{more}\n\n"
        f"Add an entry under ## [Unreleased]. If a number moved, say what was published before, "
        f"for how long, and what it is now — that is what #157 needed and did not have.\n\n"
        f"If this change genuinely publishes nothing (a pure refactor, a test-only touch), apply "
        f"the '{SKIP_LABEL}' label to say so on the record."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--changed-files",
        required=True,
        type=Path,
        help="File holding one changed path per line (git diff --name-only).",
    )
    ap.add_argument("--labels", default="", help="Comma-separated PR labels.")
    args = ap.parse_args()

    text = args.changed_files.read_text(encoding="utf-8")
    changed = [line.strip() for line in text.splitlines() if line.strip()]

    # An empty diff means the base was not fetched, not that the PR is empty. Failing loudly beats
    # passing every PR forever on a silently shallow checkout — the shape of guard this repo has
    # already been bitten by twice.
    if not changed:
        print("check-changelog-entry: the changed-file list is EMPTY.", file=sys.stderr)
        print(
            "  A PR always changes something, so this means the diff was computed wrong "
            "(usually a shallow checkout with no base ref). Refusing to pass.",
            file=sys.stderr,
        )
        return 1

    ok, message = decide(changed, args.labels.split(","))
    if ok:
        print(f"check-changelog-entry: {message}")
        return 0
    print(f"check-changelog-entry: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
