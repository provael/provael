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
from provael.types import MEASURED_REAL_TRANSFER, STUB_VALIDATED_SCAFFOLDING, RunReport

#: Filename written into a run's output directory.
OSCAL_JSON = "report.oscal.json"

#: Placeholder timestamp (no deterministic clock available); stamp at emit time if required.
_PLACEHOLDER_TS = "1970-01-01T00:00:00+00:00"

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/provael/provael")


def _uid(report: RunReport, *parts: str) -> str:
    """A stable uuid5 for ``parts`` within this run (deterministic — no random/clock)."""
    name = ":".join((report.policy, report.suite, *parts))
    return str(uuid.uuid5(_NS, name))


def to_oscal(
    report: RunReport,
    *,
    profile_href: str | None = None,
    reviewed_control_ids: list[str] | None = None,
) -> dict[str, object]:
    """Build an OSCAL assessment-results object (as a dict).

    With no keyword args the output is byte-identical to the historical exporter (empty
    ``import-ap.href``, no reviewed-controls). The ``certify`` path passes ``profile_href`` (the
    conformity profile the results are assessed against) and ``reviewed_control_ids`` (the crosswalk
    clauses), which populate ``import-ap.href`` and an OSCAL ``reviewed-controls`` block so a GRC
    consumer can bind each finding to the standard clause it informs.
    """
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

    adv_rate, adv_s, adv_n = report.adversarial_headline()
    lo, hi = wilson_ci(adv_s, adv_n) if adv_n else (0.0, 0.0)
    # D1: the same run-level honesty tier the compliance export and attestation carry, so an OSCAL
    # consumer cannot misread stub scaffolding as a conformity-relevant real-transfer measurement.
    transfer_status = (
        MEASURED_REAL_TRANSFER
        if report.policy != "stub" and report.suite != "stub"
        else STUB_VALIDATED_SCAFFOLDING
    )
    finding = {
        "uuid": _uid(report, "finding", "overall"),
        "title": "Adversarial Attack Success Rate",
        "description": (
            f"Adversarial ASR {adv_rate:.4f} ({adv_s}/{adv_n}), 95% CI [{lo:.4f}, {hi:.4f}]; "
            f"all-episode observed-unsafe {report.asr:.4f} ({report.successes}/{report.attempts})"
            + ("" if report.benign_fpr is None else f"; benign FPR {report.benign_fpr:.4f}")
        ),
        "props": [
            {"name": "adversarial-asr", "value": f"{adv_rate:.4f}"},
            {"name": "adversarial-n", "value": str(adv_n)},
            {"name": "all-episode-unsafe-rate", "value": f"{report.asr:.4f}"},
            {"name": "ci95-low", "value": f"{lo:.4f}"},
            {"name": "ci95-high", "value": f"{hi:.4f}"},
            {"name": "calibrated", "value": str(report.calibrated).lower()},
            {"name": "transfer-status", "value": transfer_status},
        ],
    }

    result: dict[str, object] = {
        "uuid": _uid(report, "result"),
        "title": "Provael red-team result",
        "description": "Behavioural-susceptibility measurement via templated attacks.",
        "start": _PLACEHOLDER_TS,
        "observations": observations,
        "risks": risks,
        "findings": [finding],
    }
    # certify path: bind the findings to the conformity clauses under review, so a GRC consumer
    # reads which standard controls this assessment informs. Omitted (and thus byte-identical to the
    # historical output) when no crosswalk is supplied.
    if reviewed_control_ids:
        result["reviewed-controls"] = {
            "control-selections": [
                {"include-controls": [{"control-id": cid} for cid in reviewed_control_ids]}
            ]
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
            "import-ap": {"href": profile_href or ""},
            "results": [result],
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
