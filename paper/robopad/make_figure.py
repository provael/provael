"""Benign-arm firings per task, derived from the committed run artifacts.

Reads the two committed benign arms and plots per-task firing counts pooled over both runs.
Nothing here is hardcoded: the counts, the task ids and the two instruction strings are all read
from the reports. Run from the repository root.

    python paper/vlm4rwd/make_figure.py

ANONYMITY: the figure carries no path, no user, no host and no project name. Matplotlib writes
`/Producer` and `/Creator` into PDF metadata by default, so both are blanked below; the anonymity
checker reads the rendered file rather than trusting this comment.
"""

from __future__ import annotations

import glob
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RUNS = ("smolvla_libero_object_control", "smolvla_libero_object_suite")
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent / "benign_firings.pdf"


def load(run: str) -> list[dict]:
    rows: list[dict] = []
    for f in sorted(glob.glob(str(ROOT / "results" / run / "libero_object_*" / "report.json"))):
        with open(f, encoding="utf-8") as fh:
            rows.extend(json.load(fh)["results"])
    if not rows:
        raise SystemExit(f"no records read for {run}; run this from the repository root")
    return rows


def main() -> None:
    benign = [r for run in RUNS for r in load(run) if r["attack"] == "none"]
    tasks = sorted({r["task"] for r in benign}, key=lambda t: int(t.split("/")[-1]))
    fired = {t: sum(1 for r in benign if r["task"] == t and r["success"]) for t in tasks}
    total = {t: sum(1 for r in benign if r["task"] == t) for t in tasks}
    # The instruction is read from the artifact, so a relabelled task cannot mislabel a bar.
    instr = {r["task"]: r["original_instruction"] for r in benign}

    if sum(total.values()) != 100:
        raise SystemExit(f"expected 100 benign episodes, read {sum(total.values())}")

    fig, ax = plt.subplots(figsize=(7.0, 3.1))
    labels = [t.split("/")[-1] for t in tasks]
    counts = [fired[t] for t in tasks]
    bars = ax.bar(labels, counts, color=["#9E3123" if c else "#C9C2B4" for c in counts], width=0.62)

    for t, b, c in zip(tasks, bars, counts, strict=True):
        if c:
            ax.annotate(
                f'{c}/{total[t]}\n"{instr[t]}"',
                xy=(b.get_x() + b.get_width() / 2, c),
                xytext=(0, 6), textcoords="offset points",
                ha="center", va="bottom", fontsize=7.0, linespacing=1.35,
            )

    ax.set_ylim(0, 4.6)
    ax.set_yticks(range(5))
    ax.set_xlabel("task index within the suite", fontsize=9)
    ax.set_ylabel("benign episodes flagged unsafe", fontsize=9)
    ax.tick_params(labelsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#E4DED2", linewidth=0.7)
    fig.tight_layout()

    # Blank the metadata matplotlib would otherwise fill with tool and user provenance.
    fig.savefig(OUT, metadata={"Creator": "", "Producer": "", "Author": "", "Title": ""})
    fired_n, total_n = sum(counts), sum(total.values())
    print(f"wrote {OUT.name}: {fired_n}/{total_n} firings across {len(tasks)} tasks")
    print("  per task:", {t.split('/')[-1]: f"{fired[t]}/{total[t]}" for t in tasks})


if __name__ == "__main__":
    main()
