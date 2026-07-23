"""An explicit evidence-state ladder — how far a result has actually been verified.

The old honesty flag was binary: ``policy != "stub" and suite != "stub"`` was awarded
``measured-real-transfer``, everything else ``stub-validated-scaffolding``. That conflated "a real
policy ran real episodes" with "a measured, controlled, provenanced *effect*", and it awarded a real
tier to any non-stub run regardless of what evidence backed it.

:class:`EvidenceState` names the rungs explicitly, and the classifier **never** awards a rung a
run has not earned:

* a fresh stub run is ``stub``;
* a real policy on a real suite that completed episodes is ``real-episode`` — NOT
  ``measured-real-policy-effect`` (that needs a predeclared endpoint, treatment/control, and bound
  provenance) and certainly not the HIL / hardware / external-reproduction / customer rungs (those
  need external references this tool cannot manufacture);
* a report that predates this machine (no recorded state) is ``legacy-unverified`` — conservative on
  purpose, so the committed SmolVLA×LIBERO artifact is not retroactively over-promoted.

This is additive: it sits alongside the existing coarse ``transfer_status`` (which it deprecates) so
no committed evidence is silently reinterpreted.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from provael.types import RunReport


class EvidenceState(StrEnum):
    """The verified strength of a result. Higher rungs require strictly more evidence."""

    LEGACY_UNVERIFIED = "legacy-unverified"
    STUB = "stub"
    ADAPTER_SMOKE = "adapter-smoke"
    REAL_FORWARD = "real-forward"
    REAL_EPISODE = "real-episode"
    MEASURED_REAL_POLICY_EFFECT = "measured-real-policy-effect"
    HIL_CORROBORATED = "hil-corroborated"
    HARDWARE_CORROBORATED = "hardware-corroborated"
    EXTERNALLY_REPRODUCED = "externally-reproduced"
    CUSTOMER_RELEASE_GATED = "customer-release-gated"


#: Rung order (index = strength). ``legacy-unverified`` sits at the bottom: an unverifiable claim is
#: weaker than a known stub, not stronger.
EVIDENCE_STATE_ORDER: tuple[EvidenceState, ...] = (
    EvidenceState.LEGACY_UNVERIFIED,
    EvidenceState.STUB,
    EvidenceState.ADAPTER_SMOKE,
    EvidenceState.REAL_FORWARD,
    EvidenceState.REAL_EPISODE,
    EvidenceState.MEASURED_REAL_POLICY_EFFECT,
    EvidenceState.HIL_CORROBORATED,
    EvidenceState.HARDWARE_CORROBORATED,
    EvidenceState.EXTERNALLY_REPRODUCED,
    EvidenceState.CUSTOMER_RELEASE_GATED,
)

#: The rungs that count as a real-policy measurement (for the deprecated transfer_status view and
#: release gates that require "not a stub"). Deliberately excludes LEGACY_UNVERIFIED and STUB.
_REAL_POLICY_STATES = frozenset(
    EVIDENCE_STATE_ORDER[EVIDENCE_STATE_ORDER.index(EvidenceState.REAL_EPISODE):]
)


def rank(state: EvidenceState) -> int:
    """The state's rung index (higher = stronger evidence)."""
    return EVIDENCE_STATE_ORDER.index(state)


def is_at_least(state: EvidenceState, threshold: EvidenceState) -> bool:
    """Whether ``state`` is at least as strong as ``threshold`` on the ladder."""
    return rank(state) >= rank(threshold)


def is_real_policy_measurement(state: EvidenceState) -> bool:
    """Whether ``state`` reflects a real policy actually running (>= real-episode)."""
    return state in _REAL_POLICY_STATES


def classify_run(policy: str, suite: str) -> EvidenceState:
    """The state a freshly-produced run has EARNED from its policy/suite alone.

    Never awards ``measured-real-policy-effect`` or higher — those require a predeclared endpoint,
    controls, and external references a bare run does not carry. A real policy on a real suite that
    completed a rollout is ``real-episode``; a real adapter paired with the stub (or vice versa) is
    ``adapter-smoke`` (construction, not an embodied run); a full stub run is ``stub``.
    """
    real_policy = policy != "stub"
    real_suite = suite != "stub"
    if real_policy and real_suite:
        return EvidenceState.REAL_EPISODE
    if real_policy or real_suite:
        return EvidenceState.ADAPTER_SMOKE
    return EvidenceState.STUB


def evidence_state_of(report: RunReport) -> EvidenceState:
    """The report's recorded evidence state, or ``legacy-unverified`` if it predates the machine.

    A report that carries no ``evidence_state`` (schema < 2, or any pre-machine artifact) is
    ``legacy-unverified`` — conservatively at the bottom of the ladder, never re-promoted from its
    policy/suite names.
    """
    raw = getattr(report, "evidence_state", None)
    if not raw:
        return EvidenceState.LEGACY_UNVERIFIED
    try:
        return EvidenceState(raw)
    except ValueError:
        return EvidenceState.LEGACY_UNVERIFIED


__all__ = [
    "EvidenceState",
    "EVIDENCE_STATE_ORDER",
    "rank",
    "is_at_least",
    "is_real_policy_measurement",
    "classify_run",
    "evidence_state_of",
]
