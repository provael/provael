# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""A to-do whose date has passed cannot sit in a paper README or the roadmap's Now section.

THE INCIDENT. ``paper/spais/README.md`` listed what was "Still to do before 1 October": fold in the
calibrated-predicate result if a run landed in time, a read-through, and the OpenReview upload. The
deadline passed on 2 October 2026 and the sentence stayed, so the repository could not tell a
reader whether the paper had gone in, and it still implied that a re-fit the roadmap dates to
24 October could arrive before a 1 October deadline. The roadmap promises that each proof "has a
date this page will keep or publicly miss", and nothing checked that a dated to-do was ever
resolved either way.

WHAT THIS HOLDS. In ``paper/*/README.md`` and in the ``## Now`` section of ``docs/roadmap.md``,
"to do before <day> <Month> [<year>]" fails once that day is earlier than today's UTC date. A
missing year means the current year, so a to-do that crosses a year end must carry its year. The
words are matched across any run of whitespace, a line break included, because the README wrapped
the phrase as "Still to" / "do before". The text is matched as written rather than normalised
first, so a failure names the file's own line.

WHAT IT LEAVES ALONE. Only the to-do phrase. A deadline line ("OpenReview due 2 Oct 11:59 UTC"), a
proof's original target, and every other past date are history and keep passing: a past date is not
wrong, an unresolved promise dated in the past is.

The real-tree test reads the clock, so it can go red on main with no commit: the day a dated to-do
passes unresolved is the day it should. That is the freshness badge's design too, which goes stale
on its own instead of waiting for someone to remember.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROADMAP = "docs/roadmap.md"

_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

#: "to do before 1 October" or "to do before 1 October 2026", day first as this repository writes
#: dates, with any whitespace between the words.
_TODO = re.compile(
    r"\bto\s+do\s+before\s+(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\b(?:\s+(\d{4})\b)?",
    re.IGNORECASE,
)


def _scanned(rel: str, text: str) -> tuple[int, int]:
    """The span this guard reads: a whole paper README, or only the roadmap's Now section."""
    if rel != ROADMAP:
        return 0, len(text)
    start = text.find("\n## Now")
    assert start != -1, f"{ROADMAP} has no '## Now' section; this test reads it"
    end = text.find("\n## ", start + 1)
    return start, end if end != -1 else len(text)


def past_todos(root: Path, rels: Iterable[str], today: date) -> list[str]:
    """Every to-do in ``rels`` dated before ``today``, as ``file:line: phrase (date)``."""
    offenders: list[str] = []
    for rel in rels:
        text = (root / rel).read_text(encoding="utf-8")
        lo, hi = _scanned(rel, text)
        for m in _TODO.finditer(text, lo, hi):
            line = text.count("\n", 0, m.start()) + 1
            phrase = " ".join(m.group(0).split())
            year = int(m.group(3)) if m.group(3) else today.year
            try:
                due = date(year, _MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))
            except ValueError:
                offenders.append(f"{rel}:{line}: '{phrase}' is not a calendar date")
                continue
            if due < today:
                offenders.append(f"{rel}:{line}: '{phrase}' was due {due.isoformat()}")
    return offenders


def _scanned_files() -> list[str]:
    readmes = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("paper/*/README.md"))
    assert readmes, "no paper/*/README.md found; this test would check nothing"
    return [*readmes, ROADMAP]


def test_no_paper_readme_or_roadmap_now_section_keeps_a_past_dated_todo() -> None:
    today = datetime.now(UTC).date()
    offenders = past_todos(ROOT, _scanned_files(), today)
    assert not offenders, (
        f"A to-do dated before today ({today.isoformat()}) is still written as a to-do. Say what "
        "happened instead (done, dropped, or moved to a new date), in the past tense:\n  "
        + "\n  ".join(offenders)
    )


def _write(root: Path, rel: str, text: str) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel


def test_a_past_dated_todo_fails_when_the_phrase_wraps_a_line(tmp_path: Path) -> None:
    rel = _write(
        tmp_path,
        "paper/x/README.md",
        "Deadline **1 October 2026 AoE**.\nIt builds. Still to\ndo before 1 October: the upload.\n",
    )
    assert past_todos(tmp_path, [rel], date(2026, 10, 2)) == [
        "paper/x/README.md:2: 'to do before 1 October' was due 2026-10-01"
    ]


def test_a_past_year_fails_and_a_bad_date_is_named(tmp_path: Path) -> None:
    rel = _write(
        tmp_path,
        "paper/x/README.md",
        "Still to do before 3 March 2025.\nAlso to do before 31 February.\n",
    )
    assert past_todos(tmp_path, [rel], date(2026, 10, 2)) == [
        "paper/x/README.md:1: 'to do before 3 March 2025' was due 2025-03-03",
        "paper/x/README.md:2: 'to do before 31 February' is not a calendar date",
    ]


def test_a_todo_dated_today_or_later_passes(tmp_path: Path) -> None:
    rel = _write(
        tmp_path,
        "paper/x/README.md",
        "Still to do before 2 October. Then to do before 24 October 2026.\n",
    )
    assert past_todos(tmp_path, [rel], date(2026, 10, 2)) == []


def test_history_and_the_rest_of_the_roadmap_are_left_alone(tmp_path: Path) -> None:
    """A past deadline is history; outside the roadmap's Now section the guard does not read."""
    readme = _write(
        tmp_path,
        "paper/x/README.md",
        "Deadline **1 October 2026 AoE** (OpenReview due 2 Oct 11:59 UTC). Submitted.\n",
    )
    roadmap = _write(
        tmp_path,
        ROADMAP,
        "# Roadmap\n\n## Now\n\nStill to do before 1 October: the upload.\n\n"
        "## Shipped\n\nOnce to do before 1 September: a release.\n",
    )
    assert past_todos(tmp_path, [readme, roadmap], date(2026, 10, 2)) == [
        "docs/roadmap.md:5: 'to do before 1 October' was due 2026-10-01"
    ]
