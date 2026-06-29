"""EAI Top-10 mapping: attack metadata, the report.eai map, and the report tables."""

from __future__ import annotations

import io

from rich.console import Console

from provael.attacks.action import FreezeAttack, TrajectoryHijackAttack
from provael.attacks.baseline import NoOpAttack
from provael.attacks.injection import MCPToolDescInjection, SceneTextInjection
from provael.attacks.instruction import (
    GoalSubstitutionAttack,
    ParaphraseAttack,
    RolePlayAttack,
)
from provael.attacks.registry import make_attack
from provael.attacks.visual import DecoyObjectAttack, PatchAttack
from provael.config import RunConfig
from provael.eai import CATALOG
from provael.report import build_summary_table, to_markdown
from provael.runner import run

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
        assert risk.help_uri.endswith(f"docs/TOP10.md#{risk.anchor}")
        assert risk.anchor.startswith(eai_id.lower())
