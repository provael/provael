"""Cross-suite validation — the same attacks, run on two different suites, on CPU.

This is the artifact that answers "you only proved it on one suite" with *data*. It runs the
identical four attack families against the SAME policy on two genuinely different suites:

  * ``stub``  — a *scalar* predicate (danger vs. a per-seed threshold)
  * ``reach`` — a *spatial* predicate (end-effector vs. a keep-out zone)

Both are pure CPU (no GPU, no model). The attacks are suite-agnostic: they perturb the
instruction/observation, and each suite scores "unsafe" its own way — so the ASR differs by
suite while the attack code is unchanged. Extend the SUITES list with ``libero`` / ``metaworld``
(GPU) to add real simulators.

    python examples/cross_suite_validation/compare.py
"""

from __future__ import annotations

from provael.config import RunConfig
from provael.runner import run

SUITES = ["stub", "reach"]  # both CPU; add "libero" / "metaworld" on a GPU box
ATTACKS = ["instruction", "visual", "injection", "action"]


def main() -> None:
    reports = {
        suite: run(RunConfig(policy="stub", suite=suite, attacks=ATTACKS, episodes=10, seed=0))
        for suite in SUITES
    }

    # Per-attack ASR side by side.
    attacks = sorted(next(iter(reports.values())).by_attack)
    width = max(len(a) for a in attacks)
    header = f"{'attack':<{width}}  " + "  ".join(f"{s:>12}" for s in SUITES)
    print(header)
    print("-" * len(header))
    for attack in attacks:
        cells = []
        for suite in SUITES:
            stat = reports[suite].by_attack[attack]
            cells.append(f"{stat.successes}/{stat.attempts} ({stat.successes / stat.attempts:.0%})")
        print(f"{attack:<{width}}  " + "  ".join(f"{c:>12}" for c in cells))

    print("-" * len(header))
    totals = "  ".join(f"{reports[s].successes}/{reports[s].attempts:>2}".rjust(12) for s in SUITES)
    print(f"{'OVERALL':<{width}}  " + totals)
    print(
        "\nSame attacks, different predicates => different ASR. The attack code never changed; "
        "only the suite did."
    )


if __name__ == "__main__":
    main()
