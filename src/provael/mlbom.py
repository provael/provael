"""Emit a Provael run as a CycloneDX ML-BOM (E4 — supply-chain / AI Act Art. 11 evidence).

A CycloneDX **ML-BOM** (https://cyclonedx.org/capabilities/mlbom/) is the standard machine-readable
record of a model — its identity, what it was evaluated on, and its metrics. Attaching the Provael
ASR (with its Wilson CI, the benign-FPR control, and the honest transfer-status label) as model-card
metrics ties the red-team result into the same supply-chain evidence auditors already ingest (OWASP
Dependency-Track), and maps onto the **EU AI Act Art. 11 / Annex IV** technical-documentation
expectation for accuracy, robustness and cybersecurity.

**Evidence, not conformity.** This documents a measured simulation result; it is not a conformity
declaration. DETERMINISM: no wall-clock timestamp is emitted, so a deterministic run yields a
byte-identical BOM (``sort_keys``-stable), exactly like the SARIF/OSCAL exporters.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.calibration import wilson_ci
from provael.types import MEASURED_REAL_TRANSFER, STUB_VALIDATED_SCAFFOLDING, RunReport

#: Filename written into a run's output directory.
ML_BOM_JSON = "report.mlbom.json"

#: CycloneDX spec version — 1.6 introduced the ML-BOM model-card capability and is widely consumed.
SPEC_VERSION = "1.6"

#: What the AI Act asks this evidence to inform (factual pointer; no conformity claim).
_AI_ACT_ART11 = (
    "Adversarial-robustness testing evidence toward the technical documentation of AI Act Art. 11 "
    "/ Annex IV (accuracy, robustness, cybersecurity). Evidence, not conformity; not legal advice."
)


def to_ml_bom(report: RunReport) -> dict[str, object]:
    """Build a CycloneDX ML-BOM (as a dict) recording the policy under test and its ASR metrics."""
    lo, hi = wilson_ci(report.successes, report.attempts) if report.attempts else (0.0, 0.0)
    transfer_status = (
        MEASURED_REAL_TRANSFER
        if report.policy != "stub" and report.suite != "stub"
        else STUB_VALIDATED_SCAFFOLDING
    )
    metrics: list[dict[str, object]] = [
        {
            "type": "attack-success-rate",
            "value": round(report.asr, 4),
            "slice": f"provael:{report.suite}",
            "confidenceInterval": {"lowerBound": round(lo, 4), "upperBound": round(hi, 4)},
        }
    ]
    if report.benign_fpr is not None:
        metrics.append({
            "type": "benign-false-positive-rate",
            "value": round(report.benign_fpr, 4),
            "slice": f"provael:{report.suite}",
        })

    eai_ids = sorted({tag.id for tag in report.eai.values()})
    model_component: dict[str, object] = {
        "type": "machine-learning-model",
        "bom-ref": f"policy:{report.policy}",
        "name": report.policy,
        "modelCard": {
            "quantitativeAnalysis": {"performanceMetrics": metrics},
            "considerations": {
                "technicalLimitations": [
                    f"Transfer status: {transfer_status}. A stub-validated result is a property of "
                    "the deterministic CPU fixture, not a real VLA; cross-model transfer is "
                    "claimed only for a real policy x real suite.",
                    "Simulation only. Redirection in sim is a robustness signal, not a real-world "
                    "exploit.",
                ]
            },
        },
        "properties": [
            {"name": "provael:suite", "value": report.suite},
            {"name": "provael:attempts", "value": str(report.attempts)},
            {"name": "provael:transfer-status", "value": transfer_status},
            {"name": "provael:eai-covered", "value": ",".join(eai_ids)},
        ],
    }

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "provael",
                "version": report.tool_version,
            },
            "properties": [
                {"name": "provael:ai-act-art11", "value": _AI_ACT_ART11},
                {"name": "provael:transfer-status", "value": transfer_status},
            ],
        },
        "components": [model_component],
    }


def to_ml_bom_json(report: RunReport) -> str:
    """Serialise the ML-BOM as deterministic, sorted JSON (no trailing newline)."""
    return json.dumps(to_ml_bom(report), indent=2, sort_keys=True)


def write_ml_bom(report: RunReport, path: Path) -> Path:
    """Write the ML-BOM JSON to ``path`` (parent dirs created). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_ml_bom_json(report) + "\n", encoding="utf-8")
    return path


__all__ = ["ML_BOM_JSON", "SPEC_VERSION", "to_ml_bom", "to_ml_bom_json", "write_ml_bom"]
