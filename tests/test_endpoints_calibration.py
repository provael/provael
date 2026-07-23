"""Phase 7: independent semantic endpoints + calibration as a bound, leakage-checked state.

Pins both by running them: the endpoints stay independent (a safety violation is not a task success),
N/A where the suite surfaces no signal, and `success` remains the `unsafe_envelope` endpoint; and a
calibration binding is a *verifiable* state — seed leakage is refused, an eval FPR above target is
invalid, and an untouched eval split is enforced disjoint from fit/calibration.
"""

from __future__ import annotations

import pytest

from provael.calibration import (
    CalibrationBinding,
    SeedLeakageError,
    build_calibration_binding,
    seed_set_digest,
    split_seeds_three,
)
from provael.endpoints import (
    AUTHORIZED_TASK_SUCCESS,
    CONTROLLER_INTERVENTION,
    PHYSICAL_HAZARD,
    UNAUTHORIZED_ACTION,
    UNSAFE_ENVELOPE,
    endpoint_outcome,
    endpoint_outcomes,
)
from provael.types import AttackResult


def _res(*, success: bool, task_success: bool | None = None,
         endpoints: dict[str, bool | None] | None = None) -> AttackResult:
    return AttackResult(
        task="reach", attack="roleplay", family="instruction", seed=0, success=success,
        steps=1, steps_to_success=1 if success else None, danger=0.0, threshold=0.5,
        original_instruction="x", adversarial_instruction="x",
        task_success=task_success, endpoints=endpoints or {},
    )


# --------------------------------------------------------------------------------------------
# semantic endpoints are independent, and N/A where there is no signal
# --------------------------------------------------------------------------------------------

def test_unsafe_envelope_is_the_legacy_success_field() -> None:
    assert endpoint_outcome(_res(success=True), UNSAFE_ENVELOPE) is True
    assert endpoint_outcome(_res(success=False), UNSAFE_ENVELOPE) is False


def test_authorized_task_success_is_independent_of_the_safety_violation() -> None:
    # completed the task AND violated safety — two different endpoints, not one boolean
    r = _res(success=True, task_success=True)
    assert endpoint_outcome(r, UNSAFE_ENVELOPE) is True
    assert endpoint_outcome(r, AUTHORIZED_TASK_SUCCESS) is True


def test_endpoints_with_no_signal_are_na_not_false() -> None:
    outcomes = endpoint_outcomes(_res(success=True))  # stub-style result, no specialized signals
    assert outcomes[UNSAFE_ENVELOPE] is True
    for endpoint in (UNAUTHORIZED_ACTION, PHYSICAL_HAZARD, CONTROLLER_INTERVENTION):
        assert endpoint not in outcomes  # absent == N/A, never a fabricated False
        assert endpoint_outcome(_res(success=True), endpoint) is None


def test_a_suite_populated_endpoint_is_preserved() -> None:
    r = _res(success=False, endpoints={PHYSICAL_HAZARD: True})
    assert endpoint_outcome(r, PHYSICAL_HAZARD) is True  # a real-sim suite may surface it


# --------------------------------------------------------------------------------------------
# calibration binding is a verifiable state — leakage refused, fail-closed validity
# --------------------------------------------------------------------------------------------

def test_three_way_split_is_disjoint_and_eval_is_last() -> None:
    seeds = list(range(9))
    fit, cal, ev = split_seeds_three(seeds)
    assert set(fit) & set(ev) == set() and set(cal) & set(ev) == set()
    assert ev == seeds[-len(ev):]  # eval is the tail (never used to fit the threshold)


def test_seed_leakage_is_refused_at_build() -> None:
    with pytest.raises(SeedLeakageError, match="overlap"):
        build_calibration_binding(
            endpoint_id="unsafe_envelope", oracle_version="v1", policy="stub", suite="stub",
            task="reach", target_fpr=0.05, achieved_eval_fpr=0.0, threshold=0.7,
            fit_seeds=[0, 1, 2], calibration_seeds=[3, 4], eval_seeds=[2, 5],  # 2 leaks into eval
        )


def _binding(**kw: object) -> CalibrationBinding:
    base: dict[str, object] = {
        "endpoint_id": "unsafe_envelope", "oracle_version": "v1", "policy": "stub", "suite": "stub",
        "task": "reach", "target_fpr": 0.05, "achieved_eval_fpr": 0.0, "threshold": 0.7,
        "fit_seeds": [0, 1, 2], "calibration_seeds": [3, 4], "eval_seeds": [5, 6],
    }
    base.update(kw)
    return build_calibration_binding(**base)  # type: ignore[arg-type]


def test_disjoint_binding_is_valid() -> None:
    ok, reason = _binding().valid()
    assert ok is True and "within target" in reason


def test_eval_fpr_above_target_is_invalid_not_calibrated_with_warning() -> None:
    ok, reason = _binding(achieved_eval_fpr=0.2, target_fpr=0.05).valid()
    assert ok is False and "exceeds target" in reason


def test_explicit_invalidation_fails_closed() -> None:
    binding = _binding()
    binding.invalidated = True
    binding.invalidation_reason = "checkpoint changed"
    ok, reason = binding.valid()
    assert ok is False and reason == "checkpoint changed"


def test_seed_set_digest_is_order_independent() -> None:
    assert seed_set_digest([3, 1, 2]) == seed_set_digest([1, 2, 3])
    assert seed_set_digest([1, 2, 3]) != seed_set_digest([1, 2, 4])
