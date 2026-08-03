"""One guard for the regulatory dates that get restated outside ``attest.REGULATORY_CLOCK``.

The clock is embedded in the payload of every **signed** attestation. That raises the cost of a
stale date above the usual: a signature does not make a fact true, it makes a wrong fact
*tamper-evident and durable*. A bundle carrying a superseded application date guarantees the
integrity of something false, and the recipient — a notified body, an insurer — has no way to tell
from the bundle that the date moved.

WHAT WENT WRONG, AND WHY A DATE GUARD EXISTS AT ALL. The EU AI Act entry carried
``applies_from="2027-08-02"`` with a note explaining that the Digital Omnibus deferral to 2028 was
only provisionally agreed and had not reached the Official Journal. That note was accurate when it
was written and ``last_verified`` recorded 2026-07-23. Regulation (EU) 2026/1744 was published in
the OJ on **2026-07-24** and entered into force on **2026-07-27** — the fact was checked one day
before it changed, and nothing re-read it. The website had already been corrected (its
``check-facts.mjs`` bans the old phrasings outright); the product had not, so the two repos
disagreed about a legal date while one of them was signing it.

WHY THIS BANS PHRASES AND NOT THE DATE. ``2027-08-02`` is still correct prose — it is the
superseded statutory baseline, and naming it is *more* honest than deleting it. What cannot come
back is the framing that the deferral is pending: that is what turns a historical note into a
current claim. So the scan targets the stale framing, mirroring the forbidden-string list the
website already enforces, and leaves the dates alone.

Two exemptions, both deliberate:

* ``CHANGELOG.md`` — historical entries legitimately record what was true at the time.
* **This file** — it is scanned like any other tracked file, and it necessarily spells out the
  phrases it bans. ``test_the_exemption_list_stays_short`` keeps that from quietly growing.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from provael.attest import REGULATORY_CLOCK

REPO = Path(__file__).resolve().parent.parent

#: The operative date for AI Act Annex I embedded high-risk, post-Omnibus.
AI_ACT_APPLIES_FROM = "2028-08-02"

#: Framing that asserts the Omnibus deferral is still pending. Each was true before 2026-07-24 and
#: is false after it. Matched case-insensitively.
_SUPERSEDED_FRAMING: tuple[tuple[str, str], ...] = (
    (r"not yet formally adopted", "says the Omnibus deferral is unadopted"),
    (r"provisional agreement", "calls the Omnibus deferral provisional"),
    (r"provisional \*{0,2}2028-08-02", "calls the adopted 2028 date provisional"),
    (r"proposed 2028-08-02", "calls the 2028 date proposed"),
    (r"treat 2027 as binding", "instructs the reader to plan against the superseded date"),
)

#: Files allowed to contain the superseded framing. Keep this short; a missing entry fails loudly,
#: which is the safe direction for a check like this.
_EXEMPT = frozenset({"CHANGELOG.md", "tests/test_regulatory_consistency.py"})


def _tracked_text_files() -> list[Path]:
    """Every git-tracked file that reads as text, relative to the repo root."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=False
    )
    paths: list[Path] = []
    for name in out.stdout.split("\0"):
        if not name:
            continue
        p = REPO / name
        try:
            p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        paths.append(p)
    return paths


def test_the_clock_names_the_operative_date() -> None:
    """``REGULATORY_CLOCK`` is the single source of truth, so it is checked directly."""
    ai_act = {c.framework_id: c for c in REGULATORY_CLOCK}["eu-ai-act"]
    assert ai_act.applies_from == AI_ACT_APPLIES_FROM
    assert "2026/1744" in ai_act.note, "the instrument that moved the date must be cited in-band"


def test_no_tracked_file_carries_the_superseded_framing() -> None:
    """The stale framing must not survive anywhere a reader or a signature can pick it up."""
    offenders: list[str] = []
    for path in _tracked_text_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in _EXEMPT:
            continue
        body = path.read_text(encoding="utf-8")
        for pattern, why in _SUPERSEDED_FRAMING:
            if re.search(pattern, body, re.I):
                offenders.append(f"{rel}: {why} (matched {pattern!r})")
    assert not offenders, "superseded AI Act framing found:\n  " + "\n  ".join(offenders)


def test_every_restatement_of_the_date_agrees_with_the_clock() -> None:
    """``hosted/report.py`` restates the date for the API surface; it cannot drift from the clock.

    A second copy is the whole problem this file exists for. It is kept rather than derived because
    the hosted payload is a plain dict shipped without importing the attest module, but a copy that
    nothing compares is a copy that will diverge.
    """
    hosted = (REPO / "src/provael/hosted/report.py").read_text(encoding="utf-8")
    ai_act_rows = re.findall(r'"instrument":\s*"([^"]*AI Act[^"]*)"[\s\S]{0,200}?"applies_from":\s*"([^"]+)"', hosted)
    assert ai_act_rows, "no AI Act row found in hosted/report.py — has the shape changed?"
    for instrument, applies_from in ai_act_rows:
        assert applies_from == AI_ACT_APPLIES_FROM, (
            f"hosted/report.py says {applies_from} for {instrument!r}, "
            f"clock says {AI_ACT_APPLIES_FROM}"
        )


def test_the_scan_actually_reads_files() -> None:
    """Guard the guard: a scan that reads nothing passes every assertion above."""
    files = _tracked_text_files()
    assert len(files) > 100, f"only {len(files)} tracked text files — the scan is not working"
    assert any(f.name == "attest.py" for f in files)


@pytest.mark.parametrize("pattern", [p for p, _ in _SUPERSEDED_FRAMING])
def test_each_banned_pattern_compiles(pattern: str) -> None:
    """A pattern that does not compile silently bans nothing."""
    assert re.compile(pattern, re.I) is not None


def test_the_exemption_list_stays_short() -> None:
    """Exemptions are the failure mode of an inverted allow-list. Two is the intended size."""
    assert sorted(_EXEMPT) == ["CHANGELOG.md", "tests/test_regulatory_consistency.py"]
