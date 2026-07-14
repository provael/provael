"""P0.4 honest reporting + INV-4 metadata + D6 accelerator.

These pin the credibility-critical schema/stats the roadmap makes a P0 dependency:

* the **anytime-valid CI** is checked by *running it* — a Monte-Carlo coverage test verifies the
  time-uniform guarantee empirically under optional stopping (a wrong constant would miss ~50% of
  the time), plus a check that the bisection inverts the same Beta-mixture martingale it claims to;
* the **matched-benign FPR** control, the **per-episode log**, the **INV-4** access/head metadata,
  and the **D6** ``accelerator``/``precision`` slot (incl. ``tpu`` → ``NotImplementedError``);
* a **canary**: adding all of the above leaves the frozen stub ASRs byte-identical.
"""

from __future__ import annotations

import math
import random

import pytest

from provael.calibration import anytime_ci, wilson_ci
from provael.config import RunConfig
from provael.report import to_json, to_markdown
from provael.runner import run
from provael.scoring.asr import matched_benign_fpr
from provael.types import AttackResult, Decision

# --------------------------------------------------------------------------------------------
# anytime-valid CI — a genuine Beta-mixture confidence sequence
# --------------------------------------------------------------------------------------------

def _betaln(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _log_m(s: int, n: int, p: float, a: float = 1.0, b: float = 1.0) -> float:
    """Independent reference for log M_n(p) — the mixture wealth against the null 'rate == p'."""
    log_lik = (s * math.log(p) if s > 0 else 0.0) + (
        (n - s) * math.log1p(-p) if n - s > 0 else 0.0
    )
    return (_betaln(a + s, b + n - s) - _betaln(a, b)) - log_lik


def test_anytime_ci_no_data_is_the_whole_unit_interval() -> None:
    assert anytime_ci(0, 0) == (0.0, 1.0)


def test_anytime_ci_contains_the_mle_and_clamps() -> None:
    for s, n in [(0, 10), (3, 10), (5, 10), (10, 10), (1, 100), (50, 100)]:
        lo, hi = anytime_ci(s, n)
        assert 0.0 <= lo <= s / n <= hi <= 1.0  # always brackets the MLE, clamped to [0,1]
    # A one-sided count pins the corresponding bound at the edge.
    assert anytime_ci(0, 20)[0] == 0.0
    assert anytime_ci(20, 20)[1] == 1.0


def test_anytime_ci_endpoints_solve_the_martingale_threshold() -> None:
    # The interval is exactly {p : M_n(p) < 1/alpha}; its finite endpoints sit on log M = -log alpha.
    alpha = 0.05
    threshold = -math.log(alpha)
    for s, n in [(3, 10), (5, 10), (7, 20), (30, 100)]:
        lo, hi = anytime_ci(s, n, alpha=alpha)
        if lo > 0.0:
            assert abs(_log_m(s, n, lo) - threshold) < 1e-6
        if hi < 1.0:
            assert abs(_log_m(s, n, hi) - threshold) < 1e-6


def test_anytime_ci_is_wider_than_wilson_at_a_fixed_n() -> None:
    # Anytime validity costs width: the sequence interval contains the fixed-n Wilson interval.
    for s, n in [(5, 10), (2, 20), (40, 100)]:
        a_lo, a_hi = anytime_ci(s, n)
        w_lo, w_hi = wilson_ci(s, n)
        assert a_lo <= w_lo + 1e-9 and a_hi >= w_hi - 1e-9


def test_anytime_ci_is_symmetric_under_success_relabelling() -> None:
    lo, hi = anytime_ci(3, 10)
    lo2, hi2 = anytime_ci(7, 10)  # relabel success<->failure -> interval mirrors about 0.5
    assert abs(lo - (1.0 - hi2)) < 1e-9 and abs(hi - (1.0 - lo2)) < 1e-9


def test_anytime_ci_has_time_uniform_coverage_under_optional_stopping() -> None:
    """Verify-by-running: the truth stays inside the sequence for ALL n with prob >= 1 - alpha.

    Checks the coverage event directly on the martingale (``M_n(p0) >= 1/alpha`` ever) — the exact
    condition ``anytime_ci`` inverts — so a mis-derived constant would blow the empirical miss rate
    far past alpha. Conservative CSs sit well under alpha; the loose 0.08 bound never flakes.
    """
    rng = random.Random(20260715)
    alpha = 0.05
    threshold = -math.log(alpha)
    trials, horizon = 500, 40
    for true_p in (0.25, 0.6):
        misses = 0
        for _ in range(trials):
            s = 0
            for n in range(1, horizon + 1):
                s += 1 if rng.random() < true_p else 0
                if _log_m(s, n, true_p) >= threshold:  # truth left the sequence at some n
                    misses += 1
                    break
        assert misses / trials <= 0.08


# --------------------------------------------------------------------------------------------
# matched-benign FPR
# --------------------------------------------------------------------------------------------

def _result(task: str, attack: str, seed: int, success: bool, *, applicable: bool = True) -> AttackResult:
    family = "baseline" if attack == "none" else "instruction"
    return AttackResult(
        task=task, attack=attack, family=family, seed=seed, success=success,
        steps=1, steps_to_success=1 if success else None, danger=0.0, threshold=0.5,
        original_instruction="reach", adversarial_instruction="reach", applicable=applicable,
    )


def test_matched_benign_fpr_matches_twins_by_task_and_seed() -> None:
    results = [
        _result("reach", "none", 0, False),
        _result("reach", "none", 1, True),   # this benign twin fired
        _result("reach", "roleplay", 0, True),
        _result("reach", "roleplay", 1, True),
    ]
    # Both attacked cells (0, 1) have benign twins; twin at seed 1 fired -> 1/2.
    assert matched_benign_fpr(results) == 0.5


def test_matched_benign_fpr_none_without_baseline_or_twins() -> None:
    assert matched_benign_fpr([_result("reach", "roleplay", 0, True)]) is None  # no baseline
    # Baseline exists but at a (task, seed) no attack touched -> no matched twin.
    only_far = [_result("reach", "none", 9, True), _result("reach", "roleplay", 0, True)]
    assert matched_benign_fpr(only_far) is None


def test_matched_benign_fpr_is_zero_on_the_stub() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "roleplay"], episodes=6))
    assert report.matched_benign_fpr == 0.0  # the stub's benign baseline never fires
    assert report.benign_fpr == 0.0  # coincides with the marginal control on this balanced run


# --------------------------------------------------------------------------------------------
# per-episode log + INV-4 metadata
# --------------------------------------------------------------------------------------------

def test_per_episode_log_is_populated_and_deterministic() -> None:
    cfg = RunConfig(policy="stub", suite="stub", attacks=["roleplay"], episodes=4, seed=0)
    report = run(cfg)
    assert report.results
    for r in report.results:
        assert r.decisions  # at least one step logged
        first = r.decisions[0]
        assert isinstance(first, Decision)
        assert first.step == 1 and first.action  # a real action vector was recorded
        # The success step is the last logged decision, flagged unsafe.
        assert r.decisions[-1].unsafe is r.success
    assert to_json(run(cfg)) == to_json(report)  # per-episode log stays byte-deterministic


def test_inv4_metadata_defaults_none_and_round_trips() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["roleplay"], episodes=2))
    r = report.results[0]
    assert r.attacker_access is None and r.action_head_class is None  # stub asserts nothing
    # A populated value survives serialisation.
    tagged = r.model_copy(update={"attacker_access": "white-box-gradient", "action_head_class": "flow"})
    back = AttackResult.model_validate_json(tagged.model_dump_json())
    assert back.attacker_access == "white-box-gradient" and back.action_head_class == "flow"


# --------------------------------------------------------------------------------------------
# report-level P0.4 fields + D6 accelerator
# --------------------------------------------------------------------------------------------

def test_report_carries_both_intervals_and_seed_provenance() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["roleplay"], episodes=6, seed=0))
    assert report.ci95 is not None and report.anytime_ci is not None
    assert report.seeds == 6 and report.preliminary is False  # >=5 seeds -> banked
    # The anytime interval contains the Wilson interval (honest extra width).
    assert report.anytime_ci[0] <= report.ci95[0] + 1e-9
    assert report.anytime_ci[1] >= report.ci95[1] - 1e-9
    md = to_markdown(report)
    assert "anytime-valid CI" in md and "ASR 95% CI (Wilson)" in md


def test_fewer_than_five_seeds_is_preliminary() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["roleplay"], episodes=3))
    assert report.seeds == 3 and report.preliminary is True
    assert "Preliminary" in to_markdown(report)


def test_accelerator_and_precision_are_recorded() -> None:
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["roleplay"], episodes=2,
                  accelerator="cpu", precision="fp32")
    )
    assert report.accelerator == "cpu" and report.precision == "fp32"
    assert "| accelerator / precision | `cpu` / `fp32` |" in to_markdown(report)


def test_accelerator_tpu_raises_not_implemented_and_unknown_rejected() -> None:
    with pytest.raises(NotImplementedError, match="ROADMAP"):
        RunConfig(accelerator="tpu")
    for ok in ("cpu", "cuda", "mps"):
        assert RunConfig(accelerator=ok).accelerator == ok
    with pytest.raises(ValueError, match="unsupported accelerator"):
        RunConfig(accelerator="gpu")  # not a recognised device string


# --------------------------------------------------------------------------------------------
# canary: none of the new instrumentation moves the frozen stub ASRs
# --------------------------------------------------------------------------------------------

def test_instruction_visual_injection_canary_is_unchanged() -> None:
    report = run(RunConfig(
        policy="stub", suite="stub", attacks=["instruction", "visual", "injection"],
        episodes=10, seed=0,
    ))
    assert (report.successes, report.attempts) == (47, 70)  # the frozen headline canary
