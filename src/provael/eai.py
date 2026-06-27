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
    "EAI05": EaiRisk(
        id="EAI05",
        name="Indirect / embodied prompt injection",
        description=(
            "Text the agent ingests from its environment or tools (a sign, a poisoned "
            "tool description) carries an imperative the policy then executes."
        ),
        anchor="eai05--indirect--embodied-prompt-injection",
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
