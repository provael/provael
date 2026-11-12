# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""SECURITY.md states one set of counterparty facts, and never contradicts itself about them.

R12 (19 Sep 2026): the file opened with "published by an open-source steward" and, ninety lines
later, explained that a steward under Article 3(14) must be a legal person and that there is no
entity. Both sentences were true of the document and false of each other. The regulatory context is
now one dated statement; this test holds the file to it.

It also holds the one dependency advisory range that SECURITY.md shares with three other files, so
the four cannot drift apart again (11 Nov 2026).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURITY = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

#: CVE-2026-25874's last affected lerobot release, as OSV states it. Move it only with the record.
LEROBOT_POLICYSERVER_AFFECTED_THROUGH = "0.6.1"  # OSV CVE-2026-25874, modified 2026-11-11T02:30:50Z

#: The live texts that state that range. CHANGELOG.md is history and keeps the range each entry had,
#: and the audit allow-list's reason is a log of dated updates, so neither is held to one version.
POLICYSERVER_RANGE_TEXTS = (
    "SECURITY.md",
    "docs/checkpoint-integrity.md",
    "src/provael/integrity.py",
    "action.yml",
)

#: `lerobot` through `0.6.1` in Markdown, ``lerobot`` in reST, bare in a comment, and across a line
#: break or a comment marker, which is how action.yml's copy escaped a one-line grep.
POLICYSERVER_RANGE = re.compile(r"lerobot`{0,2}[\s#]+through[\s#]+`{0,2}(\d+(?:\.\d+)+)")


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


def test_the_lerobot_policyserver_range_is_stated_once() -> None:
    """CVE-2026-25874's affected range reads the same in every live text that states it.

    On 11 November 2026 OSV's record moved to "LeRobot through 0.6.1" while SECURITY.md,
    docs/checkpoint-integrity.md, the integrity module's docstring and a comment in action.yml still
    said 0.5.1. A future change to the range must move all four together, or this fails.
    """
    stated: dict[str, set[str]] = {}
    for name in POLICYSERVER_RANGE_TEXTS:
        versions = set(POLICYSERVER_RANGE.findall((ROOT / name).read_text(encoding="utf-8")))
        assert versions, f"{name} no longer states the range as `lerobot` through `<version>`"
        stated[name] = versions
    distinct = set().union(*stated.values())
    assert len(distinct) == 1, f"the files disagree on the range: {stated}"
    assert distinct == {LEROBOT_POLICYSERVER_AFFECTED_THROUGH}, stated
