# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The keep-out path viewer draws only what the report carries, and says so when it carries nothing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from provael.config import RunConfig
from provael.report import to_json
from provael.runner import run
from provael.types import Trajectory

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "plot_keepout_paths.py"


def _report_with_paths(tmp_path: Path) -> Path:
    """A stub report re-labelled as a LIBERO task, with synthetic 3-D trajectories attached."""
    report = json.loads(
        to_json(run(RunConfig(policy="stub", suite="stub", attacks=["none", "roleplay"], episodes=2, seed=0)))
    )
    for i, row in enumerate(report["results"]):
        row["task"] = "libero_object/0"
        # benign paths stay outside the default box; roleplay paths drift into it
        drift = 0.0 if row["attack"] == "none" else 0.3
        path = [[-0.2 + 0.05 * t + drift * (t / 8), -0.25 - 0.02 * t, 0.9] for t in range(9)]
        row["trajectory"] = Trajectory.encode(path).model_dump(mode="json")
        row["steps_to_success"] = 5 if row["attack"] == "roleplay" else None
        del i
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return run_dir


def test_it_writes_one_svg_per_task_with_zone_paths_and_markers(tmp_path: Path) -> None:
    run_dir = _report_with_paths(tmp_path)
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir), "--out", str(tmp_path / "fig")],
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    svg = (tmp_path / "fig" / "libero_object-0__roleplay.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "keep-out default" in svg  # the documented default box, named
    assert svg.count("<polyline") == 8  # (2 benign + 2 roleplay paths) x two panels
    assert svg.count("<circle") == 4  # a first-unsafe marker per roleplay episode, per panel
    assert "benign `none` ×2 (blue) · `roleplay` ×2 (red, 2 reached the zone" in svg


def test_a_report_without_trajectories_draws_nothing_and_says_so(tmp_path: Path) -> None:
    run_dir = tmp_path / "old"
    run_dir.mkdir()
    old = ROOT / "results" / "smolvla_libero_object_suite" / "libero_object_0" / "report.json"
    (run_dir / "report.json").write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir), "--out", str(tmp_path / "fig")],
        capture_output=True, text=True,
    )
    assert done.returncode == 1
    assert "no episode" in done.stderr and "3-D trajectory" in done.stderr
    assert not (tmp_path / "fig").exists()
