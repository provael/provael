"""Plot ASR by attack family from a Provael run (matplotlib optional).

A tiny, CPU-only gallery script: run a scan, aggregate per family, and bar-chart it. Without
matplotlib it prints the per-family ASR table instead of crashing.

    python examples/python-api/plot_asr_by_family.py
"""

from __future__ import annotations

from collections import defaultdict

from provael.attacks.registry import make_attack
from provael.config import RunConfig
from provael.runner import run


def asr_by_family() -> dict[str, float]:
    report = run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["instruction", "visual", "injection", "action"], episodes=10, seed=0,
        )
    )
    buckets: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # family -> [successes, attempts]
    for name, stat in report.by_attack.items():
        fam = make_attack(name).family
        buckets[fam][0] += stat.successes
        buckets[fam][1] += stat.attempts
    return {fam: (s / n if n else 0.0) for fam, (s, n) in buckets.items()}


def main() -> None:
    data = asr_by_family()
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — ASR by family:")
        for fam, asr in sorted(data.items()):
            print(f"  {fam:<12} {asr:.0%}")
        return

    families = sorted(data)
    plt.figure(figsize=(6, 4))
    plt.bar(families, [data[f] for f in families], color="#3f51b5")
    plt.ylabel("ASR")
    plt.title("Provael — ASR by attack family (stub)")
    plt.ylim(0, 1)
    plt.tight_layout()
    plt.savefig("asr_by_family.png", dpi=120)
    print("Wrote asr_by_family.png")


if __name__ == "__main__":
    main()
