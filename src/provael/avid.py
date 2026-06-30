"""Export a Provael run as an AVID (AI Vulnerability Database) report record.

AVID (https://avidml.org) is an open, 501(c)(3) AI vulnerability database with an `avidtools`
schema; garak and Inspect AI results already flow into it, and it maps records to MITRE ATLAS /
CVSS. Emitting an AVID record makes Provael's ASR *citable evidence in a recognised database* —
the same adoption pattern the incumbent scanners use.

This writes an AVID-report-shaped JSON object (following the avidtools `Report` fields). Ids are
stable ``uuid5`` (deterministic — no random/clock); `reported_date` is a placeholder to stamp at
submission time. Submitting the record to AVID is an external action and is **gated** (drafted
locally for review, never auto-submitted).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from provael.calibration import wilson_ci
from provael.eai import CATALOG
from provael.types import RunReport

#: Filename written into a run's output directory.
AVID_JSON = "report.avid.json"

_PLACEHOLDER_DATE = "1970-01-01"
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://avidml.org/provael")


def to_avid(report: RunReport) -> dict[str, object]:
    """Build an AVID report record (as a dict) from a Provael run."""
    eai_ids = sorted({tag.id for tag in report.eai.values()})
    lo, hi = wilson_ci(report.successes, report.attempts) if report.attempts else (0.0, 0.0)
    risk_lines = "; ".join(
        f"{eid} {CATALOG[eid].name}" for eid in eai_ids if eid in CATALOG
    )
    return {
        "data_type": "AVID",
        "data_version": "0.2",
        "metadata": {"report_id": str(uuid.uuid5(_NS, f"{report.policy}:{report.suite}"))},
        "affects": {
            "developer": [],
            "deployer": [],
            "artifacts": [{"type": "Model", "name": report.policy}],
        },
        "problemtype": {
            "classof": "VLA Evaluation",
            "type": "Detection",
            "description": {
                "lang": "eng",
                "value": (
                    f"Provael red-team of VLA policy '{report.policy}' in suite "
                    f"'{report.suite}': attack-induced unsafe behaviour across {risk_lines}."
                ),
            },
        },
        "metrics": [
            {
                "name": "Attack Success Rate",
                "detection_method": {"type": "Simulation red-team (templated attacks)"},
                "results": {
                    "asr": round(report.asr, 4),
                    "successes": report.successes,
                    "attempts": report.attempts,
                    "ci95": [round(lo, 4), round(hi, 4)],
                    "benign_fpr": report.benign_fpr,
                    "by_attack": {n: round(s.asr, 4) for n, s in report.by_attack.items()},
                },
            }
        ],
        "references": [
            {
                "type": "source",
                "label": "Provael",
                "url": "https://github.com/provael/provael",
            },
            {
                "type": "taxonomy",
                "label": "Embodied AI Security Top 10",
                "url": "https://github.com/provael/provael/blob/main/docs/TOP10.md",
            },
        ],
        "impact": {
            "avid": {
                "risk_domain": ["Security"],
                "sep_view": ["S0403: Adversarial Example", "S0100: Software Vulnerability"],
                "taxonomy_version": "0.2",
            }
        },
        "credit": [{"lang": "eng", "value": "Provael"}],
        "reported_date": _PLACEHOLDER_DATE,
    }


def to_avid_json(report: RunReport) -> str:
    """Serialise the AVID record as deterministic JSON."""
    return json.dumps(to_avid(report), indent=2, sort_keys=True)


def write_avid(report: RunReport, path: Path) -> Path:
    """Write the AVID JSON to ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_avid_json(report), encoding="utf-8")
    return path


__all__ = ["AVID_JSON", "to_avid", "to_avid_json", "write_avid"]
