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
from provael.scoring.asr import benign_control
from provael.types import RunReport

#: Filename written into a run's output directory.
AVID_JSON = "report.avid.json"

_PLACEHOLDER_DATE = "1970-01-01"
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://avidml.org/provael")


def to_avid(report: RunReport) -> dict[str, object]:
    """Build an AVID report record (as a dict) from a Provael run."""
    eai_ids = sorted({tag.id for tag in report.eai.values()})
    # An AVID record is a vulnerability-database submission, so "Attack Success Rate" there must be
    # the ADVERSARIAL rate over the adversarial denominator — not report.asr, which folds the benign
    # control in and understates the attack rate (with an interval that can exclude the true ASR).
    adv_rate, adv_s, adv_n = report.adversarial_headline()
    benign = benign_control(report)
    lo, hi = wilson_ci(adv_s, adv_n) if adv_n else (0.0, 0.0)
    all_lo, all_hi = wilson_ci(report.successes, report.attempts) if report.attempts else (0.0, 0.0)
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
                    # Adversarial episodes only; the benign control is excluded by semantic role.
                    "asr": None if adv_n == 0 else round(adv_rate, 4),
                    "successes": adv_s,
                    "attempts": adv_n,
                    "ci95": None if adv_n == 0 else [round(lo, 4), round(hi, 4)],
                    # The control arm, with the same shape the ASR above is given: a rate is
                    # not comparable to an interval, so the floor carries its own.
                    "benign_fpr": None if benign is None else round(benign.rate, 4),
                    "benign_successes": None if benign is None else benign.successes or None,
                    "benign_attempts": None if benign is None else benign.attempts or None,
                    "benign_ci95": (
                        None
                        if benign is None or benign.ci95 is None
                        else [round(benign.ci95[0], 4), round(benign.ci95[1], 4)]
                    ),
                    # An attack with no applicable episode has no rate: null, never a measured 0.0.
                    "by_attack": {
                        n: (None if s.attempts == 0 else round(s.asr, 4))
                        for n, s in report.by_attack.items()
                    },
                    # The benign control rows stay in `by_attack` (dropping them would hide the
                    # control) but are named here, so a database reader cannot take the baseline's
                    # rate for an attack's under a metric titled "Attack Success Rate". Untagged
                    # rows are the control: `report.eai` tags adversarial attacks only.
                    "baseline_control_attacks": sorted(
                        n for n in report.by_attack if n not in report.eai
                    ),
                },
            },
            {
                # Kept as a separately-named metric so a database consumer cannot read the diluted
                # figure as the attack-success rate.
                "name": "All-episode observed-unsafe rate",
                "detection_method": {"type": "Simulation red-team (benign control included)"},
                "results": {
                    "rate": None if report.attempts == 0 else round(report.asr, 4),
                    "successes": report.successes,
                    "attempts": report.attempts,
                    "ci95": (
                        None if report.attempts == 0 else [round(all_lo, 4), round(all_hi, 4)]
                    ),
                    "note": "Includes the benign control in the denominator; NOT the ASR.",
                },
            },
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
                "url": "https://github.com/provael/provael/blob/main/docs/top10.md",
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
