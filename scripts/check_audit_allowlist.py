#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Fail the GPU-extras audit on anything its reviewed allow-list does not account for.

WHAT WENT WRONG. The extras that load in-process ([lerobot], [openvla], [attest], [hosted]) were
audited in a CI lane that could not fail, so a new advisory in torch, transformers or diffusers
printed a line nobody had to read and the merge went ahead. Simply removing `continue-on-error`
would not have helped: torch and transformers advisories often have no fixed version, lerobot's
0.5.1 pin holds most of the rest back, and a detector that is always red reports nothing.

WHAT THIS DOES INSTEAD. Known ids sit in `.github/pip-audit-extras-allowlist.toml`, each with a
reason, a reachability finding and a review date. This exits non-zero, printing one line per
problem, on:

* an advisory not listed for that package and version;
* a listed advisory the audit no longer reports (stale, so it gets removed);
* a `review_by` that has passed, or that sits more than 60 days out;
* an entry saying `reachable = "yes"`, which belongs in an issue rather than on a list;
* a report that checked nothing: missing, unreadable, empty, or with a skipped dependency. pip-audit
  exits 1 both when it finds something and when it crashes, so the lane ignores its exit status and
  this is what stops a crash from reading as a pass.

FOUR THINGS A READER WOULD OTHERWISE RE-DERIVE.

Matching goes through aliases. pip-audit prints whichever id the feed's record carries, PYSEC today
and possibly GHSA tomorrow, for the same advisory. An entry keeps working across that relabel.

Matching includes the version. A bump that leaves an advisory open changes the code its reason was
written against, so it reads as one new advisory plus one stale entry, and somebody re-reads it.

Repeated rows count once. pip-audit repeats an id when the feed holds two records for one advisory:
it printed 16 rows for 13 ids on 7 November 2026.

`in_feed = false` exists for one honest case. GHSA-f7vj-73pm-m822 is real and has a justification,
but neither PyPI's feed nor OSV maps it to lerobot, so the audit cannot report it and would call it
stale forever. Dropping it would lose the only thing that makes somebody re-read it every 60 days.

    python scripts/check_audit_allowlist.py audit-extras.json
    python scripts/check_audit_allowlist.py audit-extras.json --today 2027-01-06  # preview a date
    uvx pip-audit==2.10.1 --format json -r reqs.txt | python scripts/check_audit_allowlist.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

#: The reviewed list the lane reads.
DEFAULT_ALLOWLIST = ROOT / ".github" / "pip-audit-extras-allowlist.toml"

#: What every entry has to carry.
REQUIRED_FIELDS = ("id", "package", "version", "reason", "reachable", "review_by")

#: What an entry may say. "yes" is refused: a reachable advisory is an open issue, not an exception.
LISTABLE = ("no", "not assessed")

#: The longest a review can be put off.
MAX_REVIEW_DAYS = 60


@dataclass(frozen=True)
class Advisory:
    """One advisory as the audit reported it, with its repeated rows merged."""

    id: str
    package: str
    version: str
    names: frozenset[str]
    fix_versions: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.id} {self.package} {self.version}"


@dataclass(frozen=True)
class Entry:
    """One well-formed table of the allow-list."""

    id: str
    package: str
    version: str
    review_by: date
    in_feed: bool

    def __str__(self) -> str:
        return f"{self.id} {self.package} {self.version}"

    def covers(self, advisory: Advisory) -> bool:
        return (
            self.package == advisory.package
            and self.version == advisory.version
            and self.id in advisory.names
        )


def canonical(name: str) -> str:
    """PEP 503, so a package typed by hand matches the name in the report."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_report(report: Any) -> tuple[list[Advisory], list[str]]:
    """The advisories in a pip-audit JSON report, and every dependency it skipped."""
    merged: dict[tuple[str, str, str], Advisory] = {}
    problems: list[str] = []
    for dep in report["dependencies"]:
        package = canonical(dep["name"])
        if "skip_reason" in dep:
            problems.append(f"{package}: pip-audit skipped it, so it was not audited")
            continue
        for vuln in dep.get("vulns", []):
            key = (vuln["id"], package, dep["version"])
            names = {vuln["id"], *vuln.get("aliases", [])}
            fixes = tuple(vuln.get("fix_versions", []))
            if key in merged:
                names |= merged[key].names
                fixes = merged[key].fix_versions or fixes
            merged[key] = Advisory(vuln["id"], package, dep["version"], frozenset(names), fixes)
    return list(merged.values()), problems


def parse_entry(raw: dict[str, Any], today: date) -> tuple[Entry | None, list[str]]:
    """One table of the allow-list, and what is wrong with it. None when it cannot be matched."""
    label = f"{raw.get('id', '?')} {raw.get('package', '?')} {raw.get('version', '?')}"
    missing = [field for field in REQUIRED_FIELDS if not raw.get(field)]
    if missing:
        return None, [f"{label}: the allow-list entry is missing {', '.join(missing)}"]
    review_by = raw["review_by"]
    if type(review_by) is not date:
        return None, [f"{label}: review_by must be a TOML date, not {review_by!r}"]

    problems: list[str] = []
    if raw["reachable"] == "yes":
        problems.append(f'{label}: reachable = "yes" cannot be allow-listed; open an issue')
    elif raw["reachable"] not in LISTABLE:
        problems.append(f"{label}: reachable must be one of {LISTABLE}, not {raw['reachable']!r}")
    if review_by < today:
        problems.append(f"{label}: review_by {review_by} has passed; re-read it and move the date")
    elif review_by > today + timedelta(days=MAX_REVIEW_DAYS):
        problems.append(f"{label}: review_by {review_by} is over {MAX_REVIEW_DAYS} days out")
    in_feed = raw.get("in_feed", True) is not False
    entry = Entry(raw["id"], canonical(raw["package"]), raw["version"], review_by, in_feed)
    return entry, problems


def parse_allowlist(allowlist: dict[str, Any], today: date) -> tuple[list[Entry], list[str]]:
    """Every well-formed entry, and what is wrong with the list."""
    entries: list[Entry] = []
    problems: list[str] = []
    for raw in allowlist.get("advisory", []):
        entry, entry_problems = parse_entry(raw, today)
        problems += entry_problems
        if entry is not None:
            entries.append(entry)
    counts = Counter(str(entry) for entry in entries)
    problems += [f"{label}: listed {n} times" for label, n in counts.items() if n > 1]
    return entries, problems


def check(report: Any, allowlist: dict[str, Any], today: date) -> list[str]:
    """Every problem with this report against this list, one line each. Empty means pass."""
    if not report.get("dependencies"):
        return ["the audit report lists no dependencies, so it checked nothing"]
    advisories, problems = parse_report(report)
    entries, list_problems = parse_allowlist(allowlist, today)
    problems += list_problems

    for advisory in advisories:
        if not any(entry.covers(advisory) for entry in entries):
            fix = ", ".join(advisory.fix_versions) or "none"
            problems.append(f"{advisory}: not on the allow-list (fixed in: {fix})")
    for entry in entries:
        reported = any(entry.covers(advisory) for advisory in advisories)
        if reported and not entry.in_feed:
            problems.append(f"{entry}: the audit reports it now; remove in_feed and re-read it")
        elif entry.in_feed and not reported:
            problems.append(f"{entry}: stale, the audit no longer reports it; remove the entry")
    return problems


def _summary(report: Any, allowlist: dict[str, Any]) -> str:
    advisories, _ = parse_report(report)
    next_review = min((raw["review_by"] for raw in allowlist.get("advisory", [])), default="never")
    return (
        f"{len(advisories)} advisories in {len({a.package for a in advisories})} packages, "
        f"all on the reviewed allow-list; next review by {next_review}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check a pip-audit JSON report against the reviewed allow-list."
    )
    parser.add_argument(
        "report", nargs="?", default="-", help="pip-audit --format json output; default: stdin"
    )
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument(
        "--today", type=date.fromisoformat, help="check as of this date (default: today, UTC)"
    )
    args = parser.parse_args(argv)
    today = args.today or datetime.now(UTC).date()

    try:
        text = sys.stdin.read() if args.report == "-" else Path(args.report).read_text("utf-8")
        report = json.loads(text)
    except (OSError, ValueError) as exc:
        print(f"cannot read the audit report, so pip-audit may have crashed: {exc}")
        return 1
    try:
        allowlist = tomllib.loads(args.allowlist.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        print(f"cannot read the allow-list {args.allowlist}: {exc}")
        return 1
    try:
        problems = check(report, allowlist, today)
    except (AttributeError, KeyError, TypeError) as exc:
        print(f"the audit report is not pip-audit JSON: {exc!r}")
        return 1

    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(_summary(report, allowlist))
    return 0


if __name__ == "__main__":
    sys.exit(main())
