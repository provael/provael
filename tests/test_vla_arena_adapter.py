# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""VLA-Arena suite adapter, exercised against a fake env shaped by VLA-Arena's own source.

The package pins Python 3.11 and never enters the CPU build, so nothing here imports it. The fake
below reproduces the surface the adapter reads — read from ``bddl_base_domain.py``,
``env_wrapper.py``, ``benchmark/__init__.py`` and ``models/smolvla/evaluator.py`` on 14 September
2026 — and the tests assert the adapter's contract with provael: the declared predicate is read
and not decided, the observation reaches a policy adapter in lerobot's LIBERO-wrapper shape, and a
task name can never be attributed to a different benchmark or level.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import numpy as np
import pytest

from provael.suites import SCAFFOLDING_SUITES, make_suite, suite_is_ready
from provael.suites.vla_arena import (
    VLA_ARENA_BENCHMARKS,
    VLA_ARENA_DUMMY_ACTION,
    VLA_ARENA_SAFETY_BENCHMARKS,
    MissingVlaArenaError,
    VlaArenaSuiteAdapter,
    parse_vla_arena_task,
)
from provael.types import IMAGE_KEY


# ── the fake, shaped by the source ───────────────────────────────────────────
class _FakeEnv:
    """``OffScreenRenderEnv`` as the adapter uses it: seed/reset/set_init_state/step/get_observation."""

    def __init__(self, bddl_file_name: str, camera_heights: int, camera_widths: int) -> None:
        self.bddl_file_name = bddl_file_name
        self.h, self.w = camera_heights, camera_widths
        self.seeds: list[int] = []
        self.steps: list[np.ndarray] = []
        self.init_state: Any = None
        self.cost_on_steps: set[int] = set()
        self.success_on_step: int | None = None
        self._t = 0

    def seed(self, seed: int) -> None:
        self.seeds.append(int(seed))

    def reset(self) -> dict[str, Any]:
        self._t = 0
        return self._obs()

    def set_init_state(self, init_state: Any) -> dict[str, Any]:
        self.init_state = init_state
        return self._obs()

    def get_observation(self) -> dict[str, Any]:
        return self._obs()

    def step(self, action: np.ndarray) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        self.steps.append(np.asarray(action, dtype=np.float32))
        self._t += 1
        # As bddl_base_domain.step: info['cost'] = cost * 10, info['success'], info['timeout'];
        # done = success or timeout.
        cost = 1.0 if self._t in self.cost_on_steps else 0.0  # one temporal predicate, x0.1, x10
        success = self.success_on_step is not None and self._t >= self.success_on_step
        info = {"cost": cost, "success": success, "timeout": False}
        return self._obs(), 0.0, bool(success), info

    def _obs(self) -> dict[str, Any]:
        frame = np.full((self.h, self.w, 3), (self._t * 5) % 256, dtype=np.uint8)
        frame[0, 0] = (255, 0, 0)  # a marker at the raw frame's top-left
        return {
            "agentview_image": frame,
            "robot0_eye_in_hand_image": np.zeros((self.h, self.w, 3), dtype=np.uint8),
            "robot0_eef_pos": np.array([0.1, 0.2, 1.0 + 0.01 * self._t], dtype=np.float32),
            "robot0_eef_quat": np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32),
            "robot0_gripper_qpos": np.array([0.02, -0.02], dtype=np.float32),
            "robot0_gripper_qvel": np.zeros(2, dtype=np.float32),
            "robot0_joint_pos": np.zeros(7, dtype=np.float32),
            "robot0_joint_vel": np.zeros(7, dtype=np.float32),
            "kiwi_1_pos": np.array([0.3, 0.1, 0.9], dtype=np.float32),
        }


class _FakeTask:
    def __init__(self, level: int, level_id: int) -> None:
        self.language = f"pick up the kiwi (L{level} task {level_id})"
        self.level, self.level_id = level, level_id


class _FakeBenchmark:
    """``get_benchmark(name)()`` — level-indexed task lookup as in benchmark/__init__.py."""

    n_per_level = 5

    def get_task_by_level_id(self, level: int, i: int) -> _FakeTask | None:
        return _FakeTask(level, i) if 0 <= i < self.n_per_level else None

    def get_task_bddl_file_path(self, level: int, i: int) -> str | None:
        return f"/fake/bddl_files/suite/level_{level}/task_{i}.bddl" if 0 <= i < self.n_per_level else None

    def get_task_init_states(self, level: int, i: int) -> np.ndarray:
        return np.stack([np.full(3, k, dtype=np.float32) for k in range(4)])

    def get_num_tasks_by_level(self, level: int) -> int:
        return self.n_per_level


@pytest.fixture
def fake_vla_arena(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Install fake ``vla_arena.vla_arena{,.benchmark,.envs}`` modules and report what was built."""
    made: dict[str, Any] = {"envs": []}

    def _make_env(**kwargs: Any) -> _FakeEnv:
        env = _FakeEnv(**kwargs)
        made["envs"].append(env)
        return env

    root = types.ModuleType("vla_arena")
    inner = types.ModuleType("vla_arena.vla_arena")
    bench = types.ModuleType("vla_arena.vla_arena.benchmark")
    bench.get_benchmark = lambda name: _FakeBenchmark  # a CLASS, as in the source
    envs = types.ModuleType("vla_arena.vla_arena.envs")
    envs.OffScreenRenderEnv = _make_env
    inner.benchmark = bench
    inner.envs = envs
    root.vla_arena = inner
    for name, mod in (
        ("vla_arena", root), ("vla_arena.vla_arena", inner),
        ("vla_arena.vla_arena.benchmark", bench), ("vla_arena.vla_arena.envs", envs),
    ):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(VlaArenaSuiteAdapter, "vla_arena_available", staticmethod(lambda: True))
    return made


# ── names, registration, honesty labels ──────────────────────────────────────
def test_task_names_carry_benchmark_level_and_id() -> None:
    assert parse_vla_arena_task("safety_hazard_avoidance/L0/3") == ("safety_hazard_avoidance", 0, 3)
    assert parse_vla_arena_task("long_horizon/l2/0") == ("long_horizon", 2, 0)
    for bad in ("safety_hazard_avoidance/3", "nope/L0/1", "safety_hazard_avoidance/L7/0", "3"):
        with pytest.raises(ValueError):
            parse_vla_arena_task(bad)


def test_it_is_registered_as_scaffolding_until_a_run_is_committed() -> None:
    assert "vla_arena" in SCAFFOLDING_SUITES
    assert suite_is_ready("vla_arena") is False
    assert VLA_ARENA_BENCHMARKS[:5] == VLA_ARENA_SAFETY_BENCHMARKS
    suite = make_suite("vla_arena")
    assert isinstance(suite, VlaArenaSuiteAdapter)
    assert suite.tasks() == ["safety_hazard_avoidance/L0/0"]
    assert suite.metadata()["declares_cost"] is True


def test_the_factory_builds_exactly_one_benchmark_at_one_level_from_the_tasks() -> None:
    suite = make_suite("vla_arena", tasks=["safety_cautious_grasp/L1/2", "safety_cautious_grasp/L1/0"])
    assert isinstance(suite, VlaArenaSuiteAdapter)
    assert (suite.benchmark, suite.level, suite.task_ids) == ("safety_cautious_grasp", 1, (2, 0))
    with pytest.raises(ValueError, match="exactly one benchmark"):
        make_suite("vla_arena", tasks=["safety_cautious_grasp/L1/0", "long_horizon/L1/0"])
    with pytest.raises(ValueError, match="exactly one benchmark"):
        make_suite("vla_arena", tasks=["long_horizon/L0/0", "long_horizon/L1/0"])


def test_missing_package_is_an_actionable_error() -> None:
    suite = VlaArenaSuiteAdapter()
    with pytest.raises(MissingVlaArenaError, match="Python 3.11"):
        suite.reset("safety_hazard_avoidance/L0/0", 0)


def test_no_calibration_can_replace_the_declared_predicate() -> None:
    suite = VlaArenaSuiteAdapter()
    assert suite.calibration_signal({"cost": 3.0}) is None
    assert suite.keep_out_zones() == []


# ── the rollout against the fake ─────────────────────────────────────────────
def test_reset_follows_the_reference_evaluator(fake_vla_arena: dict[str, Any]) -> None:
    suite = VlaArenaSuiteAdapter(benchmark="safety_hazard_avoidance", level=0, task_ids=(1,))
    obs = suite.reset("safety_hazard_avoidance/L0/1", seed=6)
    env = fake_vla_arena["envs"][-1]
    assert env.bddl_file_name.endswith("level_0/task_1.bddl") and (env.h, env.w) == (256, 256)
    assert env.seeds == [6]
    assert np.array_equal(env.init_state, np.full(3, 6 % 4, dtype=np.float32))  # seed % n states
    assert len(env.steps) == 10 and all(np.array_equal(s, VLA_ARENA_DUMMY_ACTION) for s in env.steps)
    assert obs["instruction"].startswith("pick up the kiwi") and obs["task"] == "safety_hazard_avoidance/L0/1"
    assert obs["step"] == 0 and obs["seed"] == 6
    # the LIBERO-wrapper shape a policy adapter consumes: batched pixels + nested robot_state
    raw = obs["raw"]
    assert raw["pixels"]["image"].shape == (1, 256, 256, 3) and raw["pixels"]["image2"].shape == (1, 256, 256, 3)
    assert raw["robot_state"]["eef"]["pos"].shape == (1, 3)
    assert raw["robot_state"]["eef"]["quat"].shape == (1, 4)
    assert raw["robot_state"]["gripper"]["qpos"].shape == (1, 2)
    assert obs[IMAGE_KEY].shape == (256, 256, 3) and obs["pixels_key"] == "image"
    assert obs["ee_pos"] == pytest.approx([0.1, 0.2, 1.0 + 0.1])


def test_reset_refuses_a_task_from_another_benchmark_or_level(fake_vla_arena: dict[str, Any]) -> None:
    suite = VlaArenaSuiteAdapter(benchmark="safety_hazard_avoidance", level=0)
    with pytest.raises(ValueError, match="wrong suite"):
        suite.reset("safety_cautious_grasp/L0/0", 0)
    with pytest.raises(ValueError, match="wrong suite"):
        suite.reset("safety_hazard_avoidance/L1/0", 0)
    with pytest.raises(ValueError, match="no task 9"):
        suite.reset("safety_hazard_avoidance/L0/9", 0)
    assert fake_vla_arena["envs"] == []  # nothing was built for any of them


def test_unsafe_is_exactly_the_declared_cost_firing(fake_vla_arena: dict[str, Any]) -> None:
    suite = VlaArenaSuiteAdapter()
    suite.reset("safety_hazard_avoidance/L0/0", 0)
    env = fake_vla_arena["envs"][-1]
    env.cost_on_steps = {12, 13}  # steps counted after the 10 settling steps: policy steps 2 and 3
    env.success_on_step = 15
    seen = []
    for _ in range(6):
        obs, done, state = suite.step(np.zeros(7, dtype=np.float32))
        seen.append((state["step"], state["cost"], suite.is_unsafe(state), state["task_success"], done))
        if done:
            break
    assert [s[0] for s in seen] == [1, 2, 3, 4, 5]
    assert [s[2] for s in seen] == [False, True, True, False, False]
    assert [s[1] for s in seen] == [0.0, 1.0, 1.0, 0.0, 0.0]
    assert seen[-1][3] is True and seen[-1][4] is True  # native success flag, episode done
    assert state["cost_total"] == 2.0
    # a step's action reaches the env as a 7-vector
    assert env.steps[-1].shape == (7,)


def test_display_frame_turns_the_raw_frame_round(fake_vla_arena: dict[str, Any]) -> None:
    suite = VlaArenaSuiteAdapter()
    obs = suite.reset("safety_hazard_avoidance/L0/0", 0)
    shown = suite.display_frame(obs)
    assert shown is not None and tuple(shown[-1, -1]) == (255, 0, 0)
    assert tuple(obs[IMAGE_KEY][0, 0]) == (255, 0, 0)  # the attack surface is untouched


def test_envs_are_cached_per_task(fake_vla_arena: dict[str, Any]) -> None:
    suite = VlaArenaSuiteAdapter(task_ids=(0, 1))
    suite.reset("safety_hazard_avoidance/L0/0", 0)
    suite.reset("safety_hazard_avoidance/L0/1", 0)
    suite.reset("safety_hazard_avoidance/L0/0", 1)
    assert len(fake_vla_arena["envs"]) == 2
