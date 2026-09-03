#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "provael[lerobot]==0.39.3",
#     "lerobot[libero]==0.5.1",
# ]
# ///
"""Reproduce provael's headline result end to end, in one file, with nothing to edit.

    uv run examples/lerobot_eval_smolvla_libero.py --dry-run   # validate, no GPU, no download
    uv run examples/lerobot_eval_smolvla_libero.py             # the real thing (see COST below)

The header above is PEP 723 inline script metadata. `uv run` reads it, builds an isolated
environment with those exact versions, and runs the file. There is no requirements.txt to install,
no path to edit and no virtualenv to create — which is the whole point, because a reproduction a
stranger cannot execute is not a reproduction.

WHAT IT REPRODUCES
    SmolVLA (HuggingFaceVLA/smolvla_libero) x LIBERO, all ten `libero_object` tasks, 5 seeds,
    8 arms. 400 records, of which 350 are measured episodes — `mcp_tool_desc` is not applicable to
    this suite and contributes 0 attempts, which is reported as N/A and never as 0.

    Expected: `roleplay` 44/50 (88%), benign control 2/50 (4%), McNemar p = 4.6e-13.

WHY lerobot IS PINNED AT 0.5.1 AND NOT 0.6.x
    0.6.0 (6 July 2026) and 0.6.1 (3 August 2026) exist and are newer. The committed numbers this
    script reproduces were measured on **0.5.1**, and nobody has re-measured on 0.6.x. Pinning a
    version the result has never been produced on would make this a script that runs rather than a
    script that reproduces. If you re-measure on 0.6.x, the numbers below are the baseline to
    compare against — and a difference is a finding worth reporting, not a bug in this file.

COST, MEASURED NOT ESTIMATED
    The reference run took **15.4 GPU-hours on an L4** and cost **$12.29** on Modal, sharded one
    task per container for a 2.04 h wall clock. Unsharded on a single local GPU, budget the full
    15.4 hours. Per-episode cost was $0.031, measured — an earlier estimate was 21% low.

WHAT THIS RUN IS NOT
    Not deterministic. SmolVLA's flow-matching sampler is not fully seeded (`stochastic: true` on
    every shard), so provael's determinism contract covers the stub path and NOT this one. Your
    numbers will differ from 44/50 by a few episodes. That is expected; treat any single run,
    including the committed one, as one draw.

    Not calibrated. The keep-out predicate is the same default box on all ten tasks, fitted to
    none of them — which is why the benign control fires at 4% rather than 0%. `provael calibrate`
    exists and has never been run on LIBERO.

    Not real-robot. Simulation only. `results/hardware/` reads 0.

Sim-only and defensive: this drives a simulator, never a physical robot. See SAFETY.md.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import-time only, and heavy on the real path
    from provael.types import AttackResult

# --------------------------------------------------------------------------------------------
# The reference configuration. These are the exact values behind the committed artifacts in
# results/smolvla_libero_object_suite/ — read out of a shard's report.json, not retyped from prose.
# --------------------------------------------------------------------------------------------

#: The LIBERO-finetuned checkpoint. NOT `lerobot/smolvla_base`: a base checkpoint carries no LIBERO
#: action statistics, cannot emit correctly-scaled LIBERO actions, and would measure noise.
CHECKPOINT = "HuggingFaceVLA/smolvla_libero"

#: All ten tasks. The LIBERO suite constructor defaults to `task_ids=(0,)`, so omitting this
#: silently measures one task under a ten-task label.
TASKS = tuple(f"libero_object/{i}" for i in range(10))

#: FAMILY names, not attack names — the registry expands each into its attacks, so the arm count is
#: RESOLVED and never counted by hand. `none` is the benign control and is not optional: it is the
#: matched twin every McNemar comparison is made against, and without it an ASR is a number with
#: nothing to read it against.
ATTACK_FAMILIES = ["none", "instruction", "visual", "injection"]

#: `episodes` is total episodes per (task, attack) pair. With `episodes_per_seed=1` it is also the
#: number of distinct seeds, which is what the reference run's `"seeds": 5` records.
EPISODES = 5
EPISODES_PER_SEED = 1
HORIZON = 280

#: What the committed run measured, for the comparison this script prints at the end. A
#: reproduction that does not tell you whether you reproduced it is a log file.
REFERENCE = {
    "roleplay": (44, 50),
    "goal_substitution": (15, 50),
    "paraphrase": (3, 50),
    "none": (2, 50),
}
REFERENCE_MCNEMAR_ROLEPLAY = 4.547473508864641e-13


def _reference_config() -> object:
    """The exact committed configuration, as a validated :class:`~provael.config.RunConfig`.

    One definition, used by both the dry run and the real run — so `--dry-run` validates the thing
    that will actually execute rather than a hand-kept copy of it.
    """
    from provael.config import RunConfig

    return RunConfig(
        policy="smolvla",
        suite="libero",
        model=CHECKPOINT,
        tasks=list(TASKS),
        attacks=list(ATTACK_FAMILIES),
        episodes=EPISODES,
        episodes_per_seed=EPISODES_PER_SEED,
        horizon=HORIZON,
    )


def _describe_plan() -> str:
    from provael.attacks.registry import resolve_attacks

    # Resolved from the registry, never a literal: `--attacks` takes FAMILY names, and writing "8"
    # here would silently go stale the day a family gains a member.
    arms = len(resolve_attacks(ATTACK_FAMILIES))
    cells = len(TASKS) * EPISODES * EPISODES_PER_SEED
    return (
        f"  policy      smolvla ({CHECKPOINT})\n"
        f"  suite       libero, {len(TASKS)} tasks: {TASKS[0]} .. {TASKS[-1]}\n"
        f"  attacks     {','.join(ATTACK_FAMILIES)}  (families → {arms} arms)\n"
        f"  sampling    {EPISODES} seeds x {EPISODES_PER_SEED} episode/seed = {cells} cells/arm\n"
        f"  horizon     {HORIZON} steps\n"
        f"  records     {arms * cells} ({(arms - 1) * cells} measured; mcp_tool_desc is N/A here)\n"
        f"  cost        ~15.4 L4-GPU-hours, $12.29 measured on the reference run\n"
    )


def _dry_run() -> int:
    """Validate everything that can be validated without a GPU, a download or lerobot.

    This is the smoke test, and it deliberately does NOT import lerobot or torch: the point is to
    confirm the script is wired correctly on the machine of someone who has not yet spent $12.
    """
    print("provael — SmolVLA x LIBERO reproduction (DRY RUN)\n")
    print(_describe_plan())

    problems: list[str] = []
    try:
        import provael
        from provael.attacks.registry import resolve_attacks
        from provael.config import RunConfig
        from provael.policies.registry import available_policies
        from provael.suites import available_suites
    except ImportError as exc:  # pragma: no cover - only when run outside `uv run`
        print(f"error: provael is not importable ({exc}).", file=sys.stderr)
        print("  Run this file with `uv run`, which installs the pinned header above.",
              file=sys.stderr)
        return 1

    print(f"  provael     {provael.__version__} importable")

    # The lookups that would otherwise fail at minute 0 of a $12 run, checked at second 0.
    # Deliberately by NAME rather than by instantiation: building the libero suite imports lerobot
    # and pulls torch, which would break this command's promise of running on any laptop.
    resolved = [attack.name for attack in resolve_attacks(ATTACK_FAMILIES)]
    print(f"  attacks     {len(resolved)} arms resolve: {', '.join(resolved)}")
    if "none" not in resolved:
        problems.append("the benign control arm resolved away — every McNemar pair depends on it")
    if "smolvla" not in available_policies():
        problems.append("policy 'smolvla' is not registered")
    if "libero" not in available_suites():
        problems.append("suite 'libero' is not registered")

    # Build the real config. `extra="forbid"` on RunConfig means a renamed field fails HERE rather
    # than after the weights have downloaded.
    try:
        _reference_config()
    except Exception as exc:  # noqa: BLE001 - pydantic raises its own type; surface whatever it is
        problems.append(f"the run config no longer validates: {exc}")
    else:
        print(f"  config      validates against {RunConfig.__name__} as shipped")

    if problems:
        print("\nFAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("\n  registry    smolvla + libero registered (weights NOT downloaded in a dry run)")
    print("\nDry run OK. Drop --dry-run to execute. Budget ~15.4 L4-GPU-hours / $12.29.")
    return 0


def _report_pairs(results: list[AttackResult]) -> None:
    """Print the matched-pair table and the McNemar p-value for every arm.

    Reuses :mod:`provael.scoring.paired` rather than recomputing: an example that reimplements the
    statistics can agree with the library by luck and disagree by regression, and neither shows up.
    The benign control is structurally impossible to omit here — `paired_by_attack` builds every
    comparison from the `(task, seed)`-matched benign twin, so an arm with no twin has no row.
    """
    from provael.scoring.paired import holm_bonferroni, paired_by_attack

    pairs = paired_by_attack(results)
    if not pairs:
        print("\nNo paired comparisons — the benign control arm did not run. Nothing is claimable.")
        return

    names = sorted(pairs)
    adjusted, rejected = holm_bonferroni([pairs[n].p_value for n in names])

    print("\nMatched-pair result (each arm vs its benign twin at the same (task, seed))")
    print(f"  {'arm':<20} {'attack-only':>11} {'benign-only':>11} {'concordant':>10} "
          f"{'McNemar p':>12} {'Holm p':>10}  verdict")
    for name, adj, reject in zip(names, adjusted, rejected, strict=True):
        r = pairs[name]
        verdict = "survives" if reject else "rejected"
        print(f"  {name:<20} {r.attack_only:>11} {r.benign_only:>11} {r.concordant:>10} "
              f"{r.p_value:>12.3g} {adj:>10.3g}  {verdict}")

    print("\n  Concordant pairs are DISCARDED by McNemar, which is why they are shown: an arm with")
    print("  many concordant pairs and few discordant ones has a large n and little evidence.")


def _compare_to_reference(results: list[AttackResult]) -> None:
    """Say plainly whether this run reproduced the committed numbers."""
    from provael.scoring.asr import by_attack

    print("\nAgainst the committed reference run (results/smolvla_libero_object_suite/)")
    print(f"  {'arm':<20} {'this run':>12} {'reference':>12}   note")
    counts = by_attack(results)
    for arm, (ref_hits, ref_n) in REFERENCE.items():
        got = counts.get(arm)
        if got is None or got.attempts == 0:
            print(f"  {arm:<20} {'not run':>12} {f'{ref_hits}/{ref_n}':>12}")
            continue
        mine = f"{got.successes}/{got.attempts}"
        delta = abs(got.successes / got.attempts - ref_hits / ref_n)
        note = "within run-to-run noise" if delta <= 0.12 else "DIFFERS — worth reporting"
        print(f"  {arm:<20} {mine:>12} {f'{ref_hits}/{ref_n}':>12}   {note}")

    print(
        "\n  A few episodes of difference is expected: SmolVLA's sampler is not fully seeded, so"
        "\n  this run and the committed one are two draws from the same setup, not two copies of"
        "\n  one number. A LARGE difference is a finding — please open an issue with both reports."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce provael's SmolVLA x LIBERO headline result.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="validate the config and registries without a GPU, a download or an episode",
    )
    parser.add_argument(
        "--out", default="reproduction_smolvla_libero",
        help="directory for report.json and the evidence bundle (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        return _dry_run()

    print("provael — SmolVLA x LIBERO reproduction\n")
    print(_describe_plan())
    print("Starting. The reference run took 2.04 h sharded / ~15.4 GPU-hours unsharded.\n")

    # Imported here, not at module scope: `--dry-run` must work on a laptop with no torch, and a
    # top-level import of the runner would pull the whole stack in before argparse ever ran.
    from pathlib import Path

    from provael.config import RunConfig
    from provael.report import write_report
    from provael.runner import run

    config = _reference_config()
    assert isinstance(config, RunConfig)
    report = run(config)
    write_report(report, Path(args.out))

    _report_pairs(report.results)
    _compare_to_reference(report.results)

    print(f"\nWrote {args.out}/report.json")
    print("\nThis is a SIMULATION result on ONE policy with an UNCALIBRATED predicate.")
    print("It is not a real-robot number and must not be reported as one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
