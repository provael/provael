#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Run the sharded LIBERO screen on ONE machine, resumably, and aggregate its shards.

The workstation twin of :mod:`modal_libero_suite`. That recipe fans ten tasks out to ten rented
containers; this one runs the same protocol on a box you already have, N tasks at a time, with the
same per-task ``report.json`` shards, the same append-only ledgers, and the same cross-shard
aggregate. The point of keeping the two recipes shaped alike is that a workstation run and a Modal
run are then the same experiment executed in two places, which is what makes them comparable.

WHY N SHARDS AND NOT ONE. Measured on 14 September 2026 on an RTX 2000 Ada (16 GB) with a 24-core
i9-14900K: one SmolVLA × LIBERO process runs at ~0.39 s/step and leaves the GPU 25-44 % busy — the
physics, the rendering and the tokenisation are CPU work in between policy calls. Three processes
took the GPU to 99 % at 4.1 GB of VRAM; a fourth gains little on that card. ``--parallel`` is
therefore a measured knob, not a default to trust: run one episode, watch ``nvidia-smi``, then pick.

WHY A LEDGER PER SHARD. ``provael attack --resume`` replays the episodes a killed process already
measured. A power cut at hour three costs the episode in flight, not the three hours. Re-running
``launch`` with the same arguments continues; it never restarts.

WHY THE AGGREGATE IS NOT A REPORT. Each shard's ``report.json`` is an attestable artifact whose
digest is a pure function of its own config. Ten of them stitched into an eleventh would look
signable and be nothing: no single execution produced it. So ``aggregate`` writes
``aggregate.json`` — a named analysis keyed to the shards — and the public evidence manifest
records every shard's digest (``provael evidence-manifest`` handles a sharded directory).

PROVENANCE. ``provael`` records the source commit from the ``PROVAEL_COMMIT`` environment variable
when it is not running inside a git checkout, which a ``pip``-installed workstation never is. Pass
``--commit`` (the installed release's tag commit) so the execution manifests name the code that
produced them; without it they say ``commit: null``, which is exactly the gap the scheduled Modal
canaries carried for a month. Set ``PROVAEL_REPOSITORY=provael/provael`` too, and run a provael
>= 0.42.0 so the installed-set lock digest and the checkpoint's precision are recorded: from
20 September 2026 ``tests/test_results_provenance.py`` refuses to accept a committed run whose
shards lack any of ``repository``, ``commit``, ``dep_lock_digest`` or ``precision``, and there is no
exemption list for new runs.

    python local_libero_sweep.py launch --out ~/data/runs/smolvla-obj --parallel 3 \\
        --commit <sha of the installed release> \\
        [--policy smolvla --model HuggingFaceVLA/smolvla_libero]
    python local_libero_sweep.py status --out ~/data/runs/smolvla-obj
    python local_libero_sweep.py aggregate --out ~/data/runs/smolvla-obj

Requires the ``[lerobot]`` extra and a Linux GPU box (LIBERO does not install on macOS or
Windows; WSL2 counts as Linux and renders through EGL).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from provael.suites.libero import LIBERO_HORIZON

#: The shipped protocol — the `full` stage of modal_libero_suite.py, arm for arm. ``instruction``
#: expands to roleplay, goal_substitution, paraphrase; ``visual`` to patch, decoy_object;
#: ``injection`` to scene_text, mcp_tool_desc; ``none`` is the matched benign twin. Eight arms.
DEFAULT_ATTACKS = "none,instruction,visual,injection"
DEFAULT_SUITE = "libero_object"
DEFAULT_TASKS = tuple(range(10))
# The horizon defaults to the chosen suite's own budget (LIBERO_HORIZON); a single fixed default
# ran libero_spatial at object's 280 unless --horizon was passed by hand.
DEFAULT_SEEDS = 5


def _horizon(args: argparse.Namespace) -> int:
    """The explicit --horizon, or the suite's OpenVLA evaluation budget."""
    return int(args.horizon) if args.horizon is not None else LIBERO_HORIZON[args.suite]


def _task_name(suite: str, task_id: int) -> str:
    return f"{suite}/{task_id}"


def _shard_dir(out: pathlib.Path, task_id: int) -> pathlib.Path:
    return out / str(task_id)


def _attack_command(args: argparse.Namespace, task_id: int) -> list[str]:
    shard = _shard_dir(args.out, task_id)
    cmd = [
        "provael", "attack",
        "--policy", args.policy,
        "--suite", "libero",
        "--tasks", _task_name(args.suite, task_id),
        "--attacks", args.attacks,
        "--seeds", str(args.seeds),
        "--episodes-per-seed", "1",
        "--horizon", str(_horizon(args)),
        "--seed", str(args.base_seed),
        "--resume", str(shard / "ledger.jsonl"),
        "--out", str(shard),
    ]
    if args.model:
        cmd += ["--model", args.model]
    if args.calib:
        cmd += ["--calib", str(args.calib)]
    if args.query_budget:
        cmd += ["--query-budget", str(args.query_budget)]
    return cmd


def _run_shard(args: argparse.Namespace, task_id: int) -> tuple[int, int, float]:
    """Run one task to completion (or to ``--timeout``), streaming its output to a log file."""
    shard = _shard_dir(args.out, task_id)
    shard.mkdir(parents=True, exist_ok=True)
    log = args.out / f"{task_id}.log"
    cmd = _attack_command(args, task_id)
    env = dict(os.environ)
    if args.commit:
        env["PROVAEL_COMMIT"] = args.commit
    started = time.monotonic()
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n$ {shlex.join(cmd)}\n")
        handle.flush()
        try:
            done = subprocess.run(  # noqa: S603 - argv list, no shell
                cmd, stdout=handle, stderr=subprocess.STDOUT, env=env, timeout=args.timeout,
                check=False,
            )
            code = done.returncode
        except subprocess.TimeoutExpired:
            handle.write(f"\n[timeout after {args.timeout}s — rerun launch to resume]\n")
            code = 124
    return task_id, code, time.monotonic() - started


def cmd_launch(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = [t for t in args.tasks if not (_shard_dir(args.out, t) / "report.json").exists()]
    skipped = [t for t in args.tasks if t not in tasks]
    if skipped:
        print(f"already complete (report.json present): {skipped}")
    if not tasks:
        print("nothing to run")
        return 0
    if not args.commit and not os.environ.get("PROVAEL_COMMIT"):
        print(
            "WARNING: no --commit and PROVAEL_COMMIT unset; execution manifests will record "
            "commit: null. Pass the installed release's tag commit.",
            file=sys.stderr,
        )
    if not os.environ.get("PROVAEL_REPOSITORY"):
        print(
            "WARNING: PROVAEL_REPOSITORY unset; execution manifests will record repository: null, "
            "and a run committed after 2026-09-20 fails tests/test_results_provenance.py on it.",
            file=sys.stderr,
        )
    print(f"launching {len(tasks)} task(s), {args.parallel} at a time, into {args.out}")
    print(f"protocol: suite={args.suite} attacks={args.attacks} seeds={args.seeds} "
          f"horizon={_horizon(args)} policy={args.policy} model={args.model}")
    failures = 0
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        for task_id, code, elapsed in pool.map(lambda t: _run_shard(args, t), tasks):
            state = "ok" if code == 0 else f"exit={code}"
            print(f"  task {task_id}: {state} in {elapsed/60:.1f} min")
            failures += code != 0
    if failures:
        print(f"{failures} shard(s) did not finish; rerun the same command to resume them")
        return 1
    print("all shards complete; run `aggregate` next")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    for task_id in args.tasks:
        shard = _shard_dir(args.out, task_id)
        ledger = shard / "ledger.jsonl"
        episodes = sum(1 for _ in ledger.open(encoding="utf-8")) if ledger.exists() else 0
        report = (shard / "report.json").exists()
        flag = "yes" if report else "no"
        print(f"  task {task_id}: {episodes} episode(s) in ledger, report={flag}")
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    """Port of modal_libero_suite.aggregate: paired stats across shards, written as an analysis."""
    from provael import __version__
    from provael.scoring.paired import cluster_bootstrap_ci, holm_bonferroni, paired_by_attack
    from provael.types import AttackResult

    shards = sorted(args.out.glob("*/report.json"), key=lambda p: int(p.parent.name)
                    if p.parent.name.isdigit() else p.parent.name)
    if not shards:
        print(f"no shard reports under {args.out} — nothing to aggregate")
        return 1
    results: list[AttackResult] = []
    per_shard: list[str] = []
    tool_versions: set[str] = set()
    for path in shards:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = [AttackResult(**r) for r in data.get("results", [])]
        results.extend(rows)
        tool_versions.add(str(data.get("tool_version")))
        per_shard.append(f"  {path.parent.name}: {len(rows)} episodes, asr={data.get('asr')}")
    tasks = sorted({r.task for r in results})
    lines = [
        f"=== AGGREGATE over {len(shards)} shards — NOT a single attestable report ===",
        f"tasks={len(tasks)} episodes={len(results)} tool_version(s)={sorted(tool_versions)}",
        *per_shard,
        "",
        "=== per-arm counts ===",
    ]
    by_attack: dict[str, list[AttackResult]] = {}
    for r in results:
        by_attack.setdefault(r.attack, []).append(r)
    for name in sorted(by_attack):
        rows = by_attack[name]
        applicable = [r for r in rows if getattr(r, "applicable", True)]
        successes = sum(1 for r in applicable if r.success)
        na = len(rows) - len(applicable)
        suffix = f"  ({na} N/A)" if na else ""
        lines.append(f"  {name:20s} {successes:3d}/{len(applicable):<3d}{suffix}")
    lines += ["", "=== McNemar (paired at matched (task, seed)) + Holm across the family ==="]
    paired = paired_by_attack(results)
    names = sorted(paired)
    mcnemar: dict[str, dict[str, object]] = {}
    if names:
        adjusted, reject = holm_bonferroni([paired[n].p_value for n in names])
        for name, adj, rej in zip(names, adjusted, reject, strict=True):
            m = paired[name]
            ci = cluster_bootstrap_ci(results, attack=name)
            ci_txt = "None (needs >=2 tasks)" if ci is None else f"[{ci[0]:.1%}, {ci[1]:.1%}]"
            lines.append(
                f"  {name:20s} attack_only={m.attack_only:3d} benign_only={m.benign_only:3d} "
                f"concordant={m.concordant:3d} p={m.p_value:.3g} holm={adj:.3g} "
                f"{'SURVIVES' if rej else 'rejected'}  clustered95={ci_txt}"
            )
            mcnemar[name] = {
                "attack_only": m.attack_only, "benign_only": m.benign_only,
                "concordant": m.concordant, "p_value": m.p_value, "holm_adjusted": adj,
                "clustered_ci95": list(ci) if ci is not None else None,
            }
    else:
        lines.append("  (no paired comparisons — is the benign 'none' arm present?)")
    out = args.out / "aggregate.json"
    out.write_text(json.dumps({
        "kind": "cross-shard-aggregate",
        "not_a_report": "Each shard's report.json is the attestable artifact; this is an analysis.",
        "aggregated_with": __version__,
        "tool_versions_in_shards": sorted(tool_versions),
        "shards": [str(p.relative_to(args.out)) for p in shards],
        "tasks": tasks,
        "episodes": len(results),
        "mcnemar": mcnemar,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines.append(f"\nwrote {out}")
    print("\n".join(lines))
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--out", type=pathlib.Path, required=True, help="run directory (one subdir per task)"
        )
        sp.add_argument("--suite", default=DEFAULT_SUITE, help="LIBERO task suite")
        sp.add_argument(
            "--tasks", type=int, nargs="+", default=list(DEFAULT_TASKS), help="task ids"
        )
        sp.add_argument(
            "--attacks", default=DEFAULT_ATTACKS,
            help="family/attack list, as `provael attack --attacks`",
        )

    launch = sub.add_parser("launch", help="run the shards, N at a time, resumably")
    common(launch)
    launch.add_argument("--policy", default="smolvla")
    launch.add_argument("--model", default="HuggingFaceVLA/smolvla_libero")
    launch.add_argument("--seeds", type=int, default=DEFAULT_SEEDS)
    launch.add_argument(
        "--horizon", type=int, default=None,
        help="env steps per episode; default: the suite's OpenVLA budget (LIBERO_HORIZON)",
    )
    launch.add_argument("--base-seed", type=int, default=0)
    launch.add_argument(
        "--parallel", type=int, default=1, help="shards at once — measure before raising"
    )
    launch.add_argument(
        "--timeout", type=int, default=5 * 3600,
        help="seconds per shard before it is killed (resume later)",
    )
    launch.add_argument(
        "--commit", default=None, help="source commit to record in execution manifests"
    )
    launch.add_argument(
        "--calib", type=pathlib.Path, default=None, help="calibration artifacts dir"
    )
    launch.add_argument("--query-budget", type=int, default=None)

    status = sub.add_parser("status", help="episodes per ledger, reports present")
    common(status)

    agg = sub.add_parser("aggregate", help="paired statistics across the shards -> aggregate.json")
    common(agg)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    handlers = {"launch": cmd_launch, "status": cmd_status, "aggregate": cmd_aggregate}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
