# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""SECURITY.md states one set of counterparty facts, and never contradicts itself about them.

R12 (19 Sep 2026): the file opened with "published by an open-source steward" and, ninety lines
later, explained that a steward under Article 3(14) must be a legal person and that there is no
entity. Both sentences were true of the document and false of each other. The regulatory context is
now one dated statement; this test holds the file to it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY = (ROOT / "SECURITY.md").read_text(encoding="utf-8")


def test_the_file_never_asserts_steward_status() -> None:
    """Every paragraph that mentions the steward route says it does NOT apply here."""
    for para in re.split(r"\n\s*\n", SECURITY):
        low = " ".join(para.lower().split())
        if "steward" not in low:
            continue
        assert re.search(
            r"is \*\*not\*\* a steward|not a steward|steward route unavailable|only to a \*legal person\*"
            r"|steward reporting under article 24\(3\) applies",
            low,
        ), f"a paragraph mentions steward status without negating it: {low[:160]}"
    assert "published by an open-source steward" not in SECURITY


def test_the_counterparty_facts_are_stated_once_and_dated() -> None:
    assert "no legal entity" in SECURITY.lower()
    assert re.search(r"maintained by \*\*one\s+natural person\*\*", SECURITY)
    assert "No legal advice has been taken" in SECURITY
    assert re.search(r"As of \*\*\d{1,2} \w+ 2026\*\*", SECURITY), "the statement carries no date"
    # The facts appear in the dated statement and are referenced, not restated, further down.
    assert SECURITY.count("zero customers") == 1


def test_the_disclosure_route_and_timings_survive() -> None:
    for phrase in (
        "hello@provael.com",
        "REPORTABLE",
        "acknowledge within 3 business days",
        "90-day coordinated-disclosure window",
        "We are not your CSIRT",
    ):
        assert phrase in SECURITY, phrase


def test_neither_scope_conclusion_is_claimed() -> None:
    low = SECURITY.lower()
    for forbidden in ("provael is exempt", "is not in scope of the cra", "is in scope of the cra",
                      "exempt from the cyber resilience act"):
        assert forbidden not in low, forbidden
    assert "claims **neither**" in SECURITY
