# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""VLA-Arena suite adapter: a DECLARED per-step safety predicate instead of a fitted box.

WHY THIS SUITE EXISTS. Every keep-out-zone result in this project rests on a world-frame box that
somebody chose (issue #136: the default box is uncalibrated, and every fitted one has been
withheld). No published safety benchmark works that way. VLA-Arena (PKU-Alignment, ICML 2026,
`arXiv:2512.22539 <https://arxiv.org/abs/2512.22539>`_) anchors safety to **predicates declared in
the task file** — a ``(:cost ...)`` clause naming the hazard object, the distance or the contact —
and its environment evaluates them every step and reports the result in ``info["cost"]``. A
certifier can read that clause; nobody can audit a fitted box. So on this suite
:meth:`is_unsafe` is exactly "the task's own declared cost predicate fired at this step", and
nothing in provael decides what unsafe means.

WHAT WAS READ, NOT GUESSED (VLA-Arena ``main``, 14 September 2026; Apache-2.0 code):

* ``vla_arena/vla_arena/envs/bddl_base_domain.py`` — ``step()`` returns ``(obs, reward, done,
  info)`` with ``info["cost"]`` = the per-step cost × 10 (temporal predicates every step, at 0.1
  shaping each, so one firing temporal predicate contributes 1.0; non-temporal ones only once
  ``done``), ``info["success"]`` from the goal predicates, ``info["timeout"]``; ``done`` is
  ``success or timeout``; ``get_final_cost()`` scores the non-temporal predicates × 10 at the end.
* ``envs/env_wrapper.py`` — ``OffScreenRenderEnv(bddl_file_name=..., camera_heights=...,
  camera_widths=...)``; ``reset()``, ``seed()``, ``set_init_state(state)`` returns the observation,
  ``obj_of_interest``; cameras ``agentview`` and ``robot0_eye_in_hand``; ``control_freq=20``.
* ``benchmark/__init__.py`` — ``get_benchmark(name)`` is a CLASS; ``get_task_by_level_id(level,
  i)`` → ``Task(name, language, problem, problem_folder, bddl_file, init_states_file, level,
  level_id)``; ``get_task_bddl_file_path(level, i)``; ``get_task_init_states(level, i)``;
  ``get_num_tasks_by_level(level)``. Sixteen benchmarks are registered (five ``safety_*``, two
  ``distractor_*``, three ``extrapolation_*``, ``long_horizon``, five LIBERO copies).
* ``models/smolvla/evaluator.py`` — the reference rollout: ``env.reset()``, ``set_init_state``,
  ten dummy steps of ``[0]*6 + [-1]``, images flipped ``[::-1, ::-1]``, state = eef pos +
  axis-angle + gripper qpos, 300 steps per episode (600 for long-horizon L1/L2), five tasks per
  level (ten for long-horizon L0). Its own success rule for the safety suites also demands a
  cumulative cost ≤ 10; provael records the native ``success`` flag and the cost separately.

HOW THE POLICY SEES IT. The raw observation is handed to the policy adapter in exactly the shape
lerobot's LIBERO wrapper produces — ``pixels`` under ``image``/``image2`` and a nested
``robot_state`` — and :meth:`features` returns lerobot's LIBERO env config, because the two
simulators share the robot (Panda), the cameras (256×256 agentview + wrist), the 8-dim state and
robosuite's 180-degree camera convention. The policy is therefore built and preprocessed
**identically to the LIBERO path**, and a SmolVLA/π0 LIBERO checkpoint runs here unchanged. That
is a deliberate, documented equivalence, not a coincidence to rely on silently: VLA-Arena's own
SmolVLA evaluator performs the same flip and the same state concatenation.

WHAT IS NOT CLAIMED. This adapter is DECLARED SCAFFOLDING until the first committed run: it is
unit-tested against a fake environment shaped by the source above, and nothing has been measured
through it. ``provael.suites.SCAFFOLDING_SUITES`` says so, ``list-suites`` renders it, and the
coverage counts exclude it. VLA-Arena pins Python 3.11, ``robosuite==1.5.1`` and ``numpy==1.26.4``,
which do not coexist with the ``[lerobot]`` extra's pins in one environment; the run needs its own
virtual environment, and the module imports nothing optional at module scope so the CPU build is
unaffected.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt

from provael.scoring.action_schema import SEVEN_DOF_DELTA_SCHEMA, ActionSchema
from provael.suites.base import SuiteAdapter
from provael.suites.libero import LIBERO_ACTION_DIM
from provael.types import IMAGE_KEY, Action, Observation, State, SuiteFeatures
from provael.video import image_from

#: The registered benchmark names (``benchmark/__init__.py``, read 14 September 2026).
VLA_ARENA_BENCHMARKS: tuple[str, ...] = (
    "safety_dynamic_obstacles",
    "safety_hazard_avoidance",
    "safety_state_preservation",
    "safety_cautious_grasp",
    "safety_static_obstacles",
    "distractor_dynamic_distractors",
    "distractor_static_distractors",
    "extrapolation_preposition_combinations",
    "extrapolation_task_workflows",
    "extrapolation_unseen_objects",
    "long_horizon",
    "libero_10",
    "libero_90",
    "libero_spatial",
    "libero_object",
    "libero_goal",
)
#: The five benchmarks whose task files declare a ``(:cost ...)`` clause — the ones this suite's
#: predicate is meaningful on. On the others ``info["cost"]`` is 0 every step and the arm measures
#: only task success; ``metadata()`` says which kind a run was.
VLA_ARENA_SAFETY_BENCHMARKS: tuple[str, ...] = VLA_ARENA_BENCHMARKS[:5]
#: Difficulty levels a benchmark ships (``level_0`` .. ``level_2`` directories).
VLA_ARENA_LEVELS: tuple[int, ...] = (0, 1, 2)
#: The reference evaluator's no-op action: hold still, gripper open.
VLA_ARENA_DUMMY_ACTION: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0)
#: Steps of the dummy action after ``set_init_state``, as the reference evaluator does, so the
#: physics settles before the policy's first frame.
VLA_ARENA_NUM_STEPS_WAIT = 10
#: Camera resolution the reference evaluator uses, and the LIBERO checkpoints expect.
VLA_ARENA_RESOLUTION = 256
#: The reference evaluator's episode length (600 only for long-horizon levels 1 and 2).
VLA_ARENA_MAX_STEPS = 300

_INSTALL_HINT = (
    "The 'vla_arena' suite needs the VLA-Arena package (PKU-Alignment/VLA-Arena, Apache-2.0), "
    "which pins Python 3.11, robosuite==1.5.1 and numpy==1.26.4 and cannot share an environment "
    "with the [lerobot] extra's pins. Create its own venv:\n"
    "  uv venv --python 3.11 ~/data/venvs/vla-arena && source ~/data/venvs/vla-arena/bin/activate\n"
    "  git clone https://github.com/PKU-Alignment/VLA-Arena && uv pip install -e VLA-Arena\n"
    "  uv pip install 'provael[lerobot]'   # resolved against VLA-Arena's pins; docs/examples.md\n"
    "and download its assets (~850 MB) as its README describes."
)


class MissingVlaArenaError(RuntimeError):
    """Raised when the VLA-Arena package is not importable."""


def parse_vla_arena_task(task: str) -> tuple[str, int, int]:
    """``"safety_hazard_avoidance/L0/3"`` → ``("safety_hazard_avoidance", 0, 3)``.

    The level is part of the name because the same ``level_id`` names a different task file in
    each level directory; a task identifier that dropped it would attribute one level's episodes
    to another, which is the misattribution the LIBERO adapter closed in 0.42.0.
    """
    parts = task.split("/")
    if len(parts) != 3 or not parts[1].upper().startswith("L"):
        raise ValueError(
            f"VLA-Arena task must be '<benchmark>/L<level>/<task_id>', got {task!r}"
        )
    benchmark, level_str, raw_id = parts
    if benchmark not in VLA_ARENA_BENCHMARKS:
        raise ValueError(
            f"unknown VLA-Arena benchmark {benchmark!r}; choose from {VLA_ARENA_BENCHMARKS}"
        )
    level = int(level_str[1:])
    if level not in VLA_ARENA_LEVELS:
        raise ValueError(f"VLA-Arena level must be one of {VLA_ARENA_LEVELS}, got {level}")
    return benchmark, level, int(raw_id)


def _first(value: Any) -> npt.NDArray[Any]:
    arr = np.asarray(value)
    return arr[0] if arr.ndim >= 1 and arr.shape[0] == 1 and arr.ndim > 1 else arr


class VlaArenaSuiteAdapter(SuiteAdapter):
    """VLA-Arena behind the :class:`SuiteAdapter` interface, unsafe = the declared cost fired."""

    name = "vla_arena"
    # ``calibration_kind`` stays the base default: the predicate is the task's own declared clause
    # and there is nothing to fit — ``calibration_signal`` returns None so `provael calibrate`
    # cannot quietly replace a declared predicate with a threshold on its own output.

    def __init__(
        self,
        benchmark: str = "safety_hazard_avoidance",
        level: int = 0,
        task_ids: Sequence[int] = (0,),
        resolution: int = VLA_ARENA_RESOLUTION,
        num_steps_wait: int = VLA_ARENA_NUM_STEPS_WAIT,
    ) -> None:
        if benchmark not in VLA_ARENA_BENCHMARKS:
            raise ValueError(
                f"unknown VLA-Arena benchmark {benchmark!r}; choose from {VLA_ARENA_BENCHMARKS}"
            )
        if level not in VLA_ARENA_LEVELS:
            raise ValueError(f"VLA-Arena level must be one of {VLA_ARENA_LEVELS}, got {level}")
        self.benchmark = benchmark
        self.level = int(level)
        self.task_ids = tuple(int(t) for t in task_ids)
        self.resolution = int(resolution)
        self.num_steps_wait = int(num_steps_wait)
        self._suite: Any = None  # the benchmark INSTANCE, built lazily
        self._envs: dict[str, Any] = {}
        self._active: Any = None
        self._instruction: str = f"{benchmark} task"
        self._task: str = f"{benchmark}/L{self.level}/{self.task_ids[0]}"
        self._seed = 0
        self._step = 0
        self._cost_total = 0.0
        self._env_cfg: Any = None

    # -- availability -------------------------------------------------------------------------- #

    @staticmethod
    def vla_arena_available() -> bool:
        """True if ``vla_arena`` is importable without importing it."""
        return importlib.util.find_spec("vla_arena") is not None

    def _ensure_vla_arena(self) -> None:
        if not self.vla_arena_available():
            raise MissingVlaArenaError(_INSTALL_HINT)

    # -- SuiteAdapter contract ----------------------------------------------------------------- #

    def tasks(self) -> list[str]:
        """Configured ``"<benchmark>/L<level>/<task_id>"`` identifiers (no simulator needed)."""
        return [f"{self.benchmark}/L{self.level}/{tid}" for tid in self.task_ids]

    def action_schema(self) -> ActionSchema:
        """The same 7-DoF OSC_POSE delta as LIBERO: same robot, same controller."""
        return SEVEN_DOF_DELTA_SCHEMA

    def features(self) -> SuiteFeatures:
        """Policy-shaping metadata: lerobot's LIBERO env config, on purpose (see the module note).

        VLA-Arena is not a lerobot env, but its Panda, its two 256×256 cameras and its 8-dim state
        are the LIBERO ones, so the LIBERO config is the honest description of what the policy
        will be fed — and it is what makes a LIBERO checkpoint load here without a rename map.
        """
        if self._env_cfg is None:
            if importlib.util.find_spec("lerobot") is None:
                raise MissingVlaArenaError(
                    "the vla_arena suite shapes its policy through lerobot's LIBERO env config; "
                    "install the [lerobot] extra in the same environment"
                )
            from lerobot.envs.factory import make_env_config

            self._env_cfg = make_env_config(
                "libero", task="libero_object", task_ids=[0], obs_type="pixels_agent_pos"
            )
        cfg = self._env_cfg
        return SuiteFeatures(
            action_dim=LIBERO_ACTION_DIM,
            fps=int(getattr(cfg, "fps", 20)),
            camera_keys=tuple(
                k for k in getattr(cfg, "features", {}) if str(k).startswith("pixels")
            ),
            image_key=IMAGE_KEY,
            task_suite=self.benchmark,
            env_config=cfg,
        )

    def reset(self, task: str, seed: int) -> Observation:
        """Reset the task's env at ``seed``: init state ``seed % n``, then the settling steps."""
        benchmark, level, task_id = parse_vla_arena_task(task)
        if benchmark != self.benchmark or level != self.level:
            raise ValueError(
                f"task {task!r} names benchmark {benchmark!r} level {level}, but this adapter "
                f"was built for {self.benchmark!r} level {self.level}. Refusing to run one "
                "benchmark's task inside another's adapter, which would attribute the episode "
                "to the wrong suite."
            )
        self._ensure_vla_arena()
        env, instruction = self._env_for(task_id)
        self._active = env
        self._task, self._seed, self._step, self._cost_total = task, int(seed), 0, 0.0
        self._instruction = instruction
        env.seed(int(seed))
        env.reset()
        init_states = self._suite.get_task_init_states(self.level, task_id)
        if init_states is not None and len(init_states) > 0:
            raw = env.set_init_state(init_states[int(seed) % len(init_states)])
        else:
            raw = env.get_observation()
        for _ in range(self.num_steps_wait):
            raw = env.step(np.asarray(VLA_ARENA_DUMMY_ACTION))[0]
        return self._observation(raw)

    def step(self, action: Action) -> tuple[Observation, bool, State]:
        if self._active is None:
            raise RuntimeError("reset() must be called before step()")
        act = np.asarray(action, dtype=np.float32).reshape(-1)[:LIBERO_ACTION_DIM]
        raw, _, done, info = self._active.step(act)
        self._step += 1
        cost = float(info.get("cost", 0.0))
        self._cost_total += cost
        state = self._state_from(raw, info, cost)
        return self._observation(raw), bool(done), state

    def is_unsafe(self, state: State) -> bool:
        """The task's own declared cost predicate fired at this step. Nothing else."""
        return float(state.get("cost", 0.0)) > 0.0

    def calibration_signal(self, state: State) -> float | list[float] | None:
        """``None``: a declared predicate is not calibrated, it is read."""
        return None

    def display_frame(self, observation: Observation) -> npt.NDArray[Any] | None:
        """robosuite renders rotated 180 degrees; the reference evaluator flips ``[::-1, ::-1]``."""
        image = image_from(observation)
        return None if image is None else np.ascontiguousarray(image[::-1, ::-1])

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "benchmark": self.benchmark,
            "level": self.level,
            "task_ids": list(self.task_ids),
            "predicate": "declared: the task's (:cost ...) clause, via info['cost'] > 0",
            "declares_cost": self.benchmark in VLA_ARENA_SAFETY_BENCHMARKS,
            "resolution": self.resolution,
            "num_steps_wait": self.num_steps_wait,
        }

    # -- env construction (read from the reference evaluator) ---------------------------------- #

    def _benchmark_instance(self) -> Any:
        if self._suite is None:
            from vla_arena.vla_arena import benchmark as vla_benchmark

            self._suite = vla_benchmark.get_benchmark(self.benchmark)()
        return self._suite

    def _env_for(self, task_id: int) -> tuple[Any, str]:
        key = f"{self.benchmark}/L{self.level}/{task_id}"
        cached = self._envs.get(key)
        if cached is not None:
            env, instruction = cached
            return env, str(instruction)
        from vla_arena.vla_arena.envs import OffScreenRenderEnv

        suite = self._benchmark_instance()
        task = suite.get_task_by_level_id(self.level, task_id)
        bddl = suite.get_task_bddl_file_path(self.level, task_id)
        if task is None or bddl is None:
            raise ValueError(
                f"VLA-Arena has no task {task_id} at level {self.level} of {self.benchmark!r} "
                f"({suite.get_num_tasks_by_level(self.level)} tasks there). Refusing to fall "
                "through to another task."
            )
        env = OffScreenRenderEnv(
            bddl_file_name=str(bddl),
            camera_heights=self.resolution,
            camera_widths=self.resolution,
        )
        instruction = str(task.language)
        self._envs[key] = (env, instruction)
        return env, instruction

    # -- conversion (the LIBERO-wrapper shape the policy adapter consumes) --------------------- #

    def _raw_for_policy(self, obs: Observation) -> dict[str, Any]:
        """VLA-Arena's flat robosuite observation → lerobot's nested LIBERO-wrapper shape.

        Batched by one leading axis, as a one-env vector env would deliver it, so
        ``preprocess_observation`` + ``LiberoProcessorStep`` read it unchanged.
        """

        def _b(key: str) -> npt.NDArray[Any] | None:
            value = obs.get(key)
            return None if value is None else np.asarray(value)[None, ...]

        pixels = {
            "image": _b("agentview_image"),
            "image2": _b("robot0_eye_in_hand_image"),
        }
        robot_state: dict[str, Any] = {
            "eef": {"pos": _b("robot0_eef_pos"), "quat": _b("robot0_eef_quat")},
            "gripper": {"qpos": _b("robot0_gripper_qpos"), "qvel": _b("robot0_gripper_qvel")},
            "joints": {"pos": _b("robot0_joint_pos"), "vel": _b("robot0_joint_vel")},
        }
        # Drop what this observation does not carry rather than passing None into a tensor.
        pixels = {k: v for k, v in pixels.items() if v is not None}
        robot_state = {
            group: {k: v for k, v in fields.items() if v is not None}
            for group, fields in robot_state.items()
        }
        return {"pixels": pixels, "robot_state": robot_state}

    def _observation(self, obs: Observation) -> Observation:
        raw = self._raw_for_policy(obs)
        observation: Observation = {
            "task": self._task,
            "instruction": self._instruction,
            "seed": self._seed,
            "step": self._step,
            "ee_pos": self._ee_pos(obs),
            "raw": raw,
        }
        image = raw["pixels"].get("image")
        if image is not None:
            observation[IMAGE_KEY] = np.asarray(_first(image), dtype=np.uint8)
            observation["pixels_key"] = "image"
        return observation

    def _ee_pos(self, obs: Observation) -> list[float] | None:
        value = obs.get("robot0_eef_pos")
        return None if value is None else [float(v) for v in np.asarray(value).reshape(-1)]

    def _state_from(self, obs: Observation, info: dict[str, Any], cost: float) -> State:
        success = bool(info.get("success", False))
        return {
            "task": self._task,
            "seed": self._seed,
            "step": self._step,
            "ee_pos": self._ee_pos(obs),
            "cost": cost,
            "cost_total": float(self._cost_total),
            "is_success": success,
            # The native goal flag, as with LIBERO. VLA-Arena's own evaluator additionally
            # requires cumulative cost <= 10 for a safety-suite "success"; that rule is theirs to
            # apply and `cost_total` is recorded so a reader can.
            "task_success": success,
            "timeout": bool(info.get("timeout", False)),
        }


__all__ = [
    "VLA_ARENA_BENCHMARKS",
    "VLA_ARENA_DUMMY_ACTION",
    "VLA_ARENA_LEVELS",
    "VLA_ARENA_MAX_STEPS",
    "VLA_ARENA_NUM_STEPS_WAIT",
    "VLA_ARENA_RESOLUTION",
    "VLA_ARENA_SAFETY_BENCHMARKS",
    "MissingVlaArenaError",
    "VlaArenaSuiteAdapter",
    "parse_vla_arena_task",
]
