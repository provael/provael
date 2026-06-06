"""The ``baseline`` family: a no-op control for measuring attack *lift*.

A red-team ASR is only meaningful **relative to the un-attacked policy**. ``NoOpAttack``
runs the benign task unchanged, so its ASR is the baseline rate at which the policy ends
in the unsafe state on its own (given the configured predicate). An attack family's ASR
minus this baseline is the lift attributable to the attack — the honest signal,
especially while the LIBERO keep-out predicate is an uncalibrated default.
"""

from __future__ import annotations

from vla_redteam.attacks.base import Attack
from vla_redteam.types import Observation

FAMILY = "baseline"


class NoOpAttack(Attack):
    """Identity control: returns the instruction and observation unchanged."""

    name = "none"
    family = FAMILY

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        return instruction, observation


__all__ = ["FAMILY", "NoOpAttack"]
