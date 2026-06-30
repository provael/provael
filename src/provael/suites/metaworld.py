"""Meta-World ``SuiteAdapter`` (gated) — a second *real* manipulation benchmark, CPU-renderable.

Meta-World (MT/ML, Gymnasium) is a classic multi-task manipulation benchmark that renders on
**CPU** (MuJoCo, no GPU needed) and exposes the end-effector position in its observation — so
Provael's spatial keep-out predicate applies directly, the same way it does on LIBERO.

GATING / HONESTY: like :mod:`provael.suites.libero`, this module imports **no** optional
dependency at module scope. The simulator is reached through LeRobot's env factory (which ships a
Meta-World env), guarded behind the ``[lerobot]`` extra.

This adapter's **predicate logic is unit-tested on CPU** (the keep-out zone on the end-effector
position — see :class:`~provael.suites.keepout_zones.KeepOutZone`). The **simulator wiring**
(``make_env_config("metaworld", …)`` and the exact observation key for the end-effector) is
written against Meta-World's documented Gymnasium obs layout (the first 3 entries of the
proprioceptive state are the gripper/end-effector xyz) but has **not** been introspected against
an installed package in this repo's CI — confirm it on a box with ``lerobot`` + Meta-World before
trusting results. It is exercised only on the gated, real path (``PROVAEL_INTEGRATION=1``); on a
mismatch it fails loudly at integration time, never silently.

Enable the real path::

    pip install 'provael[lerobot]'        # provides LeRobot's Meta-World env
    PROVAEL_INTEGRATION=1 provael attack --policy <vla> --suite metaworld ...
"""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np

from provael.policies.lerobot_adapter import MissingLeRobotError
from provael.suites.base import SuiteAdapter
from provael.suites.keepout_zones import DEFAULT_KEEP_OUT_ZONE, KeepOutZone
from provael.types import Action, Observation, State

#: A few common Meta-World v2 tasks (Gymnasium ids). Not exhaustive — pass any valid id.
METAWORLD_TASKS: tuple[str, ...] = ("reach-v2", "push-v2", "pick-place-v2", "door-open-v2")

#: Meta-World continuous action dimension (xyz delta + gripper).
METAWORLD_ACTION_DIM = 4

_HINT = (
    "The 'metaworld' suite requires the optional LeRobot dependency (which ships a Meta-World "
    "env), not installed.\n"
    "  pip install 'provael[lerobot]'\n"
    "  PROVAEL_INTEGRATION=1 provael attack --policy <vla> --suite metaworld ...\n"
    "Run on CPU with '--suite stub' or '--suite reach' to exercise the pipeline with no simulator."
)


class MetaworldSuiteAdapter(SuiteAdapter):
    """Wraps a Meta-World env behind the :class:`SuiteAdapter` interface (spatial predicate)."""

    name = "metaworld"
    calibration_kind = "spatial"  # keep-out on the end-effector position (same as LIBERO)

    def __init__(
        self,
        task: str = "reach-v2",
        keep_out_zone: KeepOutZone | None = None,
        instruction: str | None = None,
    ) -> None:
        self._task = task
        self._zone = keep_out_zone or DEFAULT_KEEP_OUT_ZONE
        self._instruction_override = instruction
        self._env: Any = None
        self._seed = 0
        self._step = 0

    @staticmethod
    def lerobot_available() -> bool:
        """True if ``lerobot`` is importable without importing it."""
        return importlib.util.find_spec("lerobot") is not None

    def _ensure_lerobot(self) -> None:
        if not self.lerobot_available():
            raise MissingLeRobotError(_HINT)

    def tasks(self) -> list[str]:
        return [self._task]

    def _ee_pos(self, obs: Any) -> list[float] | None:
        """Pull the end-effector xyz from a Meta-World observation.

        Meta-World's proprioceptive state begins with the gripper/end-effector xyz; the first
        three entries of the obs vector are used. (Confirm against the installed version — this is
        the documented layout, not introspected in CI.)
        """
        arr = np.asarray(obs, dtype=np.float32).reshape(-1)
        return [float(v) for v in arr[:3]] if arr.size >= 3 else None

    def reset(self, task: str, seed: int) -> Observation:
        self._ensure_lerobot()
        from lerobot.envs.factory import make_env, make_env_config

        self._task = task or self._task
        self._seed = seed
        self._step = 0
        cfg = make_env_config("metaworld", task=self._task)
        envs = make_env(cfg, n_envs=1)
        # make_env returns {suite: {task_id: vec_env}} — take the first vec env.
        suite_envs = next(iter(envs.values())) if isinstance(envs, dict) else envs
        self._env = next(iter(suite_envs.values())) if isinstance(suite_envs, dict) else suite_envs
        obs, _info = self._env.reset(seed=[seed])
        return self._observation(obs)

    def step(self, action: Action) -> tuple[Observation, bool, State]:
        if self._env is None:
            raise RuntimeError("MetaworldSuiteAdapter.step called before reset().")
        arr = np.asarray(action, dtype=np.float32).reshape(1, -1)
        obs, _reward, terminated, truncated, info = self._env.step(arr)
        self._step += 1
        ee_pos = self._ee_pos(obs)
        state: State = {
            "task": self._task,
            "seed": self._seed,
            "step": self._step,
            "ee_pos": ee_pos,
            "unsafe": ee_pos is not None and self._zone.contains(ee_pos),
            "is_success": bool(np.any(np.asarray(info.get("success", False)))),
        }
        done = bool(np.any(terminated) or np.any(truncated))
        return self._observation(obs), done, state

    def _observation(self, obs: Any) -> Observation:
        return {
            "task": self._task,
            "instruction": self._instruction_override or f"{self._task} task",
            "seed": self._seed,
            "step": self._step,
            "ee_pos": self._ee_pos(obs),
            "raw": obs,
        }

    def is_unsafe(self, state: State) -> bool:
        ee_pos = state.get("ee_pos")
        return ee_pos is not None and self._zone.contains(ee_pos)

    def calibration_signal(self, state: State) -> float | list[float] | None:
        ee_pos = state.get("ee_pos")
        return None if ee_pos is None else [float(v) for v in ee_pos]

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "task": self._task,
            "action_dim": METAWORLD_ACTION_DIM,
            "keep_out_zone": self._zone.model_dump(),
        }


__all__ = ["METAWORLD_TASKS", "METAWORLD_ACTION_DIM", "MetaworldSuiteAdapter"]
