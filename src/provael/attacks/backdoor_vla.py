"""The ``backdoor`` attack family (EAI03): objective-decoupled trigger screening.

Where the other families perturb the *live* task, this family screens a policy for a **latent,
objective-decoupled backdoor** — a benign-looking trigger that, on a *backdoored* checkpoint, flips
the policy to an attacker objective while clean inputs behave normally (BadVLA arXiv:2505.16640;
AttackVLA / BackdoorVLA arXiv:2511.12149). Two attacks ship, both sim-only and routed through the
standard :class:`~provael.attacks.base.Attack` interface (model-agnostic — they emit a perturbation,
no model-specific code):

  * ``object_trigger`` — a **BadVLA-style visual/object trigger**: injects a battery of candidate
    trigger markers into the scene (the dedicated backdoor channel), modelling a benign-looking
    object/sticker whose presence a poisoned policy keys on. The visible instruction is left
    untouched, so any activation is attributable to the trigger, not the text goal.
  * ``phrase_trigger`` — an **AttackVLA-style objective-decoupled trigger phrase**: injects a rare
    trigger phrase while the visible task instruction stays benign, modelling a text trigger a
    poisoned checkpoint responds to.

Both are a **pre-deployment screen**, not an exploit: Provael neither trains nor implants a real
backdoor. On the deterministic :class:`~provael.suites.stub.StubSuite` core the paired
:class:`~provael.policies.stub.StubPolicy` is a **known-planted fixture** that activates on the
:data:`~provael.scoring.backdoor.PLANTED_TRIGGER`, so the screen demonstrably fires and the family
runs CPU-only and reproducibly. **Honest scope:** this is **stub-validated scaffolding**. A clean,
un-backdoored public checkpoint carries no such implant, so the same battery should screen ~0% — an
honest null; the real SmolVLA × LIBERO / Meta-World transfer is GPU-gated and **not run here**, so
no cross-model transfer is claimed. The trigger protocol + predicate live in
:mod:`provael.scoring.backdoor`.

Prior art (see PRIOR_ART.md): **BadVLA** (arXiv 2505.16640, objective-decoupled backdoor that
survives fine-tuning); **AttackVLA / BackdoorVLA** (arXiv 2511.12149, targeted action-sequence
backdoor); **TrojanRobot** (arXiv 2411.11683, physical-world backdoor via a malicious VLM).
"""

from __future__ import annotations

from provael.attacks._payload import append_channel
from provael.attacks.base import Attack
from provael.eai import CATALOG
from provael.scoring.backdoor import (
    BACKDOOR_SURFACE_KEY,
    BACKDOOR_TRIGGER_KEY,
    TRIGGER_BATTERY,
    build_trigger_cue,
)
from provael.types import Observation

FAMILY = "backdoor"
_EAI = CATALOG["EAI03"]

#: The candidate-trigger cues a screen injects — the whole battery, so a checkpoint planted with any
#: one of them lights up. Includes the sim-fixture's planted trigger, so the stub screen fires.
_BATTERY_CUES: tuple[str, ...] = tuple(build_trigger_cue(t) for t in TRIGGER_BATTERY)


class ObjectTriggerBackdoor(Attack):
    """BadVLA-style visual/object trigger: screen for a scene-object backdoor.

    Injects the candidate-trigger battery into the dedicated backdoor channel as benign-looking
    scene markers; a policy planted with a matching trigger activates its hidden objective. The
    instruction is left untouched (objective-decoupled), so a resulting activation is attributable
    to the trigger, not the text goal.
    """

    name = "object_trigger"
    family = FAMILY
    eai_id = _EAI.id
    eai_name = _EAI.name

    def applicable(self, observation: Observation) -> bool:
        # N/A on suites that surface no backdoor-activation signal (excluded from the ASR
        # denominator, never faked) — e.g. a suite that hasn't implemented EAI03 screening.
        return bool(observation.get(BACKDOOR_SURFACE_KEY))

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        return instruction, append_channel(observation, BACKDOOR_TRIGGER_KEY, *_BATTERY_CUES)


class PhraseTriggerBackdoor(Attack):
    """AttackVLA-style objective-decoupled trigger phrase: screen for a text-trigger backdoor.

    Injects the candidate-trigger battery as trigger phrases into the backdoor channel while the
    visible task instruction stays benign (objective-decoupled). Models a rare phrase a poisoned
    checkpoint keys on; a policy planted with a matching trigger activates its hidden objective.
    """

    name = "phrase_trigger"
    family = FAMILY
    eai_id = _EAI.id
    eai_name = _EAI.name

    def applicable(self, observation: Observation) -> bool:
        return bool(observation.get(BACKDOOR_SURFACE_KEY))

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        return instruction, append_channel(observation, BACKDOOR_TRIGGER_KEY, *_BATTERY_CUES)


__all__ = [
    "FAMILY",
    "ObjectTriggerBackdoor",
    "PhraseTriggerBackdoor",
]
