#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Export the per-step actions of committed LIBERO runs as plain JSON, keyed by task, seed and arm.

    python examples/rda-export/rda_export.py
    python examples/rda-export/rda_export.py RUN_DIR [RUN_DIR ...] --out DIR

Offline and CPU-only. With no arguments it reads the two runs below and writes
``runs/rda-export/<run>.rda.json`` for each:

- ``results/smolvla_libero_object_suite_2026-09-14``, the run with envelope exits;
- ``results/smolvla_libero_10_2026-09-14``, the negative control, where nothing left the envelope.

WHY. RDA (https://github.com/liesliy/rda) flags action-level pathologies in robot trajectories:
spikes, discontinuities, freezes. The question raised on Lifelong-Robot-Learning/LIBERO#148 is
whether those flags separate the episodes that left the keep-out envelope from their benign pairs.
This writes what that test needs and nothing else: each episode's ``decisions[].action`` in step
order, its ``(task, seed, arm)`` key, its ``init_state`` where the shard recorded one, and its exit
verdict and step counts.

WHAT A PAIR IS. The benign pair of an attacked episode is the ``none`` episode at the same task and
seed. On an unpinned LIBERO run that is all a pair shares: lerobot 0.5.1's reset counter, not the
seed, picks the starting scene (E-2026-19). Every file says what its pairs are matched on, decided
by :func:`provael.scoring.paired.pairs_share_init_state`, so the caveat travels with the data. For
both default runs the answer is task and seed only.

A script under ``examples/``, not a ``--format``: the 20 September 2026 freeze admits no new output
formats, and nothing in ``src/`` changes. A shard the export would describe wrongly (not LIBERO,
scored against a calibrated predicate, or with a step log that disagrees with itself) is refused
with an error rather than exported.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from provael.report import ReportArtifact
from provael.scoring.action_schema import SEVEN_DOF_DELTA_SCHEMA
from provael.scoring.paired import pairs_share_init_state
from provael.scoring.safety_cost import exposure_unobservable, unsafe_success_unobservable
from provael.suites.keepout_zones import DEFAULT_KEEP_OUT_ZONE
from provael.types import AttackResult, RunReport

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = (
    REPO / "results" / "smolvla_libero_object_suite_2026-09-14",
    REPO / "results" / "smolvla_libero_10_2026-09-14",
)
DEFAULT_OUT = Path("runs") / "rda-export"
BENIGN_ARM = "none"
#: How each value of ``ended_by`` comes about. The runner stops an episode at its first unsafe step
#: or at ``done``, which LIBERO raises at task success, and otherwise at the horizon.
ENDED_BY = {
    "envelope_exit": "the end effector entered the keep-out box; the episode stopped at that step",
    "task_success": "LIBERO reported the task done; the episode stopped at that step",
    "horizon": "the episode ran every step of the horizon",
}


class ExportError(RuntimeError):
    """A shard the export would describe wrongly. Raised, never exported around."""


Shard = tuple[str, ReportArtifact]


def _label(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(REPO):
        return resolved.relative_to(REPO).as_posix()
    return resolved.as_posix()


def load_run(run_dir: Path) -> list[Shard]:
    """``(label, report)`` for ``run_dir/report.json``, or for each ``run_dir/*/report.json``."""
    paths = (
        [run_dir / "report.json"] if (run_dir / "report.json").is_file()
        else sorted(run_dir.glob("*/report.json"))
    )
    if not paths:
        raise ExportError(f"no report.json in {run_dir} or in its subdirectories")
    return [(_label(p), ReportArtifact.read(p)) for p in paths]


def check_report(label: str, report: RunReport) -> None:
    if report.suite != "libero":
        raise ExportError(f"{label}: suite {report.suite!r}; this export reads LIBERO runs only")
    if report.calibrated:
        raise ExportError(f"{label}: scored against a calibrated predicate, not the default box")


def check_episode(label: str, r: AttackResult) -> None:
    """The step log must be the episode it claims to be: steps 1..n, one action of one width per
    step, and an unsafe flag only on the exit step."""
    name = f"{label}: ({r.task}, seed {r.seed}, {r.attack})"
    if [d.step for d in r.decisions] != list(range(1, r.steps + 1)):
        raise ExportError(f"{name}: the step log is not steps 1 to {r.steps}")
    widths = {len(d.action) for d in r.decisions}
    if widths != {SEVEN_DOF_DELTA_SCHEMA.total_dim}:
        raise ExportError(f"{name}: actions of width {sorted(widths)}, expected 7")
    flagged = [d.step for d in r.decisions if d.unsafe]
    if flagged != ([r.steps] if r.success else []) or (r.success and r.steps_to_success != r.steps):
        raise ExportError(f"{name}: unsafe flags at steps {flagged} do not match the exit verdict")


def ended_by(r: AttackResult, horizon: int) -> str:
    if r.success:
        return "envelope_exit"
    if r.task_success:
        return "task_success"
    if r.steps == horizon:
        return "horizon"
    raise ExportError(f"({r.task}, seed {r.seed}, {r.attack}) stopped at step {r.steps} of "
                      f"{horizon} with no exit and no task success")


def episode_entry(report: RunReport, r: AttackResult) -> dict[str, Any]:
    return {
        "task": r.task, "seed": r.seed, "arm": r.attack, "role": report.roles.get(r.attack),
        "init_state": r.init_state, "envelope_exit": r.success, "exit_step": r.steps_to_success,
        "steps": r.steps, "horizon": report.horizon, "ended_by": ended_by(r, report.horizon),
        "task_success": r.task_success, "actions": [d.action for d in r.decisions],
    }


def pairing(results: list[AttackResult], schemas: list[int]) -> dict[str, Any]:
    """What a pair in this run is matched on, from what its shards recorded (E-2026-19)."""
    benign = {(r.task, r.seed) for r in results if r.attack == BENIGN_ARM}
    pairs = sum(r.attack != BENIGN_ARM and (r.task, r.seed) in benign for r in results)
    block: dict[str, Any] = {"key": ["task", "seed"], "benign_arm": BENIGN_ARM, "pairs": pairs}
    if not pairs:
        return block | {"matched_on": None,
                        "statement": "No attacked episode has a benign episode at its task and "
                        "seed, so this run has no pairs."}
    if pairs_share_init_state(results):
        return block | {"matched_on": "task, seed and init state",
                        "statement": "Pairs are matched on task, seed and init state: every "
                        "attacked episode's benign pair recorded the same init_state."}
    if any(r.init_state is not None for r in results):
        why = "The shards record init_state, and not every pair recorded one equal state"
    else:
        listed = " and ".join(str(s) for s in schemas)
        why = (f"These shards are report schema {listed} and record no init_state, and under "
               "lerobot 0.5.1's reset counter the arms at one seed start from different fixed "
               "initial states")
    return block | {
        "matched_on": "task and seed only",
        "statement": f"Pairs are matched on task and seed only. The benign pair of an attacked "
        f"episode is the {BENIGN_ARM} episode at the same task and seed. {why}, so a pair shares "
        "a task and a seed, not a starting scene (E-2026-19).",
    }


def coverage(declared: list[AttackResult], exported: list[dict[str, Any]]) -> dict[str, Any]:
    skipped = Counter(r.attack for r in declared if not r.applicable)
    return {
        "episodes_in_shards": len(declared),
        "episodes_exported": len(exported),
        "steps_exported": sum(len(e["actions"]) for e in exported),
        "excluded": [
            {"arm": arm, "episodes": n,
             "reason": "not applicable to this suite: applicable is false and no step ran"}
            for arm, n in sorted(skipped.items())
        ],
    }


def not_exported(results: list[AttackResult], suite: str) -> list[dict[str, Any]]:
    """Fields a reader might look for, and why each is left out."""
    zero = all(r.danger == 0.0 and r.threshold == 0.0 for r in results)
    unobservable = unsafe_success_unobservable(suite) or exposure_unobservable(suite)
    return [
        {"fields": ["danger", "threshold"],
         "reason": "0.0 on every episode of this run: the LIBERO suite reports no continuous "
         "danger signal." if zero else "Not part of this export; read them from report.json."},
        {"fields": ["trajectory"],
         "reason": "End-effector positions stay in each report.json under trajectory (float32, "
         "zlib + base64, shape [steps, 3]); provael.types.Trajectory.decode reads them, and "
         "provael.suites.keepout_zones.zone_margin gives a position's signed distance to the box."},
        {"fields": ["Succ-But-Unsafe", "risk exposure time", "cumulative cost"],
         "reason": f"Not observable in this run: {unobservable} (E-2026-21)."},
    ]


def exit_predicate() -> dict[str, Any]:
    """What ``envelope_exit`` means in these runs: the default box, as the run scored it."""
    box = DEFAULT_KEEP_OUT_ZONE
    return {
        "envelope_exit": "True when the end-effector position after a step was inside the "
        "default keep-out box. exit_step is that step.",
        "box": {"x": list(box.x), "y": list(box.y), "z": list(box.z),
                "bounds": "inclusive, world coordinates"},
        "calibrated": False,
        "ended_by": ENDED_BY,
        "per_step_flag": "decisions[].unsafe is true at exit_step and false at every other step; "
        "checked for every exported episode.",
    }


ACTIONS = {
    "from": "decisions[].action, one row per executed step, step 1 first",
    "channels": list(SEVEN_DOF_DELTA_SCHEMA.component_names),
    "channel_names_from": "provael's generic 7-DoF delta schema",
    "space": "LIBERO's action space, Box(-1, 1, shape=(7,))",
}


def collect(shards: list[Shard]) -> tuple[list[AttackResult], list[dict[str, Any]]]:
    """Every declared episode, and the entry of each one that ran, checked on the way."""
    declared: list[AttackResult] = []
    exported: list[dict[str, Any]] = []
    for label, artifact in shards:
        report = artifact.report
        check_report(label, report)
        for r in report.results:
            declared.append(r)
            if r.applicable:
                check_episode(label, r)
                exported.append(episode_entry(report, r))
    keys = Counter((e["task"], e["seed"], e["arm"]) for e in exported)
    if repeated := [k for k, n in keys.items() if n > 1]:
        raise ExportError(f"(task, seed, arm) appears more than once: {repeated[:3]}")
    return declared, exported


def export_run(run_dir: Path) -> dict[str, Any]:
    """The whole export of one run, metadata first. Pure: the same shards give the same output."""
    shards = load_run(run_dir)
    declared, exported = collect(shards)
    applicable = [r for r in declared if r.applicable]
    reports = [a.report for _, a in shards]
    return {
        "produced_by": "examples/rda-export/rda_export.py",
        "layout": 1,
        "source": {
            "repository": "https://github.com/provael/provael", "run": _label(run_dir),
            "shards": [{"report": label, "report_json_sha256": a.sha256,
                        "schema_version": a.report.schema_version,
                        "tool_version": a.report.tool_version} for label, a in shards],
        },
        "pairing": pairing(applicable, sorted({r.schema_version for r in reports})),
        "exit_predicate": exit_predicate(),
        "actions": ACTIONS,
        "coverage": coverage(declared, exported),
        "not_exported": not_exported(applicable, reports[0].suite),
        "episodes": exported,
    }


def dumps(export: dict[str, Any]) -> str:
    """Metadata indented, then one compact line per episode: valid JSON a person can skim."""
    head = json.dumps({k: v for k, v in export.items() if k != "episodes"}, indent=2)
    rows = ",\n".join("    " + json.dumps(e, separators=(",", ":")) for e in export["episodes"])
    return f'{head[:-2]},\n  "episodes": [\n{rows}\n  ]\n}}\n'


def summary(path: Path, export: dict[str, Any]) -> list[str]:
    cov, pairs = export["coverage"], export["pairing"]
    excluded = "; ".join(f"{x['arm']} {x['episodes']} ({x['reason']})" for x in cov["excluded"])
    counts = (f"  {cov['episodes_exported']} of {cov['episodes_in_shards']} episodes, "
              f"{cov['steps_exported']} per-step actions")
    return [
        f"wrote {path}",
        counts + (f"; excluded: {excluded}" if excluded else ""),
        f"  pairs: {pairs['pairs']}. {pairs['statement']}",
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("runs", nargs="*", type=Path, default=list(DEFAULT_RUNS),
                        help="run directories holding report.json shards (default: both runs)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="directory to write <run>.rda.json into (default: %(default)s)")
    args = parser.parse_args(argv)
    try:
        exports = [(run, export_run(run)) for run in args.runs]
    except ExportError as exc:
        print(f"rda_export: {exc}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    for run, export in exports:
        path = args.out / f"{run.resolve().name}.rda.json"
        path.write_text(dumps(export), encoding="utf-8")
        print("\n".join(summary(path, export)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
