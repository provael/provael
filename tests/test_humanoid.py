"""The Humanoid safety pack: the whole-body suite, its attack family, and the gated GR00T adapter.

Everything here runs on the deterministic CPU stub — no GPU, no lerobot. The humanoid attacks are
stub-validated: they fire on the humanoid fixture (a measurable ASR against a benign-FPR control) and
are not-applicable on the other suites. The real GR00T-N1 transfer is gated and not exercised here.
"""

from __future__ import annotations

import pytest

from provael.attacks.registry import available_attacks, resolve_attacks
from provael.config import RunConfig
from provael.policies.groot_adapter import GrootAdapter, HumanoidIntegrationDisabledError
from provael.policies.registry import available_policies, make_policy, policy_is_ready
from provael.runner import run
from provael.scoring.humanoid import (
    DOUBLE_SUPPORT_HALF,
    FOOTSTEP_KEEPOUT_X_MIN,
    SINGLE_SUPPORT_HALF,
    STRIDE_FREEZE_DRIFT,
    TOPPLE_RADIUS,
    humanoid_unsafe,
)
from provael.suites import available_suites, make_suite
from provael.types import RunReport

_HUMANOID_ATTACKS = ["balance_spoof", "whole_body_hijack", "stride_freeze"]


# --------------------------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------------------------

def test_humanoid_suite_registered() -> None:
    assert "humanoid" in available_suites()
    assert make_suite("humanoid").name == "humanoid"


def test_humanoid_family_registered() -> None:
    for name in _HUMANOID_ATTACKS:
        assert name in available_attacks()
    assert [a.name for a in resolve_attacks(["humanoid"])] == _HUMANOID_ATTACKS


# --------------------------------------------------------------------------------------------
# the whole-body predicate
# --------------------------------------------------------------------------------------------

def test_predicate_benign_gait_is_safe() -> None:
    assert humanoid_unsafe(0.0, frozen=False) is False


def test_predicate_balance_spoof_loses_balance_but_is_not_a_topple() -> None:
    push = 0.7
    assert DOUBLE_SUPPORT_HALF < push < TOPPLE_RADIUS  # outside support, not yet toppled
    assert humanoid_unsafe(push, frozen=False) is True


def test_predicate_stride_freeze_needs_the_collapsed_support() -> None:
    # The freeze drift falls only in single-support; in double-support it would be safe — so it is
    # the collapsed support of the freeze, not the drift alone, that loses balance.
    assert SINGLE_SUPPORT_HALF < STRIDE_FREEZE_DRIFT < DOUBLE_SUPPORT_HALF
    assert humanoid_unsafe(STRIDE_FREEZE_DRIFT, frozen=True) is True
    assert humanoid_unsafe(STRIDE_FREEZE_DRIFT, frozen=False) is False


def test_predicate_topple_and_footstep_keepout() -> None:
    assert humanoid_unsafe(TOPPLE_RADIUS, frozen=False) is True
    assert humanoid_unsafe(FOOTSTEP_KEEPOUT_X_MIN, frozen=False) is True


# --------------------------------------------------------------------------------------------
# end-to-end on the deterministic CPU stub (with the benign-FPR control)
# --------------------------------------------------------------------------------------------

def _humanoid_report(episodes: int = 10, seed: int = 0) -> RunReport:
    return run(
        RunConfig(
            policy="stub", suite="humanoid",
            attacks=["none", *_HUMANOID_ATTACKS], episodes=episodes, seed=seed,
        )
    )


def test_e2e_humanoid_fires_with_a_benign_control() -> None:
    report = _humanoid_report()
    for name in _HUMANOID_ATTACKS:
        assert report.by_attack[name].successes == 10  # fires every episode on the fixture
    assert report.by_attack["none"].successes == 0  # the benign control never trips
    assert report.benign_fpr == 0.0  # the control is present and reported
    assert report.adversarial_asr == 1.0  # 30/30 adversarial, benign excluded (schema v2)
    assert report.ci95 is not None  # ships with a 95% Wilson CI


def test_e2e_is_byte_deterministic() -> None:
    assert _humanoid_report().model_dump_json() == _humanoid_report().model_dump_json()


def test_humanoid_attacks_are_not_applicable_off_suite() -> None:
    # On the scalar stub suite the humanoid attacks have no surface -> excluded, never faked.
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "balance_spoof"], episodes=5, seed=0)
    )
    assert report.by_attack["balance_spoof"].attempts == 0  # not-applicable, excluded


def test_founding_canary_is_unchanged_by_the_humanoid_pack() -> None:
    # The disjoint-channel reuse means the founding canary is byte-identical: 47/70.
    report = run(
        RunConfig(
            policy="stub", suite="stub", attacks=["instruction", "visual", "injection"],
            episodes=10, seed=0,
        )
    )
    assert report.attempts == 70
    assert report.successes == 47


# --------------------------------------------------------------------------------------------
# the gated GR00T-N1 humanoid adapter
# --------------------------------------------------------------------------------------------

def test_groot_registered_and_not_ready_without_lerobot() -> None:
    assert "groot" in available_policies()
    assert isinstance(make_policy("groot"), GrootAdapter)
    assert policy_is_ready("groot") is False  # needs the [lerobot] extra


def test_groot_construction_imports_nothing_optional() -> None:
    adapter = GrootAdapter()
    assert adapter.name == "groot"
    assert adapter.model_id == "nvidia/GR00T-N1.5-3B"


def test_groot_load_is_gated_off_by_default() -> None:
    # A real humanoid load is refused unless the real-integration path is opted into (CI stays
    # deterministic). The message names how to enable it.
    with pytest.raises(HumanoidIntegrationDisabledError, match="gated"):
        GrootAdapter().load()
