# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""A `calibrate` dispatch refuses to roll out the seeds the published headline run scored.

WHY THIS EXISTS. #136's status on 19 October 2026: the `calibrate` stage rolls out seeds 0-19 and
fits on 0-6, and the uncalibrated headline run (`results/smolvla_libero_object_suite_2026-09-14/`)
scored seeds 0-4. A calibrated re-run on 0-4 would score its benign floor on episodes the envelope
was fitted on, the leakage the three-way split exists to prevent, one level up. `scripts/gpu_arm_plan.py` is the
step that speaks before anything bills, so the refusal lives there, and it reads the headline's
seeds from the run's records rather than from a constant.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "gpu-ci" / "modal_libero_suite.py"

_spec = importlib.util.spec_from_file_location(
    "gpu_arm_plan", REPO / "scripts" / "gpu_arm_plan.py"
)
assert _spec and _spec.loader
plan_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_module)


def _fake_repo(root: Path, seeds_by_shard: dict[str, list[int]]) -> None:
    """A board source naming one run, and that run's shards holding records at these seeds."""
    source = root / "leaderboard" / "results" / "source.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"run": "results/some_run"}), encoding="utf-8")
    for shard, seeds in seeds_by_shard.items():
        report = root / "results" / "some_run" / shard / "report.json"
        report.parent.mkdir(parents=True)
        payload = {"results": [{"seed": seed} for seed in seeds]}
        report.write_text(json.dumps(payload), encoding="utf-8")


def test_the_committed_calibrate_stage_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    """Base seed 0, 20 seeds: fit 0-6, and the headline scored 0-4, so the plan step exits 1.

    This is the state on main until one side moves off those seeds (#136). The change that moves
    one updates this test with it.
    """
    assert plan_module.main(["calibrate"]) == 1
    out = capsys.readouterr().out
    assert "fit 0-6, tuning 7-13, eval 14-19" in out
    assert "scored seeds 0-4 in its 400 episode records" in out
    assert "**Refused:**" in out
    assert "0-4 in the fit split" in out


def test_only_calibrate_is_seed_checked(capsys: pytest.CaptureFixture[str]) -> None:
    """Attack stages fit nothing, so a seed they share with the headline is not leakage."""
    assert plan_module.main(["control"]) == 0
    assert "Seeds" not in capsys.readouterr().out


def test_a_calibration_clear_of_the_headline_seeds_passes() -> None:
    cfg = {**plan_module.stages()["calibrate"], "seed": "100"}
    ok, text = plan_module.seed_check("calibrate", cfg)
    assert ok, text
    assert "fit 100-106, tuning 107-113, eval 114-119" in text
    assert "No overlap" in text


def test_the_headline_seeds_come_from_the_run_records(tmp_path: Path) -> None:
    """Point the board at another run and the check reads that run's seeds, in every split."""
    _fake_repo(tmp_path, {"libero_object_0": [7, 3], "libero_object_1": [3]})
    assert plan_module.headline_seeds(tmp_path) == ("results/some_run", [3, 7], 3)
    ok, text = plan_module.seed_check("calibrate", {"seed": "0", "seeds": "20"}, tmp_path)
    assert not ok
    assert "3 in the fit split; 7 in the tuning split" in text
    ok, text = plan_module.seed_check("calibrate", {"seed": "8", "seeds": "20"}, tmp_path)
    assert ok, text


def test_a_run_without_records_refuses_rather_than_passes(tmp_path: Path) -> None:
    """A check that cannot see the headline's seeds has not shown they are clear."""
    _fake_repo(tmp_path, {})
    with pytest.raises(SystemExit, match="no episode records"):
        plan_module.seed_check("calibrate", {"seed": "100", "seeds": "20"}, tmp_path)


def test_the_container_passes_the_seed_the_plan_checks() -> None:
    """The plan step reads `STAGES["calibrate"]["seed"]`, so the command must pass that, not a
    literal. A literal would let the two drift: the check would pass one seed range while the
    containers rolled out another.
    """
    for node in ast.walk(ast.parse(EXAMPLE.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.List):
            continue
        words = [elt.value if isinstance(elt, ast.Constant) else None for elt in node.elts]
        if words[:2] == ["provael", "calibrate"]:
            passed = node.elts[words.index("--seed") + 1]
            assert ast.unparse(passed) == "cfg['seed']", ast.unparse(passed)
            return
    pytest.fail("no `provael calibrate` command list found in the example")
