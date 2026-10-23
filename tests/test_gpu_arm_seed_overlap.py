# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""A `calibrate` dispatch refuses to roll out the seeds the published headline run scored.

WHY THIS EXISTS. #136's status on 19 October 2026: the `calibrate` stage rolls out seeds 0-19 and
fits on 0-6, and the uncalibrated headline run (`results/smolvla_libero_object_suite_2026-09-14/`)
scored seeds 0-4. A calibrated re-run on 0-4 would score its benign floor on episodes the envelope
was fitted on, the leakage the three-way split exists to prevent, one level up. `scripts/gpu_arm_plan.py` is the
step that speaks before anything bills, so the refusal lives there, and it reads the headline's
seeds from the run's records rather than from a constant.

AND THE SCENES (23 October 2026). Under lerobot 0.5.1 the seed does not pick a LIBERO episode's
starting scene; a reset counter does, and a fresh env starts it at init state 0. So a fit whose
seeds are all clear of 0-4 still starts each task where the uncalibrated headline's first episode
on that task started. The plan step refuses that too, from the same records.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import tomllib
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


def _fake_repo(root: Path, seeds_by_task: dict[str, list[int]]) -> None:
    """A board source naming one run, and one shard per task holding records at these seeds."""
    source = root / "leaderboard" / "results" / "source.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"run": "results/some_run"}), encoding="utf-8")
    for task, seeds in seeds_by_task.items():
        report = root / "results" / "some_run" / task.replace("/", "_") / "report.json"
        report.parent.mkdir(parents=True)
        payload = {"results": [{"task": task, "seed": seed} for seed in seeds]}
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
    assert "#### Starting scenes" in out


def test_only_calibrate_is_seed_checked(capsys: pytest.CaptureFixture[str]) -> None:
    """Attack stages fit nothing, so a seed they share with the headline is not leakage."""
    assert plan_module.main(["control"]) == 0
    out = capsys.readouterr().out
    assert "Seeds" not in out
    assert "scenes" not in out


def test_disjoint_seeds_still_share_the_first_scene() -> None:
    """Seeds 100-119 miss the headline's 0-4, and the fit is still refused.

    Under lerobot 0.5.1 the seed does not reach the counter that picks the scene, so the first fit
    rollout on every task starts at init state 0, which is where the headline's first episode on
    that task started. No value of `seed` in the stage can move it.
    """
    cfg = {**plan_module.stages()["calibrate"], "seed": "100"}
    ok, text = plan_module.seed_check("calibrate", cfg)
    assert "fit 100-106, tuning 107-113, eval 114-119" in text
    assert "No overlap" in text  # the seeds are clear
    assert not ok, text  # the scenes are not
    assert "init state 0" in text
    assert "libero_object/0-9" in text


def test_the_headline_seeds_come_from_the_run_records(tmp_path: Path) -> None:
    """Point the board at another run and the check reads that run's seeds, in every split."""
    _fake_repo(tmp_path, {"libero_object/0": [7, 3], "libero_object/1": [3]})
    assert plan_module.headline_seeds(tmp_path) == ("results/some_run", [3, 7], 3)
    # A task that run never scored, so only its seeds can refuse the stage.
    elsewhere = "libero_object/5"
    cfg = {"seed": "0", "seeds": "20", "tasks": elsewhere}
    ok, text = plan_module.seed_check("calibrate", cfg, tmp_path)
    assert not ok
    assert "3 in the fit split; 7 in the tuning split" in text
    ok, text = plan_module.seed_check("calibrate", {**cfg, "seed": "8"}, tmp_path)
    assert ok, text


def test_the_headline_scenes_come_from_the_run_records(tmp_path: Path) -> None:
    """The tasks whose first scene the fit would share are read from the records, not assumed.

    Refused for the task the run scored, passed for one it never ran, with seeds clear of both.
    """
    _fake_repo(tmp_path, {"libero_object/0": [0, 1]})
    cfg = {"seed": "100", "seeds": "20", "tasks": "libero_object/1"}
    ok, text = plan_module.seed_check("calibrate", cfg, tmp_path)
    assert ok, text
    assert "fits no task" in text
    ok, text = plan_module.seed_check(
        "calibrate", {**cfg, "tasks": "libero_object/0,libero_object/1"}, tmp_path
    )
    assert not ok
    assert "on libero_object/0." in text


def test_the_scene_rule_is_the_one_the_adapter_runs() -> None:
    """The rule the check applies was read from lerobot 0.5.1 as the LIBERO adapter drives it.

    One sub-env per task (so the counter starts at 0) and no scene chosen by the adapter. If the
    pin moves or the adapter starts setting the init state itself, the rule has to be read again,
    and this fails before a dispatch is waved through on a stale one.
    """
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    pins = pyproject["project"]["optional-dependencies"]["lerobot"]
    assert any(
        pin.startswith("lerobot[") and pin.endswith(f"=={plan_module.LEROBOT_RULE_VERSION}")
        for pin in pins
    ), pins
    adapter = (REPO / "src" / "provael" / "suites" / "libero.py").read_text(encoding="utf-8")
    assert "make_env(cfg, n_envs=1)" in adapter
    assert "init_state" not in adapter


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
