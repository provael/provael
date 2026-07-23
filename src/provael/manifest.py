"""A deterministic public evidence manifest — the JSON a website can consume safely (Phase 10).

``build_evidence_manifest`` is a pure function of a :class:`~provael.types.RunReport` plus a
**pinned** repository + commit. It restates the exact metric semantics (adversarial ASR vs the
all-episode observed rate vs the benign control), the per-attack results with Wilson intervals and
applicability (N/A stays N/A, never a fabricated 0), the evidence-ladder state, the verdict, and the
limitations — and it never claims hardware / calibration / external reproduction the report has not
earned. It carries no wall-clock (the commit is passed in), so the same report+commit yields
byte-identical bytes.
"""

from __future__ import annotations

import json
from typing import Any

from provael.attest import canonical_json, sha256_hex
from provael.calibration import wilson_ci
from provael.evidence import evidence_state_of
from provael.scoring.asr import (
    BASELINE_FAMILY,
    adversarial_asr,
    all_episode_observed_unsafe_rate,
    benign_unsafe_rate,
)
from provael.types import RunReport
from provael.verdict import release_verdict

#: Public evidence-manifest format id.
EVIDENCE_MANIFEST_FORMAT = "provael-evidence-manifest/v1"


def _registry_counts() -> dict[str, int]:
    from provael.attacks.registry import FAMILIES

    baseline = len(FAMILIES.get(BASELINE_FAMILY, []))
    total = sum(len(names) for names in FAMILIES.values())
    return {
        "families_total": len(FAMILIES),
        "families_adversarial": len(FAMILIES) - (1 if baseline else 0),
        "attacks_total": total,
        "attacks_adversarial": total - baseline,
        "attacks_baseline": baseline,
    }


def _report_digest(report: RunReport) -> str:
    return sha256_hex(canonical_json(json.loads(report.model_dump_json())))


def _per_attack(report: RunReport) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attack, stat in report.by_attack.items():
        applicable = stat.attempts > 0
        rows.append({
            "attack": attack,
            "eai": report.eai[attack].id if attack in report.eai else None,
            "role": report.roles.get(attack),
            "successes": stat.successes,
            "attempts": stat.attempts,
            "applicable": applicable,
            # N/A stays N/A — never a fabricated 0
            "rate": stat.measured_rate,
            "wilson_ci95": list(wilson_ci(stat.successes, stat.attempts)) if applicable else None,
        })
    return rows


def build_evidence_manifest(
    report: RunReport,
    *,
    repository: str,
    commit: str,
    regulatory_clock_version: str,
) -> dict[str, Any]:
    """Build the deterministic public evidence manifest. ``commit`` must be a pinned ref.

    Raises ``ValueError`` if ``commit`` is empty — a manifest must pin its source, never a moving
    branch.
    """
    if not commit.strip():
        raise ValueError("evidence manifest requires a pinned commit (never a moving branch)")

    adv = adversarial_asr(report.results)
    allep = all_episode_observed_unsafe_rate(report.results)
    a_lo, a_hi = wilson_ci(adv.successes, adv.attempts) if adv.attempts else (None, None)
    decision = release_verdict(report)
    return {
        "format": EVIDENCE_MANIFEST_FORMAT,
        "tool_version": report.tool_version,
        "report_schema_version": report.schema_version,
        "repository": repository,
        "commit": commit,
        "source_report_sha256": _report_digest(report),
        "policy": report.policy,
        "suite": report.suite,
        "evidence_state": evidence_state_of(report).value,
        "calibrated": report.calibrated,
        "release_verdict": decision.verdict.value,
        "registry": _registry_counts(),
        "metric_semantics": {
            "adversarial_asr": "successes / attempts over ADVERSARIAL episodes (benign excluded "
            "by role); the headline.",
            "all_episode_observed_unsafe_rate": "unsafe rate over ALL applicable episodes (benign "
            "included); diluted below the adversarial ASR — NOT the attack rate.",
            "benign_unsafe_rate": "the benign-control false-positive rate (the ASR's control).",
        },
        "adversarial_asr": {
            "successes": adv.successes, "attempts": adv.attempts, "rate": adv.measured_rate,
            "wilson_ci95": [a_lo, a_hi] if adv.attempts else None,
        },
        "all_episode_observed_unsafe_rate": {
            "successes": allep.successes, "attempts": allep.attempts, "rate": allep.measured_rate,
        },
        "benign_unsafe_rate": benign_unsafe_rate(report.results),
        "per_attack": _per_attack(report),
        "regulatory_clock_version": regulatory_clock_version,
        "limitations": [
            "Simulation only: a redirection/activation in sim is a robustness signal, not a "
            "real-world exploit; cross-model transfer is claimed only where a real policy ran.",
            f"Evidence state is '{evidence_state_of(report).value}': no hardware, calibration, or "
            "external-reproduction claim is made beyond what this state supports.",
            "The all-episode observed-unsafe rate includes the benign control and is NOT the "
            "adversarial ASR.",
            "Not-applicable attacks are N/A (excluded from the denominator), never scored as 0%.",
        ],
    }


def to_evidence_manifest_json(
    report: RunReport, *, repository: str, commit: str, regulatory_clock_version: str
) -> str:
    """Serialise the manifest to stable, indented JSON (keys sorted; trailing newline)."""
    manifest = build_evidence_manifest(
        report, repository=repository, commit=commit,
        regulatory_clock_version=regulatory_clock_version,
    )
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


__all__ = [
    "EVIDENCE_MANIFEST_FORMAT",
    "build_evidence_manifest",
    "to_evidence_manifest_json",
]
