"""Transfer-test path: by_family aggregation + the rate/CI/benign/status transfer-test."""

from __future__ import annotations

from provael.calibration import transfer_test
from provael.config import RunConfig
from provael.runner import run
from provael.scoring.asr import by_family
from provael.types import REAL_TRANSFER, STUB_SCAFFOLDING, ASRStat


def _report(policy: str = "stub", suite: str = "stub"):
    return run(RunConfig(
        policy=policy, suite=suite,
        attacks=["none", "backdoor", "action"], episodes=10, seed=0,
    ))


def test_by_family_groups_results() -> None:
    fam = by_family(_report().results)
    assert fam["backdoor"].attempts == 20 and fam["backdoor"].successes == 20
    assert fam["action"].attempts == 20 and fam["action"].successes == 20
    assert fam["baseline"].attempts == 10 and fam["baseline"].successes == 0


def test_transfer_test_carries_rate_ci_and_benign_control() -> None:
    fam = by_family(_report().results)
    tt = transfer_test(
        fam["backdoor"], benign=fam["baseline"], policy="stub", suite="stub", family="backdoor"
    )
    assert tt.family == "backdoor"
    assert tt.rate == 1.0
    assert tt.ci95 is not None and 0.0 <= tt.ci95[0] <= tt.ci95[1] <= 1.0
    assert tt.ci95[0] > 0.8  # 20/20 → a tight, high Wilson interval
    assert tt.benign_fpr == 0.0  # the `none` control
    assert tt.n == 20


def test_transfer_status_is_stub_on_the_stub() -> None:
    fam = by_family(_report().results)
    tt = transfer_test(
        fam["backdoor"], benign=fam["baseline"], policy="stub", suite="stub", family="backdoor"
    )
    assert tt.transfer_status == STUB_SCAFFOLDING
    assert "not a real VLA" in tt.note


def test_transfer_status_is_real_for_a_real_policy_suite() -> None:
    # Labelling is by (policy, suite): a real policy x real suite is a real-transfer measurement.
    stat = ASRStat(attempts=10, successes=6, asr=0.6)
    benign = ASRStat(attempts=10, successes=0, asr=0.0)
    tt = transfer_test(stat, benign=benign, policy="smolvla", suite="libero", family="instruction")
    assert tt.transfer_status == REAL_TRANSFER
    assert tt.benign_fpr == 0.0
    assert tt.ci95 is not None


def test_transfer_test_handles_empty_slice() -> None:
    empty = ASRStat(attempts=0, successes=0, asr=0.0)
    tt = transfer_test(empty, benign=None, policy="stub", suite="stub", family="backdoor")
    assert tt.ci95 is None  # no applicable episodes → no interval
    assert tt.benign_fpr is None
    assert tt.n == 0


def test_transfer_test_json_is_byte_stable() -> None:
    fam = by_family(_report().results)
    tt = transfer_test(
        fam["backdoor"], benign=fam["baseline"], policy="stub", suite="stub", family="backdoor"
    )
    assert tt.model_dump_json() == tt.model_dump_json()
