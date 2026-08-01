"""EAI Top-10 mapping: attack metadata, the report.eai map, and the report tables."""

from __future__ import annotations

import io
import re
from pathlib import Path

from rich.console import Console

from provael.attacks.action import FreezeAttack, TrajectoryHijackAttack
from provael.attacks.baseline import NoOpAttack
from provael.attacks.injection import MCPToolDescInjection, SceneTextInjection
from provael.attacks.instruction import (
    GoalSubstitutionAttack,
    ParaphraseAttack,
    RolePlayAttack,
)
from provael.attacks.registry import available_attacks, make_attack
from provael.attacks.visual import DecoyObjectAttack, PatchAttack
from provael.config import RunConfig
from provael.eai import CATALOG, attacked_ids
from provael.report import build_summary_table, to_markdown
from provael.runner import run

REPO = Path(__file__).resolve().parent.parent

# Expected (attack -> EAI id) for every shipped attack; baseline `none` is untagged.
EXPECTED: dict[str, str] = {
    "roleplay": "EAI01",
    "goal_substitution": "EAI01",
    "paraphrase": "EAI01",
    "patch": "EAI02",
    "decoy_object": "EAI02",
    "scene_text": "EAI05",
    "mcp_tool_desc": "EAI05",
    "freeze": "EAI04",
    "trajectory_hijack": "EAI04",
}


def test_attack_classes_carry_eai_metadata() -> None:
    assert RolePlayAttack().eai_id == "EAI01"
    assert RolePlayAttack().eai_name == "Policy & instruction jailbreak"
    assert GoalSubstitutionAttack().eai_id == "EAI01"
    assert ParaphraseAttack().eai_id == "EAI01"
    assert PatchAttack().eai_id == "EAI02"
    assert DecoyObjectAttack().eai_id == "EAI02"
    assert SceneTextInjection().eai_id == "EAI05"
    assert MCPToolDescInjection().eai_id == "EAI05"
    assert FreezeAttack().eai_id == "EAI04"
    assert FreezeAttack().eai_name == "Action-space integrity"
    assert TrajectoryHijackAttack().eai_id == "EAI04"


def test_baseline_is_untagged() -> None:
    none = NoOpAttack()
    assert none.eai_id is None
    assert none.eai_name is None


def test_attack_tags_are_consistent_with_catalog() -> None:
    for name, eai_id in EXPECTED.items():
        attack = make_attack(name)
        assert attack.eai_id == eai_id
        assert attack.eai_name == CATALOG[eai_id].name


def test_runreport_eai_map_excludes_baseline() -> None:
    report = run(
        RunConfig(
            policy="stub",
            suite="stub",
            attacks=["none", "instruction", "visual", "injection", "action"],
            episodes=2,
            seed=0,
        )
    )
    assert "none" not in report.eai  # the control is not an attack technique
    assert set(report.eai) == set(EXPECTED)
    for name, eai_id in EXPECTED.items():
        assert report.eai[name].id == eai_id


def test_markdown_table_has_eai_column_and_links() -> None:
    report = run(RunConfig(attacks=["none", "instruction"], episodes=2, seed=0))
    md = to_markdown(report)
    assert "| attack | EAI | ASR | successes | attempts |" in md
    # Tagged attack -> deep link into the Top-10 doc; baseline -> em-dash.
    assert f"[EAI01]({CATALOG['EAI01'].help_uri})" in md
    assert "| none | — |" in md


def test_cli_summary_table_shows_eai() -> None:
    report = run(RunConfig(attacks=["instruction"], episodes=2, seed=0))
    buf = io.StringIO()
    Console(file=buf, width=300).print(build_summary_table(report))
    assert "EAI01" in buf.getvalue()


def test_eai_help_uris_point_at_top10_anchors() -> None:
    for eai_id, risk in CATALOG.items():
        assert risk.help_uri.endswith(f"docs/top10.md#{risk.anchor}")
        assert risk.anchor.startswith(eai_id.lower())


def test_every_attacked_risk_carries_a_structured_atlas_mapping() -> None:
    # D5: the ATLAS mapping is structured data on every risk we actually attack (promoted from the
    # prose table), phrased as a tactic -> technique and never as an invented AML.TXXXX id.
    for eai_id in attacked_ids():
        risk = CATALOG[eai_id]
        assert risk.atlas_techniques, f"{eai_id} ships attacks but carries no ATLAS mapping"
        for technique in risk.atlas_techniques:
            assert isinstance(technique, str) and "→" in technique
            assert "AML.T" not in technique  # descriptive phrasing only, no fabricated ids


def test_unattacked_risks_have_no_fabricated_atlas_mapping() -> None:
    """EAI07 and EAI10 must stay empty rather than be padded to make the column look complete.

    ATLAS enumerates adversary techniques against ML systems. A firmware/radio compromise and a
    missing governance control are, respectively, out of its scope and not an adversary action at
    all — so there is nothing on-point to cite. Filling the column anyway is the exact fabrication
    the "no invented AML.TXXXX ids" rule exists to prevent, and it would also be self-serving:
    a populated ATLAS row reads as coverage. The note has to carry the explanation instead.
    """
    for eai_id in set(CATALOG) - set(attacked_ids()):
        risk = CATALOG[eai_id]
        assert risk.atlas_techniques == (), (
            f"{eai_id} ships no attacks but claims ATLAS techniques {risk.atlas_techniques}"
        )
        assert len(risk.coverage_note) > 80, (
            f"{eai_id} is uncovered, so its note is the only thing a reader gets; it must say "
            f"what the boundary is and what closing it would take"
        )


def test_declared_coverage_matches_the_attack_registry() -> None:
    """The catalog claims which risks have attacks; the registry is what actually has them.

    Derived from the registry rather than asserted by hand, so shipping a new family for a
    previously-uncovered risk fails here until the catalog is updated to say so — and, more
    importantly, so a risk can never claim coverage it does not have.
    """
    implemented: set[str] = set()
    for name in available_attacks():
        eai_id = make_attack(name).eai_id
        if eai_id is not None:
            implemented.add(eai_id)

    claimed = set(attacked_ids())
    assert claimed == implemented, (
        f"catalog claims attacks for {sorted(claimed)} but the registry implements "
        f"{sorted(implemented)}; over-claimed={sorted(claimed - implemented)} "
        f"under-claimed={sorted(implemented - claimed)}"
    )


def test_catalog_and_top10_doc_define_the_same_risks() -> None:
    """The bug this whole change exists for: the doc defined ten risks and the code held eight.

    EAI07 and EAI10 were absent from the catalog, so they were silently dropped from every
    crosswalk, scorecard and compliance report — a category vanishing rather than being reported
    as untested. Both sides must enumerate the same set, in both directions.
    """
    top10 = (REPO / "docs" / "TOP10.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^## (EAI\d\d) — ", top10, re.MULTILINE))

    assert documented, "found no `## EAIxx — ` headings in docs/top10.md; the scan is broken"
    assert set(CATALOG) == documented, (
        f"catalog and docs/top10.md disagree: "
        f"in the doc only={sorted(documented - set(CATALOG))}, "
        f"in the catalog only={sorted(set(CATALOG) - documented)}"
    )


def test_the_published_coverage_claim_is_generated_not_typed() -> None:
    """docs/top10.md's headline number must match the catalog, not a hand-typed count."""
    top10 = (REPO / "docs" / "TOP10.md").read_text(encoding="utf-8")
    expected = f"{len(attacked_ids())} / {len(CATALOG)}"
    assert expected in top10, f"docs/top10.md does not state the generated coverage {expected!r}"
    # And every uncovered risk must be named where the claim is made — "8 / 10" alone tells a
    # reader nothing about which two are missing or why.
    for eai_id in set(CATALOG) - set(attacked_ids()):
        assert eai_id in top10
