"""Standards-aligned assurance profiles over a :class:`~provael.types.RunReport` (sim-only).

``provael attest --profile <iso-10218-2|iec-62443|insurer>`` embeds one of these views inside the
signed attestation. Each maps the **same** measured ASR + EAI-Top-10 findings + per-family
transfer-test results onto a standards framing — reusing :mod:`provael.scoring`,
:mod:`provael.compliance`, and the insurer report (:mod:`provael.hosted.report`); **nothing is
re-measured, re-scored, or re-signed**. Every view carries the honest per-family transfer caveat
(a stub-only family is never presented as a real-model result) and the evidence-not-certification
disclaimer.

**Not a conformity assessment.** This is red-team *evidence* that feeds a cyber-risk assessment,
an insurer's underwriting, or a third-party safety-certification process. Provael is an independent
project and is **not** affiliated with, endorsed by, or a certification body for ISO, IEC, the EU,
NIST, NVIDIA, UL, or any organisation named below. The Embodied AI Security Top 10 is Provael's
own list (never "OWASP"). No "first" claim is made.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from provael.calibration import wilson_ci
from provael.compliance import REQUIREMENTS
from provael.hosted.report import build_insurer_report
from provael.scoring.asr import by_family, matched_benign_fpr
from provael.types import MEASURED_REAL_TRANSFER, STUB_VALIDATED_SCAFFOLDING, RunReport

#: Machine-readable format id for the embedded assurance view.
ASSURANCE_FORMAT = "provael-assurance/v1"

#: Families whose numbers are always stub-validated scaffolding regardless of the policy/suite (the
#: optimized search families are validated on the deterministic stub; real transfer is GPU-gated).
_ALWAYS_STUB: frozenset[str] = frozenset({"optimized", "optimized_patch"})

_NOT_A_CONFORMITY_ASSESSMENT = (
    "This is EVIDENCE INPUT to a conformity / underwriting / certification process. It is NOT a "
    "conformity assessment or certificate; it confers no presumption of conformity. Provael is "
    "not a notified body or a certification body, and is not affiliated with or endorsed by any "
    "framework owner named here."
)

_TRANSFER_CAVEAT = (
    "Every family below carries its transfer status. A 'stub-validated-scaffolding' rate is a "
    "property of the deterministic CPU fixture, NOT a real VLA — it must never be read as a "
    "real-model result. A 'measured-real-transfer' rate was measured against the stated real "
    "policy x suite; read it against its 95% Wilson CI and the benign false-positive control."
)


class AssuranceProfile(StrEnum):
    """Which standards-aligned assurance view to embed in the attestation."""

    iso_10218_2 = "iso-10218-2"
    iec_62443 = "iec-62443"
    insurer = "insurer"


#: NVIDIA Halos / third-party cert-readiness cross-reference (static). This states, factually, which
#: functional- and AI-safety frameworks a red-team ASR result is an INPUT to — a readiness
#: cross-reference, NOT a certification and NOT an endorsement by any of these owners.
CERT_READINESS: tuple[dict[str, str], ...] = (
    {
        "framework": "NVIDIA Halos",
        "kind": "AI/autonomy safety framework",
        "readiness_role": "Adversarial-robustness ASR is a safety-case input for the AI-safety "
        "pillar; provael provides red-team evidence, not a Halos assessment or NVIDIA sign-off.",
    },
    {
        "framework": "UL 4600",
        "kind": "Standard for safety of autonomous products",
        "readiness_role": "Measured attack-success evidence supports the safety-case claims/"
        "argument for an autonomous product; one input among many, not a UL certification.",
    },
    {
        "framework": "ISO/PAS 8800",
        "kind": "AI safety for road vehicles (AI safety lifecycle)",
        "readiness_role": "Per-EAI ASR feeds the AI-safety argument (robustness of the learned "
        "function); evidence input, not conformity.",
    },
    {
        "framework": "ISO 21448 (SOTIF)",
        "kind": "Safety of the intended functionality",
        "readiness_role": "Adversarially-triggered unsafe behaviour is a triggering-condition "
        "input to the SOTIF analysis; provael measures it, it does not close the SOTIF case.",
    },
    {
        "framework": "ISO/IEC TR 5469",
        "kind": "AI functional safety",
        "readiness_role": "Names the AI-robustness property provael measures; used to map the "
        "evidence, not to claim functional-safety conformance.",
    },
)


def _req(key: str) -> dict[str, str]:
    """The compliance Requirement row for ``key`` (reused from REQUIREMENTS, not rebuilt)."""
    req = next(r for r in REQUIREMENTS if r.key == key)
    return {
        "key": req.key,
        "framework": req.framework,
        "framework_id": req.framework_id,
        "control_id": req.control_id,
        "control_title": req.control_title,
        "evidence_signal": req.provael_signal,
    }


def _family_to_eai(report: RunReport) -> dict[str, dict[str, str]]:
    """Map each family present in the run to its EAI tag (from the report's own eai tags)."""
    from provael.attacks.registry import FAMILIES

    name_to_family = {name: fam for fam, names in FAMILIES.items() for name in names}
    out: dict[str, dict[str, str]] = {}
    for attack, tag in report.eai.items():
        family = name_to_family.get(attack, attack)
        out.setdefault(family, {"eai_id": tag.id, "eai_name": tag.name})
    return out


def family_transfer_table(report: RunReport) -> list[dict[str, Any]]:
    """The honest per-family table: measured ASR + 95% Wilson CI + benign-FPR + transfer status.

    Reuses :func:`provael.scoring.asr.by_family` + :func:`provael.calibration.wilson_ci` +
    :func:`provael.scoring.asr.matched_benign_fpr` — no statistic is recomputed by hand. This is the
    "which families transfer on the real model" table an insurer / assessor reads.
    """
    real_run = report.policy != "stub" and report.suite != "stub"
    mbf = matched_benign_fpr(report.results)
    fam_eai = _family_to_eai(report)
    rows: list[dict[str, Any]] = []
    for family, stat in by_family(report.results).items():
        if family == "baseline" or stat.attempts == 0:
            continue  # the benign control becomes benign_fpr, not a row; skip N/A families
        lo, hi = wilson_ci(stat.successes, stat.attempts)
        stub_only = (not real_run) or (family in _ALWAYS_STUB)
        status = STUB_VALIDATED_SCAFFOLDING if stub_only else MEASURED_REAL_TRANSFER
        tag = fam_eai.get(family, {})
        rows.append({
            "family": family,
            "eai_id": tag.get("eai_id"),
            "eai_name": tag.get("eai_name"),
            "asr": round(stat.asr, 4),
            "n": stat.attempts,
            "successes": stat.successes,
            "wilson_ci95": [round(lo, 4), round(hi, 4)],
            "benign_fpr": report.benign_fpr,
            "matched_benign_fpr": mbf,
            "transfer_status": status,
        })
    return sorted(rows, key=lambda r: r["family"])


def _iso_10218_2(report: RunReport) -> dict[str, Any]:
    """ISO 10218-2:2025 cyber-risk-assessment evidence, routing to IEC 62443 SL2."""
    return {
        "instrument": "ISO 10218-2:2025 — robot applications & robot cells (cybersecurity clauses)",
        "role": "cyber-risk-assessment evidence input for AI-enabled robot cells "
        "(feeds the EU Machinery Regulation cyber-risk assessment; not a conformity assessment)",
        "requirement": _req("iso-10218-2:cyber"),
        "routes_to": {
            "framework": "IEC 62443",
            "target_security_level": "SL2",
            "rationale": "A collaborative-robot cell exposed to intentional manipulation by simple "
            "means maps to IEC 62443 SL2; the per-EAI ASR is an input toward that target, not a "
            "security-level achievement.",
        },
        "risk_assessment_items": family_transfer_table(report),
    }


def _iec_62443(report: RunReport) -> dict[str, Any]:
    """IEC 62443 SL2 evidence: the measured ASR as input to the applicable FRs."""
    return {
        "instrument": "IEC 62443 (security for industrial automation & control systems)",
        "role": "security-level evidence input (not a security-level achievement or certification)",
        "requirement": _req("iec-62443:slv"),
        "target_security_level": "SL2",
        "applicable_foundational_requirements": [
            {"fr": "FR3 System Integrity", "why": "Adversarial redirection / hijack of the "
             "commanded action is an integrity-violation signal; ASR measures resistance to it."},
            {"fr": "FR7 Resource Availability", "why": "The freeze / action-freeze facet is an "
             "availability (DoS-style) signal at the policy layer."},
        ],
        "sl2_note": "SL2 = protection against intentional violation using simple means. The ASR "
        "below is one robustness input toward an SL2 case; it does not by itself establish SL2.",
        "evidence_items": family_transfer_table(report),
    }


def _insurer(report: RunReport, *, issued_at: str, commit: str) -> dict[str, Any]:
    """Insurer-consumable summary: reuses the shipped insurer report + the family transfer table."""
    return {
        "instrument": "insurer / underwriting summary",
        "role": "underwriting input — the honest 'which families transfer on the real model' table "
        "with its statistical controls",
        "insurer_report": build_insurer_report(report, issued_at=issued_at, commit=commit),
        "family_transfer_table": family_transfer_table(report),
    }


def build_assurance(
    report: RunReport, profile: AssuranceProfile, *, issued_at: str, commit: str
) -> dict[str, Any]:
    """Build the profile-specific assurance view (pure, deterministic — no wall-clock read here).

    Reuses the shipped scoring / compliance / insurer surfaces; every view carries the transfer
    caveat, the shared cert-readiness cross-reference, and the evidence-not-cert disclaimer.
    """
    if profile is AssuranceProfile.iso_10218_2:
        view = _iso_10218_2(report)
    elif profile is AssuranceProfile.iec_62443:
        view = _iec_62443(report)
    else:
        view = _insurer(report, issued_at=issued_at, commit=commit)
    return {
        "format": ASSURANCE_FORMAT,
        "profile": profile.value,
        "real_model_run": report.policy != "stub" and report.suite != "stub",
        **view,
        "cert_readiness_crossref": [dict(row) for row in CERT_READINESS],
        "transfer_caveat": _TRANSFER_CAVEAT,
        "not_a_conformity_assessment": _NOT_A_CONFORMITY_ASSESSMENT,
    }


__all__ = [
    "ASSURANCE_FORMAT",
    "AssuranceProfile",
    "CERT_READINESS",
    "family_transfer_table",
    "build_assurance",
]
