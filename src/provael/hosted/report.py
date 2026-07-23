"""Structured assurance-report **draft** — an evidence export, NOT an insurer/conformity opinion.

:func:`build_insurer_report` is a **pure function** of a :class:`~provael.types.RunReport` and the
issuance metadata: it wraps the *same* attestation statement the free ``provael attest`` produces
(:func:`provael.attest.build_statement`) and adds a **candidate conformity mapping** that lines each
piece of Provael evidence up against the EU Machinery Regulation 2023/1230, the AI Act Annex-I
machinery route, and ISO 10218:2025.

It is a **structured evidence draft**, not an opinion: it is **evidence, not certification**, **not
an insurer or conformity-assessment opinion**, and **not legal advice**. A qualified assessor (a
Notified Body, an insurer, your safety engineer) reaches the actual conclusion. Provael is an
independent project and is not affiliated with ISO, the EU, NIST, IEC, OWASP, or MITRE. The
regulatory dates are the factual application dates carried in
:data:`provael.attest.REGULATORY_CLOCK`; confirm against the primary text. This function does no
signing itself; a bound SHA-256 digest ties the draft to its attestation.
"""

from __future__ import annotations

import json
from typing import Any

from provael.attest import build_statement
from provael.compliance import to_compliance_dict
from provael.types import MEASURED_REAL_TRANSFER, STUB_VALIDATED_SCAFFOLDING, RunReport

#: The conformity mapping: each row lines a Provael artifact up against the instrument + date it
#: informs. Dates mirror :data:`provael.attest.REGULATORY_CLOCK` (factual application dates).
CONFORMITY_MAPPING: tuple[dict[str, str], ...] = (
    {
        "obligation": "Protection against corruption of safety functions; AI-enabled safety "
        "components require third-party conformity assessment.",
        "instrument": "Regulation (EU) 2023/1230 (Machinery Regulation), Annex I",
        "applies_from": "2027-01-20",
        "provael_evidence": "Measured ASR per EAI risk with a 95% Wilson CI and the benign-FPR "
        "control (report.json + SARIF); the digest-bound, dated attestation statement.",
    },
    {
        "obligation": "High-risk AI safety-component obligations for AI embedded in machinery "
        "(robustness, accuracy, cybersecurity — Art. 15).",
        "instrument": "Regulation (EU) 2024/1689 (AI Act), Annex I machinery",
        "applies_from": "2027-08-02",
        "provael_evidence": "Per-family transfer-test (rate + 95% Wilson CI + benign control) and "
        "the compliance crosswalk, carried inside the attestation. A move to 2028-08-02 is "
        "proposed in the Digital Omnibus but NOT yet adopted; treat 2027 as binding until it is.",
    },
    {
        "obligation": "Cybersecurity risk assessment for industrial / collaborative robots.",
        "instrument": "ISO 10218-1/-2:2025 (cyber clauses)",
        "applies_from": "2025-04-01",
        "provael_evidence": "Per-EAI ASR as a documented input to the robot's cyber-risk "
        "assessment; the EAI04 monitored-stop / action-integrity evidence.",
    },
)

#: Standing disclaimers carried on every assurance-report draft.
DISCLAIMERS: tuple[str, ...] = (
    "Draft, not an opinion. This is a structured evidence export for a qualified assessor (a "
    "Notified Body, an insurer, your safety engineer) to evaluate — not an insurer or "
    "conformity-assessment opinion, and not a decision.",
    "Evidence, not certification. This report documents measured simulation results; it is not a "
    "conformity certificate and confers no legal presumption of conformity.",
    "Not legal advice. Confirm every instrument and date against its primary text.",
    "Provael is an independent project and is not affiliated with ISO, the EU, NIST, IEC, OWASP, "
    "or MITRE. The 'Embodied AI Security Top 10' is an independent community list, not OWASP.",
    "Simulation only. Redirection/activation in simulation is a robustness signal, not a "
    "real-world exploit; cross-model transfer is only claimed where a real policy was run.",
)


def build_insurer_report(
    report: RunReport,
    *,
    issued_at: str,
    commit: str,
) -> dict[str, Any]:
    """Build the insurer / Notified-Body-ready report (pure) — wraps the attestation statement.

    Args:
        report: the run under assessment.
        issued_at: UTC ISO-8601 issuance timestamp (passed in — never read here, to preserve the
            report-determinism contract).
        commit: the source commit the ruleset came from.
    """
    statement = build_statement(report, issued_at=issued_at, commit=commit)
    stmt_dict: dict[str, Any] = json.loads(statement.model_dump_json())
    transfer_status = (
        MEASURED_REAL_TRANSFER
        if report.policy != "stub" and report.suite != "stub"
        else STUB_VALIDATED_SCAFFOLDING
    )
    adv_rate, _adv_s, adv_n = report.adversarial_headline()
    return {
        "format": "provael-assurance-report-draft/v1",
        "tool_version": report.tool_version,
        "issued_at": issued_at,
        "subject": stmt_dict["subject"],
        "executive_summary": {
            "policy": report.policy,
            "suite": report.suite,
            # The headline is the ADVERSARIAL ASR (benign control excluded); the all-episode rate is
            # shown separately so an assessor never reads the diluted figure as the attack rate.
            "adversarial_asr": adv_rate if adv_n else None,
            "all_episode_unsafe_rate": report.asr,
            # P0.4 honesty: read the headline against BOTH intervals + the matched-benign control,
            # and the run-level transfer tier — so an assessor never reads a stub number as real.
            "wilson_ci95": list(report.ci95) if report.ci95 is not None else None,
            "anytime_ci": list(report.anytime_ci) if report.anytime_ci is not None else None,
            "benign_fpr": report.benign_fpr,
            "matched_benign_fpr": report.matched_benign_fpr,
            "transfer_status": transfer_status,
            "seeds": report.seeds,
            "preliminary": report.preliminary,
            "attacks": report.attacks,
            "calibrated": report.calibrated,
        },
        "attestation_statement": stmt_dict,
        "conformity_mapping": [dict(row) for row in CONFORMITY_MAPPING],
        "compliance_crosswalk": to_compliance_dict(report),
        "disclaimers": list(DISCLAIMERS),
    }


def to_insurer_report_json(
    report: RunReport, *, issued_at: str, commit: str
) -> str:
    """Serialise the insurer report to stable, indented JSON (keys sorted)."""
    return json.dumps(
        build_insurer_report(report, issued_at=issued_at, commit=commit),
        indent=2,
        sort_keys=True,
    )


__all__ = [
    "CONFORMITY_MAPPING",
    "DISCLAIMERS",
    "build_insurer_report",
    "to_insurer_report_json",
]
