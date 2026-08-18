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

from provael.calibration import wilson_ci
from provael.eai import CATALOG, all_ids, coverage_counts, coverage_headline
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
    # Imported here rather than at module scope, matching the existing deferral for FAMILIES.
    from provael.attacks.registry import FAMILIES
    from provael.defenses.registry import DEFENSES, make_defense

    baseline = len(FAMILIES.get(BASELINE_FAMILY, []))
    total = sum(len(names) for names in FAMILIES.values())
    # Defense counts, DERIVED so they cannot drift from the code. `defenses_measured` reads each
    # Defense.study — the same class attribute `provael list-defenses` uses for its status column —
    # so a defense registered without a published study raises the total and NOT the measured
    # count. The manifest is what a buyer reads; now that the tool files a measured mitigation as
    # conformity evidence, a manifest that could not say how many mitigations exist, or how many are
    # actually measured, was materially incomplete.
    measured = sum(1 for name in DEFENSES if make_defense(name).study)
    return {
        "families_total": len(FAMILIES),
        "families_adversarial": len(FAMILIES) - (1 if baseline else 0),
        "attacks_total": total,
        "attacks_adversarial": total - baseline,
        "attacks_baseline": baseline,
        "defenses_total": len(DEFENSES),
        "defenses_measured": measured,
    }


def _eai_coverage() -> dict[str, Any]:
    """Every Top-10 risk and whether Provael ships attacks for it (independent of any run)."""
    return {
        "counts": coverage_counts(),
        "headline": coverage_headline(),
        "risks": [
            {
                "id": eai_id,
                "name": CATALOG[eai_id].name,
                "coverage": CATALOG[eai_id].coverage.value,
                "coverage_note": CATALOG[eai_id].coverage_note,
            }
            for eai_id in all_ids()
        ],
    }


def _report_digest(report: RunReport) -> str:
    """Delegates to the ONE schema-aware implementation rather than repeating it.

    This used to inline `sha256_hex(canonical_json(...))`, which was identical to
    `execution.report_digest` right up until that one learned to strip fields added after a
    report's own schema_version. A duplicated digest that silently disagrees with the attested
    subject is the worst kind of duplication: both look right, and only the artifact that was
    signed by the other one fails.
    """
    from provael.execution import report_digest

    return report_digest(report)


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
    source_reports: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the deterministic public evidence manifest. ``commit`` must be a pinned ref.

    ``source_reports`` is for a SHARDED run: a ten-task suite executed one task per container has
    ten independent ``report.json`` files and no single artifact to digest. Pass the per-shard
    ``{path, sha256}`` list and the manifest records all of them, so a consumer can re-fetch and
    verify each shard independently. ``source_report_sha256`` then digests the COMBINED view, which
    is reproducible from those shards but is not itself a committed file — see
    :mod:`provael.combine` for why no merged ``report.json`` is ever written.

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
        # Present ONLY for a sharded run, and its presence is the signal that this manifest
        # describes several artifacts rather than one. A consumer that ignores it still gets a
        # correct digest of the combined view; a consumer that reads it can verify every shard.
        **({"source_reports": source_reports} if source_reports else {}),
        **({"shards": len(source_reports)} if source_reports else {}),
        "policy": report.policy,
        "suite": report.suite,
        "evidence_state": evidence_state_of(report).value,
        "calibrated": report.calibrated,
        "release_verdict": decision.verdict.value,
        "registry": _registry_counts(),
        # All ten Top-10 risks with their coverage state. Carried in the manifest — not only in
        # the human-readable report — so a downstream consumer reading this file learns which
        # risks Provael does not test, instead of inferring coverage from which ids happen to
        # appear under `per_attack`.
        "eai_coverage": _eai_coverage(),
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
    report: RunReport,
    *,
    repository: str,
    commit: str,
    regulatory_clock_version: str,
    source_reports: list[dict[str, str]] | None = None,
) -> str:
    """Serialise the manifest to stable, indented JSON (keys sorted; trailing newline)."""
    manifest = build_evidence_manifest(
        report, repository=repository, commit=commit,
        regulatory_clock_version=regulatory_clock_version,
        source_reports=source_reports,
    )
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


__all__ = [
    "EVIDENCE_MANIFEST_FORMAT",
    "build_evidence_manifest",
    "to_evidence_manifest_json",
]
