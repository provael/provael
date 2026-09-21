# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Compliance-evidence export for a :class:`~provael.types.RunReport` (v0.5.0).

Turns a red-team run into an **auditor-readable evidence artifact** that maps the run's measured
signals (the redirection rate + 95% Wilson CI under the run's predicate — calibrated or the
documented default, and every row says which — the benign-FPR control, the EAI risks exercised, the
per-task calibration metadata where a calibration ran) onto the framework requirements in
``docs/compliance/index.md`` — **EU AI Act** (Reg. (EU) 2024/1689), the **EU Machinery Regulation**
(Reg. (EU) 2023/1230 — the operative route for AI-enabled robots after the 2026 Digital Omnibus),
**ISO 10218-1/-2:2025** (cyber), **NIST AI 100-2 / AI RMF**, and **IEC 62443** — plus the
functional-safety standards an accredited AI-safety inspection programme assesses robot software
against (**IEC 61508**, **ISO 13849-1/-2**, **ISO/IEC TR 5469:2024**) and the in-development
Type-C standard for dynamically stable robots (**ISO 25785-1**), plus the first non-EU national
statute in the catalogue, Korea's **AI Framework Act** (Act No. 20676, in force 22 January 2026),
and the automotive cybersecurity regime a type-approved vehicle with a learned component already
sits inside: **UN Regulation No. 155** (cybersecurity and the CSMS, in force 22 January 2021) and
the engineering standard its audits lean on, **ISO/SAE 21434:2021**.

A boundary that holds across all of those: Provael supplies adversarial-robustness evidence as an
**input** to a functional-safety argument. It computes **no SIL, no Performance Level, and makes no
functional-safety claim** — those are determined from architecture, MTTFd, diagnostic coverage and
CCF by the designer and confirmed by an assessor. An attack-success rate is not one of those inputs.

This is the generator the ``docs/compliance/index.md`` pre-spec described. It is **evidence, not
certification**: each requirement entry carries a ``status`` of ``evidence-present`` or ``gap``
against what *this run* actually produced, never an assertion of legal conformity. Three
honest-scope caveats from the crosswalk travel with every entry (adversarial-only,
evidence-not-certification, behavioural-not-worst-case).

It reuses an existing ``report.json`` — no attacks are re-run — so the whole path is
CPU/stub-runnable in CI. Output is ``sort_keys``-stable, so a deterministic run yields a
byte-identical artifact.

ROWS DESCRIBE THE EVIDENCE PRESENT, since 0.43.0. Three signal strings used to read "calibrated
redirection rate" whatever the run's predicate was, and the Article 15 row showed
``evidence-present`` for the uncalibrated public sample beside a footer saying the run was
uncalibrated. A footer does not correct a row. Each entry now carries ``predicate`` — the state
the rate was actually scored under — the signal strings name the rate without presupposing
calibration, and the release decision (``acceptance``) travels with the report under the protocol
that produced it, or as not assessed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from provael.attacks.registry import FAMILIES
from provael.calibration import describe_calibration, wilson_ci
from provael.eai import CATALOG, EaiCoverage, status_for
from provael.evidence import EvidenceState, evidence_state_of, transfer_status_of
from provael.types import RunReport
from provael.verdict import ReleaseDecision, acceptance_block, release_verdict

COMPLIANCE_JSON = "report.compliance.json"
COMPLIANCE_MD = "report.compliance.md"

#: Independent-project disclaimer carried at the top of every artifact.
DISCLAIMER = (
    "Independent project — not affiliated with or endorsed by ISO, the EU, NIST, IEC, OWASP, or "
    "MITRE. Evidence, not certification. Not legal advice. Provael produces engineering evidence "
    "for the adversarial-robustness and cybersecurity expectations of these frameworks; running "
    "it does not make a system compliant or certified."
)

Status = Literal["evidence-present", "gap"]

#: Attack name -> family (e.g. ``"roleplay" -> "instruction"``), from the registry.
_NAME_TO_FAMILY: dict[str, str] = {
    name: family for family, names in FAMILIES.items() for name in names
}


# --------------------------------------------------------------------------------------------
# Honest-scope caveats (from docs/compliance/index.md "Honest scope"). Attached to every entry
# by id.
# --------------------------------------------------------------------------------------------

CAVEATS: dict[str, str] = {
    "adversarial-only": (
        "Adversarial security only. Functional/mechanical safety (ISO 10218 safety clauses; "
        "ISO 13482:2014, under revision as ISO/DIS 13482 — retitled to service robots; and "
        "ISO/TS 15066:2016, whose power-and-force-limiting requirements are now incorporated into "
        "ISO 10218-1/-2:2025) and non-adversarial reliability are out of scope."
    ),
    "evidence-not-certification": (
        "Evidence, not conformity. EU AI Act / ISO conformity also needs a quality-management "
        "system, technical documentation, human oversight, and logging; Provael covers the "
        "robustness/cybersecurity testing-evidence slice only."
    ),
    "behavioural-not-worst-case": (
        "Behavioural, not worst-case. Attacks are templated/auditable, not gradient/search-"
        "optimised; treat results as a floor on susceptibility, not a certified bound."
    ),
}

#: Every entry carries all three — they apply universally to Provael evidence.
_ENTRY_CAVEATS: tuple[str, ...] = ("adversarial-only", "evidence-not-certification",
                                   "behavioural-not-worst-case")


# --------------------------------------------------------------------------------------------
# Requirement catalog — the crosswalk targets (docs/compliance/index.md). One entry per mapped
# control.
# --------------------------------------------------------------------------------------------

#: The two tiers a mapped framework can sit in, decided on 20 September 2026 when the compliance
#: layer was frozen (docs/roadmap.md, "The freeze"). ``operative`` = the route a machinery
#: assessor actually reads a robot's adversarial-robustness evidence through, and the one this
#: project keeps developing: the Machinery Regulation (the legal instrument), ISO 10218:2025 (the
#: robot type-C standard whose cybersecurity risk assessment that route is written against), and
#: the three implemented safety/security standards an assessor asks for beside them — ISO 13849,
#: IEC 61508, IEC 62443. ``reference`` = every other mapping in this catalogue: kept, emitted,
#: checked, but reference material — no new rows, crosswalks or emitters for them until the three
#: proofs and a paid engagement exist. ISO 12100 and ISO/IEC TS 22440 belong to the operative
#: conversation and are NOT rows here: neither is implemented, and a tier is not a licence to add
#: crosswalks.
TIER_OPERATIVE = "operative"
TIER_REFERENCE = "reference"
OPERATIVE_FRAMEWORKS: frozenset[str] = frozenset(
    {"eu-machinery", "iso-10218", "iso-13849", "iec-61508", "iec-62443"}
)


def framework_tier(framework_id: str) -> str:
    """``operative`` for the assessor-read route, ``reference`` for every other mapping."""
    return TIER_OPERATIVE if framework_id in OPERATIVE_FRAMEWORKS else TIER_REFERENCE


@dataclass(frozen=True)
class Requirement:
    """One framework control Provael evidence maps onto (a crosswalk row)."""

    key: str
    framework: str
    framework_id: str
    control_id: str
    control_title: str
    provael_signal: str
    evidence_refs: tuple[str, ...]
    indicative: bool
    #: EAI families this row's ``provael_signal`` names as its on-point evidence. When set, the row
    #: is a gap unless every listed family actually ran — otherwise a run containing any one tagged
    #: attack marks it evidence-present while asserting a measurement that never happened. Left
    #: empty for rows satisfied by adversarial evidence generally (e.g. the taxonomy mapping, which
    #: maps risks rather than claiming all of them were exercised).
    required_eai: tuple[str, ...] = ()
    #: ``operative`` or ``reference`` — a property of the FRAMEWORK, filled from
    #: :func:`framework_tier` so no row can carry a tier its framework does not. Declared as a
    #: field rather than a property so ``dataclasses.asdict`` (the website's mirror recipe) and the
    #: emitted :class:`ComplianceEntry` carry it.
    tier: str = ""

    def __post_init__(self) -> None:
        if not self.tier:
            object.__setattr__(self, "tier", framework_tier(self.framework_id))
        elif self.tier != framework_tier(self.framework_id):
            raise ValueError(
                f"{self.key}: tier {self.tier!r} disagrees with its framework's "
                f"{framework_tier(self.framework_id)!r}; the tier is decided per framework"
            )


_EU = "EU AI Act (Regulation (EU) 2024/1689)"
_MACHINERY = "EU Machinery Regulation (Regulation (EU) 2023/1230)"
_CRA = "EU Cyber Resilience Act (Regulation (EU) 2024/2847)"
_ISO = "ISO 10218:2025"
_NIST = "NIST AI 100-2 / AI RMF"
_IEC = "IEC 62443"
_ISO_TR_5469 = "ISO/IEC TR 5469:2024"
_ISO_42001 = "ISO/IEC 42001:2023"
_ISO_23894 = "ISO/IEC 23894:2023"
#: The two classical functional-safety standards an accredited AI-safety inspection programme
#: assesses robot software against alongside ISO/IEC TR 5469. Provael is an INPUT to those
#: arguments and computes neither a SIL nor a Performance Level — see the rows' provael_signal.
_IEC_61508 = "IEC 61508"
_ISO_13849 = "ISO 13849"
#: The first Type-C standard for dynamically stable (legged / humanoid) robots — ISO/TC 299 WG 12,
#: still a Committee Draft (ISO/CD, registered 8 May 2026). Named here as anticipatory
#: positioning, never as a conformity claim.
_ISO_25785 = "ISO 25785-1 (under development)"
#: The first enforceable comprehensive AI statute outside the EU, and the first non-EU national
#: statute in this catalogue. In force 22 January 2026 (promulgated 21 January 2025, commencing one
#: year later under its own Addenda Art. 1). Article numbers below are the Act's own, read from the
#: CSET English translation of Law No. 20676; the Enforcement Decree sets the numeric thresholds and
#: is NOT the source of anything asserted here.
#:
#: SCOPE IS SECTORAL, NOT "ANY PHYSICAL MACHINE". Art. 2(4) enumerates the areas that make a system
#: high-impact — energy, drinking water, health care, medical devices, nuclear, biometrics for
#: criminal investigation, employment and loan assessment, transport, public decisions, school
#: assessment. A VLA policy is inside this Act when it is deployed in one of those, not merely
#: because it drives a robot. A general warehouse or factory arm is not enumerated.
_KR_AI = "Korea AI Framework Act (Act No. 20676)"
#: The automotive cybersecurity regime, in force since 22 January 2021 and applied in the EU through
#: Regulation (EU) 2019/2144 Annex II row D4 (refusal of EU type-approval from 6 July 2022;
#: registration prohibited from 7 July 2024). Paragraph numbers below are the Regulation's own, read
#: from its publication in OJ L 82, 9.3.2021 (CELEX 42021X0387). R155 is a TYPE-APPROVAL regime with
#: its own auditor: the Certificate of Compliance for a CSMS is granted by an Approval Authority and
#: is valid for a maximum of three years (para. 6.7). Provael feeds nothing into that grant and
#: determines nothing about it; the rows below are inputs a manufacturer's own processes can hold.
#:
#: SCOPE IS THE TYPE-APPROVED VEHICLE. Para. 1.1 applies the Regulation to categories M and N, to
#: O where fitted with at least one electronic control unit, and to L6 and L7 with automated driving
#: functionalities from level 3 onwards. A warehouse AGV that is machinery rather than a road
#: vehicle is under the Machinery Regulation instead.
_UN_R155 = "UN Regulation No. 155 (cybersecurity and CSMS)"
#: The process standard a CSMS is audited against in practice: ISO/SAE 21434:2021, Edition 1,
#: published August 2021 by ISO/TC 22/SC 32 with SAE, under systematic review (stage 90.20) as of
#: 18 September 2026. Clause titles below are the standard's own, read from its published preview.
#: Clause 11 (Cybersecurity validation) is deliberately NOT mapped: it validates an item at the
#: vehicle level, and a simulation result about one learned component does not reach it.
_ISO_SAE_21434 = "ISO/SAE 21434:2021"

#: Ordered so the artifact (and tests) are deterministic.
REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(
        key="eu-ai-act:art15",
        framework=_EU, framework_id="eu-ai-act",
        control_id="Article 15", control_title="Accuracy, robustness and cybersecurity",
        provael_signal=(
            "Redirection rate + 95% CI per EAI risk under the run's predicate (calibrated or the "
            "documented default — the row says which), with the benign-FPR control; SARIF for the "
            "security review. For MACHINERY this article is the measurement anchor, not the "
            "instrument: since Regulation (EU) 2026/1744 the Machinery Regulation sits in AI Act "
            "Annex I Section B, and Art. 15's requirements reach a robot through Machinery "
            "Regulation Annex III by delegated act (Art. 8, third paragraph, applying by "
            "2028-08-02) — see the eu-machinery rows"
        ),
        evidence_refs=("report.json", "report.json#/by_attack", "report.sarif"),
        indicative=False,
    ),
    Requirement(
        key="eu-ai-act:art9",
        framework=_EU, framework_id="eu-ai-act",
        control_id="Article 9", control_title="Risk-management system",
        provael_signal="EAI risk taxonomy as the threat catalogue + a measured rate per risk",
        evidence_refs=("report.json#/eai", "docs/top10.md"),
        indicative=True,
    ),
    Requirement(
        key="eu-ai-act:art72",
        framework=_EU, framework_id="eu-ai-act",
        control_id="Article 72", control_title="Post-market monitoring",
        provael_signal=(
            "Re-run per model/checkpoint update; redirection rate tracked over time (leaderboard)"
        ),
        evidence_refs=("leaderboard/results/leaderboard.json", "report.json#/tool_version"),
        indicative=True,
    ),
    Requirement(
        key="eu-machinery:cyber",
        framework=_MACHINERY, framework_id="eu-machinery",
        control_id="Reg. (EU) 2023/1230 (applies 2027-01-20); Annex III 1.1.9 and 1.2.1",
        control_title="Machinery — protection against corruption / safety-function AI",
        provael_signal=(
            "Measured redirection rate per EAI risk as input to the mandatory cyber-risk "
            "assessment for AI-enabled machinery, with action-space integrity (EAI04: keep-out "
            "hijack / critical-step freeze of the commanded motion) as the on-point evidence for "
            "the corruption-of-safety-function essential requirement (Annex III 1.1.9; control "
            "systems 1.2.1); SARIF for the security file. The AI-specific requirements the Digital "
            "Omnibus routes to machinery (Reg. (EU) 2026/1744 -> Art. 8, third paragraph, "
            "delegated acts applying by 2028-08-02, reflecting AI Act Art. 15) land in this same "
            "Annex; until then Art. 20(10) presumes conformity through the AI Act's harmonised "
            "standards"
        ),
        evidence_refs=("report.json#/by_attack", "report.sarif", "docs/compliance/index.md"),
        indicative=True,
        required_eai=("EAI04",),
    ),
    Requirement(
        key="eu-machinery:annex-i-part-a",
        framework=_MACHINERY, framework_id="eu-machinery",
        control_id="Article 25(2) via Article 6(1); Annex I Part A, point 5",
        control_title="Annex I Part A — third-party conformity assessment of ML self-evolving-"
        "behaviour safety components",
        provael_signal=(
            "Per-family adversarial evidence (ASR + 95% Wilson CI + anytime-valid CI + benign-FPR "
            "control + Succ-But-Unsafe + BH-FDR across families) with the honest per-family "
            "real-policy transfer statement — the adversarial-robustness input a notified body "
            "reviews for an ML safety component routed to a third-party conformity assessment "
            "under Article 25(2). Annex I Part A point 5 verified verbatim against CELEX "
            "32023R1230 (2026-08-01): 'Safety components with fully or partially self-evolving "
            "behaviour using machine learning approaches ensuring safety functions'; point 6 "
            "covers the embedded-system variant, and Part B point 19 is the Article 25(3) sibling "
            "— do not substitute it"
        ),
        evidence_refs=(
            "dossier.json", "dossier.oscal.json", "report.json#/by_attack", "attestation.json",
        ),
        indicative=True,
    ),
    Requirement(
        key="eu-machinery:annex-i-part-a-6",
        framework=_MACHINERY, framework_id="eu-machinery",
        control_id="Article 25(2) via Article 6(1); Annex I Part A, point 6",
        control_title="Annex I Part A — third-party conformity assessment of machinery with an "
        "embedded ML self-evolving-behaviour safety system",
        provael_signal=(
            "The same per-family adversarial evidence as point 5, filed for the EMBEDDED case. "
            "Point 5 lists the safety component placed on the market on its own; point 6 verbatim "
            "against CELEX 32023R1230 (2026-08-01) covers 'Machinery having embedded systems with "
            "fully or partially self-evolving behaviour using machine learning approaches ensuring "
            "safety functions'. An integrator shipping a whole robot — a humanoid, an AMR — is "
            "placing machinery with an embedded ML safety system on the market, not a standalone "
            "component, so this is the point its file is routed under. Both land on the Article "
            "25(2) third-party route via Article 6(1); Part B point 19 is the Article 25(3) "
            "sibling and is NOT interchangeable with either"
        ),
        evidence_refs=(
            "dossier.json", "dossier.oscal.json", "report.json#/by_attack", "attestation.json",
        ),
        indicative=True,
    ),
    Requirement(
        key="iso-10218-1:cyber",
        framework=_ISO, framework_id="iso-10218",
        control_id="ISO 10218-1:2025",
        control_title="Robots & robotic devices — Safety — Part 1 (cybersecurity requirements)",
        provael_signal=(
            "Measured redirection rate per EAI risk as cyber-risk-assessment input, with "
            "action-space integrity (EAI04: keepout_hijack / critical_freeze) as the on-point "
            "evidence for the monitored-stop / space-limiting safety functions"
        ),
        evidence_refs=("report.json#/by_attack", "docs/compliance/index.md"),
        indicative=True,
        required_eai=("EAI04",),
    ),
    Requirement(
        key="iso-10218-2:cyber",
        framework=_ISO, framework_id="iso-10218",
        control_id="ISO 10218-2:2025",
        control_title="Robot applications & cells — Part 2 (cybersecurity requirements)",
        provael_signal="Measured redirection rate per EAI risk as cyber-risk-assessment input",
        evidence_refs=("report.json#/by_attack", "docs/compliance/index.md"),
        indicative=True,
    ),
    Requirement(
        key="nist-ai-100-2:taxonomy",
        framework=_NIST, framework_id="nist",
        control_id="NIST AI 100-2e2025",
        control_title="Adversarial ML taxonomy",
        provael_signal=(
            "EAI01/02/04/05 mapped to the adversarial-ML taxonomy (evasion / abuse / indirect "
            "injection / action-integrity violation)"
        ),
        evidence_refs=(
            "report.json#/eai",
            "docs/top10.md#cross-framework-crosswalk-corrected-verbatim-source-items",
        ),
        indicative=False,
    ),
    Requirement(
        key="nist-ai-100-2:privacy",
        framework=_NIST, framework_id="nist",
        control_id="NIST AI 100-2e2025 (Privacy)",
        control_title="Privacy attacks — model extraction / membership inference (NISTAML.03)",
        provael_signal=(
            "Measured confidentiality-leak rate + 95% CI for the EAI09 family "
            "(membership inference / extraction) as evidence for the privacy-attack pillar; "
            "also MITRE ATLAS Exfiltration"
        ),
        evidence_refs=("report.json#/by_attack", "report.json#/eai"),
        indicative=False,
        required_eai=("EAI09",),
    ),
    Requirement(
        key="nist-ai-rmf:measure",
        framework=_NIST, framework_id="nist",
        control_id="AI RMF — MEASURE",
        control_title="Measure identified risks",
        provael_signal=(
            "Redirection rate + 95% CI + benign FPR under a CALIBRATED predicate — a measured, "
            "controlled metric; a gap under the default predicate"
        ),
        evidence_refs=(
            "report.json#/calibration", "report.json#/benign_fpr", "report.json#/by_attack",
        ),
        indicative=False,
    ),
    Requirement(
        key="nist-ai-rmf:govern-map",
        framework=_NIST, framework_id="nist",
        control_id="AI RMF — GOVERN / MAP",
        control_title="Govern & map the risk context",
        provael_signal="Red-team process + EAI taxonomy as the mapped risk context",
        evidence_refs=("report.json#/eai", "docs/top10.md"),
        indicative=False,
    ),
    Requirement(
        key="nist-ai-rmf:manage",
        framework=_NIST, framework_id="nist",
        control_id="AI RMF — MANAGE",
        control_title="Manage risks (eval/observability + remediation)",
        provael_signal="Eval/observability gaps (EAI10) + remediation tracking",
        evidence_refs=("report.json#/calibration",),
        indicative=False,
    ),
    Requirement(
        key="iec-62443:slv",
        framework=_IEC, framework_id="iec-62443",
        control_id="IEC 62443",
        control_title="Security for industrial automation & control systems",
        provael_signal=(
            "Measured redirection rate per EAI as control-system security input; "
            "security-level verification"
        ),
        evidence_refs=("report.json#/by_attack", "docs/compliance/index.md"),
        indicative=True,
    ),
    Requirement(
        key="iec-61508:systematic-capability",
        framework=_IEC_61508, framework_id="iec-61508",
        control_id="IEC 61508 (E/E/PE functional safety)",
        control_title="Functional safety of electrical / electronic / programmable electronic "
        "safety-related systems — systematic-capability argument",
        provael_signal=(
            "Adversarial-robustness evidence for the action channel (EAI04: keep-out hijack / "
            "critical-step freeze of the commanded motion) with its ASR, 95% Wilson CI and "
            "benign-FPR control, plus the mitigation report where a defence was applied. This is "
            "an INPUT to the systematic-capability argument for an ML element used in or alongside "
            "a safety function — a record of how the element behaved under adversarial input, "
            "which the argument must account for. **Provael computes no SIL, no Performance Level, "
            "and makes no functional-safety claim.** Determining systematic capability, and "
            "everything in the IEC 61508 lifecycle around it, is the assessor's work, not this "
            "tool's. Named here because an accredited AI-safety inspection programme assesses "
            "robot software against IEC 61508 alongside ISO/IEC TR 5469 (see "
            "docs/crosswalk/halos-integrator.md)"
        ),
        evidence_refs=(
            "report.json#/by_attack", "report.mitigation.json", "attestation.json",
        ),
        indicative=True,
        required_eai=("EAI04",),
    ),
    Requirement(
        key="iso-13849:pl-validation",
        framework=_ISO_13849, framework_id="iso-13849",
        control_id="ISO 13849-1/-2 (safety-related parts of control systems)",
        control_title="Safety-related parts of control systems — design (Part 1) and validation "
        "(Part 2)",
        provael_signal=(
            "The same EAI04 action-channel evidence, filed against the Part 2 validation activity: "
            "adversarial episodes are fault cases the validation plan can cite for the "
            "safety-related control function, each with its ASR, 95% Wilson CI and benign-FPR "
            "control. This is an INPUT to the validation argument. **Provael computes no "
            "Performance Level (PL), no PLr, no SIL, no MTTFd, no diagnostic coverage, and makes "
            "no functional-safety claim.** A PL is determined from architecture, MTTFd, DC and CCF "
            "by the designer and confirmed by validation; an attack-success rate is none of those "
            "inputs and must never be presented as one"
        ),
        evidence_refs=(
            "report.json#/by_attack", "report.json#/benign_fpr",
            "dossier.json#/adversarial_evidence/per_family",
        ),
        indicative=True,
        required_eai=("EAI04",),
    ),
    Requirement(
        key="iso-25785-1:dynamically-stable",
        framework=_ISO_25785, framework_id="iso-25785",
        control_id="ISO 25785-1 (Committee Draft — not yet published)",
        control_title="Industrial mobile robots — dynamically stable robots",
        provael_signal=(
            "The humanoid family — `balance_spoof` (EAI02), `whole_body_hijack` (EAI04) and "
            "`stride_freeze` (EAI04) — measured on the whole-body / locomotion suite, whose unsafe "
            "predicate is a fall, a centre-of-mass excursion outside the support polygon, a "
            "self-collision, or a footstep keep-out breach: the balance-and-fall hazards a "
            "dynamically stable robot has and a statically stable one does not. **ISO 25785-1 is "
            "an ISO/TC 299 WG 12 Committee Draft (ISO/CD) and is NOT PUBLISHED**, so this row is "
            "anticipatory "
            "positioning — a statement that the evidence exists ahead of the standard — and is "
            "explicitly NOT a conformity claim against a text that does not yet exist; no clause "
            "is cited because there is no stable clause to cite. The humanoid suite is "
            "**stub-validated, with no real-model transfer claimed**: the GR00T-N1 study is "
            "pre-registered and unrun (docs/studies/humanoid-locomotion-transfer.md)"
        ),
        evidence_refs=(
            "dossier.json#/adversarial_evidence/per_family", "dossier.json",
        ),
        indicative=True,
        required_eai=("EAI04",),
    ),
    Requirement(
        key="eu-cra:cyber",
        framework=_CRA, framework_id="eu-cra",
        control_id="Reg. (EU) 2024/2847, Annex I (reporting 2026-09-11; main 2027-12-11)",
        control_title="Products with digital elements — essential cybersecurity requirements",
        provael_signal=(
            "Measured redirection rate per EAI risk as adversarial-robustness testing evidence for "
            "the essential cybersecurity requirements of an AI-enabled product with digital "
            "elements; SARIF for the security file"
        ),
        evidence_refs=("report.json#/by_attack", "report.sarif"),
        indicative=True,
    ),
    Requirement(
        key="iso-iec-tr-5469:ai-safety",
        framework=_ISO_TR_5469, framework_id="iso-iec-tr-5469",
        control_id="ISO/IEC TR 5469:2024",
        control_title="AI — Functional safety and AI systems (verification & validation evidence)",
        provael_signal=(
            "Adversarial-robustness ASR + benign-FPR control as V&V evidence for an AI element "
            "used in or alongside a safety function (the report is one input to the AI-safety "
            "lifecycle)"
        ),
        evidence_refs=("report.json#/by_attack", "report.json#/benign_fpr"),
        indicative=True,
    ),
    Requirement(
        key="iso-42001:aims",
        framework=_ISO_42001, framework_id="iso-42001",
        control_id="ISO/IEC 42001:2023, Annex A (AI operation & risk treatment)",
        control_title="AI management system — red-teaming as an operational control",
        provael_signal=(
            "The red-team run + its signed attestation as evidence of an operational AI risk-"
            "treatment control (adversarial testing pre-deployment), not a management-system audit"
        ),
        evidence_refs=("report.json", "attestation.json"),
        indicative=True,
    ),
    Requirement(
        key="iso-23894:ai-risk",
        framework=_ISO_23894, framework_id="iso-23894",
        control_id="ISO/IEC 23894:2023 (AI risk management)",
        control_title="AI risk management — risk identification & assessment input",
        provael_signal=(
            "The EAI taxonomy as the mapped AI-risk context and the measured rate per risk as "
            "risk-assessment input to the AI risk-management process"
        ),
        evidence_refs=("report.json#/eai", "docs/top10.md"),
        indicative=True,
    ),
    # Korea, Art. 34(1) — the duties on an operator "providing high-impact AI or AI-based products
    # and services". Only the three subparagraphs a red-team result actually speaks to are mapped.
    # Art. 34(1)2 (explainability), 34(1)3 (user protection) and 34(1)6 (Committee-resolved matters)
    # are deliberately absent: Provael produces nothing on-point for them, and a row per
    # subparagraph would read as coverage of the whole Article.
    Requirement(
        key="korea-ai-framework:art34-risk-management",
        framework=_KR_AI, framework_id="korea-ai-framework",
        control_id="Article 34(1)1",
        control_title="Establishment and operation of a risk management plan",
        provael_signal=(
            "The EAI risk taxonomy as the threat catalogue for a high-impact system, with the "
            "redirection rate + 95% CI per risk under the run's predicate and the benign-FPR "
            "control as the adversarial input to the operator's risk-management plan"
        ),
        evidence_refs=("report.json#/eai", "docs/top10.md"),
        indicative=True,
    ),
    Requirement(
        key="korea-ai-framework:art34-human-supervision",
        framework=_KR_AI, framework_id="korea-ai-framework",
        control_id="Article 34(1)4",
        control_title="Human management and supervision of high-impact AI",
        provael_signal=(
            "Measured policy behaviour under adversarial instruction and observation, with "
            "action-space integrity (EAI04) as the on-point evidence, showing WHAT a human "
            "supervisor has to catch. It is not evidence of the supervisory arrangement itself, "
            "and not of any stop, interruption or rollback mechanism: those are system-design "
            "duties over the deployed system, and Provael exercises the policy, not the stop"
        ),
        evidence_refs=("report.json#/by_attack", "report.sarif"),
        indicative=True,
        required_eai=("EAI04",),
    ),
    Requirement(
        key="korea-ai-framework:art34-documentation",
        framework=_KR_AI, framework_id="korea-ai-framework",
        control_id="Article 34(1)5",
        control_title=(
            "Preparation and storage of documents that demonstrate measures taken to ensure AI "
            "safety and reliability"
        ),
        provael_signal=(
            "report.json bound to its execution manifest by digest, plus the SARIF run, as one "
            "such document for the adversarial-robustness measure and nothing wider. The "
            "retention period, the rest of the document set and the storage duty are the "
            "operator's"
        ),
        evidence_refs=("report.json", "report.json#/calibration", "report.sarif"),
        indicative=True,
    ),
    # UN R155 — the three places a red-team result actually lands. Para. 7.2.2.2 lists the CSMS
    # processes the manufacturer must demonstrate; (e) is the testing process, and a repeatable,
    # seeded run with its ledger and execution manifest is one record such a process produces.
    # Paras. 7.3.3 and 7.3.6 are the vehicle-type duties: the exhaustive risk assessment against
    # Annex 5 Part A, and the testing that verifies the mitigations before approval. Not mapped:
    # 7.3.4 (implementing mitigations), 7.3.7 (detection and forensics on the vehicle), 7.3.8
    # (cryptography) — Provael produces nothing on-point for them, and a row per paragraph would
    # read as coverage of the whole specification.
    Requirement(
        key="un-r155:csms-testing-process",
        framework=_UN_R155, framework_id="un-r155",
        control_id="Para. 7.2.2.2(e)",
        control_title="The processes used for testing the cybersecurity of a vehicle type",
        provael_signal=(
            "A seeded, resumable red-team run whose report is bound to its execution manifest by "
            "digest, with the attack catalogue and the benign control it was run against, as one "
            "record a CSMS testing process can show an Approval Authority. It is a record of one "
            "test on the learned component in simulation, not the process itself"
        ),
        evidence_refs=("report.json", "execution-manifest.json", "report.sarif"),
        indicative=True,
    ),
    Requirement(
        key="un-r155:risk-assessment",
        framework=_UN_R155, framework_id="un-r155",
        control_id="Para. 7.3.3",
        control_title=(
            "Exhaustive risk assessment for the vehicle type, considering the threats in Annex 5, "
            "Part A"
        ),
        provael_signal=(
            "For the learned policy's rows of that assessment: the EAI taxonomy as the threat list "
            "beside Annex 5 Part A, and a measured redirection rate per risk with its 95% Wilson "
            "interval and benign-FPR control as the likelihood column. Annex 5 lists manipulation "
            "of vehicle parameters (threat 25) and malicious messages (threat 11); a learned "
            "policy that changes behaviour under a reworded instruction is a threat the table does "
            "not yet name, which is why the rate has to be measured rather than looked up"
        ),
        evidence_refs=("report.json#/eai", "report.json#/by_attack", "docs/top10.md"),
        indicative=True,
    ),
    Requirement(
        key="un-r155:testing-before-approval",
        framework=_UN_R155, framework_id="un-r155",
        control_id="Para. 7.3.6",
        control_title=(
            "Appropriate and sufficient testing to verify the effectiveness of the security "
            "measures implemented"
        ),
        provael_signal=(
            "An attack-success rate for the learned component under adversarial instruction and "
            "perception, with its benign control and interval, as one test in the set the "
            "manufacturer assembles before approval. Simulation only, on the policy alone: whether "
            "the set is appropriate and sufficient is the Approval Authority's judgement, and a "
            "single simulated rate does not settle it"
        ),
        evidence_refs=("report.json#/by_attack", "report.sarif"),
        indicative=True,
    ),
    # ISO/SAE 21434 — the two clauses a component-level, simulated measurement can feed. Clause 15
    # is the TARA method set, where the attack-feasibility and impact judgements live; Clause 10
    # is product development, where cybersecurity requirements are implemented and verified.
    # Clause 11 (validation at the vehicle level) is left out on purpose; see _ISO_SAE_21434.
    Requirement(
        key="iso-sae-21434:tara",
        framework=_ISO_SAE_21434, framework_id="iso-sae-21434",
        control_id="Clause 15",
        control_title="Threat analysis and risk assessment methods",
        provael_signal=(
            "A measured attack-success rate with a denominator, per risk, as the "
            "attack-feasibility and impact evidence for the learned component's threat "
            "scenarios, in place of a "
            "qualitative likelihood. The threat scenarios, the risk values and their treatment "
            "remain the analyst's; Provael supplies the measurement, not the assessment"
        ),
        evidence_refs=("report.json#/eai", "report.json#/by_attack", "docs/top10.md"),
        indicative=True,
    ),
    Requirement(
        key="iso-sae-21434:product-development-verification",
        framework=_ISO_SAE_21434, framework_id="iso-sae-21434",
        control_id="Clause 10",
        control_title="Product development",
        provael_signal=(
            "Verification evidence for a cybersecurity requirement placed on the learned "
            "component, such as a bound on redirection under adversarial instruction: the rate, "
            "its interval, its benign control and the reproducible trace behind each finding, "
            "re-run in CI on every retrain. Component-level and in simulation; it does not reach "
            "the vehicle-level validation of Clause 11"
        ),
        evidence_refs=("report.json#/by_attack", "report.sarif", "report.json#/results"),
        indicative=True,
    ),
)


# --------------------------------------------------------------------------------------------
# Output models.
# --------------------------------------------------------------------------------------------

class EaiBreakdown(BaseModel):
    """Evidence for one EAI risk, aggregated across the attacks that exercise it.

    Emitted for **all ten** risks, including those with ``attempts == 0``. A conformity reader is
    reconciling this table against a clause list, so a risk that is simply absent reads as one
    with nothing to report — ``coverage`` and ``status`` say which kind of nothing it is.
    """

    eai_id: str
    name: str
    attempts: int
    successes: int
    redirection_rate: float
    ci95: tuple[float, float]
    coverage: str = Field(
        EaiCoverage.attacks_implemented.value,
        description="Whether Provael ships attacks for this risk (provael.eai.EaiCoverage).",
    )
    status: str = Field(
        "measured",
        description="Why this row is empty when it is: not exercised, or not testable at all.",
    )
    coverage_note: str = Field(
        "", description="One sentence: what is covered, or what closing the gap would take."
    )

    @property
    def measured(self) -> bool:
        """Whether this row carries a real rate. ``redirection_rate`` is 0.0 at zero attempts."""
        return self.attempts > 0


class EvidenceResult(BaseModel):
    """The measured signals from the run, shared by every requirement entry as its evidence."""

    redirection_rate: float | None = Field(
        ..., description="Adversarial ASR under the run's predicate (None if nothing ran)."
    )
    ci95: tuple[float, float] | None = Field(..., description="95% Wilson CI on the overall rate.")
    benign_fpr: float | None = Field(
        ..., description="Benign baseline FPR (the 'none' control) — None if no baseline ran."
    )
    clean_task_success_rate: float | None = Field(
        None,
        description="Clean-task-success control: benign unattacked task-completion rate — the "
        "competence control the ASR is read against. None if no benign task-success signal.",
    )
    n: int = Field(..., description="Total attempts the rate is over.")
    calibrated: bool
    target_fpr: float | None = Field(
        ..., description="Benign-FPR target the calibration aimed for (None if uncalibrated)."
    )
    transfer_status: str = Field(
        ...,
        description="D1 honesty tier: 'measured-real-transfer' (real policy x real suite) or "
        "'stub-validated-scaffolding' (the deterministic CPU stub). Run-level — the same signed "
        "vocabulary the attestation carries — so an auditor cannot misread stub evidence as "
        "conformity-relevant. Per-attack nuance (e.g. the optimized family) lives in the "
        "attestation's `transfer` list, which this run-level summary does not override.",
    )
    evidence_state: str = Field(
        EvidenceState.LEGACY_UNVERIFIED.value,
        description="Evidence-ladder state (provael.evidence.EvidenceState) — the finer-grained "
        "successor to transfer_status: 'stub' / 'real-episode' for a fresh run, else "
        "'legacy-unverified'. Never 'measured-real-policy-effect' or higher without "
        "the bound evidence those rungs require.",
    )
    eai_ids_covered: list[str]
    attack_families: list[str]
    by_eai: list[EaiBreakdown]


class ScopeCaveat(BaseModel):
    """One honest-scope caveat (id + full text)."""

    id: str
    text: str


class ComplianceEntry(BaseModel):
    """One mapped requirement, with its status and the caveats that qualify it."""

    key: str = Field(..., description="Stable machine id for this control, e.g. 'eu-ai-act:art15'.")
    framework: str
    framework_id: str
    control_id: str
    control_title: str
    provael_signal: str
    status: Status
    gap_reason: str | None = Field(
        None, description="Why this requirement is a gap for this run (None if evidence-present)."
    )
    indicative: bool = Field(
        ..., description="True where the precise sub-clause depends on the full standard text."
    )
    evidence_refs: list[str]
    caveats: list[str] = Field(..., description="Honest-scope caveat ids (see scope_caveats).")
    predicate: str = Field(
        "default (uncalibrated)",
        description="The predicate the rate behind this row was scored under: 'calibrated' or "
        "'default (uncalibrated)'. Carried per row so no row can describe evidence the run did not "
        "produce.",
    )
    tier: str = Field(
        TIER_REFERENCE,
        description="'operative' — the Machinery Regulation route and the three implemented "
        "safety/security standards an assessor reads beside it (ISO 13849, IEC 61508, IEC 62443) "
        "— or 'reference' for every other mapping, kept and checked but not developed further "
        "(the 20 September 2026 freeze).",
    )


class Acceptance(BaseModel):
    """The release decision this report was produced under — the same one every emitter renders."""

    verdict: str
    assessed: bool = Field(
        False, description="False when no acceptance protocol was named: nothing was decided."
    )
    protocol: str | None = None
    protocol_digest: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ComplianceReport(BaseModel):
    """An auditor-readable evidence map from a Provael run to framework requirements."""

    tool_version: str
    generated_from: str = Field(
        "report.json", description="The artifact this evidence was derived from."
    )
    policy: str
    suite: str
    calibrated: bool
    predicate: str = Field(
        "default (uncalibrated)", description="'calibrated' or 'default (uncalibrated)'."
    )
    acceptance: Acceptance = Field(
        default_factory=lambda: Acceptance(verdict="incomplete"),
        description="The release decision under a named protocol, or not assessed.",
    )
    disclaimer: str
    scope_caveats: list[ScopeCaveat]
    result: EvidenceResult
    summary: dict[str, int] = Field(
        ..., description="Counts of entries by status (evidence-present / gap)."
    )
    entries: list[ComplianceEntry]


# --------------------------------------------------------------------------------------------
# Builders.
# --------------------------------------------------------------------------------------------

def _by_eai(report: RunReport) -> list[EaiBreakdown]:
    """Per-EAI-risk evidence rows for **all ten** risks, sorted by id.

    Rows used to be emitted only for the risks a run happened to exercise, so EAI07 and EAI10 —
    absent from the catalog entirely — could never appear, and a risk Provael does not test looked
    identical to one it never got around to. Both now appear with an explicit status.
    """
    buckets: dict[str, tuple[int, int]] = {}  # eai_id -> (attempts, successes)
    for attack, tag in report.eai.items():
        stat = report.by_attack.get(attack)
        if stat is None:
            continue
        att, suc = buckets.get(tag.id, (0, 0))
        buckets[tag.id] = (att + stat.attempts, suc + stat.successes)

    attributable = bool(report.eai)
    rows: list[EaiBreakdown] = []
    for eai_id in sorted(set(CATALOG) | set(buckets)):
        attempts, successes = buckets.get(eai_id, (0, 0))
        rate = successes / attempts if attempts else 0.0
        risk = CATALOG.get(eai_id)
        if risk is None:
            status = "measured" if attempts else "not in the catalog"
        else:
            status = status_for(risk.coverage, attempts=attempts, attributable=attributable)
        rows.append(
            EaiBreakdown(
                eai_id=eai_id,
                name=risk.name if risk is not None else eai_id,
                attempts=attempts,
                successes=successes,
                redirection_rate=rate,
                ci95=wilson_ci(successes, attempts),
                coverage=risk.coverage.value if risk is not None else "unknown",
                status=status,
                coverage_note=risk.coverage_note if risk is not None else "",
            )
        )
    return rows


def _target_fpr(report: RunReport) -> float | None:
    """The single benign-FPR target the run calibrated to, or None (uncalibrated / mixed)."""
    targets = {
        meta.target_fpr for meta in report.calibration.values() if meta.target_fpr is not None
    }
    return next(iter(targets)) if len(targets) == 1 else None


def _evidence(report: RunReport) -> EvidenceResult:
    """Collect the run's measured signals into the shared evidence block."""
    eai_ids = sorted({tag.id for tag in report.eai.values()})
    families = sorted({_NAME_TO_FAMILY[a] for a in report.attacks if a in _NAME_TO_FAMILY})
    # Headline evidence is the ADVERSARIAL ASR (the benign control excluded by role), so an auditor
    # reads the same rate the report headline does — never the all-episode figure that folds the
    # benign 'none' control into the denominator. Legacy reports are recomputed from `results`.
    adv_rate, adv_successes, adv_attempts = report.adversarial_headline()
    has_adv = adv_attempts > 0
    # D1/Phase-2: the transfer status is derived from the evidence ladder via the ONE shared helper
    # (evidence.transfer_status_of), not re-inferred from policy/suite names here.
    return EvidenceResult(
        redirection_rate=adv_rate if has_adv else None,
        ci95=wilson_ci(adv_successes, adv_attempts) if has_adv else None,
        benign_fpr=report.benign_fpr,
        clean_task_success_rate=report.clean_task_success_rate,
        n=adv_attempts,
        calibrated=report.calibrated,
        target_fpr=_target_fpr(report),
        transfer_status=transfer_status_of(report),
        evidence_state=evidence_state_of(report).value,
        eai_ids_covered=eai_ids,
        attack_families=families,
        by_eai=_by_eai(report),
    )


def _status(req: Requirement, ev: EvidenceResult) -> tuple[Status, str | None]:
    """Decide whether the run carries evidence for a requirement, and why not when it doesn't.

    Gap rules (deterministic, so they're testable):

    * ``art72`` / ``manage`` — always a gap from a single run: post-market monitoring is
      longitudinal, and the observability risk (EAI10) isn't exercised by the shipping attacks.
    * ``measure`` — a gap unless the run is calibrated *and* has a benign-FPR control (MEASURE
      asks for a controlled metric, not a bare rate).
    * ``art15`` — a gap without a benign baseline control, or with no EAI-tagged attacks.
    * any row declaring :attr:`Requirement.required_eai` — a gap unless every family it names as
      its on-point evidence actually ran. Without this, ANY tagged attack satisfied ANY row, so a
      ``none,roleplay`` run signed an attestation asserting a measured EAI09 confidentiality-leak
      rate and EAI04 keep-out evidence that no episode produced.
    * everything else — present once any EAI-tagged adversarial attack ran.
    """
    key = req.key
    has_eai = bool(ev.eai_ids_covered)
    has_control = ev.benign_fpr is not None

    if key == "eu-ai-act:art72":
        return "gap", (
            "Post-market monitoring is longitudinal — evidence it by re-running on each "
            "model/checkpoint update and tracking the redirection rate over time (leaderboard), "
            "not from a single run."
        )
    if key == "nist-ai-rmf:manage":
        return "gap", (
            "The eval/observability risk (EAI10) and remediation tracking are not exercised by "
            "the shipping attack families — manage them outside this run."
        )
    if key == "nist-ai-rmf:measure":
        if ev.calibrated and has_control:
            return "evidence-present", None
        return "gap", (
            "MEASURE needs a calibrated predicate with a benign-FPR control — run "
            "`provael calibrate` then `provael attack --calib …` (include the `none` baseline)."
        )
    if key == "eu-ai-act:art15":
        if has_eai and has_control:
            return "evidence-present", None
        if not has_control:
            return "gap", "No benign baseline control in this run — add the `none` attack."
        return "gap", "No EAI-tagged adversarial families were run."

    # Checked before `required_eai` so a run with NO adversarial evidence at all keeps the general
    # reason: naming one missing family there would imply the others ran.
    if not has_eai:
        return "gap", "No EAI-tagged adversarial attacks were run."

    missing = [eai for eai in req.required_eai if eai not in ev.eai_ids_covered]
    if missing:
        return "gap", (
            f"This row's on-point evidence is the {'/'.join(missing)} family, which did not run "
            "in this run — add its attacks and re-run before citing this control."
        )

    return "evidence-present", None


def _predicate_label(report: RunReport) -> str:
    return "calibrated" if report.calibrated else "default (uncalibrated)"


def _entry(req: Requirement, ev: EvidenceResult, predicate: str) -> ComplianceEntry:
    status, gap_reason = _status(req, ev)
    return ComplianceEntry(
        key=req.key,
        framework=req.framework,
        framework_id=req.framework_id,
        control_id=req.control_id,
        control_title=req.control_title,
        provael_signal=req.provael_signal,
        status=status,
        gap_reason=gap_reason,
        indicative=req.indicative,
        evidence_refs=list(req.evidence_refs),
        caveats=list(_ENTRY_CAVEATS),
        predicate=predicate,
        tier=req.tier,
    )


def to_compliance(
    report: RunReport, decision: ReleaseDecision | None = None
) -> ComplianceReport:
    """Build a :class:`ComplianceReport` from a run report (no attacks are re-run).

    ``decision`` is the release decision the caller made (under a named protocol, or not
    assessed); derived here only when none is passed, so this artifact cannot disagree with the
    report, the SARIF or the manifest of the same run.
    """
    ev = _evidence(report)
    predicate = _predicate_label(report)
    entries = [_entry(req, ev, predicate) for req in REQUIREMENTS]
    summary = {"evidence-present": 0, "gap": 0}
    for entry in entries:
        summary[entry.status] += 1
    decision = decision if decision is not None else release_verdict(report)
    return ComplianceReport(
        tool_version=report.tool_version,
        generated_from="report.json",
        policy=report.policy,
        suite=report.suite,
        calibrated=report.calibrated,
        predicate=predicate,
        acceptance=Acceptance(**acceptance_block(decision)),
        disclaimer=DISCLAIMER,
        scope_caveats=[ScopeCaveat(id=cid, text=CAVEATS[cid]) for cid in _ENTRY_CAVEATS],
        result=ev,
        summary=summary,
        entries=entries,
    )


def to_compliance_dict(
    report: RunReport, decision: ReleaseDecision | None = None
) -> dict[str, object]:
    """The compliance report as a JSON-safe dict (keys sorted for stability)."""
    data: dict[str, object] = json.loads(to_compliance(report, decision).model_dump_json())
    return data


def to_compliance_json(report: RunReport, decision: ReleaseDecision | None = None) -> str:
    """Serialise the compliance report to stable, indented JSON (no trailing newline)."""
    return json.dumps(to_compliance_dict(report, decision), indent=2, sort_keys=True)


# --------------------------------------------------------------------------------------------
# Markdown rendering (the version a buyer / auditor reads).
# --------------------------------------------------------------------------------------------

def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def _rate_ci(rate: float | None, ci: tuple[float, float] | None) -> str:
    if rate is None or ci is None:
        return "n/a"
    return f"{100.0 * rate:.1f}% [{100.0 * ci[0]:.0f}–{100.0 * ci[1]:.0f}%]"


_STATUS_GLYPH: dict[str, str] = {"evidence-present": "✅ evidence-present", "gap": "⚠️ gap"}


def to_compliance_markdown(report: RunReport, decision: ReleaseDecision | None = None) -> str:
    """Render the compliance report as an auditor-readable Markdown document."""
    cr = to_compliance(report, decision)
    ev = cr.result
    # The same sentence the Markdown report prints, from the same function, so an auditor reading
    # both never meets two descriptions of one predicate.
    predicate = (
        f"benign-FPR target {_pct(ev.target_fpr)}; {describe_calibration(report.calibration)}"
        if cr.calibrated
        else "default (uncalibrated)"
    )
    lines: list[str] = []
    lines.append("# Provael — compliance evidence report")
    lines.append("")
    lines.append(f"> {cr.disclaimer}")
    lines.append("")

    lines.append("## Run under test")
    lines.append("")
    lines.append("| field | value |")
    lines.append("| --- | --- |")
    lines.append(f"| tool version | `{cr.tool_version}` |")
    lines.append(f"| policy | `{cr.policy}` |")
    lines.append(f"| suite | `{cr.suite}` |")
    lines.append(f"| predicate | {predicate} |")
    lines.append(f"| derived from | `{cr.generated_from}` |")
    lines.append(f"| release verdict | **{cr.acceptance.verdict}** |")
    protocol = (
        f"`{cr.acceptance.protocol}` ({cr.acceptance.protocol_digest})"
        if cr.acceptance.assessed
        else "none named — not assessed"
    )
    lines.append(f"| acceptance protocol | {protocol} |")
    lines.append("")
    for reason in cr.acceptance.reasons:
        lines.append(f"- {reason}")
    lines.append("")

    lines.append("## Measured evidence (this run)")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("| --- | --- |")
    lines.append(
        f"| overall redirection rate (95% CI) | {_rate_ci(ev.redirection_rate, ev.ci95)} |"
    )
    lines.append(f"| transfer status | **{ev.transfer_status}** |")
    lines.append(f"| evidence state | **{ev.evidence_state}** |")
    lines.append(f"| benign baseline FPR (control) | {_pct(ev.benign_fpr)} |")
    lines.append(
        f"| clean-task-success (competence control) | {_pct(ev.clean_task_success_rate)} |"
    )
    lines.append(f"| attempts | {ev.n} |")
    lines.append(f"| EAI risks covered | {', '.join(ev.eai_ids_covered) or '—'} |")
    lines.append(f"| attack families | {', '.join(ev.attack_families) or '—'} |")
    lines.append("")
    if ev.by_eai:
        lines.append("### By EAI risk")
        lines.append("")
        lines.append(
            "All ten Top-10 risks are listed. A risk with no measured rate is stated as such — "
            "an omitted row would read as nothing to report."
        )
        lines.append("")
        lines.append("| EAI | risk | redirection rate (95% CI) | successes | attempts | status |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in ev.by_eai:
            rate = _rate_ci(row.redirection_rate, row.ci95) if row.measured else "—"
            lines.append(
                f"| {row.eai_id} | {row.name} | {rate} | "
                f"{row.successes if row.measured else '—'} | "
                f"{row.attempts if row.measured else '—'} | {row.status} |"
            )
        lines.append("")
        uncovered = [r for r in ev.by_eai if r.coverage != EaiCoverage.attacks_implemented.value]
        if uncovered:
            lines.append("**Risks Provael ships no attacks for:**")
            lines.append("")
            for row in uncovered:
                lines.append(
                    f"- **{row.eai_id} {row.name}** ({row.coverage}) — {row.coverage_note}"
                )
            lines.append("")

    lines.append("## Scope and caveats")
    lines.append("")
    for caveat in cr.scope_caveats:
        lines.append(f"- **{caveat.id}** — {caveat.text}")
    lines.append("")

    present = cr.summary.get("evidence-present", 0)
    gaps = cr.summary.get("gap", 0)
    lines.append("## Evidence summary")
    lines.append("")
    lines.append(f"**{present} evidence-present · {gaps} gap** across {len(cr.entries)} mapped "
                 "controls. Status is advisory — `evidence-present` means this run produced the "
                 "artifact a reviewer would attach for that control. It is not an assertion of "
                 "legal compliance, and it does not mean the whole standard or regulation is "
                 "satisfied; the `predicate` column says what each rate was scored under, and a "
                 f"row scored under the {cr.predicate} predicate is exactly that.")
    lines.append("")
    lines.append("| framework | tier | control | status | predicate | Provael signal |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for entry in cr.entries:
        flag = " *(indicative)*" if entry.indicative else ""
        lines.append(
            f"| {entry.framework_id} | {entry.tier} | {entry.control_id}{flag} | "
            f"{_STATUS_GLYPH[entry.status]} | {entry.predicate} | {entry.provael_signal} |"
        )
    lines.append("")
    lines.append(
        "`tier`: **operative** rows are the route a machinery assessor reads this evidence "
        "through — the Machinery Regulation, ISO 10218:2025, ISO 13849, IEC 61508, IEC 62443 — "
        "and the one this project develops; **reference** rows are kept, emitted and checked, but "
        "are reference material and are not developed further until the three proofs and a paid "
        "engagement exist (docs/roadmap.md, 20 September 2026)."
    )
    lines.append("")

    lines.append("## Detail")
    lines.append("")
    seen_framework: set[str] = set()
    for entry in cr.entries:
        if entry.framework not in seen_framework:
            seen_framework.add(entry.framework)
            lines.append(f"### {entry.framework}")
            lines.append("")
        indicative = " *(indicative — confirm the exact sub-clause against the full standard)*" \
            if entry.indicative else ""
        lines.append(f"#### {entry.control_id} — {entry.control_title}  ·  "
                     f"{_STATUS_GLYPH[entry.status]}{indicative}")
        lines.append("")
        lines.append(f"- **Provael signal:** {entry.provael_signal}")
        lines.append(f"- **Tier:** {entry.tier}")
        lines.append(f"- **Predicate:** {entry.predicate}")
        lines.append(f"- **Evidence:** {', '.join(f'`{ref}`' for ref in entry.evidence_refs)}")
        if entry.gap_reason is not None:
            lines.append(f"- **Gap:** {entry.gap_reason}")
        lines.append(f"- **Caveats:** {', '.join(entry.caveats)}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Independent · not legal advice · evidence, not certification. See "
                 "[docs/compliance/index.md](COMPLIANCE.md) for the full crosswalk.*")
    lines.append("")
    return "\n".join(lines)


def write_compliance_json(
    report: RunReport, path: Path, decision: ReleaseDecision | None = None
) -> Path:
    """Write the compliance JSON to ``path`` (parent dirs created). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_compliance_json(report, decision) + "\n", encoding="utf-8")
    return path


def write_compliance_markdown(
    report: RunReport, path: Path, decision: ReleaseDecision | None = None
) -> Path:
    """Write the compliance Markdown to ``path`` (parent dirs created). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_compliance_markdown(report, decision), encoding="utf-8")
    return path


__all__ = [
    "COMPLIANCE_JSON",
    "COMPLIANCE_MD",
    "DISCLAIMER",
    "CAVEATS",
    "REQUIREMENTS",
    "Requirement",
    "EaiBreakdown",
    "EvidenceResult",
    "ScopeCaveat",
    "Acceptance",
    "ComplianceEntry",
    "ComplianceReport",
    "to_compliance",
    "to_compliance_dict",
    "to_compliance_json",
    "to_compliance_markdown",
    "write_compliance_json",
    "write_compliance_markdown",
]
