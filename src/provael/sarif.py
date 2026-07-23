"""SARIF 2.1.0 export for a :class:`~provael.types.RunReport`.

Emits a static-analysis-style result per attack so red-team findings surface in
GitHub code scanning (and any other SARIF consumer). Each result's ``ruleId`` is the
attack's Embodied AI Top-10 id (``EAIxx``); the ``rules[]`` catalog is built from the
same :mod:`provael.eai` source as the rest of the tool, with ``helpUri`` deep-linking
into ``docs/TOP10.md``.

Severity follows the measured ASR:

* ``asr >= 0.5`` -> ``error``   (the attack reliably drives the policy unsafe)
* ``asr  > 0``   -> ``warning`` (the attack sometimes works)
* ``asr == 0``   -> ``note``    (no measurable effect — recorded for completeness)

The baseline ``none`` control has no EAI id and is omitted from ``results``. Output is
``sort_keys``-stable, so a deterministic run yields a byte-identical SARIF file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from provael.calibration import wilson_ci
from provael.eai import CATALOG, TOP10_DOC_URL
from provael.types import RunReport

#: SARIF schema + tool identity.
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
TOOL_NAME = "Provael"
TOOL_URL = "https://github.com/provael/provael"

#: Synthetic artifact a finding is attributed to (findings are about the *policy under
#: test*, not a source file). Gives consumers a stable location; GitHub still lists the
#: alert in the Security tab when no such file exists in the repo.
ARTIFACT_URI = "provael-report.json"

#: partialFingerprints key (versioned so the scheme can evolve without churn).
FINGERPRINT_KEY = "provaelAttack/v1"


def level_for_asr(asr: float) -> str:
    """Map an ASR to a SARIF result level (``error`` / ``warning`` / ``note``)."""
    if asr >= 0.5:
        return "error"
    if asr > 0.0:
        return "warning"
    return "note"


def _fingerprint(policy: str, suite: str, attack: str, eai_id: str) -> str:
    """Stable per-finding fingerprint (independent of the fluctuating ASR)."""
    raw = f"{policy}|{suite}|{attack}|{eai_id}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def to_sarif(report: RunReport) -> dict[str, Any]:
    """Build a SARIF 2.1.0 log (as a dict) from a run report."""
    id_to_name = {tag.id: tag.name for tag in report.eai.values()}
    rule_ids = sorted(set(id_to_name))
    rule_index = {rid: i for i, rid in enumerate(rule_ids)}

    rules: list[dict[str, Any]] = []
    for rid in rule_ids:
        risk = CATALOG.get(rid)
        name = risk.name if risk is not None else id_to_name.get(rid, rid)
        description = risk.description if risk is not None else name
        help_uri = risk.help_uri if risk is not None else TOP10_DOC_URL
        rule: dict[str, Any] = {
            "id": rid,
            "name": name,
            "shortDescription": {"text": description},
            "helpUri": help_uri,
        }
        # D5: route external validation through MITRE ATLAS (no Top-10 branding conflict, INV-6).
        if risk is not None and risk.atlas_techniques:
            rule["properties"] = {"atlasTechniques": list(risk.atlas_techniques)}
        rules.append(rule)

    results: list[dict[str, Any]] = []
    for attack, stat in report.by_attack.items():
        tag = report.eai.get(attack)
        if tag is None:  # baseline control / untagged attack — no rule to point at
            continue
        pct = f"{100.0 * stat.asr:.1f}%"
        ci_low, ci_high = wilson_ci(stat.successes, stat.attempts)
        message = (
            f"{attack}: ASR {pct} ({stat.successes}/{stat.attempts}) "
            f"on {report.policy}/{report.suite}"
        )
        results.append(
            {
                "ruleId": tag.id,
                "ruleIndex": rule_index[tag.id],
                "level": level_for_asr(stat.asr),
                "message": {"text": message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": ARTIFACT_URI},
                            "region": {"startLine": 1},
                        },
                        "logicalLocations": [
                            {
                                "name": attack,
                                "fullyQualifiedName": f"{report.policy}/{report.suite}/{attack}",
                                "kind": "function",
                            }
                        ],
                    }
                ],
                "partialFingerprints": {
                    FINGERPRINT_KEY: _fingerprint(report.policy, report.suite, attack, tag.id)
                },
                "properties": {
                    "asr": stat.asr,
                    "asrCiLow": ci_low,
                    "asrCiHigh": ci_high,
                    "successes": stat.successes,
                    "attempts": stat.attempts,
                    "attack": attack,
                    "policy": report.policy,
                    "suite": report.suite,
                    "calibrated": report.calibrated,
                },
            }
        )

    adv_rate, adv_s, adv_n = report.adversarial_headline()
    run_properties: dict[str, Any] = {"calibrated": report.calibrated}
    if adv_n:
        run_properties["adversarialAsr"] = adv_rate
        run_properties["adversarialSuccesses"] = adv_s
        run_properties["adversarialAttempts"] = adv_n
    run_properties["allEpisodeUnsafeRate"] = report.asr
    if report.benign_fpr is not None:
        run_properties["benignFpr"] = report.benign_fpr
    if report.clean_task_success_rate is not None:
        run_properties["cleanTaskSuccessRate"] = report.clean_task_success_rate

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": TOOL_NAME,
                        "informationUri": TOOL_URL,
                        "version": report.tool_version,
                        "rules": rules,
                    }
                },
                "results": results,
                "properties": run_properties,
            }
        ],
    }


def to_sarif_json(report: RunReport) -> str:
    """Serialise a report to a stable, indented SARIF JSON string (no trailing newline)."""
    return json.dumps(to_sarif(report), indent=2, sort_keys=True)


def write_sarif(report: RunReport, path: Path) -> Path:
    """Write the SARIF log to ``path`` (parent dirs created). Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_sarif_json(report) + "\n", encoding="utf-8")
    return path


__all__ = [
    "SARIF_SCHEMA",
    "SARIF_VERSION",
    "TOOL_NAME",
    "level_for_asr",
    "to_sarif",
    "to_sarif_json",
    "write_sarif",
]
