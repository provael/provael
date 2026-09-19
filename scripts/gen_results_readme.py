#!/usr/bin/env python3
"""Render a results directory's README.md from its own artifacts — no number typed by hand.

WHY. Every committed results directory carries a README whose table restates the shards'
numbers, and a restated number is the thing this project keeps finding wrong months later (a
family count that survived a release, a control arm named as an attack). This script reads the
``report.json`` shards (or a single ``report.json``), the ``execution-manifest.json`` beside each,
and ``aggregate.json`` when the sweep script has written one, and renders the README from those
alone. Re-running it on an unchanged directory is a no-op; ``--check`` fails if it would differ.

WHAT IT RENDERS. The header line (episodes, tasks, arms, seeds, dates, tool version, hardware);
the per-arm table with the semantic role, pooled counts, the Wilson interval and — when the
benign arm is present — the paired McNemar p-value, Holm adjustment and the task-clustered
bootstrap interval; the benign floor and the controls called out by name; the competence
control (clean task success); a per-task grid; provenance; and a fixed "what this does not
establish" block. Arms with no applicable episode are printed as N/A, never as 0.

WHAT IT DOES NOT DO. It does not decide what a result means. The prose a maintainer wants to add
— why the run exists, what the numbers change — goes in a ``NOTES.md`` beside the shards, which
is included verbatim under its own heading and is the one hand-written part.

Usage::

    python scripts/gen_results_readme.py results/smolvla_libero_object_suite_2026-09-14
    python scripts/gen_results_readme.py results/... --check   # fail if README.md would change
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from provael.calibration import wilson_ci  # noqa: E402
from provael.campaign import REQUIRED_PROVENANCE, provenance_gaps  # noqa: E402
from provael.scoring.asr import semantic_role  # noqa: E402
from provael.scoring.paired import (  # noqa: E402
    cluster_bootstrap_ci,
    holm_bonferroni,
    paired_by_attack,
)
from provael.types import AttackResult  # noqa: E402

ROLE_LABEL = {
    "benign-control": "benign control (the floor)",
    "harmless-variation": "harmless-variation control",
    "adversarial-treatment": "adversarial treatment",
}


def _pct(x: float) -> str:
    return f"{100.0 * x:.0f}%"


def _load_shards(run_dir: Path) -> list[tuple[Path, dict[str, Any], dict[str, Any] | None]]:
    """``(shard_dir, report, manifest)`` for every ``report.json`` under ``run_dir``."""
    candidates = [run_dir] if (run_dir / "report.json").exists() else sorted(
        p.parent for p in run_dir.glob("*/report.json")
    )
    shards = []
    for shard in candidates:
        report = json.loads((shard / "report.json").read_text(encoding="utf-8"))
        manifest_path = shard / "execution-manifest.json"
        manifest = None
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        shards.append((shard, report, manifest))
    if not shards:
        raise SystemExit(f"no report.json under {run_dir}")
    return shards


Shard = tuple[Path, dict[str, Any], dict[str, Any] | None]


def _results(shards: list[Shard]) -> list[AttackResult]:
    out: list[AttackResult] = []
    for _, report, _ in shards:
        out.extend(AttackResult(**r) for r in report.get("results", []))
    return out


def _dates(shards: list[Shard]) -> str:
    starts = sorted(m["started_at"][:10] for _, _, m in shards if m and m.get("started_at"))
    ends = sorted(m["ended_at"][:10] for _, _, m in shards if m and m.get("ended_at"))
    if not starts or not ends:
        return "dates not recorded"
    return starts[0] if starts[0] == ends[-1] else f"{starts[0]} to {ends[-1]}"


def _field(shards: list[Shard], key: str) -> str:
    values = sorted({str(m.get(key)) for _, _, m in shards if m and m.get(key) is not None})
    return ", ".join(values) if values else "not recorded"


def render(run_dir: Path) -> str:
    shards = _load_shards(run_dir)
    results = _results(shards)
    reports = [r for _, r, _ in shards]
    aggregate_path = run_dir / "aggregate.json"
    aggregate = (
        json.loads(aggregate_path.read_text(encoding="utf-8")) if aggregate_path.exists() else None
    )
    mcnemar_from_aggregate = (aggregate or {}).get("mcnemar") or {}

    tasks = sorted({r.task for r in results})
    arms = list(dict.fromkeys(a for report in reports for a in report.get("attacks", [])))
    seeds = sorted({r.seed for r in results})
    versions = sorted({str(r.get("tool_version")) for r in reports})
    policy = ", ".join(sorted({str(r.get("policy")) for r in reports}))
    model = ", ".join(sorted({str(r.get("model")) for r in reports if r.get("model")})) or "—"
    suite = ", ".join(sorted({str(r.get("suite")) for r in reports}))
    horizon = ", ".join(sorted({str(r.get("horizon")) for r in reports}))

    by_attack: dict[str, list[AttackResult]] = defaultdict(list)
    roles: dict[str, str] = {}
    for r in results:
        by_attack[r.attack].append(r)
        roles.setdefault(r.attack, semantic_role(r))

    # Paired statistics: from aggregate.json when the sweep script wrote one (the same functions),
    # else computed here — same code path, same numbers.
    paired = paired_by_attack(results)
    names = [a for a in arms if a in paired] or sorted(paired)
    holm: dict[str, tuple[float, bool]] = {}
    if names:
        adjusted, reject = holm_bonferroni([paired[n].p_value for n in names])
        holm = {n: (adj, rej) for n, adj, rej in zip(names, adjusted, reject, strict=True)}

    title = run_dir.name.replace("_", " ")
    lines: list[str] = [
        f"# {title}",
        "",
        f"**{len(results)} episode records · {len(tasks)} task(s) · {len(arms)} arm(s) · "
        f"{len(seeds)} seed(s) · {_dates(shards)} · provael {', '.join(versions)}**",
        "",
        f"- **Policy:** `{policy}` — checkpoint `{model}`",
        f"- **Suite:** `{suite}`; tasks: {', '.join(f'`{t}`' for t in tasks)}",
        f"- **Horizon:** {horizon} steps; base seed {reports[0].get('seed')}",
        f"- **Hardware:** {_field(shards, 'hardware')} · accelerator "
        f"{_field(shards, 'accelerator')} · precision {_field(shards, 'precision')}",
        f"- **Source commit recorded:** {_field(shards, 'commit')}",
        "",
        "> Generated by `scripts/gen_results_readme.py` from the shards' own `report.json`,",
        "> `execution-manifest.json` and `aggregate.json`. Each shard's `report.json` is the",
        "> attestable artifact; this page is an analysis of them and is not itself a report.",
        "",
        "## Result",
        "",
        "| arm | role | pooled | 95% Wilson | McNemar vs `none` | Holm | task-clustered 95% CI "
        "| verdict |",
        "| --- | --- | ---: | --- | ---: | ---: | --- | --- |",
    ]
    for name in arms:
        rows = by_attack.get(name, [])
        applicable = [r for r in rows if r.applicable]
        na = len(rows) - len(applicable)
        successes = sum(1 for r in applicable if r.success)
        role = roles.get(name, "adversarial-treatment")
        if not applicable:
            lines.append(
                f"| `{name}` | {ROLE_LABEL.get(role, role)} | **not applicable** ({na} records) "
                "| — | — | — | — | not measured on this suite |"
            )
            continue
        lo, hi = wilson_ci(successes, len(applicable))
        pooled = f"**{successes}/{len(applicable)} ({_pct(successes / len(applicable))})**"
        suffix = f" ({na} N/A)" if na else ""
        if name in paired and role == "adversarial-treatment":
            m = paired[name]
            agg = mcnemar_from_aggregate.get(name, {})
            ci = agg.get("clustered_ci95")
            if ci is None and len(tasks) >= 2:
                computed = cluster_bootstrap_ci(results, attack=name)
                ci = list(computed) if computed is not None else None
            if ci is not None:
                ci_txt = f"[{_pct(ci[0])}, {_pct(ci[1])}]"
            elif len(tasks) < 2:
                ci_txt = "— (single task)"
            else:
                ci_txt = "— (degenerate: no discordant tasks)"
            adj, rej = holm.get(name, (float("nan"), False))
            verdict = "**survives**" if rej else "rejected"
            lines.append(
                f"| `{name}` | {ROLE_LABEL[role]} | {pooled}{suffix} | [{_pct(lo)}, {_pct(hi)}] "
                f"| p={m.p_value:.2g} ({m.attack_only}–{m.benign_only}) | {adj:.2g} "
                f"| {ci_txt} | {verdict} |"
            )
        else:
            lines.append(
                f"| `{name}` | {ROLE_LABEL.get(role, role)} | {pooled}{suffix} "
                f"| [{_pct(lo)}, {_pct(hi)}] | — | — | — | "
                + (
                    "the floor every treatment is read against |"
                    if role == "benign-control"
                    else "enters neither the ASR nor the floor |"
                )
            )
    lines += [
        "",
        "McNemar is paired at matched (task, seed) against the benign arm; the pair counts are "
        "attack-only–benign-only discordant episodes. Holm adjusts across the adversarial arms of "
        "this run. The task-clustered interval resamples whole tasks (an attack that works on one "
        "task works on all its seeds), so it is the honest width; it needs at least two tasks.",
    ]

    # Competence control
    clean = [r.get("clean_task_success_rate") for r in reports]
    clean = [c for c in clean if c is not None]
    if clean:
        benign = [
            r for r in by_attack.get("none", []) if r.applicable and r.task_success is not None
        ]
        if benign:
            ok = sum(1 for r in benign if r.task_success)
            lines += [
                "",
                f"**Competence control (clean task success on the benign arm):** "
                f"{ok}/{len(benign)} ({_pct(ok / len(benign))}). A policy that cannot do the task "
                "cannot be redirected "
                "from it; read every rate above against this.",
            ]

    # Per-task grid
    if len(tasks) > 1:
        header = "| task | " + " | ".join(f"`{a}`" for a in arms) + " |"
        rule = "| --- |" + " ---: |" * len(arms)
        lines += ["", "## Per task (unsafe / applicable)", "", header, rule]
        for task in tasks:
            cells = []
            for name in arms:
                rows = [r for r in by_attack.get(name, []) if r.task == task and r.applicable]
                unsafe = sum(1 for r in rows if r.success)
                cells.append("—" if not rows else f"{unsafe}/{len(rows)}")
            lines.append(f"| `{task}` | " + " | ".join(cells) + " |")

    shard_names = [
        f"`{(s.relative_to(run_dir) if s != run_dir else Path('.'))}/report.json`"
        for s, _, _ in shards
    ]
    aggregated_with = (
        f"; aggregated with {aggregate.get('aggregated_with')}"
        if aggregate and aggregate.get("aggregated_with")
        else ""
    )
    notes = run_dir / "NOTES.md"
    if notes.exists():
        lines += ["", "## Notes (hand-written)", "", notes.read_text(encoding="utf-8").strip()]

    # Required provenance, per shard, by value. Gaps are stated and labelled unknown — never
    # backfilled from what the operator remembers — and the aggregate is named as derived from
    # the shards, each of which keeps its own manifest and digest.
    gap_lines: list[str] = []
    complete = 0
    for shard, _, manifest in shards:
        rel = shard.relative_to(run_dir) if shard != run_dir else Path(".")
        manifest_path = shard / "execution-manifest.json"
        if manifest is None:
            gap_lines.append(f"  - `{rel}`: no execution manifest (unknown; not backfilled)")
            continue
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:16]
        gaps = provenance_gaps(manifest)
        if gaps:
            gap_lines.append(
                f"  - `{rel}` (manifest sha256 `{digest}`): missing {', '.join(gaps)} — recorded "
                "as unknown, not backfilled"
            )
        else:
            complete += 1
            gap_lines.append(f"  - `{rel}` (manifest sha256 `{digest}`): complete")
    provenance_state = (
        "complete on every shard"
        if complete == len(shards)
        else f"complete on {complete} of {len(shards)} shard(s); the gaps stay unknown"
    )

    lines += [
        "",
        "## Provenance",
        "",
        "- Shards: " + ", ".join(shard_names),
        f"- Tool version(s) in the shards: {', '.join(versions)}{aggregated_with}",
        f"- Dates (UTC, execution manifests): {_dates(shards)}",
        f"- OS / Python: {_field(shards, 'os')} / {_field(shards, 'python_version')}",
        f"- Evidence state: {_field(shards, 'evidence_state')} · release verdict as recorded by "
        f"the run: {_field(shards, 'release_verdict')} (a verdict recorded by a run before 0.43.0 "
        "was a default gate's answer, not a decision under a named protocol)",
        f"- Required provenance ({', '.join(REQUIRED_PROVENANCE)}): {provenance_state}",
        *gap_lines,
        "- Every aggregate number above is derived from these shards; each shard keeps its own "
        "execution manifest, and no combined report.json exists or is attested.",
        "",
        "## What this does not establish",
        "",
        "- Nothing about any physical robot: every episode is a simulator rollout.",
        "- Nothing about other checkpoints of the same model family, other suites, or other tasks.",
        "- No conformity with any standard or regulation; `provael report --format test-report` "
        "on a "
        "shard renders the assessor-shaped document, and it says the same.",
        "- The policy samples its actions: episodes are seeded and the applied seed is recorded, "
        "so a "
        "re-execution matches in distribution, not byte for byte.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--check", action="store_true", help="fail if README.md would change")
    args = parser.parse_args()
    text = render(args.run_dir)
    target = args.run_dir / "README.md"
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != text:
            print(f"{target} is stale; rerun without --check", file=sys.stderr)
            return 1
        print(f"ok       {target}")
        return 0
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
