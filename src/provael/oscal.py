"""Emit a Provael run as NIST OSCAL assessment-results JSON (compliance-as-code).

OSCAL (https://pages.nist.gov/OSCAL/) is NIST's machine-readable model for security assessment
results — the format GRC / ATO tooling ingests. Mapping a Provael run to OSCAL assessment-results
lets buyers pipe ASR evidence straight into those workflows, beyond SARIF.

Mapping: each attack -> an **observation** (method TEST); each EAI risk -> a **risk**; the overall
ASR + benign control -> a **finding**.

DETERMINISM: ids are stable ``uuid5`` derived from the run (no random/clock), so a deterministic
run yields a byte-identical document. Timestamps are not available deterministically here, so
``metadata.last-modified`` is a placeholder the emitter/consumer should stamp at emit time — this
is stated in a metadata property.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from provael.calibration import wilson_ci
from provael.eai import CATALOG
from provael.types import RunReport

#: Filename written into a run's output directory.
OSCAL_JSON = "report.oscal.json"

#: Placeholder timestamp (no deterministic clock available); stamp at emit time if required.
_PLACEHOLDER_TS = "1970-01-01T00:00:00+00:00"

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/provael/provael")


def _uid(report: RunReport, *parts: str) -> str:
    """A stable uuid5 for ``parts`` within this run (deterministic — no random/clock)."""
    name = ":".join((report.policy, report.suite, *parts))
    return str(uuid.uuid5(_NS, name))


def to_oscal(report: RunReport) -> dict[str, object]:
    """Build an OSCAL assessment-results object (as a dict)."""
    observations = [
        {
            "uuid": _uid(report, "obs", name),
            "description": f"Provael attack '{name}': {stat.successes}/{stat.attempts} unsafe.",
            "methods": ["TEST"],
            "props": [
                {"name": "attack", "value": name},
                {"name": "asr", "value": f"{stat.asr:.4f}"},
                {"name": "eai", "value": report.eai[name].id} if name in report.eai else
                {"name": "control", "value": "baseline"},
            ],
        }
        for name, stat in report.by_attack.items()
    ]

    risks = []
    seen: set[str] = set()
    for _attack_name, tag in report.eai.items():
        if tag.id in seen:
            continue
        seen.add(tag.id)
        risk = CATALOG.get(tag.id)
        risks.append({
            "uuid": _uid(report, "risk", tag.id),
            "title": f"{tag.id}: {risk.name if risk is not None else tag.id}",
            "description": f"Embodied AI Security {tag.id} exercised by Provael attacks.",
            "status": "open",
        })

    lo, hi = wilson_ci(report.successes, report.attempts) if report.attempts else (0.0, 0.0)
    finding = {
        "uuid": _uid(report, "finding", "overall"),
        "title": "Overall Attack Success Rate",
        "description": (
            f"ASR {report.asr:.4f} ({report.successes}/{report.attempts}), "
            f"95% CI [{lo:.4f}, {hi:.4f}]"
            + ("" if report.benign_fpr is None else f"; benign FPR {report.benign_fpr:.4f}")
        ),
        "props": [
            {"name": "asr", "value": f"{report.asr:.4f}"},
            {"name": "ci95-low", "value": f"{lo:.4f}"},
            {"name": "ci95-high", "value": f"{hi:.4f}"},
            {"name": "calibrated", "value": str(report.calibrated).lower()},
        ],
    }

    return {
        "assessment-results": {
            "uuid": _uid(report, "assessment-results"),
            "metadata": {
                "title": f"Provael VLA red-team — {report.policy} x {report.suite}",
                "last-modified": _PLACEHOLDER_TS,
                "version": report.tool_version,
                "oscal-version": "1.1.2",
                "props": [
                    {"name": "tool", "value": "Provael"},
                    {"name": "note", "value": "Stamp last-modified at emit time if required."},
                ],
            },
            "import-ap": {"href": ""},
            "results": [
                {
                    "uuid": _uid(report, "result"),
                    "title": "Provael red-team result",
                    "description": "Behavioural-susceptibility measurement via templated attacks.",
                    "start": _PLACEHOLDER_TS,
                    "observations": observations,
                    "risks": risks,
                    "findings": [finding],
                }
            ],
        }
    }


def to_oscal_json(report: RunReport) -> str:
    """Serialise the OSCAL assessment-results as deterministic JSON."""
    return json.dumps(to_oscal(report), indent=2, sort_keys=True)


def write_oscal(report: RunReport, path: Path) -> Path:
    """Write the OSCAL JSON to ``path`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_oscal_json(report), encoding="utf-8")
    return path


__all__ = ["OSCAL_JSON", "to_oscal", "to_oscal_json", "write_oscal"]
