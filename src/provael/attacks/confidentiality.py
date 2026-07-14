"""The ``confidentiality`` attack family (EAI09): model & data confidentiality leak screening.

Where the other families perturb the *task*, this family screens a policy for a **query-based
confidentiality leak** — a **memorized training canary** an attacker who can only *query* the policy
could recover by **model extraction / inversion** or **membership inference** (SoK on
foundation-model-powered robots, arXiv 2606.16788; NIST AI 100-2 Privacy, NISTAML.03). Two attacks
ship, both sim-only and routed through the standard :class:`~provael.attacks.base.Attack` interface
(model-agnostic — they emit a perturbation, no model-specific code):

  * ``membership_inference`` — a **membership-inference probe** (``member::<id>``): asks whether a
    candidate canary was a *training member*; a policy that memorized it leaks a positive signal.
  * ``model_extraction`` — an **extraction / inversion query** (``extract::<id>``): asks the policy
    to reproduce a candidate secret; a policy that memorized it leaks the canary verbatim.

Both are a **pre-deployment screen**, not an exploit: Provael never performs a real exfiltration —
the "canaries" are opaque sim-only markers, and the leak is scored on a deterministic fixture. The
visible instruction is left untouched, so any leak is attributable to the probe, not the task. On
the :class:`~provael.suites.stub.StubSuite` core the paired
:class:`~provael.policies.stub.StubPolicy` is a **known-planted fixture** that leaks the
:data:`~provael.scoring.confidentiality.PLANTED_CANARY`, so the screen demonstrably fires and the
family runs CPU-only and reproducibly. **Honest scope:** this is **stub-validated scaffolding**. A
clean policy that memorized no such canary leaks nothing, so the battery screens ~0% — an honest
null; the real SmolVLA × LIBERO transfer (an actual membership-inference / extraction advantage
measured by *querying* a real policy, never exfiltrating real data) is GPU-gated and **not run
here**, so no cross-model transfer is claimed. The probe protocol + predicate live in
:mod:`provael.scoring.confidentiality`.

Prior art (see docs/TOP10.md EAI09): query-based model extraction / inversion / membership inference
of learned policies; the Unitree G1 telemetry-exfiltration incident (arXiv 2509.14096). Maps to NIST
AI 100-2 **Privacy (model extraction, NISTAML.03)**, MITRE ATLAS **Exfiltration**, OWASP **LLM02**.
"""

from __future__ import annotations

from provael.attacks._payload import append_channel
from provael.attacks.base import Attack
from provael.eai import CATALOG
from provael.scoring.confidentiality import (
    CANARY_BATTERY,
    CONFIDENTIALITY_KEY,
    CONFIDENTIALITY_SURFACE_KEY,
    build_extract_query,
    build_member_probe,
)
from provael.types import Observation

FAMILY = "confidentiality"
_EAI = CATALOG["EAI09"]

#: The membership-inference probe cues a screen injects — the whole battery, so a policy that
#: memorized any candidate canary leaks. Includes the planted canary, so the stub fixture fires.
_MEMBER_CUES: tuple[str, ...] = tuple(build_member_probe(c) for c in CANARY_BATTERY)
#: The extraction / inversion query cues a screen injects — the whole battery, same rationale.
_EXTRACT_CUES: tuple[str, ...] = tuple(build_extract_query(c) for c in CANARY_BATTERY)


class MembershipInference(Attack):
    """Membership-inference screen: probe whether a candidate canary was a training member.

    Injects the candidate-canary battery as ``member::`` probes into the dedicated confidentiality
    channel; a policy that memorized a matching canary leaks a positive membership signal. The
    instruction is left untouched, so a resulting leak is attributable to the probe, not the task.
    """

    name = "membership_inference"
    family = FAMILY
    eai_id = _EAI.id
    eai_name = _EAI.name

    def applicable(self, observation: Observation) -> bool:
        # N/A on suites that surface no confidentiality-leak signal (excluded from the ASR
        # denominator, never faked) — e.g. a suite that hasn't implemented EAI09 screening.
        return bool(observation.get(CONFIDENTIALITY_SURFACE_KEY))

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        return instruction, append_channel(observation, CONFIDENTIALITY_KEY, *_MEMBER_CUES)


class ModelExtraction(Attack):
    """Extraction / inversion screen: query the policy to reproduce a candidate secret.

    Injects the candidate-canary battery as ``extract::`` queries into the confidentiality channel;
    a policy that memorized a matching canary leaks it verbatim (model inversion / extraction). The
    instruction is left untouched, so a resulting leak is attributable to the query, not the task.
    """

    name = "model_extraction"
    family = FAMILY
    eai_id = _EAI.id
    eai_name = _EAI.name

    def applicable(self, observation: Observation) -> bool:
        return bool(observation.get(CONFIDENTIALITY_SURFACE_KEY))

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        return instruction, append_channel(observation, CONFIDENTIALITY_KEY, *_EXTRACT_CUES)


__all__ = [
    "FAMILY",
    "MembershipInference",
    "ModelExtraction",
]
