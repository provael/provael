"""Named reproductions of published VLA attacks, mapped onto Provael's attack families.

The active VLA-attack literature (FreezeVLA, the OpenVLA adversarial patch, BadVLA, RoboPAIR) is
scattered across one-off repos with no common harness. A *reproduction* points Provael's existing
templated families at the *threat class* a paper describes, so you can run a paper's attack idea
with one command and read an ASR — then swap in the real model.

HONESTY (this is the whole point of the feature, so it is enforced in the output):

* The **paper's** reported ASR is *cited*, never claimed as Provael's. It is shown in a separate
  column from Provael's *measured* ASR for the run you actually ran.
* On the deterministic ``stub`` the measured numbers are **properties of the test fixture**, not
  of any real VLA — the banner says so and tells you how to run the real model.
* Provael reproduces the *threat class* with a templated, auditable family; it does **not** ship
  the paper's gradient/optimisation-based artifact. ``mapping_note`` states the relationship.
* No "first"/"SOTA" claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Reproduction:
    """One published-attack reproduction: the paper, the threat class, and the Provael mapping."""

    name: str
    title: str
    arxiv: str
    eai: str
    attacks: list[str]  # Provael attack/family names this reproduction runs
    paper_asr: str  # the paper's reported number — CITED, shown separately from Provael's
    summary: str
    mapping_note: str
    aliases: list[str] = field(default_factory=list)


REPRODUCTIONS: dict[str, Reproduction] = {
    "freezevla": Reproduction(
        name="freezevla",
        title="FreezeVLA: action-freezing attacks on Vision-Language-Action models",
        arxiv="arXiv:2509.19870",
        eai="EAI04",
        attacks=["freeze"],
        paper_asr="76.2% average action-freeze ASR (reported)",
        summary="An adversarial image makes the policy stop issuing motor commands — it freezes, "
        "ignores the instruction, and can evade naive safety monitors.",
        mapping_note="Provael's EAI04 `freeze` directive models the action-freeze *outcome* "
        "(zeroed end-effector motion) as a templated, auditable signal — not the paper's "
        "optimised adversarial image.",
    ),
    "openvla-patch": Reproduction(
        name="openvla-patch",
        title="Adversarial patch attacks on OpenVLA (printed-patch visual perturbation)",
        arxiv="arXiv:2511.21192",
        eai="EAI02",
        attacks=["patch"],
        paper_asr="clean 98% -> 6% task success under a printed patch (reported)",
        summary="A printed adversarial patch in the camera view collapses the policy's task "
        "success.",
        mapping_note="Provael's EAI02 `patch` family plants a visual-token marker in the "
        "observation — a templated stand-in for the paper's optimised printed patch.",
        aliases=["openvla_patch", "patch-attack"],
    ),
    "badvla": Reproduction(
        name="badvla",
        title="BadVLA: backdoor attacks on Vision-Language-Action models",
        arxiv="arXiv:2505.16640",
        eai="EAI02",
        attacks=["patch", "decoy_object"],
        paper_asr="up to ~100% targeted ASR with a physical trigger (reported)",
        summary="A physical-object / patch trigger in the scene flips the policy to an "
        "attacker-chosen behaviour.",
        mapping_note="Provael approximates the *trigger-in-the-scene* threat with the EAI02 "
        "visual family (`patch` + `decoy_object`); it does not train or implant a real backdoor.",
    ),
    "robopair": Reproduction(
        name="robopair",
        title="RoboPAIR: jailbreaking LLM-controlled robots",
        arxiv="arXiv:2410.13691",
        eai="EAI01",
        attacks=["roleplay"],
        paper_asr="~100% ASR jailbreaking a deployed Unitree Go2 / Jackal (reported)",
        summary="An instruction-level jailbreak reframes the task so the policy executes an "
        "unsafe action it would otherwise refuse.",
        mapping_note="Provael's EAI01 `roleplay` family is a templated instruction jailbreak — "
        "the same threat class as RoboPAIR's optimised prompts, without the search loop.",
    ),
}

#: Alias -> canonical name, so e.g. `reproduce openvla_patch` resolves.
_ALIASES: dict[str, str] = {
    alias: repro.name for repro in REPRODUCTIONS.values() for alias in repro.aliases
}


def available_reproductions() -> list[str]:
    """Canonical names of all built-in reproductions."""
    return list(REPRODUCTIONS)


def get_reproduction(name: str) -> Reproduction:
    """Resolve a reproduction by canonical name or alias.

    Raises:
        KeyError: if ``name`` is neither a known reproduction nor an alias.
    """
    canonical = _ALIASES.get(name, name)
    try:
        return REPRODUCTIONS[canonical]
    except KeyError:
        raise KeyError(
            f"unknown reproduction {name!r}; available: {available_reproductions()}"
        ) from None


__all__ = ["Reproduction", "REPRODUCTIONS", "available_reproductions", "get_reproduction"]
