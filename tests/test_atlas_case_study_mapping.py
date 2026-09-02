"""The ATLAS table in the case-study page must not drift from the catalog it mirrors.

WHY THIS EXISTS. `docs/standards/atlas-case-study.md` restates a mapping that already has a
generator: `provael.eai.CATALOG` carries `atlas_techniques`, `provael crosswalk --target atlas`
emits it, and `src/provael/sarif.py` puts it on every SARIF rule as `properties.atlasTechniques`.
The page is the human-readable mirror, and it was hand-maintained with no guard — so it drifted in
the quietest possible way: it carried EIGHT of the ten risks, and the two it dropped were exactly
the two that map to nothing. An absent row reads as an oversight rather than as the answer it is.

So this pins the shape, not the prose. Technique wording is deliberately not asserted — that lives
in the catalog, a test that fails on a rewording teaches people to edit the test, and
`tests/test_eai.py` already guards the technique strings themselves.
"""

from __future__ import annotations

import re
from pathlib import Path

from provael.eai import CATALOG, all_ids

PAGE = Path(__file__).resolve().parent.parent / "docs" / "standards" / "atlas-case-study.md"

#: The only statuses the page defines. `none-yet` is load-bearing: it is what an honest empty row
#: says, and dropping the row instead is the drift this test was written after.
VALID = {"proposed-mapped", "proposed-gap", "none-yet"}

ROW = re.compile(r"^\|\s*(EAI\d{2})\s*\|.*\|\s*`([a-z-]+)`\s*\|\s*$", re.MULTILINE)


def _expected(eai_id: str) -> str:
    """The status the catalog implies for a risk.

    Derived, never typed: an empty `atlas_techniques` is `none-yet`, a technique that marks itself
    `(proposed` is a proposed extension over a gap, and anything else is an on-point ATLAS technique
    in our own words.
    """
    techniques = CATALOG[eai_id].atlas_techniques
    if not techniques:
        return "none-yet"
    return "proposed-gap" if "(proposed" in techniques[0] else "proposed-mapped"


def _rows() -> dict[str, str]:
    return {m.group(1): m.group(2) for m in ROW.finditer(PAGE.read_text(encoding="utf-8"))}


def test_every_risk_appears_exactly_once() -> None:
    text = PAGE.read_text(encoding="utf-8")
    rows = _rows()
    assert set(rows) == set(all_ids()), (
        f"the ATLAS table lists {sorted(rows)} but the catalog has {sorted(all_ids())}. "
        "Every risk gets a row, including the ones that map to nothing."
    )
    for eai_id in all_ids():
        assert len(ROW.findall(text.replace(eai_id, eai_id, 1))) == len(rows), "duplicate rows"


def test_each_status_is_the_one_the_catalog_implies() -> None:
    for eai_id, status in _rows().items():
        assert status == _expected(eai_id), (
            f"{eai_id} is documented as `{status}` but the catalog implies `{_expected(eai_id)}`"
        )


def test_no_status_outside_the_documented_vocabulary() -> None:
    for eai_id, status in _rows().items():
        assert status in VALID, f"{eai_id} uses undefined mapping_status `{status}`"


def test_none_yet_is_actually_used() -> None:
    """A vocabulary that defines `none-yet` and never uses it is the drift wearing a disguise."""
    statuses = set(_rows().values())
    assert "none-yet" in statuses, "no row is `none-yet`, but the catalog has two risks with no ATLAS technique"
    assert sum(1 for s in _rows().values() if s == "none-yet") == sum(
        1 for e in all_ids() if not CATALOG[e].atlas_techniques
    )


def test_the_guard_can_actually_fail() -> None:
    """A dropped row must be detectable, since that is the defect this was written after."""
    kept = {k: v for k, v in _rows().items() if k != "EAI07"}
    assert set(kept) != set(all_ids())
