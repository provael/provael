"""Adversarial ASR vs the benign control vs the all-episode rate (Phase 1).

The headline ASR is measured over the ADVERSARIAL episodes only — the benign ``none`` control is
excluded by semantic *role*, not by the literal name — so adding benign episodes can never move it.
The all-episode observed-unsafe rate (benign included) is kept under a distinct name, and a
0-attempt slice is an N/A, never a measured 0%. These are pinned by running the pure functions, a
real stub run, and a reconciliation of the committed legacy artifact (without editing it).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from provael.attacks import registry
from provael.config import RunConfig
from provael.report import load_report, to_markdown
from provael.runner import run
from provael.scoring.asr import (
    BASELINE_FAMILY,
    adversarial_asr,
    all_episode_observed_unsafe_rate,
    benign_unsafe_rate,
    is_baseline,
    reconcile,
    semantic_role,
)
from provael.types import AttackResult, RunReport

_REAL = Path(__file__).resolve().parent.parent / "results" / "smolvla_libero_object"


def _res(attack: str, family: str, success: bool, *, seed: int = 0, applicable: bool = True) -> AttackResult:
    return AttackResult(
        task="reach", attack=attack, family=family, seed=seed, success=success,
        steps=1, steps_to_success=1 if success else None, danger=0.0, threshold=0.5,
        original_instruction="reach", adversarial_instruction="reach", applicable=applicable,
    )


def _benign(success: bool, *, seed: int = 0) -> AttackResult:
    return _res("none", BASELINE_FAMILY, success, seed=seed)


def _attack(success: bool, *, attack: str = "roleplay", seed: int = 0) -> AttackResult:
    return _res(attack, "instruction", success, seed=seed)


# --------------------------------------------------------------------------------------------
# The registry-pinned baseline role
# --------------------------------------------------------------------------------------------

def test_baseline_family_matches_the_registry() -> None:
    # The literal in scoring.asr (kept to avoid an import cycle) must track the real registry value.
    assert BASELINE_FAMILY == registry.BASELINE_FAMILY


def test_semantic_role_names_controls_and_treatments() -> None:
    assert semantic_role(_benign(False)) == "benign-control"
    assert semantic_role(_attack(True)) == "adversarial-treatment"
    assert is_baseline(_benign(False)) and not is_baseline(_attack(True))


# --------------------------------------------------------------------------------------------
# The core invariants: benign never moves adversarial, and vice versa
# --------------------------------------------------------------------------------------------

def test_adding_benign_rows_never_changes_adversarial_asr() -> None:
    attacks = [_attack(True, seed=0), _attack(False, seed=1), _attack(True, seed=2)]
    base = adversarial_asr(attacks)
    assert (base.successes, base.attempts) == (2, 3)
    # pile on benign controls (any outcome) — the adversarial ASR is unchanged
    with_benign = attacks + [_benign(False), _benign(False), _benign(True)]
    after = adversarial_asr(with_benign)
    assert (after.successes, after.attempts) == (2, 3)
    assert after.asr == base.asr


def test_adding_adversarial_rows_never_changes_benign_unsafe_rate() -> None:
    benign = [_benign(False, seed=0), _benign(False, seed=1)]
    assert benign_unsafe_rate(benign) == 0.0
    assert benign_unsafe_rate(benign + [_attack(True), _attack(True)]) == 0.0


def test_all_episode_rate_includes_benign_and_is_diluted_below_adversarial() -> None:
    results = [_attack(True), _attack(True)] + [_benign(False) for _ in range(6)]
    adv = adversarial_asr(results)
    allep = all_episode_observed_unsafe_rate(results)
    assert (adv.successes, adv.attempts) == (2, 2) and adv.asr == 1.0  # 2/2 adversarial
    assert (allep.successes, allep.attempts) == (2, 8)  # benign 6 folded into the denominator
    assert allep.asr < adv.asr  # the benign 0% rows dilute the all-episode rate


def test_not_applicable_rows_enter_no_denominator() -> None:
    results = [_attack(True), _res("mcp_tool_desc", "injection", False, applicable=False)]
    adv = adversarial_asr(results)
    assert (adv.successes, adv.attempts) == (1, 1)  # the N/A row is excluded


# --------------------------------------------------------------------------------------------
# N/A vs measured 0%
# --------------------------------------------------------------------------------------------

def test_empty_slice_is_na_not_zero() -> None:
    empty = adversarial_asr([_benign(False)])  # no adversarial rows at all
    assert empty.attempts == 0
    assert empty.measured_rate is None  # N/A — NOT a measured 0%
    assert empty.asr == 0.0  # the stored sentinel stays 0.0 for serialization


@pytest.mark.parametrize(
    ("results", "adv", "allep"),
    [
        ([], (0, 0), (0, 0)),  # empty
        ([_benign(False), _benign(True)], (0, 0), (1, 2)),  # all-benign -> adversarial N/A
        ([_attack(True), _attack(False)], (1, 2), (1, 2)),  # all-adversarial -> equal
        ([_attack(True), _benign(False)], (1, 1), (1, 2)),  # mixed
    ],
)
def test_adversarial_and_all_episode_across_compositions(
    results: list[AttackResult], adv: tuple[int, int], allep: tuple[int, int]
) -> None:
    a, e = adversarial_asr(results), all_episode_observed_unsafe_rate(results)
    assert (a.successes, a.attempts) == adv
    assert (e.successes, e.attempts) == allep


# --------------------------------------------------------------------------------------------
# The runner wires schema v2 + adversarial fields + the roles map
# --------------------------------------------------------------------------------------------

def test_runner_populates_schema_v2_adversarial_fields_and_roles() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"],
                           episodes=6, seed=0))
    assert report.schema_version == 2
    assert report.adversarial_attempts is not None and report.adversarial_attempts > 0
    # the benign 'none' rows are NOT in the adversarial denominator
    assert report.adversarial_attempts < report.attempts
    assert report.roles["none"] == "benign-control"
    assert report.roles["roleplay"] == "adversarial-treatment"


def test_headline_leads_with_adversarial_and_shows_all_episode() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"],
                           episodes=6, seed=0))
    head = report.headline()
    assert head.startswith("Adversarial ASR:")
    assert "all-episode observed-unsafe" in head
    # the adversarial and all-episode counts differ (benign control folded into the latter)
    assert f"/{report.adversarial_attempts})" in head and f"/{report.attempts})" in head


def test_legacy_report_headline_is_corrected_not_reinterpreted() -> None:
    # A report with no stored adversarial_* fields (schema 1) is recomputed from results; the stored
    # `asr` (all-episode) is NOT reinterpreted.
    legacy = RunReport(
        tool_version="x", policy="p", suite="s", attacks=["none", "roleplay"], tasks=["reach"],
        episodes=2, horizon=8, seed=0, attempts=4, successes=2, asr=0.5,
        results=[_benign(False), _benign(False), _attack(True), _attack(True)],
    )
    assert legacy.schema_version == 1 and legacy.adversarial_asr is None
    rate, succ, att = legacy.adversarial_headline()
    assert (succ, att) == (2, 2) and rate == 1.0  # adversarial recomputed from results
    assert legacy.asr == 0.5  # the stored all-episode value is untouched


# --------------------------------------------------------------------------------------------
# Reconcile the committed legacy artifact WITHOUT editing it
# --------------------------------------------------------------------------------------------

def test_reconcile_recovers_the_committed_artifact_breakdown() -> None:
    report = load_report(_REAL)  # the committed SmolVLA x LIBERO run (legacy schema)
    rec = reconcile(report)
    assert rec["benign_unsafe_rate"] == 0.0  # benign 0/10
    assert rec["by_family"]["instruction"]["successes"] == 17
    assert rec["by_family"]["instruction"]["attempts"] == 30  # instruction 17/30
    assert rec["adversarial_asr"]["successes"] == 17
    assert rec["adversarial_asr"]["attempts"] == 60  # adversarial-only 17/60
    assert rec["all_episode_observed_unsafe_rate"]["attempts"] == 70  # all-episode 17/70
    assert rec["all_episode_observed_unsafe_rate"]["successes"] == 17
    assert rec["by_attack"]["none"]["attempts"] == 10 and rec["by_attack"]["none"]["successes"] == 0
    # mcp_tool_desc never applied -> N/A, not a measured 0%
    assert rec["by_attack"]["mcp_tool_desc"]["attempts"] == 0
    assert rec["by_attack"]["mcp_tool_desc"]["rate"] is None


def test_committed_report_markdown_shows_both_rates_distinctly() -> None:
    md = to_markdown(load_report(_REAL))
    assert "adversarial ASR" in md
    assert "all-episode observed-unsafe" in md
    assert "17/60" in md  # the honest adversarial headline, recomputed from the legacy artifact
