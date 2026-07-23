"""The evidence-state ladder: what a run has actually EARNED, never over-promoted (Phase 2).

Pins the classifier by running it: a stub run is `stub`, a real policy on a real suite is
`real-episode` (never `measured-real-policy-effect` or a higher rung a bare run cannot back), a
report predating the ladder is `legacy-unverified`, and the committed SmolVLA×LIBERO artifact reads
`legacy-unverified` (conservative — not silently re-promoted from its non-stub names).
"""

from __future__ import annotations

from pathlib import Path

from provael.config import RunConfig
from provael.evidence import (
    EVIDENCE_STATE_ORDER,
    EvidenceState,
    classify_run,
    evidence_state_of,
    is_at_least,
    rank,
)
from provael.report import load_report
from provael.runner import run

_REAL = Path(__file__).resolve().parent.parent / "results" / "smolvla_libero_object"


def test_stub_run_is_classified_stub_not_a_real_tier() -> None:
    assert classify_run("stub", "stub") is EvidenceState.STUB
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4))
    assert report.evidence_state == EvidenceState.STUB.value
    assert evidence_state_of(report) is EvidenceState.STUB


def test_real_policy_and_suite_is_real_episode_not_measured_effect() -> None:
    # A real policy on a real suite EARNED 'real-episode' — never the stronger measured-effect rung
    # (which needs a predeclared endpoint + controls) or any HIL/hardware/external rung.
    state = classify_run("smolvla", "libero")
    assert state is EvidenceState.REAL_EPISODE
    assert not is_at_least(state, EvidenceState.MEASURED_REAL_POLICY_EFFECT)


def test_a_real_adapter_on_the_stub_is_only_adapter_smoke() -> None:
    assert classify_run("smolvla", "stub") is EvidenceState.ADAPTER_SMOKE
    assert classify_run("stub", "libero") is EvidenceState.ADAPTER_SMOKE


def test_classifier_never_awards_a_rung_above_real_episode() -> None:
    # No policy/suite pairing alone can reach measured-effect or the corroboration rungs.
    ceiling = rank(EvidenceState.REAL_EPISODE)
    for policy in ("stub", "smolvla", "openvla"):
        for suite in ("stub", "libero"):
            assert rank(classify_run(policy, suite)) <= ceiling


def test_legacy_report_without_the_field_is_legacy_unverified() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none"], episodes=2))
    legacy = report.model_copy(update={"evidence_state": None})  # simulate a pre-machine artifact
    assert evidence_state_of(legacy) is EvidenceState.LEGACY_UNVERIFIED


def test_committed_artifact_is_conservatively_legacy_unverified() -> None:
    # The real SmolVLA×LIBERO run predates the ladder -> legacy-unverified, NOT re-promoted to a
    # real tier from its non-stub policy/suite names.
    assert evidence_state_of(load_report(_REAL)) is EvidenceState.LEGACY_UNVERIFIED


def test_legacy_unverified_sits_at_the_bottom_of_the_ladder() -> None:
    # An unverifiable claim is weaker than a known stub, not stronger.
    assert EVIDENCE_STATE_ORDER[0] is EvidenceState.LEGACY_UNVERIFIED
    assert is_at_least(EvidenceState.STUB, EvidenceState.LEGACY_UNVERIFIED)
    assert not is_at_least(EvidenceState.LEGACY_UNVERIFIED, EvidenceState.STUB)


def test_evidence_state_surfaces_in_report_and_compliance_markdown() -> None:
    from provael.compliance import to_compliance_markdown
    from provael.report import to_markdown

    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4))
    assert "evidence state" in to_markdown(report)
    assert "stub" in to_markdown(report)
    assert "evidence state" in to_compliance_markdown(report)
