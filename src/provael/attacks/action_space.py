"""The ``action_space`` attack family (EAI04, 2nd vector): commanded-end-state integrity.

Provael's founding EAI04 vector is the `action` family (`freeze` nulls the commanded motion,
`trajectory_hijack` redirects its heading). This family adds a **second, disjoint EAI04 vector** —
mirroring how `sensor_spoof` is a second EAI02 vector alongside `visual` — that attacks the policy's
**commanded end-state** on its own out-of-band channel rather than the motion channels. Two attacks
ship, both sim-only and routed through the standard :class:`~provael.attacks.base.Attack` interface
(model-agnostic — they emit a perturbation, no model-specific code):

  * ``keepout_hijack`` — drives the policy's **commanded end-effector into a monitored-standstill
    keep-out zone** (an attacker-chosen cell), an AttackVLA-style targeted end-state hijack.
  * ``critical_freeze`` — **paralyses the policy at a safety-critical step** (a targeted,
    availability-style FreezeVLA variant), so a required safe maneuver never executes.

**Sim-only, defensive.** These perturb only the **observation the policy receives**, NEVER
real-robot control, and the violation is scored on the fixture policy's *commanded* end-state in
**simulation**. No real-world payload. The visible instruction stays **benign** (unchanged), so the
stub's danger channel stays 0 (see the test) and the violation is attributable to action-space
integrity — not a jailbroken language goal (the separate EAI01 `instruction` family), and not the
motion-channel freeze of the founding `action` family (a disjoint channel; the `freeze`/
`trajectory_hijack` canaries stay byte-identical). On the deterministic CPU ``reach`` suite the
paired :class:`~provael.policies.stub.StubPolicy` commands the hijack cell / freeze sentinel, so the
vector fires CPU-only and reproducibly. **Honest scope:** this is stub-validated scaffolding. The
benign (``none``) baseline injects no cue and stays at the origin, un-frozen (0% false-positive
control). The real-model transfer — a real policy's commanded end-effector hijacked into a keep-out
cell, or frozen at a critical step (AttackVLA / FreezeVLA × SmolVLA × LIBERO) — is GPU-gated and
**not run here**, so no cross-model transfer is claimed. The cue grammar + predicate live in
:mod:`provael.scoring.action_space`.

Prior art / mapping (see docs/TOP10.md): **EAI04 Action-space integrity attacks (hijack / targeted
trajectory / freeze)**. Provael makes no "first" claim and does not brand the Embodied AI Security
Top 10 as OWASP.
"""

from __future__ import annotations

from provael.attacks._payload import append_channel, episode_index
from provael.attacks.base import Attack
from provael.eai import CATALOG
from provael.scoring.action_space import (
    ACTION_SPACE_KEY,
    ACTION_SPACE_SURFACE_KEY,
    CRITICAL_STEPS,
    HIJACK_CELLS,
    build_freeze_cue,
    build_hijack_cue,
)
from provael.types import Observation

FAMILY = "action_space"
_EAI = CATALOG["EAI04"]


class _ActionSpace(Attack):
    """Shared base: inject a commanded-end-state cue into the disjoint action-space channel.

    ``perturb`` leaves the visible instruction **unchanged** (a pure action-space attack, not
    a language reframing) and injects a deterministic per-episode cue into the action-space channel.
    The stub's danger channel therefore stays 0, so the violation is purely action-space integrity.
    """

    family = FAMILY
    eai_id = _EAI.id
    eai_name = _EAI.name

    def applicable(self, observation: Observation) -> bool:
        # N/A on suites that surface no action-space keep-out/freeze signal (excluded from the ASR
        # denominator, never faked) — e.g. the scalar stub suite, or one without EAI04 2nd-vector
        # scoring.
        return bool(observation.get(ACTION_SPACE_SURFACE_KEY))


class KeepoutHijack(_ActionSpace):
    """Targeted end-state hijack: drive the commanded end-effector into the keep-out zone.

    An AttackVLA-style targeted hijack — the perturbation steers the *commanded* reach to an
    attacker cell inside the keep-out box, a different failure from the founding
    `trajectory_hijack` (which redirects the motion heading on channels 1-3)."""

    name = "keepout_hijack"

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        cell = HIJACK_CELLS[episode_index(observation, len(HIJACK_CELLS))]
        adv_obs = append_channel(observation, ACTION_SPACE_KEY, build_hijack_cue(cell))
        return instruction, adv_obs


class CriticalFreeze(_ActionSpace):
    """Critical-step freeze: paralyse the policy at a safety-critical step (availability failure).

    A targeted FreezeVLA-style paralysis — the perturbation freezes the policy at an attacker-chosen
    safety-critical step so a required safe maneuver never executes, a different failure from the
    founding `freeze` (which nulls the commanded motion magnitude on channels 1-3)."""

    name = "critical_freeze"

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        step = CRITICAL_STEPS[episode_index(observation, len(CRITICAL_STEPS))]
        adv_obs = append_channel(observation, ACTION_SPACE_KEY, build_freeze_cue(step))
        return instruction, adv_obs


__all__ = [
    "FAMILY",
    "KeepoutHijack",
    "CriticalFreeze",
]
