#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "provael==0.36.1",
# ]
# ///
"""The matched pair, in one CPU-only file with nothing to download.

    uv run examples/matched_pairs.py            # print the tables
    uv run examples/matched_pairs.py --check    # also assert the numbers below

No GPU. No model weights. No network after the dependency resolve. It finishes in seconds,
because the whole point is that a stranger can run it before deciding whether to trust anything
else here.

WHAT THIS DEMONSTRATES

An attack-success rate on its own is close to meaningless. "88% of episodes ended unsafe" invites
exactly one question — compared to what? — and a tool that cannot answer it is reporting a number,
not a measurement.

Provael answers it by running a benign twin at the SAME (task, seed) as every attacked episode and
comparing the two cell by cell. That is the matched pair, and this file is the smallest complete
demonstration of it: a 2x2 contingency table per attack, an exact McNemar p-value computed from the
discordant cells, and a task-clustered bootstrap interval.

WHY McNEMAR AND NOT FISHER

Fisher's exact test treats the two arms as independent samples. They are not: the same task and the
same seed appear in both, so the arms are paired, and a paired design carries strictly more
information. McNemar uses it by discarding the concordant cells — the pairs where both arms agreed
— because they carry nothing about the DIFFERENCE between the arms. Only the discordant cells do.

The exact binomial form is used rather than the chi-square approximation. At the sample sizes this
harness runs, the approximation is not valid, and it errs optimistic — in the direction that
flatters the result.

WHY THE CONFIDENCE INTERVAL COMES BACK None BELOW, AND WHY THAT IS THE FEATURE

`cluster_bootstrap_ci` resamples TASKS, not episodes. Episodes inside one task are correlated: an
attack that works on a task tends to work across every seed of it. Resampling episodes would
pretend otherwise and report an interval far too narrow.

Every CPU-only suite in Provael (`stub`, `reach`, `humanoid`) exposes exactly ONE task. A bootstrap
over one task resamples the same thing every iteration and returns a zero-width interval: a
confident-looking number carrying no information. So the function returns None instead, and this
script prints that rather than hiding it.

If you want the interval populated you need a multi-task suite, which means `libero` or
`metaworld`, which means the `[lerobot]` extra and a real simulator — and then it is no longer a
file you can run on a laptop with no download. That tension is real and this example does not
paper over it. The published suite result (SmolVLA x LIBERO, ten tasks) is where a populated
interval actually appears: 44/50, 95% task-clustered CI [72-100%].

WHAT THIS IS NOT

**These numbers say nothing about any real policy.** `stub` is a deterministic arithmetic fixture,
not a simulator, and StubPolicy is not a model. Provael's own evidence classifier refuses to label
a run on a fixture as `real-episode` for exactly this reason. What is being demonstrated here is
the STATISTICAL MACHINERY, on inputs chosen to make it legible. Read the p-values as "the code
does what it says", never as "instruction attacks beat robot policies 85% of the time".

The one real-policy result this project has is in `results/smolvla_libero_object_suite/`, and its
limitations travel with it.
"""

from __future__ import annotations

import sys

from provael.config import RunConfig
from provael.runner import run
from provael.scoring.paired import McNemarResult, cluster_bootstrap_ci, paired_by_attack
from provael.types import AttackResult

#: The benign twin. Present in `attacks` because the pairing needs both arms in ONE run — stitching
#: an attacked run against a separately-executed benign run would break the (task, seed) matching
#: that makes the pair a pair.
BASELINE = "none"

#: Three instruction-family attacks plus the benign control, 20 seeds each = 80 episodes.
ATTACKS = ["roleplay", "goal_substitution", "paraphrase", BASELINE]
EPISODES = 20
SEED = 0

#: Expected output, asserted under --check. The stub policy and stub suite are deterministic, so
#: these are exact, not approximate — if this file ever prints something else, either the scoring
#: changed or the fixture did, and both are worth knowing about.
EXPECTED: dict[str, tuple[int, int, int]] = {
    # attack: (attack_only, benign_only, concordant)
    "roleplay": (17, 0, 3),
    "paraphrase": (14, 0, 6),
    "goal_substitution": (10, 0, 10),
}


def contingency(m: McNemarResult, results: list[AttackResult]) -> str:
    """Render the 2x2 the McNemar p-value is computed from.

    Laid out as a real contingency table rather than four numbers on a line, because the whole
    argument is about WHICH cells carry information, and the layout is what makes that visible:
    the off-diagonal is the evidence, the diagonal is discarded.
    """
    attacked_unsafe = {(r.task, r.seed) for r in results if r.attack == m.attack and r.success}
    benign_unsafe = {(r.task, r.seed) for r in results if r.attack == BASELINE and r.success}
    both = len(attacked_unsafe & benign_unsafe)
    neither = m.concordant - both
    return "\n".join(
        [
            f"  {m.attack}",
            "                        benign: unsafe   benign: safe",
            f"    attack: unsafe  {both:>14}   {m.attack_only:>13}",
            f"    attack: safe    {m.benign_only:>14}   {neither:>13}",
            "",
            f"    discordant pairs   {m.discordant:>3}  (the only cells McNemar uses)",
            f"    concordant pairs   {m.concordant:>3}  (discarded: they carry no difference)",
            f"    McNemar exact p    {m.p_value:.3g}",
        ]
    )


def main() -> int:
    check = "--check" in sys.argv

    config = RunConfig(
        policy="stub", suite="stub", attacks=ATTACKS, episodes=EPISODES, seed=SEED
    )
    report = run(config)
    results = report.results

    tasks = sorted({r.task for r in results})
    print(f"run: {config.policy} x {config.suite} | {len(results)} episodes | tasks: {tasks}")
    print(f"     attacks: {', '.join(ATTACKS)} | {EPISODES} seeds each | seed={SEED}\n")

    paired = paired_by_attack(results)
    for attack in sorted(paired, key=lambda a: -paired[a].attack_only):
        print(contingency(paired[attack], results))
        print()

    ci = cluster_bootstrap_ci(results, attack="roleplay")
    print("task-clustered 95% bootstrap CI (roleplay):", ci)
    if ci is None:
        print(
            f"    None because this run has {len(tasks)} task. The bootstrap resamples TASKS, and\n"
            "    resampling one task returns a zero-width interval — a confident-looking number\n"
            "    carrying no information. Declining is the correct answer, not a missing feature.\n"
            "    See the module docstring."
        )

    print(
        "\nreminder: stub is an arithmetic fixture, not a simulator. These p-values show the\n"
        "machinery works. They say nothing about any real policy."
    )

    if check:
        failures: list[str] = []
        for attack, (a_only, b_only, conc) in EXPECTED.items():
            got = paired.get(attack)
            if got is None:
                failures.append(f"{attack}: missing from paired output")
                continue
            actual = (got.attack_only, got.benign_only, got.concordant)
            if actual != (a_only, b_only, conc):
                failures.append(f"{attack}: expected {(a_only, b_only, conc)}, got {actual}")
        if ci is not None:
            failures.append(f"clustered CI: expected None on a single-task suite, got {ci}")
        if failures:
            print("\nFAILED:")
            for f in failures:
                print(f"  {f}")
            return 1
        print("\nOK: all asserted values match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
