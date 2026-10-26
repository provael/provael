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
import re
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


def _fake_repo(
    root: Path,
    seeds_by_task: dict[str, list[int]],
    init_states: dict[str, list[int | None]] | None = None,
) -> None:
    """A board source naming one run, and one shard per task holding records at these seeds.

    ``init_states`` gives a task's records the `init_state` each one recorded (report schema 8),
    in seed order; ``None`` in a slot leaves that record without one, as an older run's are.
    """
    source = root / "leaderboard" / "results" / "source.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"run": "results/some_run"}), encoding="utf-8")
    for task, seeds in seeds_by_task.items():
        report = root / "results" / "some_run" / task.replace("/", "_") / "report.json"
        report.parent.mkdir(parents=True)
        states = (init_states or {}).get(task, [None] * len(seeds))
        records = []
        for seed, state in zip(seeds, states, strict=True):
            record: dict[str, object] = {"task": task, "seed": seed}
            if state is not None:
                record["init_state"] = state
            records.append(record)
        report.write_text(json.dumps({"results": records}), encoding="utf-8")


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
    """Attack stages fit nothing, so a seed they share with the headline is not leakage.

    `suite` rather than `control` since 26 October 2026: `control` pins its scenes now, and a
    stage that pins is checked against the fit (see the pinned-scene tests below).
    """
    assert plan_module.main(["suite"]) == 0
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

    One sub-env per task, so a fresh counter starts at 0. If the pin moves, the rule has to be read
    again, and this fails before a dispatch is waved through on a stale one.

    THE RULE MOVED ON PURPOSE, 24 October 2026. This used to assert that the adapter never touched
    `init_state` at all. It now reads lerobot's counter back after every reset (`init_state` on
    each record), and when a calibrate stage passes `init_state_offset` it sets where a FRESH env's
    counter starts, once, through gymnasium's `set_attr`, so a fit can begin past the states a
    scored run recorded (#136). It still never picks a state per episode: the counter moves one per
    reset and two after a success, which is what `fit_init_states` plans with.

    AND AGAIN, 26 October 2026, on purpose. A scored run can pin its scenes
    (`--pin-init-states`): the adapter then sets the counter before EVERY reset, so the seed picks
    the state, and checks the state it read back. That is a second `set_attr`, and the only one
    that picks a state per episode; the calibrate stage never pins, so its fit still walks as
    `fit_init_states` plans. So this fails if the counter is written anywhere but those two places.
    """
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    pins = pyproject["project"]["optional-dependencies"]["lerobot"]
    assert any(
        pin.startswith("lerobot[") and pin.endswith(f"=={plan_module.LEROBOT_RULE_VERSION}")
        for pin in pins
    ), pins
    adapter = (REPO / "src" / "provael" / "suites" / "libero.py").read_text(encoding="utf-8")
    assert "make_env(cfg, n_envs=1)" in adapter
    assert 'get_attr("init_state_id")' in adapter
    assert adapter.count('set_attr("init_state_id"') == 2
    assert 'set_attr("init_state_id", self._init_state_offset)' in adapter
    assert 'set_attr("init_state_id", pinned)' in adapter
    assert re.search(r"\.init_state_id\s*=", adapter) is None, "a direct write to the counter"


def test_disjoint_seeds_with_overlapping_recorded_init_states_refuse(tmp_path: Path) -> None:
    """Seeds clear of the run's, and a fit window on states the run recorded: refused.

    The run recorded the benign floor at init states 0, 2, 4, 6, 8, the way a fresh container walks
    them when every episode ends in success. The fit's rollouts can start anywhere in 0-12.
    """
    _fake_repo(tmp_path, {"libero_object/0": [0, 1, 2, 3, 4]}, {"libero_object/0": [0, 2, 4, 6, 8]})
    cfg = {"seed": "100", "seeds": "20", "tasks": "libero_object/0"}
    assert plan_module.fit_init_states(cfg) == list(range(13))
    ok, text = plan_module.seed_check("calibrate", cfg, tmp_path)
    assert "No overlap" in text  # the seeds are clear
    assert not ok, text
    assert "0,2,4,6,8 on libero_object/0" in text
    assert "An `init_state_offset` of 9 would miss every recorded state" in text


def test_disjoint_seeds_and_disjoint_recorded_init_states_pass(tmp_path: Path) -> None:
    _fake_repo(tmp_path, {"libero_object/0": [0, 1, 2, 3, 4]}, {"libero_object/0": [20, 21, 22, 23, 24]})
    cfg = {"seed": "100", "seeds": "20", "tasks": "libero_object/0"}
    ok, text = plan_module.seed_check("calibrate", cfg, tmp_path)
    assert ok, text
    assert "none of the fit's planned init states is one the run recorded" in text
    assert "not planned here" in text  # the tuning split and attacked arm are said, not hidden


def test_no_offset_is_suggested_when_no_window_fits(tmp_path: Path) -> None:
    every_fifth: list[int | None] = list(range(0, 50, 5))
    _fake_repo(tmp_path, {"libero_object/0": list(range(10))}, {"libero_object/0": every_fifth})
    ok, text = plan_module.seed_check(
        "calibrate", {"seed": "100", "seeds": "20", "tasks": "libero_object/0"}, tmp_path
    )
    assert not ok
    assert "No offset misses them all" in text


def test_a_task_with_any_record_lacking_init_state_keeps_the_opening_scene_rule(
    tmp_path: Path,
) -> None:
    """Part of the task's scenes would be unknown, and an unknown scene is not a clear one."""
    _fake_repo(tmp_path, {"libero_object/0": [0, 1]}, {"libero_object/0": [20, None]})
    ok, text = plan_module.seed_check(
        "calibrate", {"seed": "100", "seeds": "20", "tasks": "libero_object/0"}, tmp_path
    )
    assert not ok
    assert "the headline's first episode started from on libero_object/0." in text


def test_an_offset_against_a_run_without_records_is_refused_as_unplaceable(tmp_path: Path) -> None:
    """Off the opening scene, the one scene a pre-schema-8 run places, nothing shows a clear fit."""
    _fake_repo(tmp_path, {"libero_object/0": [0, 1]})
    cfg = {"seed": "100", "seeds": "20", "tasks": "libero_object/0", "init_state_offset": "30"}
    assert plan_module.fit_init_states(cfg) == list(range(30, 43))
    ok, text = plan_module.seed_check("calibrate", cfg, tmp_path)
    assert not ok
    assert "past the opening scene" in text
    assert "30-42" in text


def test_an_offset_needs_an_image_whose_provael_takes_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clear window still refuses on an image whose release predates `--init-state-offset`."""
    _fake_repo(tmp_path, {"libero_object/0": [0, 1, 2]}, {"libero_object/0": [0, 1, 2]})
    cfg = {"seed": "100", "seeds": "20", "tasks": "libero_object/0", "init_state_offset": "20"}
    monkeypatch.setattr(plan_module, "image_pin", lambda: "0.46.0")
    ok, text = plan_module.seed_check("calibrate", cfg, tmp_path)
    assert not ok
    assert "takes `--init-state-offset`" in text
    monkeypatch.setattr(plan_module, "image_pin", lambda: "0.47.0")
    ok, text = plan_module.seed_check("calibrate", cfg, tmp_path)
    assert ok, text


def test_a_fit_window_past_the_last_state_wraps() -> None:
    """lerobot takes the counter modulo the number of states, so 45 + 12 lands back on 7."""
    cfg = {"seed": "100", "seeds": "20", "init_state_offset": "45"}
    assert plan_module.fit_init_states(cfg) == [*range(8), *range(45, 50)]


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


def test_the_container_passes_the_offset_the_plan_checks() -> None:
    """Same rule as the seed: the command passes `STAGES["calibrate"]["init_state_offset"]`."""
    for node in ast.walk(ast.parse(EXAMPLE.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.List) or len(node.elts) != 2:
            continue
        flag = node.elts[0]
        if isinstance(flag, ast.Constant) and flag.value == "--init-state-offset":
            assert ast.unparse(node.elts[1]) == "cfg['init_state_offset']", ast.unparse(node)
            return
    pytest.fail("no `--init-state-offset` passed in the example")


def test_the_committed_offset_is_lerobots_own_start() -> None:
    """0 until a scored run records init states and the image takes the flag; the plan step says why."""
    assert plan_module.stages()["calibrate"]["init_state_offset"] == "0"



# PINNED SCENES (26 October 2026). A scored stage that carries `pin_init_states` starts the episode
# at seed s from init state (pin + s) mod 50, set before every reset, so its scenes are known before
# it runs and the plan compares them, per task, with the calibrate stage's fit window.

_FIT = {"tasks": "libero_object/0,libero_object/1", "seed": "100", "seeds": "20"}


def _pinned(pin: str, tasks: str = "libero_object/0,libero_object/1") -> dict[str, str]:
    return {"tasks": tasks, "seeds": "5", "pin_init_states": pin}


def test_pinned_states_follow_the_seeds_alone() -> None:
    """One state per seed, whatever the arms: five seeds from 0 at pin 45 are 45-49."""
    assert plan_module.pinned_init_states(_pinned("45")) == [45, 46, 47, 48, 49]
    # Seeds 3-7 from pin 45 run past the last state and wrap: 48, 49, then 0, 1, 2.
    assert plan_module.pinned_init_states({**_pinned("45"), "seed": "3"}) == [0, 1, 2, 48, 49]


def test_disjoint_pinned_states_pass_and_print_both_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plan_module, "image_pin", lambda: "0.47.0")
    ok, text = plan_module.pinned_scene_check(_pinned("13"), _FIT)
    assert ok, text
    assert "init states 13-17 of libero_object/0-1" in text
    assert "can start from init states 0-12 on each task" in text
    assert "No shared scene" in text


def test_pinned_states_inside_the_fit_window_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin 10 puts seeds 0-4 on 10-14; the fit's rollouts can start anywhere in 0-12."""
    monkeypatch.setattr(plan_module, "image_pin", lambda: "0.47.0")
    ok, text = plan_module.pinned_scene_check(_pinned("10"), _FIT)
    assert not ok
    assert "init states 10-12 are pinned here and inside the fit's window" in text
    assert "on libero_object/0-1" in text
    # Wrapped past the last state, 48 + 4 lands on 2, inside the window again.
    ok, text = plan_module.pinned_scene_check(_pinned("48"), _FIT)
    assert not ok
    assert "init states 0-2 are pinned here" in text


def test_a_pinned_stage_on_tasks_the_fit_never_runs_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_module, "image_pin", lambda: "0.47.0")
    ok, text = plan_module.pinned_scene_check(_pinned("0", tasks="libero_object/5"), _FIT)
    assert ok, text
    assert "fits none of this stage's tasks" in text


def test_a_pin_needs_an_image_whose_provael_takes_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_module, "image_pin", lambda: "0.46.0")
    ok, text = plan_module.pinned_scene_check(_pinned("13"), _FIT)
    assert not ok
    assert "takes `--pin-init-states`" in text
    assert "No shared scene" in text  # the scenes are clear; only the image refuses


def test_the_committed_control_stage_pins_clear_of_the_fit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """45-49 against the committed fit's 0-12: clear, and refused only by the 0.46.0 image.

    This is the state on main until a release carries `--pin-init-states` and `PROVAEL_PIN` moves
    to it. The change that moves the pin updates this test with it.
    """
    assert plan_module.stages()["control"]["pin_init_states"] == "45"
    assert plan_module.main(["control"]) == 1
    out = capsys.readouterr().out
    assert "Seeds 0-4 put it on init states 45-49 of libero_object/0-9" in out
    assert "can start from init states 0-12 on each task" in out
    assert "No shared scene" in out
    assert "takes `--pin-init-states`" in out


def test_the_container_passes_the_pin_and_the_seed_the_plan_reads() -> None:
    """The pinned states are worked out from the stage's `pin_init_states` and `seed`, so the
    `provael attack` command must pass both from STAGES, not literals."""
    tree = ast.parse(EXAMPLE.read_text(encoding="utf-8"))
    pin = seed = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.List) or not node.elts:
            continue
        words = [elt.value if isinstance(elt, ast.Constant) else None for elt in node.elts]
        if words[:2] == ["provael", "attack"]:
            seed = ast.unparse(node.elts[words.index("--seed") + 1])
        if words[0] == "--pin-init-states":
            pin = ast.unparse(node.elts[1])
    assert seed == "cfg.get('seed', '0')", seed
    assert pin == "cfg['pin_init_states']", pin
