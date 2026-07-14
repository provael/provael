"""EU Machinery Regulation **Annex III** evidence-pack (D3 — the paid enterprise deliverable).

Where the insurer report (:mod:`provael.hosted.report`) is a broad conformity *mapping*, this is a
focused **Annex III essential-health-and-safety-requirement (EHSR)** evidence-pack for the two
cybersecurity-relevant EHSRs of Regulation (EU) 2023/1230 (applies **2027-01-20**):

* **1.1.9 — Protection against corruption:** safety functions must not be corruptible such that a
  hazardous situation results.
* **1.2.1 — Safety and reliability of control systems:** control systems must resist intended and
  unintended influences, **including malicious attempts by third parties** that create a hazard.

For each, the pack lines the measured Provael evidence up against the requirement and carries the
run-level transfer tier, so a Notified Body reviewer sees exactly what was measured and on what.

**Evidence, not certification; not legal advice.** :func:`build_machinery_annex_pack` is a pure
function of a :class:`~provael.types.RunReport` and its issuance metadata (dates are the factual
application dates in :data:`provael.attest.REGULATORY_CLOCK`; confirm against the primary text). It
signs nothing itself — the operated hosted service signs the wrapped attestation with the project
key. Gate it behind :func:`provael.hosted.require_entitlement` at the server layer (paid tier, Q4).
"""

from __future__ import annotations

import json
from typing import Any

from provael.attest import build_statement
from provael.hosted.report import DISCLAIMERS
from provael.types import MEASURED_REAL_TRANSFER, STUB_VALIDATED_SCAFFOLDING, RunReport

#: The Annex III EHSRs a VLA-policy red-team informs. Static text; the per-run evidence is filled in
#: by :func:`build_machinery_annex_pack`. Dates mirror :data:`provael.attest.REGULATORY_CLOCK`.
_ANNEX_III_EHSRS: tuple[dict[str, str], ...] = (
    {
        "ehsr_id": "Annex III, 1.1.9",
        "ehsr_title": "Protection against corruption",
        "obligation": "Machinery must be designed and constructed so that connection to it, or any "
        "corruption of software/data critical for safety, does not lead to a hazardous situation.",
        "provael_evidence": "Measured ASR per EAI risk — with the EAI04 action-space-integrity "
        "family (keepout_hijack / critical_freeze) as the on-point evidence that the policy's "
        "action output can be corrupted into a hazardous command — each with a 95% Wilson CI and "
        "the benign-FPR control; bound by the dated, digest-verified attestation.",
    },
    {
        "ehsr_id": "Annex III, 1.2.1",
        "ehsr_title": "Safety and reliability of control systems",
        "obligation": "Control systems must be safe and reliable and withstand intended and "
        "unintended influences, including malicious attempts by third parties creating a hazard.",
        "provael_evidence": "Per-family transfer-test (rate + 95% Wilson CI + benign control) "
        "quantifying how often adversarial perturbation (EAI01/02/05/06) redirects the control "
        "policy out of its benign envelope — the third-party-malicious-influence evidence.",
    },
)


def build_machinery_annex_pack(
    report: RunReport,
    *,
    issued_at: str,
    commit: str,
) -> dict[str, Any]:
    """Build the Machinery Regulation Annex III evidence-pack (pure) — wraps the attestation.

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
    return {
        "format": "provael-machinery-annex-iii-pack/v1",
        "tool_version": report.tool_version,
        "issued_at": issued_at,
        "instrument": "Regulation (EU) 2023/1230 (Machinery Regulation), Annex III",
        "applies_from": "2027-01-20",
        "subject": stmt_dict["subject"],
        "transfer_status": transfer_status,
        "annex_iii_evidence": [
            {**ehsr, "transfer_status": transfer_status} for ehsr in _ANNEX_III_EHSRS
        ],
        "attestation_statement": stmt_dict,
        "disclaimers": list(DISCLAIMERS),
    }


def to_machinery_annex_pack_json(report: RunReport, *, issued_at: str, commit: str) -> str:
    """Serialise the Annex III pack to stable, indented JSON (keys sorted)."""
    return json.dumps(
        build_machinery_annex_pack(report, issued_at=issued_at, commit=commit),
        indent=2,
        sort_keys=True,
    )


__all__ = ["build_machinery_annex_pack", "to_machinery_annex_pack_json"]
