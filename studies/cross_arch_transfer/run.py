#!/usr/bin/env python3
"""Run the cross-architecture transfer study and write byte-deterministic artifacts.

Defensive, sim-only. Runs the shared instruction/visual/injection battery (+ the benign ``none``
control) against SmolVLA (LeRobot) and π0 (openpi) through the *same* runner + scoring the rest of
Provael uses — no ASR is reimplemented. On CPU this runs the deterministic stub battery (no
GPU/network, CI-green) and marks the two real backends ``pending``; on a gated box
(``PROVAEL_INTEGRATION=1`` + the ``[lerobot]`` / ``[openpi]`` extra, and for π0 a running openpi
server) the corresponding architecture is measured. Equivalent to ``provael study cross-arch``.

    python studies/cross_arch_transfer/run.py        # writes results/cross_arch_transfer/

The study logic lives in ``provael.studies.cross_arch`` so the CLI and this script share one path.
Because ``[openpi]`` and ``[lerobot]`` pin conflicting numpy majors, the real SmolVLA and π0 runs
happen in separate environments; run this there and merge the per-architecture reports offline via
``provael.studies.cross_arch.merge_reports``.
"""

from __future__ import annotations

from pathlib import Path

from provael.studies.cross_arch import build_study, render_table, write_study

#: Where the deterministic artifacts (summary + per-architecture RunReport JSON) are written.
OUT_DIR = Path("results/cross_arch_transfer")


def main() -> None:
    summary, reports = build_study()
    write_study(summary, reports, OUT_DIR)
    render_table(summary)
    measured = ", ".join(sorted(reports)) or "(none — gated backends unavailable here)"
    print(f"\nWrote {OUT_DIR}/ (summary.json + per-architecture RunReport JSON).")
    print(f"Measured architectures: {measured}.")


if __name__ == "__main__":
    main()
