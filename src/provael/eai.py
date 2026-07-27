"""The Embodied AI Security Top 10 — the catalog Provael's attacks map to.

Each attack family is tagged with the ``EAIxx`` risk it exercises (see
``docs/TOP10.md``). This module is the **single source of truth** for those ids,
their human names, a one-line description, and a stable ``helpUri`` deep-link into
the Top-10 document. Attacks import their tag from here (so the id/name on an
:class:`~provael.attacks.base.Attack` never drifts from the catalog), and the SARIF
exporter builds its ``rules[]`` from the same entries.

**All ten risks are listed, including the two Provael ships no attacks for.** They used to be
omitted: the catalog held eight entries while ``docs/TOP10.md`` defined ten, so EAI07 and EAI10
vanished from every crosswalk, scorecard and compliance report without a word. For a buyer
assembling conformity evidence, "we do not test this, and here is why" is a legitimate answer; a
category that silently disappears is not — it reads as covered. Every entry therefore carries an
explicit :class:`EaiCoverage`, and consumers render all ten.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: Canonical home of the Top-10 document (anchors below are GitHub-rendered slugs).
TOP10_DOC_URL = "https://github.com/provael/provael/blob/main/docs/TOP10.md"


class EaiCoverage(StrEnum):
    """Whether Provael ships attacks for a risk — and, when it does not, *why* not.

    The distinction between the last three matters to a reader deciding whether a gap is a backlog
    item or a deliberate boundary. Collapsing them into one "not covered" state would tell a buyer
    that a governance meta-risk and an unimplemented attack are the same kind of absence.
    """

    #: A runnable attack family exercises this risk today. Cross-checked against
    #: :mod:`provael.attacks.registry` by ``tests/test_eai.py``, not asserted by hand.
    attacks_implemented = "attacks-implemented"
    #: Attackable inside a simulator, but nothing ships yet. A backlog item, not a boundary.
    no_attacks_yet = "no-attacks-yet"
    #: Real coverage would need tooling outside a sim-only policy red-teamer's charter.
    out_of_scope_for_simulation = "out-of-scope-for-simulation"
    #: A process/governance control with no attack surface — Provael is evidence *for* it, not an
    #: attacker *of* it. Never reported as an ASR.
    process_control_not_attackable = "process-control-not-attackable"


@dataclass(frozen=True)
class EaiRisk:
    """One Embodied AI Security Top-10 risk entry."""

    id: str
    name: str
    description: str
    anchor: str  # GitHub heading slug within docs/TOP10.md
    #: Whether attacks ship for this risk. Required — a new entry cannot be added without stating
    #: its coverage, which is exactly what let two categories go missing silently.
    coverage: EaiCoverage
    #: One sentence a buyer can read: what is covered, or what closing a real gap would take.
    coverage_note: str
    #: D5: proposed MITRE ATLAS (https://atlas.mitre.org) tactic → technique mapping(s) for this
    #: risk, promoted from the prose table in ``docs/standards/atlas-case-study.md`` to structured
    #: data. Descriptive tactic→technique phrasing (not invented ``AML.TXXXX`` ids), flagged
    #: ``(proposed)`` where ATLAS's thin embodied coverage has no on-point technique. Routing
    #: external validation through ATLAS avoids any Top-10 branding conflict (INV-6).
    atlas_techniques: tuple[str, ...] = ()

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
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `instruction` family (roleplay / goal_substitution / paraphrase) and the "
            "`optimized_instruction` search. The only family with measured real-policy "
            "transfer."
        ),
        atlas_techniques=("ML Attack Staging → prompt-injection / jailbreak of an "
                          "ML-driven agent",),
    ),
    "EAI02": EaiRisk(
        id="EAI02",
        name="Adversarial perception",
        description=(
            "A perturbation of what the policy sees (patch, decoy, sensor spoof) "
            "redirects its behaviour while the text goal stays benign."
        ),
        anchor="eai02--adversarial-perception-patches--textures--sensor-spoofing",
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `visual`, `sensor_spoof` and `optimized_patch` families, plus the humanoid "
            "balance-spoof. `optimized_patch` needs a real image channel and never scores on a "
            "CPU stub suite."
        ),
        atlas_techniques=("Evasion → adversarial example in the perception channel (craft "
                          "adversarial data)",),
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
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `backdoor` family screens objective-decoupled object and phrase triggers."
        ),
        atlas_techniques=("Persistence → backdoor the ML model; ML Supply Chain Compromise → "
                          "poison an open-weights checkpoint",),
    ),
    "EAI04": EaiRisk(
        id="EAI04",
        name="Action-space integrity",
        description=(
            "An attack on the policy's action output itself — freezing it into a no-op "
            "(availability) or hijacking its trajectory toward an attacker-chosen waypoint."
        ),
        anchor="eai04--action-space-integrity-attacks-hijack--targeted-trajectory--freeze",
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `action`, `action_space` and `optimized` families, plus the humanoid "
            "whole-body hijack and stride freeze."
        ),
        atlas_techniques=("Impact → manipulate / deny the agent's actuation (proposed — ATLAS "
                          "embodied coverage is thin)",),
    ),
    "EAI05": EaiRisk(
        id="EAI05",
        name="Indirect / embodied prompt injection",
        description=(
            "Text the agent ingests from its environment or tools (a sign, a poisoned "
            "tool description) carries an imperative the policy then executes."
        ),
        anchor="eai05--indirect--embodied-prompt-injection",
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `injection` family covers both the scene-text and the MCP tool-description "
            "channel."
        ),
        atlas_techniques=("Execution → indirect prompt injection via the environment",),
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
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `misalignment` family (benign-urgency override, euphemistic reroute) measures "
            "the embodiment gap on a keep-out suite."
        ),
        atlas_techniques=("Impact → unsafe embodied action under a language-benign instruction "
                          "(proposed — the embodiment gap has no on-point ATLAS technique)",),
    ),
    "EAI07": EaiRisk(
        id="EAI07",
        name="CPS, firmware, comms & teleoperation compromise",
        description=(
            "Compromise of the robot's own cyber-physical stack rather than its policy — "
            "firmware, the radio/ROS-DDS control plane, or a teleoperation session — which "
            "reaches the actuators without ever touching the model."
        ),
        anchor="eai07--cps-firmware-comms--teleoperation-compromise",
        coverage=EaiCoverage.out_of_scope_for_simulation,
        coverage_note=(
            "No attacks, by design, and this is a boundary rather than a backlog item. Faithful "
            "coverage means exercising real firmware, real radio / ROS-DDS traffic and real "
            "teleoperation sessions — CVE-class work against physical infrastructure, and "
            "Provael ships no exploit tooling (see SAFETY.md). This layer is assessed with "
            "IEC 62443 and ATT&CK-for-ICS methods and CVE scanning against the robot's own "
            "stack: the UniPwn (CVE-2025-60250/-60251) and Go1 backdoor (CVE-2025-2894) "
            "findings came from that kind of work, not from policy red-teaming. A clean "
            "Provael run says nothing about this risk."
        ),
        # Deliberately empty: ATLAS is an ML-system taxonomy and has no on-point technique for a
        # firmware or radio compromise. Inventing one to fill the column would be exactly the
        # fabrication the ATLAS mapping discipline exists to prevent.
        atlas_techniques=(),
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
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `authorization` family screens self-authorization and scope escalation of an "
            "authorization-gated action."
        ),
        atlas_techniques=("Privilege Escalation → excessive agency / self-authorized guarded "
                          "action (proposed)",),
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
        coverage=EaiCoverage.attacks_implemented,
        coverage_note=(
            "The `confidentiality` family screens a planted memorization canary (membership "
            "inference / extraction) — never a real exfiltration."
        ),
        atlas_techniques=("Exfiltration → model extraction / membership inference via the "
                          "inference interface",),
    ),
    "EAI10": EaiRisk(
        id="EAI10",
        name="Insufficient evaluation, observability & incident response",
        description=(
            "Deploying an embodied policy with no adversarial evaluation, no runtime "
            "observability and no rehearsed incident response — the governance failure that "
            "leaves every other risk on this list undetected in production."
        ),
        anchor="eai10--insufficient-evaluation-observability--incident-response",
        coverage=EaiCoverage.process_control_not_attackable,
        coverage_note=(
            "No attacks, because there is no policy input that attacks the absence of a "
            "process. Provael sits on the mitigation side of this one: a signed run report, "
            "its scorecard, and the per-checkpoint regression gate are partial evidence that "
            "the evaluation control exists and was exercised. Partial is the operative word — "
            "they evidence the evaluation limb, not the observability or incident-response "
            "limbs, which are runtime and organisational. This category never carries an ASR; "
            "a number here would be a category error."
        ),
        # Deliberately empty: ATLAS enumerates adversary techniques, and a missing governance
        # control is not something an adversary does.
        atlas_techniques=(),
    ),
}


#: What an evidence table says for a risk that produced no episodes. An empty row is ambiguous on
#: its own — "nothing measured" can mean the attacks exist and were not selected, or that no attack
#: for this risk exists at all — and those are very different answers to "did you test this?".
#: Shared so the scorecard and the compliance report cannot describe the same state differently.
EMPTY_STATUS: dict[EaiCoverage, str] = {
    EaiCoverage.attacks_implemented: "not exercised by this run",
    EaiCoverage.no_attacks_yet: "no attacks ship yet",
    EaiCoverage.out_of_scope_for_simulation: "out of scope for simulation",
    EaiCoverage.process_control_not_attackable: "process control — not attackable",
}

#: Said when the report itself cannot answer the question. See :func:`status_for`.
UNATTRIBUTABLE_STATUS = "unknown — this report carries no EAI map (schema v1)"


def status_for(coverage: EaiCoverage, *, attempts: int, attributable: bool) -> str:
    """Why a risk's row is empty — or that we cannot say.

    ``attributable`` is False for a **schema v1** report, which predates ``RunReport.eai`` and so
    records no attack → risk mapping. Such a run may well have exercised a risk (the legacy
    insurer fixture ran ``roleplay``, ``patch`` and ``scene_text``, covering EAI01/02/05) while
    attributing nothing, so reporting "not exercised by this run" against it would state a
    falsehood — and, for the attestation path, sign it. An absent measurement and an absent
    *mapping* are different claims and must read differently.

    The judgement only applies to risks Provael attacks at all: EAI07 being out of scope and EAI10
    being a process control are properties of the tool, true of any report, old schema or not.
    """
    if attempts:
        return "measured"
    if not attributable and coverage is EaiCoverage.attacks_implemented:
        return UNATTRIBUTABLE_STATUS
    return EMPTY_STATUS[coverage]


def risk(eai_id: str) -> EaiRisk:
    """Look up a risk by id.

    Raises:
        KeyError: if ``eai_id`` is not in the catalog.
    """
    try:
        return CATALOG[eai_id]
    except KeyError:
        raise KeyError(f"unknown EAI id {eai_id!r}; known: {sorted(CATALOG)}") from None


def all_ids() -> list[str]:
    """Every EAI id, sorted. The canonical enumeration consumers iterate to render all ten."""
    return sorted(CATALOG)


def attacked_ids() -> list[str]:
    """The ids Provael ships attacks for — i.e. the ids an ASR can legitimately exist for.

    Anything outside this set must never appear with a rate: EAI07 is not tested and EAI10 is not
    attackable, so a "0%" against either would read as a clean result rather than as no result.
    """
    return sorted(
        eai_id for eai_id, entry in CATALOG.items()
        if entry.coverage is EaiCoverage.attacks_implemented
    )


def coverage_counts() -> dict[str, int]:
    """How many risks sit in each coverage state — the honest headline behind "N / 10"."""
    counts = {state.value: 0 for state in EaiCoverage}
    for entry in CATALOG.values():
        counts[entry.coverage.value] += 1
    return counts


def coverage_headline() -> str:
    """The one-line coverage claim, generated so a doc can never drift from the catalog.

    ``docs/TOP10.md`` used to hard-code "8 / 10" in prose. It happened to be right, but nothing
    connected the number to the catalog, and the two categories behind the gap were missing from
    the code entirely — so the sentence was accurate by coincidence.
    """
    attacked = attacked_ids()
    return (
        f"Provael attack coverage: {len(attacked)} / {len(CATALOG)}. "
        f"{', '.join(attacked)} ship a runnable, sim-only attack family; "
        + "; ".join(
            f"{eai_id} is {CATALOG[eai_id].coverage.value}"
            for eai_id in all_ids() if eai_id not in attacked
        )
        + "."
    )


__all__ = [
    "TOP10_DOC_URL",
    "EaiCoverage",
    "EaiRisk",
    "CATALOG",
    "EMPTY_STATUS",
    "UNATTRIBUTABLE_STATUS",
    "status_for",
    "risk",
    "all_ids",
    "attacked_ids",
    "coverage_counts",
    "coverage_headline",
]
