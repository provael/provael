"""Compliance-evidence export for a :class:`~provael.types.RunReport` (v0.5.0).

Turns a calibrated red-team run into an **auditor-readable evidence artifact** that maps the
run's measured signals (calibrated redirection rate + 95% Wilson CI, the benign-FPR control, the
EAI risks exercised, the per-task calibration metadata) onto the framework requirements in
``docs/COMPLIANCE.md`` — **EU AI Act** (Reg. (EU) 2024/1689), the **EU Machinery Regulation**
(Reg. (EU) 2023/1230 — the operative route for AI-enabled robots after the 2026 Digital Omnibus),
**ISO 10218-1/-2:2025** (cyber), **NIST AI 100-2 / AI RMF**, and **IEC 62443**.

This is the generator the ``docs/COMPLIANCE.md`` pre-spec described. It is **evidence, not
certification**: each requirement entry carries a ``status`` of ``evidence-present`` or ``gap``
against what *this run* actually produced, never an assertion of legal conformity. Three
honest-scope caveats from the crosswalk travel with every entry (adversarial-only,
evidence-not-certification, behavioural-not-worst-case).

It reuses an existing ``report.json`` — no attacks are re-run — so the whole path is
CPU/stub-runnable in CI. Output is ``sort_keys``-stable, so a deterministic run yields a
byte-identical artifact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from provael.attacks.registry import FAMILIES
from provael.calibration import wilson_ci
from provael.eai import CATALOG
from provael.evidence import EvidenceState, evidence_state_of, transfer_status_of
from provael.types import RunReport

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
# Honest-scope caveats (from docs/COMPLIANCE.md "Honest scope"). Attached to every entry by id.
# --------------------------------------------------------------------------------------------

CAVEATS: dict[str, str] = {
    "adversarial-only": (
        "Adversarial security only. Functional/mechanical safety (ISO 10218 safety clauses, "
        "ISO 13482, ISO/TS 15066) and non-adversarial reliability are out of scope."
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
# Requirement catalog — the crosswalk targets (docs/COMPLIANCE.md). One entry per mapped control.
# --------------------------------------------------------------------------------------------

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


_EU = "EU AI Act (Regulation (EU) 2024/1689)"
_MACHINERY = "EU Machinery Regulation (Regulation (EU) 2023/1230)"
_CRA = "EU Cyber Resilience Act (Regulation (EU) 2024/2847)"
_ISO = "ISO 10218:2025"
_NIST = "NIST AI 100-2 / AI RMF"
_IEC = "IEC 62443"
_ISO_TR_5469 = "ISO/IEC TR 5469:2024"
_ISO_42001 = "ISO/IEC 42001:2023"
_ISO_23894 = "ISO/IEC 23894:2023"

#: Ordered so the artifact (and tests) are deterministic.
REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(
        key="eu-ai-act:art15",
        framework=_EU, framework_id="eu-ai-act",
        control_id="Article 15", control_title="Accuracy, robustness and cybersecurity",
        provael_signal=(
            "Calibrated redirection rate + 95% CI per EAI risk, with the benign-FPR control; "
            "SARIF for the security review"
        ),
        evidence_refs=("report.json", "report.json#/by_attack", "report.sarif"),
        indicative=False,
    ),
    Requirement(
        key="eu-ai-act:art9",
        framework=_EU, framework_id="eu-ai-act",
        control_id="Article 9", control_title="Risk-management system",
        provael_signal="EAI risk taxonomy as the threat catalogue + a measured rate per risk",
        evidence_refs=("report.json#/eai", "docs/TOP10.md"),
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
        control_id="Reg. (EU) 2023/1230 (applies 2027-01-20)",
        control_title="Machinery — protection against corruption / safety-function AI",
        provael_signal=(
            "Measured redirection rate per EAI risk as input to the mandatory cyber-risk "
            "assessment for AI-enabled machinery, with action-space integrity (EAI04: keep-out "
            "hijack / critical-step freeze of the commanded motion) as the on-point evidence for "
            "the corruption-of-safety-function essential requirement; SARIF for the security file"
        ),
        evidence_refs=("report.json#/by_attack", "report.sarif", "docs/COMPLIANCE.md"),
        indicative=True,
    ),
    Requirement(
        key="eu-machinery:annex-i-part-a",
        framework=_MACHINERY, framework_id="eu-machinery",
        control_id="Article 25(2) via Article 6(1); Annex I Part A "
        "[point reference pending verification]",
        control_title="Annex I Part A — third-party conformity assessment of ML self-evolving-"
        "behaviour safety components",
        provael_signal=(
            "Per-family adversarial evidence (ASR + 95% Wilson CI + anytime-valid CI + benign-FPR "
            "control + Succ-But-Unsafe + BH-FDR across families) with the honest per-family "
            "real-policy transfer statement — the adversarial-robustness input a notified body "
            "reviews for an ML safety component routed to a third-party conformity assessment "
            "under Article 25(2). Article/annex numbers verified against CELEX 32023R1230; the "
            "granular Annex I Part A point number is marked pending until confirmed against the "
            "primary annex text"
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
        evidence_refs=("report.json#/by_attack", "docs/COMPLIANCE.md"),
        indicative=True,
    ),
    Requirement(
        key="iso-10218-2:cyber",
        framework=_ISO, framework_id="iso-10218",
        control_id="ISO 10218-2:2025",
        control_title="Robot applications & cells — Part 2 (cybersecurity requirements)",
        provael_signal="Measured redirection rate per EAI risk as cyber-risk-assessment input",
        evidence_refs=("report.json#/by_attack", "docs/COMPLIANCE.md"),
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
            "docs/TOP10.md#cross-framework-crosswalk-corrected-verbatim-source-items",
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
    ),
    Requirement(
        key="nist-ai-rmf:measure",
        framework=_NIST, framework_id="nist",
        control_id="AI RMF — MEASURE",
        control_title="Measure identified risks",
        provael_signal="Calibrated rate + 95% CI + benign FPR — a measured, controlled metric",
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
        evidence_refs=("report.json#/eai", "docs/TOP10.md"),
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
        evidence_refs=("report.json#/by_attack", "docs/COMPLIANCE.md"),
        indicative=True,
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
        evidence_refs=("report.json#/eai", "docs/TOP10.md"),
        indicative=True,
    ),
)


# --------------------------------------------------------------------------------------------
# Output models.
# --------------------------------------------------------------------------------------------

class EaiBreakdown(BaseModel):
    """Measured evidence for one EAI risk, aggregated across the attacks that exercise it."""

    eai_id: str
    name: str
    attempts: int
    successes: int
    redirection_rate: float
    ci95: tuple[float, float]


class EvidenceResult(BaseModel):
    """The measured signals from the run, shared by every requirement entry as its evidence."""

    redirection_rate: float | None = Field(
        ..., description="Overall ASR / calibrated redirection rate (None if nothing ran)."
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


class ComplianceReport(BaseModel):
    """An auditor-readable evidence map from a Provael run to framework requirements."""

    tool_version: str
    generated_from: str = Field(
        "report.json", description="The artifact this evidence was derived from."
    )
    policy: str
    suite: str
    calibrated: bool
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
    """Aggregate per-attack stats into per-EAI-risk evidence rows (sorted by id)."""
    buckets: dict[str, tuple[int, int]] = {}  # eai_id -> (attempts, successes)
    for attack, tag in report.eai.items():
        stat = report.by_attack.get(attack)
        if stat is None:
            continue
        att, suc = buckets.get(tag.id, (0, 0))
        buckets[tag.id] = (att + stat.attempts, suc + stat.successes)
    rows: list[EaiBreakdown] = []
    for eai_id in sorted(buckets):
        attempts, successes = buckets[eai_id]
        rate = successes / attempts if attempts else 0.0
        risk = CATALOG.get(eai_id)
        rows.append(
            EaiBreakdown(
                eai_id=eai_id,
                name=risk.name if risk is not None else eai_id,
                attempts=attempts,
                successes=successes,
                redirection_rate=rate,
                ci95=wilson_ci(successes, attempts),
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


def _status(key: str, ev: EvidenceResult) -> tuple[Status, str | None]:
    """Decide whether the run carries evidence for a requirement, and why not when it doesn't.

    Gap rules (deterministic, so they're testable):

    * ``art72`` / ``manage`` — always a gap from a single run: post-market monitoring is
      longitudinal, and the observability risk (EAI10) isn't exercised by the shipping attacks.
    * ``measure`` — a gap unless the run is calibrated *and* has a benign-FPR control (MEASURE
      asks for a controlled metric, not a bare rate).
    * ``art15`` — a gap without a benign baseline control, or with no EAI-tagged attacks.
    * everything else — present once any EAI-tagged adversarial attack ran.
    """
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

    if has_eai:
        return "evidence-present", None
    return "gap", "No EAI-tagged adversarial attacks were run."


def _entry(req: Requirement, ev: EvidenceResult) -> ComplianceEntry:
    status, gap_reason = _status(req.key, ev)
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
    )


def to_compliance(report: RunReport) -> ComplianceReport:
    """Build a :class:`ComplianceReport` from a run report (no attacks are re-run)."""
    ev = _evidence(report)
    entries = [_entry(req, ev) for req in REQUIREMENTS]
    summary = {"evidence-present": 0, "gap": 0}
    for entry in entries:
        summary[entry.status] += 1
    return ComplianceReport(
        tool_version=report.tool_version,
        generated_from="report.json",
        policy=report.policy,
        suite=report.suite,
        calibrated=report.calibrated,
        disclaimer=DISCLAIMER,
        scope_caveats=[ScopeCaveat(id=cid, text=CAVEATS[cid]) for cid in _ENTRY_CAVEATS],
        result=ev,
        summary=summary,
        entries=entries,
    )


def to_compliance_dict(report: RunReport) -> dict[str, object]:
    """The compliance report as a JSON-safe dict (keys sorted for stability)."""
    data: dict[str, object] = json.loads(to_compliance(report).model_dump_json())
    return data


def to_compliance_json(report: RunReport) -> str:
    """Serialise the compliance report to stable, indented JSON (no trailing newline)."""
    return json.dumps(to_compliance_dict(report), indent=2, sort_keys=True)


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


def to_compliance_markdown(report: RunReport) -> str:
    """Render the compliance report as an auditor-readable Markdown document."""
    cr = to_compliance(report)
    ev = cr.result
    predicate = (
        f"calibrated (benign-FPR target {_pct(ev.target_fpr)})" if cr.calibrated
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
        lines.append("| EAI | risk | redirection rate (95% CI) | successes | attempts |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in ev.by_eai:
            lines.append(
                f"| {row.eai_id} | {row.name} | "
                f"{_rate_ci(row.redirection_rate, row.ci95)} | {row.successes} | {row.attempts} |"
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
                 "artifact a reviewer would attach, never an assertion of legal compliance.")
    lines.append("")
    lines.append("| framework | control | status | Provael signal |")
    lines.append("| --- | --- | --- | --- |")
    for entry in cr.entries:
        flag = " *(indicative)*" if entry.indicative else ""
        lines.append(
            f"| {entry.framework_id} | {entry.control_id}{flag} | "
            f"{_STATUS_GLYPH[entry.status]} | {entry.provael_signal} |"
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
        lines.append(f"- **Evidence:** {', '.join(f'`{ref}`' for ref in entry.evidence_refs)}")
        if entry.gap_reason is not None:
            lines.append(f"- **Gap:** {entry.gap_reason}")
        lines.append(f"- **Caveats:** {', '.join(entry.caveats)}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Independent · not legal advice · evidence, not certification. See "
                 "[docs/COMPLIANCE.md](COMPLIANCE.md) for the full crosswalk.*")
    lines.append("")
    return "\n".join(lines)


def write_compliance_json(report: RunReport, path: Path) -> Path:
    """Write the compliance JSON to ``path`` (parent dirs created). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_compliance_json(report) + "\n", encoding="utf-8")
    return path


def write_compliance_markdown(report: RunReport, path: Path) -> Path:
    """Write the compliance Markdown to ``path`` (parent dirs created). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_compliance_markdown(report), encoding="utf-8")
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
    "ComplianceEntry",
    "ComplianceReport",
    "to_compliance",
    "to_compliance_dict",
    "to_compliance_json",
    "to_compliance_markdown",
    "write_compliance_json",
    "write_compliance_markdown",
]
