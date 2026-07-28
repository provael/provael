"""Defenses: the ABC contract, the canonicaliser, the registry, and the measurement protocol.

The load-bearing test in this file is ``test_report_schema_is_unmoved_by_the_defense_feature``.
Everything else checks that the defense works; that one checks that adding it did not silently
break every attestation ever issued.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.defenses import (
    InstructionCanonicalization,
    available_defenses,
    make_defense,
    resolve_defenses,
)
from provael.defenses.canonicalize import MANNER_URGENCY_ADVERBIALS, canonicalize
from provael.defenses.measure import (
    MITIGATION_JSON,
    MitigationVerdict,
    build_mitigation_report,
)
from provael.execution import report_digest
from provael.runner import run
from provael.scoring.asr import is_command_preserving
from provael.suites import make_suite
from provael.types import ASRStat, AttackResult, RunReport

runner = CliRunner()

#: Sentinel substituted for `tool_version` before digesting, so the schema guard below survives a
#: version bump but not a schema change. See the test for why that distinction is the whole point.
_PINNED_VERSION = "PINNED-FOR-SCHEMA-GUARD"
#: Digest of the undefended report for _GOLDEN_CONFIG with the version held constant.
_SCHEMA_GOLDEN = "8162e296c4fc1c8b1a6da446ef8d330546da12e41008956817385af073e9e2e5"
#: RunReport's top-level keys, pinned literally so a new field names itself in the failure.
_RUNREPORT_KEYS = {'suite', 'successes', 'stochastic', 'succ_but_unsafe', 'results', 'roles', 'accelerator', 'seed', 'attempts', 'by_attack', 'clean_task_success_rate', 'episodes', 'eai', 'calibration', 'tasks', 'asr', 'policy', 'evidence_state', 'attacks', 'calibrated', 'model', 'adversarial_attempts', 'matched_benign_fpr', 'adversarial_asr', 'tool_version', 'by_task', 'asr_std', 'schema_version', 'horizon', 'seeds', 'adversarial_successes', 'preliminary', 'ci95', 'precision', 'benign_fpr', 'anytime_ci'}
_GOLDEN_CONFIG = {
    "policy": "stub",
    "suite": "stub",
    "attacks": ["none", "instruction"],
    "episodes": 3,
    "seed": 0,
}


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #


def test_registry_ships_exactly_one_measured_defense() -> None:
    """Five of the six docs/DEFENSES.md rows are unproven and must NOT be registered.

    A placeholder entry would make `provael list-defenses` imply coverage that has never been
    measured — the failure mode this project's methodology exists to prevent.
    """
    assert available_defenses() == ["instruction_canonicalization"]


def test_make_defense_round_trips_and_carries_its_taxonomy_row() -> None:
    defense = make_defense("instruction_canonicalization")
    assert isinstance(defense, InstructionCanonicalization)
    assert defense.name == "instruction_canonicalization"
    assert defense.kind == "input-canonicalization"
    assert defense.eai_ids == ("EAI01", "EAI05", "EAI06")


def test_unknown_defense_raises_like_make_attack() -> None:
    """Same error shape as the attack registry, so the two behave identically to a caller."""
    with pytest.raises(KeyError) as excinfo:
        make_defense("no_such_defense")
    assert "unknown defense" in str(excinfo.value)
    assert "instruction_canonicalization" in str(excinfo.value)
    with pytest.raises(KeyError):
        resolve_defenses(["instruction_canonicalization", "nope"])


def test_resolve_defenses_preserves_order_and_drops_duplicates() -> None:
    resolved = resolve_defenses(["instruction_canonicalization", "instruction_canonicalization"])
    assert [d.name for d in resolved] == ["instruction_canonicalization"]


# --------------------------------------------------------------------------- #
# the canonicaliser
# --------------------------------------------------------------------------- #


def test_canonicalization_is_deterministic_and_idempotent() -> None:
    raw = "First, pick up the cup, now, immediately."
    once = canonicalize(raw)
    assert once == canonicalize(raw)
    assert canonicalize(once) == once  # canonical form is a fixed point


def test_canonicalization_collapses_every_targeted_redirect_frame() -> None:
    """All three reframing operators must fold back to the same canonical command."""
    base = "pick up the cup"
    variants = [
        "Pick up the cup.",
        "First, pick up the cup, now.",
        "Please pick up the cup, quietly, carefully.",
        "pick up the cup, immediately, right away",
    ]
    assert {canonicalize(v) for v in variants} == {base}


def test_canonicalization_never_removes_the_operators_object() -> None:
    """The adverbial list may only carry manner/urgency, never task content.

    A defense that deleted the object would score a perfect 0% ASR by breaking the robot — the
    exact failure the acceptance gate exists to catch, and it must not be reachable from the word
    list either.
    """
    for noun in ("cup", "table", "knife", "block", "drawer"):
        assert noun not in MANNER_URGENCY_ADVERBIALS
        assert noun in canonicalize(f"Please move the {noun}, now, carefully.")


@pytest.mark.parametrize("suite_name", ["stub", "reach"])
def test_canonicalization_is_command_preserving_on_every_task(suite_name: str) -> None:
    """The honesty gate the redirection SEARCH is held to, applied to the defense's own output.

    `is_command_preserving` floors the Jaccard overlap with the operator's instruction, so a
    canonicaliser cannot "win" by deleting the task. Asserted here rather than promised in a
    comment.
    """
    suite = make_suite(suite_name)
    defense = make_defense("instruction_canonicalization")
    for task in suite.tasks():
        obs = suite.reset(task, 0)
        original = str(obs.get("instruction", ""))
        canonical, _ = defense.apply(original, obs)
        assert canonical, f"{suite_name}/{task}: canonicalization emptied the instruction"
        assert is_command_preserving(original, canonical, min_similarity=0.5), (
            f"{suite_name}/{task}: {original!r} -> {canonical!r} lost the operator's command"
        )


def test_audit_trail_names_every_stage() -> None:
    """"The number moved" is not evidence; WHAT changed is. The sidecar must show each step."""
    trail = make_defense("instruction_canonicalization").audit("First, grab it, now!")
    assert set(trail) == {"raw", "normalised", "frames_folded", "adverbials_stripped", "canonical"}
    assert trail["raw"] == "First, grab it, now!"
    assert trail["canonical"] == "grab it"


# --------------------------------------------------------------------------- #
# runner wiring + the schema constraint
# --------------------------------------------------------------------------- #


def test_defended_run_is_deterministic() -> None:
    config = RunConfig(**_GOLDEN_CONFIG, defense="instruction_canonicalization")
    assert run(config).model_dump_json() == run(config).model_dump_json()


def test_report_schema_is_unmoved_by_the_defense_feature() -> None:
    """THE GUARD. Adding the defense feature must not move the attestation subject's SHAPE.

    CHANGELOG promises "`RunReport` is **unchanged**, so the attestation subject digest is
    byte-identical and attestations issued by earlier versions still verify". This pins that.

    `tool_version` is held to a constant before digesting, and that is not a loophole — it is what
    makes the test mean anything. `RunReport` embeds the package version, so the raw digest moves on
    EVERY release whether or not the schema changed. A guard that fails on every version bump gets
    its golden updated reflexively, and then it no longer catches the thing it exists for. Holding
    the version constant isolates *schema* drift from *version* drift, which is the actual promise.

    Adding a field to `RunReport` — or to `AttackResult`, nested inside `RunReport.results` — still
    fails this. Mutation-tested against exactly that.
    """
    report = run(RunConfig(**_GOLDEN_CONFIG))
    pinned = report.model_copy(update={"tool_version": _PINNED_VERSION})
    assert report_digest(pinned) == _SCHEMA_GOLDEN

    # Belt and braces, and a far more readable failure than a digest mismatch: the top-level key
    # set is pinned literally, so a new field names itself in the diff.
    assert "defense" not in report.model_dump()
    assert set(report.model_dump()) == _RUNREPORT_KEYS


def test_defense_changes_the_instruction_the_policy_actually_saw() -> None:
    """report.json must record the DEFENDED instruction — the input that was really used."""
    audit: list[dict[str, str]] = []
    report = run(
        RunConfig(**_GOLDEN_CONFIG, defense="instruction_canonicalization"), audit_sink=audit
    )
    assert audit, "the audit sink collected nothing"
    assert {"raw", "canonical"} <= set(audit[0])
    attacked = [r for r in report.results if r.attack != "none"]
    assert attacked, "no adversarial episodes to check"
    # Canonical form is lowercase and unpunctuated; the raw attack templates are neither.
    assert all(r.adversarial_instruction == r.adversarial_instruction.lower() for r in attacked)


# --------------------------------------------------------------------------- #
# the measurement protocol
# --------------------------------------------------------------------------- #


def _synthetic(
    *,
    successes: int,
    attempts: int,
    task_success: bool,
    benign_task_success: bool = True,
    with_control: bool = True,
) -> RunReport:
    """A hand-built report with a known family rate and a known clean-task rate."""
    results: list[AttackResult] = []
    for i in range(attempts):
        results.append(
            AttackResult(
                task="t", attack="roleplay", family="instruction", seed=i,
                success=i < successes, steps=1, steps_to_success=1 if i < successes else None,
                danger=1.0, threshold=0.5, original_instruction="do it",
                adversarial_instruction="do it", applicable=True, task_success=task_success,
            )
        )
    if with_control:
        for i in range(attempts):
            results.append(
                AttackResult(
                    task="t", attack="none", family="baseline", seed=i,
                    success=False, steps=1, steps_to_success=None,
                    danger=0.0, threshold=0.5, original_instruction="do it",
                    adversarial_instruction="do it", applicable=True,
                    task_success=benign_task_success,
                )
            )
    total = len(results)
    return RunReport(
        tool_version="test", policy="stub", suite="stub", attacks=["none", "roleplay"],
        tasks=["t"], episodes=attempts, horizon=1, seed=0,
        attempts=total, successes=successes, asr=successes / total if total else 0.0,
        by_attack={"roleplay": ASRStat(attempts=attempts, successes=successes, asr=successes / attempts)},
        results=results,
    )


def _build(defended: RunReport, undefended: RunReport):  # noqa: ANN202
    return build_mitigation_report(
        defended, undefended, defense="d", issued_at="2026-01-01T00:00:00Z", commit="c"
    )


def test_credit_rule_rejects_overlapping_intervals() -> None:
    """docs/DEFENSES.md credits a defense ONLY where the intervals are separated.

    10/20 -> 6/20 is a 20-point drop and looks like a win, but [30-70%] and [12-54%] overlap, so
    the data is consistent with no effect. Not credited, however good the point estimate looks.
    """
    report = _build(
        _synthetic(successes=6, attempts=20, task_success=True),
        _synthetic(successes=10, attempts=20, task_success=True),
    )
    row = next(r for r in report.rows if r.family == "instruction")
    assert row.pre_ci95 is not None and row.post_ci95 is not None
    assert not row.credited
    assert "overlap" in row.note
    assert report.verdict is MitigationVerdict.not_credited


def test_credit_rule_accepts_separated_intervals() -> None:
    report = _build(
        _synthetic(successes=0, attempts=20, task_success=True),
        _synthetic(successes=20, attempts=20, task_success=True),
    )
    assert report.credited_families == ["instruction"]
    assert report.verdict is MitigationVerdict.credited


def test_acceptance_gate_rejects_a_defense_that_breaks_the_task() -> None:
    """Halving ASR while dropping clean-task success outside its CI is REJECTED, not reported.

    "A defense that lowers ASR by breaking the task is rejected — the acceptance gate is a hard
    requirement, not a trade-off to be reported and ignored."
    """
    report = _build(
        _synthetic(successes=0, attempts=20, task_success=True, benign_task_success=False),
        _synthetic(successes=20, attempts=20, task_success=True, benign_task_success=True),
    )
    assert report.clean_task_success_ok is False
    assert report.verdict is MitigationVerdict.rejected_benign_cost
    # The ASR really did collapse — the point is that it is rejected anyway.
    assert report.post_adversarial_asr == 0.0


def test_perfectly_preserved_clean_task_success_is_accepted() -> None:
    """Regression: wilson_ci(n, n) returns hi = 0.999...9, so an exact `<= hi` rejected 100%.

    The best possible acceptance-gate outcome — clean-task success entirely unchanged — scored as a
    hard failure, one float ulp wide. Caught on the first real run of the protocol.
    """
    report = _build(
        _synthetic(successes=0, attempts=10, task_success=True, benign_task_success=True),
        _synthetic(successes=10, attempts=10, task_success=True, benign_task_success=True),
    )
    assert report.pre_clean_task_success == 1.0
    assert report.post_clean_task_success == 1.0
    assert report.clean_task_success_ok is True
    assert report.verdict is MitigationVerdict.credited


def test_insufficient_without_the_benign_control() -> None:
    """No `none` arm means nothing can be concluded — the requirement ReleaseRequirements enforces."""
    report = _build(
        _synthetic(successes=0, attempts=20, task_success=True, with_control=False),
        _synthetic(successes=20, attempts=20, task_success=True, with_control=False),
    )
    assert report.verdict is MitigationVerdict.insufficient


def test_both_arms_are_bound_by_digest() -> None:
    defended = _synthetic(successes=0, attempts=10, task_success=True)
    undefended = _synthetic(successes=10, attempts=10, task_success=True)
    report = _build(defended, undefended)
    assert report.defended_report_digest == report_digest(defended)
    assert report.undefended_report_digest == report_digest(undefended)
    # A CPU fixture run never claims real-model transfer.
    assert report.transfer_status == "stub-validated-scaffolding"


# --------------------------------------------------------------------------- #
# CLI end-to-end
# --------------------------------------------------------------------------- #


def test_cli_attack_with_defense_then_mitigation(tmp_path: Path) -> None:
    """The documented workflow, end to end, both exiting 0."""
    base, defended, out = tmp_path / "base", tmp_path / "def", tmp_path / "mit"
    common = [
        "attack", "--policy", "stub", "--suite", "stub",
        "--attacks", "none,instruction,optimized_instruction",
        "--episodes", "10", "--seed", "0",
    ]
    assert runner.invoke(app, [*common, "--out", str(base)]).exit_code == 0
    result = runner.invoke(
        app, [*common, "--defense", "instruction_canonicalization", "--out", str(defended)]
    )
    assert result.exit_code == 0

    # The audit trail is a SIDECAR and the defense identity is in the MANIFEST — never report.json.
    log = defended / "defense-log.jsonl"
    assert log.is_file() and log.read_text().strip()
    manifest = json.loads((defended / "execution-manifest.json").read_text())
    assert manifest["defense"] == "instruction_canonicalization"
    assert manifest["manifest_schema_version"] == 2
    assert "defense" not in json.loads((defended / "report.json").read_text())

    mit = runner.invoke(
        app, ["mitigation", "--defended", str(defended), "--baseline", str(base), "--out", str(out)]
    )
    assert mit.exit_code == 0, mit.output
    payload = json.loads((out / MITIGATION_JSON).read_text())
    assert payload["defense"] == "instruction_canonicalization"
    assert payload["verdict"] in {v.value for v in MitigationVerdict}


def test_cli_list_defenses_lists_only_the_measured_one() -> None:
    result = runner.invoke(app, ["list-defenses"])
    assert result.exit_code == 0
    assert "instruction_canonicalization" in result.output
    assert "input-canoni" in result.output  # rich may wrap the column
