"""Combine the per-task reports of a SHARDED run into one in-memory view.

WHY A SHARDED RUN EXISTS AT ALL. A ten-task LIBERO screen is ~15 GPU-hours, and `provael attack`
cannot resume — :mod:`provael.ledger` was built for exactly that and is not wired into the runner.
So the suite run is executed one task per container and writes ten independent ``report.json``
files. Each is a complete, self-describing artifact of its own task.

WHAT THIS IS FOR, AND WHAT IT IS NOT. The public evidence manifest describes ONE measurement, and
a suite result measured across ten shards has no single report to point at. This builds the view
those cross-shard numbers are computed from.

**It must never be written to disk as ``report.json``.** A file with that name is treated as an
attestable artifact everywhere in this project — :func:`provael.attest` signs one, the freshness
badge dates one, the manifest digests one — and a combined view has no single execution behind it
to attest. Writing it would produce a file that looks signable and is not, which is the precise
failure the sharded design was chosen to avoid. :func:`combine_reports` returns an object; nothing
here serialises it, and :mod:`provael.manifest` records EVERY shard's digest rather than one.

WHY THIS DOES NOT REFACTOR THE RUNNER. The obvious alternative is to extract ``runner.run``'s
35-field ``RunReport`` construction into a shared builder and call it from both paths. That
construction is the most determinism-critical code in the project — 44 test modules assert
byte-identical output around it — and it takes live objects (a loaded policy, resolved attack
instances) that a shard on disk does not have. Recomputing here from the same scoring functions
leaves the runner untouched and byte-identical, which is the cheaper guarantee.

THE INVARIANTS ARE CHECKED, NOT ASSUMED. Shards that disagree on the policy, checkpoint, suite,
horizon or tool version are not the same experiment, and averaging them would produce a number
describing nothing. :func:`combine_reports` raises rather than silently pooling them.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.calibration import anytime_ci, wilson_ci
from provael.report import REPORT_JSON
from provael.scoring.asr import (
    adversarial_asr,
    asr_std,
    by_attack,
    by_task,
    clean_task_success_rate,
    matched_benign_fpr,
    overall_stat,
    semantic_role,
    succ_but_unsafe,
)
from provael.types import RunReport

#: Fields every shard of one experiment must agree on. A difference in any of them means the shards
#: are not measuring the same thing, and pooling them would produce a rate describing no run that
#: ever happened. `seed` and `tasks` are deliberately absent — they are what a shard VARIES.
INVARIANT_FIELDS = (
    "tool_version",
    "schema_version",
    "policy",
    "model",
    "suite",
    "horizon",
    "evidence_state",
    "accelerator",
    "precision",
)


class ShardMismatchError(ValueError):
    """Raised when shards disagree on something that makes them one experiment."""


def load_shards(run_dir: Path) -> list[tuple[Path, RunReport]]:
    """Every ``<run_dir>/*/report.json``, sorted by path, with the path it came from.

    The path is returned alongside the report because the manifest records a digest PER SHARD, and
    a digest without the artifact it describes is not provenance.
    """
    paths = sorted(run_dir.glob(f"*/{REPORT_JSON}"))
    return [(p, RunReport.model_validate_json(p.read_text(encoding="utf-8"))) for p in paths]


def is_sharded(run_dir: Path) -> bool:
    """True when ``run_dir`` holds shard subdirectories rather than its own ``report.json``.

    A directory with BOTH is ambiguous and reads as single-run, because that is the older shape and
    a caller pointing at it means the report they can see.
    """
    return not (run_dir / REPORT_JSON).is_file() and bool(list(run_dir.glob(f"*/{REPORT_JSON}")))


def combine_reports(reports: list[RunReport]) -> RunReport:
    """One :class:`RunReport`-shaped view over the union of every shard's episodes.

    Every derived quantity is RECOMPUTED from the pooled episodes with the same scoring functions
    the runner uses — never averaged from the shards' own summaries, which would weight ten unequal
    shards equally and is wrong whenever they differ in size.

    Raises:
        ShardMismatchError: if the shards disagree on an :data:`INVARIANT_FIELDS` value, or if the
            list is empty.
    """
    if not reports:
        raise ShardMismatchError("no shards to combine")

    head = reports[0]
    for field in INVARIANT_FIELDS:
        values = {getattr(r, field) for r in reports}
        if len(values) > 1:
            raise ShardMismatchError(
                f"shards disagree on {field!r}: {sorted(map(str, values))}. These are not the same "
                f"experiment, and pooling them would report a rate describing no run that happened."
            )

    results = [r for report in reports for r in report.results]
    overall = overall_stat(results)
    adversarial = adversarial_asr(results)
    attack_breakdown = by_attack(results)
    baseline = attack_breakdown.get("none")
    n_seeds = len({r.seed for r in results})

    # `episodes` is the per-(task, attack) count, so it is the SHARD's value, not the sum: every
    # shard ran the same number per cell and summing them would report ten times the truth.
    episodes = head.episodes
    tasks = sorted({t for r in reports for t in r.tasks})
    attacks = sorted({a for r in reports for a in r.attacks})

    return RunReport(
        tool_version=head.tool_version,
        schema_version=head.schema_version,
        evidence_state=head.evidence_state,
        policy=head.policy,
        model=head.model,
        suite=head.suite,
        attacks=attacks,
        tasks=tasks,
        episodes=episodes,
        horizon=head.horizon,
        seed=min(r.seed for r in reports),
        attempts=overall.attempts,
        successes=overall.successes,
        asr=overall.asr,
        adversarial_asr=adversarial.measured_rate,
        adversarial_attempts=adversarial.attempts,
        adversarial_successes=adversarial.successes,
        asr_std=asr_std(results),
        stochastic=any(r.stochastic for r in reports),
        ci95=wilson_ci(overall.successes, overall.attempts) if overall.attempts else None,
        anytime_ci=anytime_ci(overall.successes, overall.attempts) if overall.attempts else None,
        seeds=n_seeds,
        preliminary=n_seeds < 5,
        accelerator=head.accelerator,
        precision=head.precision,
        # Calibrated only if EVERY shard was. One uncalibrated task means the pooled predicate is
        # not calibrated, and the weaker claim is the true one.
        calibrated=all(r.calibrated for r in reports),
        benign_fpr=baseline.asr if baseline is not None else None,
        matched_benign_fpr=matched_benign_fpr(results),
        succ_but_unsafe=succ_but_unsafe(results),
        clean_task_success_rate=clean_task_success_rate(results),
        calibration={k: v for r in reports for k, v in r.calibration.items()},
        by_attack=attack_breakdown,
        by_task=by_task(results),
        eai={k: v for r in reports for k, v in r.eai.items()},
        roles={r.attack: semantic_role(r) for r in results},
        results=results,
    )


def shard_digests(shards: list[tuple[Path, RunReport]], *, root: Path) -> list[dict[str, str]]:
    """Per-shard provenance: the relative path and the sha256 of its canonical report bytes.

    Ten digests rather than one, because there is no single artifact to digest. A consumer can
    re-fetch each shard and verify it independently, which a merged hash would not allow.
    """
    from provael.attest import canonical_json, sha256_hex

    out: list[dict[str, str]] = []
    for path, report in shards:
        digest = sha256_hex(canonical_json(json.loads(report.model_dump_json())))
        out.append({"path": path.relative_to(root).as_posix(), "sha256": digest})
    return out


__all__ = [
    "INVARIANT_FIELDS",
    "ShardMismatchError",
    "combine_reports",
    "is_sharded",
    "load_shards",
    "shard_digests",
]
