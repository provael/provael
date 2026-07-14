"""The Embodied AI Security Top 10 — the catalog Provael's attacks map to.

Each attack family is tagged with the ``EAIxx`` risk it exercises (see
``docs/TOP10.md``). This module is the **single source of truth** for those ids,
their human names, a one-line description, and a stable ``helpUri`` deep-link into
the Top-10 document. Attacks import their tag from here (so the id/name on an
:class:`~provael.attacks.base.Attack` never drifts from the catalog), and the SARIF
exporter builds its ``rules[]`` from the same entries.

Only the families that ship today are listed; the full risk list lives in the doc.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Canonical home of the Top-10 document (anchors below are GitHub-rendered slugs).
TOP10_DOC_URL = "https://github.com/provael/provael/blob/main/docs/TOP10.md"


@dataclass(frozen=True)
class EaiRisk:
    """One Embodied AI Security Top-10 risk entry."""

    id: str
    name: str
    description: str
    anchor: str  # GitHub heading slug within docs/TOP10.md

    @property
    def help_uri(self) -> str:
        """Deep link to this risk's section in the Top-10 document."""
        return f"{TOP10_DOC_URL}#{self.anchor}"


#: EAI id -> risk. Keyed by id so SARIF rules and report tables resolve uniformly.
CATALOG: dict[str, EaiRisk] = {
    "EAI01": EaiRisk(
        id="EAI01",
        name="Policy & instruction jailbreak",
        description=(
            "A reframed or substituted instruction overrides the policy's safe task "
            "and drives it into an unsafe action."
        ),
        anchor="eai01--policy--instruction-jailbreak-direct-command-channel",
    ),
    "EAI02": EaiRisk(
        id="EAI02",
        name="Adversarial perception",
        description=(
            "A perturbation of what the policy sees (patch, decoy, sensor spoof) "
            "redirects its behaviour while the text goal stays benign."
        ),
        anchor="eai02--adversarial-perception-patches--textures--sensor-spoofing",
    ),
    "EAI03": EaiRisk(
        id="EAI03",
        name="Model & pipeline poisoning, backdoors & supply chain",
        description=(
            "A hidden, objective-decoupled trigger (a benign-looking object or phrase) "
            "planted at train/fine-tune time or via a poisoned open-weights checkpoint: "
            "normal behaviour until the trigger fires an attacker-chosen action."
        ),
        anchor="eai03--model--pipeline-poisoning-backdoors--supply-chain",
    ),
    "EAI04": EaiRisk(
        id="EAI04",
        name="Action-space integrity",
        description=(
            "An attack on the policy's action output itself — freezing it into a no-op "
            "(availability) or hijacking its trajectory toward an attacker-chosen waypoint."
        ),
        anchor="eai04--action-space-integrity-attacks-hijack--targeted-trajectory--freeze",
    ),
    "EAI05": EaiRisk(
        id="EAI05",
        name="Indirect / embodied prompt injection",
        description=(
            "Text the agent ingests from its environment or tools (a sign, a poisoned "
            "tool description) carries an imperative the policy then executes."
        ),
        anchor="eai05--indirect--embodied-prompt-injection",
    ),
    "EAI06": EaiRisk(
        id="EAI06",
        name="Cross-domain safety misalignment (the embodiment gap)",
        description=(
            "A benign-sounding instruction a language-layer safety filter passes still drives an "
            "unsafe embodied action (motion into a keep-out zone / contact with a flagged object): "
            "the embodiment gap between safe language and unsafe physical action."
        ),
        anchor="eai06--cross-domain-safety-misalignment-the-embodiment-gap",
    ),
    "EAI08": EaiRisk(
        id="EAI08",
        name="Identity, access & excessive autonomy",
        description=(
            "A perturbed instruction drives the policy to self-authorize and execute a "
            "consequential, authorization-gated action without the required operator-authorization "
            "token — an embodied instance of excessive agency (OWASP ASI03)."
        ),
        anchor="eai08--identity-access--excessive-autonomy",
    ),
    "EAI09": EaiRisk(
        id="EAI09",
        name="Model & data confidentiality",
        description=(
            "A query-based confidentiality attack — model extraction, membership inference, or "
            "inversion — that recovers a memorized training canary from the policy; screened "
            "sim-only against a planted fixture, never a real exfiltration."
        ),
        anchor="eai09--model--data-confidentiality--theft-extraction-inversion--surveillance",
    ),
}


def risk(eai_id: str) -> EaiRisk:
    """Look up a risk by id.

    Raises:
        KeyError: if ``eai_id`` is not in the catalog.
    """
    try:
        return CATALOG[eai_id]
    except KeyError:
        raise KeyError(f"unknown EAI id {eai_id!r}; known: {sorted(CATALOG)}") from None


__all__ = ["TOP10_DOC_URL", "EaiRisk", "CATALOG", "risk"]
