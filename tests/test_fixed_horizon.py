# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Fixed-horizon termination (P1.4): every episode runs to its horizon, past exits and success.

Under first-event termination an episode stops at its first envelope exit and, on LIBERO, at task
success, so Succ-But-Unsafe, risk exposure time and cumulative cost cannot be observed
(E-2026-21). These tests drive the runner on the stub and on a fake of lerobot's LIBERO env (no
simulator here): a fixed-horizon episode keeps going past both events, an exit and a success
latch, the steps after them are scored, the report says which mode ran, and a first-event run
renders exactly as before. The LIBERO step that avoids lerobot's own reset on success is checked
against a fake; the real one is a gated test in ``tests/test_libero_adapter.py``.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from provael.attacks.registry import make_attack
from provael.config import RunConfig
from provael.ledger import append_trial, record_of
from provael.policies.stub import StubPolicy
from provael.report import to_json, to_markdown
from provael.runner import ResumeModeError, run, run_episode
from provael.scoring.safety_cost import (
    ENDS_AT_SUCCESS_OR_EXIT,
    FIRST_EVENT,
    FIXED_HORIZON,
    risk_exposure_time,
)
from provael.suites.libero import (
    STRICT_GOAL_FRAMES,
    LiberoSuiteAdapter,
    StrictSuccessRule,
    _tilt_deg,
)
from provael.suites.stub import StubSuite
from provael.types import Observation, State

TASK = "libero_object/0"


def _stub_policy() -> StubPolicy:
    policy = StubPolicy()
    policy.load()
    return policy


# --------------------------------------------------------------------------- #
# the stub: past an exit
# --------------------------------------------------------------------------- #


def _stub(mode: str) -> StubSuite:
    suite = StubSuite()
    assert suite.set_termination(mode) is True
    return suite


def test_first_event_is_the_default_and_stops_at_the_exit() -> None:
    assert RunConfig().termination == FIRST_EVENT
    # seed 0: roleplay's aggression clears the per-seed threshold on the first step.
    result = run_episode(_stub_policy(), StubSuite(), make_attack("roleplay"), "reach", 0, 8)
    assert (result.success, result.steps_to_success, result.steps) == (True, 1, 1)
    assert result.termination == "unsafe_exit"
    assert risk_exposure_time(result) == 1


def test_fixed_horizon_runs_past_an_exit_and_counts_the_dwell() -> None:
    result = run_episode(
        _stub_policy(), _stub(FIXED_HORIZON), make_attack("roleplay"), "reach", 0, 8,
        termination=FIXED_HORIZON,
    )
    assert (result.success, result.steps_to_success, result.steps) == (True, 1, 8)
    assert result.termination == "horizon"
    assert len(result.decisions) == 8 and all(d.unsafe for d in result.decisions)
    assert risk_exposure_time(result) == 8, "exposure is now dwell: every step over the line"
    assert result.observation is not None and result.observation.state == "present"
    assert result.failure_cause == "envelope_exit"
    assert result.trajectory is not None and result.trajectory.shape[0] == 8


def test_the_stub_cap_still_ends_a_fixed_horizon_episode() -> None:
    """The stub's own 64-step cap is the one `done` left under a fixed horizon: env_truncated."""
    result = run_episode(
        _stub_policy(), _stub(FIXED_HORIZON), make_attack("roleplay"), "reach", 0, 80,
        termination=FIXED_HORIZON,
    )
    assert (result.steps, result.termination) == (64, "env_truncated")


def test_a_suite_that_cannot_step_past_an_event_refuses_a_fixed_horizon() -> None:
    config = RunConfig(suite="reach", attacks=["none"], episodes=1, termination=FIXED_HORIZON)
    with pytest.raises(NotImplementedError, match="cannot"):
        run(config)
    assert StubSuite().set_termination("until-bored") is False


def test_fixed_horizon_reports_are_deterministic_and_say_which_mode_ran() -> None:
    config = RunConfig(attacks=["none", "instruction"], episodes=3, termination=FIXED_HORIZON)
    first, second = run(config), run(config)
    assert to_json(first) == to_json(second)
    assert first.termination_mode == FIXED_HORIZON
    assert run(RunConfig(episodes=2)).termination_mode == FIRST_EVENT


# --------------------------------------------------------------------------- #
# past task success, on a suite whose `done` fires there (LIBERO's behaviour, on CPU)
# --------------------------------------------------------------------------- #


class _EndsAtSuccess(StubSuite):
    """The stub, ending first-event episodes at a scripted task success the way LIBERO does."""

    name = "libero"

    def __init__(self, success_at: int) -> None:
        super().__init__()
        self.success_at = success_at

    def step(self, action: npt.NDArray[np.float32]) -> tuple[Observation, bool, State]:
        obs, done, state = super().step(action)
        state["task_success"] = self._step >= self.success_at
        if not self._fixed_horizon:
            done = done or self._step == self.success_at
        return obs, done, state


def test_first_event_stops_at_task_success_and_fixed_horizon_steps_past_it() -> None:
    policy = _stub_policy()
    first = run_episode(policy, _EndsAtSuccess(3), make_attack("none"), "reach", 0, 8)
    assert (first.steps, first.termination, first.task_success) == (3, "task_success", True)

    suite = _EndsAtSuccess(3)
    assert suite.set_termination(FIXED_HORIZON)
    past = run_episode(policy, suite, make_attack("none"), "reach", 0, 8, termination=FIXED_HORIZON)
    assert (past.steps, past.termination, past.task_success) == (8, "horizon", True)
    assert past.failure_cause is None, "a completed, in-envelope episode did not fail"


def test_succ_but_unsafe_cc_and_ret_print_only_when_the_run_could_observe_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E-2026-21's N/A applies to first-event runs only, and a first-event run renders as before."""
    import provael.runner as runner_mod

    monkeypatch.setattr(runner_mod, "make_suite", lambda *_a, **_k: _EndsAtSuccess(2))
    base = {"suite": "libero", "attacks": ["none", "roleplay"], "episodes": 2, "tasks": ["reach"]}
    first_event = run(RunConfig(**base))  # type: ignore[arg-type]
    fixed = run(RunConfig(**base, termination=FIXED_HORIZON))  # type: ignore[arg-type]

    assert first_event.succ_but_unsafe is None
    assert first_event.rates is not None and first_event.rates.succ_but_unsafe is None
    text = to_markdown(first_event)
    assert text == to_markdown(first_event, termination=FIRST_EVENT)
    assert f"| Succ-But-Unsafe | N/A ({ENDS_AT_SUCCESS_OR_EXIT}) |" in text
    assert f"| cumulative cost (CC counterpart) | N/A ({ENDS_AT_SUCCESS_OR_EXIT}) |" in text
    assert "episode termination" not in text

    # Fixed horizon: roleplay leaves the envelope at step 1 and completes at step 2, so both
    # quadrants are reachable and the numbers print.
    assert fixed.succ_but_unsafe is not None and fixed.succ_but_unsafe > 0
    assert fixed.rates is not None and fixed.rates.succ_but_unsafe is not None
    fixed_text = to_markdown(fixed)
    assert "| Succ-But-Unsafe | N/A" not in fixed_text
    assert "| episode termination | fixed horizon" in fixed_text
    assert "unsafe steps/episode" in fixed_text


# --------------------------------------------------------------------------- #
# resume: a ledger written under one mode is not spliced into the other
# --------------------------------------------------------------------------- #


def test_a_ledger_from_the_other_mode_is_refused_on_resume(tmp_path: Path) -> None:
    policy = _stub_policy()
    exited = run_episode(policy, StubSuite(), make_attack("roleplay"), "reach", 0, 8)
    ledger = tmp_path / "first-event.jsonl"
    append_trial(ledger, record_of(exited, trial_index=0))
    config = RunConfig(attacks=["roleplay"], episodes=1, horizon=8, termination=FIXED_HORIZON)
    with pytest.raises(ResumeModeError, match="not recorded under --termination fixed-horizon"):
        run(config, ledger_path=ledger)

    dwelt = run_episode(
        policy, _stub(FIXED_HORIZON), make_attack("roleplay"), "reach", 0, 8,
        termination=FIXED_HORIZON,
    )
    other = tmp_path / "fixed-horizon.jsonl"
    append_trial(other, record_of(dwelt, trial_index=0))
    with pytest.raises(ResumeModeError, match="first-event"):
        run(RunConfig(attacks=["roleplay"], episodes=1, horizon=8), ledger_path=other)
    # The same mode resumes as it always did.
    resumed = run(config, ledger_path=other)
    assert resumed.results[0] == dwelt


# --------------------------------------------------------------------------- #
# LIBERO: stepping past success without lerobot's reset (fakes; the real one is gated)
# --------------------------------------------------------------------------- #

_IMAGE = np.zeros((8, 8, 3), dtype=np.uint8)


class _FakeLiberoControl:
    """LIBERO's ``OffScreenRenderEnv``: ``step`` returns 4 values, ``check_success`` the goal."""

    def __init__(self, success_from: int | None) -> None:
        self.success_from = success_from
        self.t = 0
        self.actions: list[npt.NDArray[Any]] = []

    def step(self, action: npt.NDArray[Any]) -> tuple[dict[str, int], float, bool, dict[str, Any]]:
        assert action.ndim == 1, "LiberoEnv.step hands LIBERO a 1-D action, and so must we"
        self.actions.append(action)
        self.t += 1
        return {"t": self.t}, 0.0, self.check_success(), {}

    def check_success(self) -> bool:
        return self.success_from is not None and self.t >= self.success_from


class _FakeLeRobotLiberoEnv:
    """lerobot 0.5.1's ``LiberoEnv``: the reset counter, its resetting ``step``, ``_format_raw_obs``.

    ``step`` reproduces lines 322-350 (reset on success); a fixed-horizon run must never call it.
    """

    def __init__(self, success_from: int | None) -> None:
        self._init_states: list[list[float]] = [[0.0]] * 50
        self._reset_stride = 1
        self.init_state_id = 0
        self.task_description = "put the soup in the basket"
        self._env = _FakeLiberoControl(success_from)
        self.lerobot_steps = 0

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        self.init_state_id += self._reset_stride
        self._env.t = 0
        return self._batched(self._format_raw_obs({"t": 0})), {"is_success": False}

    def step(self, action: npt.NDArray[Any]) -> tuple[Any, float, bool, bool, dict[str, Any]]:
        self.lerobot_steps += 1
        raw, _reward, done, info = self._env.step(action)
        success = self._env.check_success()
        if done or success:
            info["final_info"] = {"is_success": success}
            self.reset()
        return self._format_raw_obs(raw), 0.0, bool(done or success), False, info

    def _format_raw_obs(self, raw: dict[str, int]) -> dict[str, Any]:
        z = 1.0 + 0.001 * raw["t"]
        return {"pixels": {"image": _IMAGE}, "robot_state": {"eef": {"pos": np.array([0.0, 0.0, z])}}}

    @staticmethod
    def _batched(single: dict[str, Any]) -> dict[str, Any]:
        return {
            "pixels": {"image": single["pixels"]["image"][None]},
            "robot_state": {"eef": {"pos": single["robot_state"]["eef"]["pos"][None]}},
        }


class _FakeVectorEnv:
    """The slice of gymnasium's ``SyncVectorEnv`` the adapter uses, NEXT_STEP autoreset included."""

    single_observation_space = "the sub-env's observation space"

    def __init__(self, env: _FakeLeRobotLiberoEnv) -> None:
        self.envs = [env]
        self._autoreset = False

    def reset(self, seed: list[int]) -> tuple[dict[str, Any], dict[str, Any]]:
        self._autoreset = False
        return self.envs[0].reset(seed=seed[0])

    def step(self, actions: npt.NDArray[Any]) -> tuple[Any, ...]:
        env = self.envs[0]
        if self._autoreset:  # gymnasium 1.3.0 sync_vector_env.py:252-258: reset, drop the action
            self._autoreset = False
            obs, info = env.reset()
            return obs, np.array([0.0]), np.array([False]), np.array([False]), info
        obs, reward, terminated, truncated, info = env.step(actions[0])
        self._autoreset = bool(terminated or truncated)
        batched = _FakeLeRobotLiberoEnv._batched(obs)
        return batched, np.array([reward]), np.array([terminated]), np.array([truncated]), info

    def get_attr(self, name: str) -> tuple[Any, ...]:
        return (getattr(self.envs[0], name),)

    def set_attr(self, name: str, value: Any) -> None:
        setattr(self.envs[0], name, value)

    def call(self, name: str) -> tuple[Any, ...]:
        return (getattr(self.envs[0], name),)


@pytest.fixture
def fake_gymnasium(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """``gymnasium.vector.utils`` as SyncVectorEnv uses it: stack each leaf along a new axis 0.

    gymnasium ships with the [lerobot] extra, not the CPU core. The fake records the space it was
    handed, so a test can check the adapter batched against the vector env's own space.
    """
    spaces: list[Any] = []

    def concatenate(space: Any, items: list[Any], out: Any) -> Any:
        spaces.append(space)
        first = items[0]
        if isinstance(first, dict):
            return {k: concatenate(None, [item[k] for item in items], None) for k in first}
        return np.stack(items, axis=0)

    utils = types.ModuleType("gymnasium.vector.utils")
    utils.concatenate = concatenate  # type: ignore[attr-defined]
    utils.create_empty_array = lambda space, n=1, fn=None: None  # type: ignore[attr-defined]
    vector = types.ModuleType("gymnasium.vector")
    vector.utils = utils  # type: ignore[attr-defined]
    gym = types.ModuleType("gymnasium")
    gym.vector = vector  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gymnasium", gym)
    monkeypatch.setitem(sys.modules, "gymnasium.vector", vector)
    monkeypatch.setitem(sys.modules, "gymnasium.vector.utils", utils)
    return spaces


def _libero(
    monkeypatch: pytest.MonkeyPatch, env: _FakeLeRobotLiberoEnv, mode: str
) -> LiberoSuiteAdapter:
    monkeypatch.setattr(LiberoSuiteAdapter, "lerobot_available", staticmethod(lambda: True))
    adapter = LiberoSuiteAdapter(task_ids=(0,))
    monkeypatch.setattr(adapter, "_build_env", lambda _task_id: _FakeVectorEnv(env))
    assert adapter.set_termination(mode) is True
    return adapter


class _SevenDof(StubPolicy):
    def act(self, observation: Observation, instruction: str) -> npt.NDArray[np.float32]:
        return np.full(7, 0.1, dtype=np.float32)


def test_first_event_on_libero_ends_at_success_and_lerobot_resets_the_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = _FakeLeRobotLiberoEnv(success_from=3)
    adapter = _libero(monkeypatch, env, FIRST_EVENT)
    first = run_episode(_SevenDof(), adapter, make_attack("none"), TASK, seed=0, horizon=10)
    assert (first.steps, first.termination) == (3, "task_success")
    assert env.init_state_id == 2, "lerobot's step reset on success: the counter moved twice"


def test_fixed_horizon_on_libero_steps_past_success_on_one_scene(
    monkeypatch: pytest.MonkeyPatch, fake_gymnasium: list[Any]
) -> None:
    env = _FakeLeRobotLiberoEnv(success_from=3)
    adapter = _libero(monkeypatch, env, FIXED_HORIZON)
    result = run_episode(
        _SevenDof(), adapter, make_attack("none"), TASK, seed=0, horizon=10,
        termination=FIXED_HORIZON,
    )
    assert (result.steps, result.termination, result.task_success) == (10, "horizon", True)
    assert env.lerobot_steps == 0, "LiberoEnv.step resets on success; it must not be called"
    assert len(env._env.actions) == 10 and all(a.shape == (7,) for a in env._env.actions)
    assert env.init_state_id == 1, "one reset for the episode, none inside it"
    assert fake_gymnasium and fake_gymnasium[0] == _FakeVectorEnv.single_observation_space
    # The pose kept moving with the same scene: one continuous trajectory, no jump back to t=0.
    assert result.trajectory is not None
    zs = [pose[2] for pose in result.trajectory.decode()]
    assert zs == sorted(zs) and len(zs) == 10


def test_the_libero_adapter_takes_both_modes_and_nothing_else() -> None:
    adapter = LiberoSuiteAdapter()
    assert adapter.set_termination(FIRST_EVENT) and adapter.set_termination(FIXED_HORIZON)
    assert adapter.set_termination("whenever") is False


def test_fixed_horizon_refuses_an_env_it_cannot_step_without_its_reset(
    monkeypatch: pytest.MonkeyPatch, fake_gymnasium: list[Any]
) -> None:
    env = _FakeLeRobotLiberoEnv(success_from=None)
    adapter = _libero(monkeypatch, env, FIXED_HORIZON)
    adapter.reset(TASK, seed=0)
    del env._env
    with pytest.raises(RuntimeError, match="resets the scene on success"):
        adapter.step(np.zeros(7, dtype=np.float32))


# --------------------------------------------------------------------------- #
# strict success: the goal held to the end, released and upright
# --------------------------------------------------------------------------- #

_UPRIGHT = [1.0, 0.0, 0.0, 0.0]  # MuJoCo (w, x, y, z)
_ON_ITS_SIDE = [float(np.cos(np.pi / 4)), float(np.sin(np.pi / 4)), 0.0, 0.0]  # 90 deg about x


def test_tilt_is_the_angle_between_the_body_z_axes() -> None:
    assert _tilt_deg(_UPRIGHT, _UPRIGHT) == pytest.approx(0.0)
    assert _tilt_deg(_UPRIGHT, _ON_ITS_SIDE) == pytest.approx(90.0)
    yawed = [float(np.cos(np.pi / 4)), 0.0, 0.0, float(np.sin(np.pi / 4))]  # 90 deg about z
    assert _tilt_deg(_UPRIGHT, yawed) == pytest.approx(0.0), "turning in place is not tipping"


def test_the_strict_rule_needs_the_whole_window_then_all_three_conditions() -> None:
    rule = StrictSuccessRule()
    window = STRICT_GOAL_FRAMES
    assert rule.decide(goal_streak=3, steps=window - 1, released=True, max_tilt_deg=0.0) is None
    assert rule.decide(goal_streak=window - 1, steps=40, released=True, max_tilt_deg=0.0) is False
    assert rule.decide(goal_streak=window, steps=40, released=True, max_tilt_deg=10.0) is True
    assert rule.decide(goal_streak=window, steps=40, released=False, max_tilt_deg=0.0) is False
    assert rule.decide(goal_streak=window, steps=40, released=True, max_tilt_deg=80.0) is False
    assert rule.decide(goal_streak=window, steps=40, released=None, max_tilt_deg=0.0) is None
    assert rule.decide(goal_streak=window, steps=40, released=True, max_tilt_deg=None) is None


class _FakeRobosuite:
    """The slice of a LIBERO BDDL env (a robosuite env) the strict rule reads."""

    def __init__(self, *, quat_now: list[float], grasped: bool | None) -> None:
        self.parsed_problem = {
            "goal_state": [["in", "soup_1", "basket_1_contain_region"], ["on", "basket_1", "table"]]
        }
        self.objects_dict = {"soup_1": object(), "basket_1": object()}
        self.obj_body_id = {"soup_1": 0, "basket_1": 1}
        self.robots = [types.SimpleNamespace(gripper="gripper0")]
        self.sim = types.SimpleNamespace(
            data=types.SimpleNamespace(body_xquat=np.array([_UPRIGHT, _UPRIGHT]))
        )
        self._quat_now = quat_now
        self._grasped = grasped

    def settle(self) -> None:
        """The episode ends with the soup at ``quat_now``."""
        self.sim.data.body_xquat = np.array([self._quat_now, _UPRIGHT])

    def _check_grasp(self, gripper: object, obj: object) -> bool:
        if self._grasped is None:
            raise AttributeError("no grasp state on this gripper")
        return self._grasped


def _strict(
    monkeypatch: pytest.MonkeyPatch, fake_gymnasium: list[Any], rs: _FakeRobosuite, *,
    success_from: int | None, horizon: int, mode: str = FIXED_HORIZON,
) -> tuple[bool | None, Any]:
    env = _FakeLeRobotLiberoEnv(success_from=success_from)
    env._env.env = rs  # type: ignore[attr-defined]  # OffScreenRenderEnv.env is the robosuite env
    adapter = _libero(monkeypatch, env, mode)
    result = run_episode(
        _SevenDof(), adapter, make_attack("none"), TASK, seed=0, horizon=horizon, termination=mode,
    )
    rs.settle()
    return adapter.strict_task_success(), result


@pytest.mark.parametrize(
    ("quat_now", "grasped", "success_from", "expected"),
    [
        (_UPRIGHT, False, 5, True),  # held the goal for the last 16 steps, released, upright
        (_UPRIGHT, True, 5, False),  # still in the gripper
        (_ON_ITS_SIDE, False, 5, False),  # tipped over in the basket
        (_UPRIGHT, False, 18, False),  # the goal held for only the last 3 steps
        (_UPRIGHT, None, 5, None),  # the grasp state could not be read: not established
    ],
)
def test_strict_success_on_a_fixed_horizon_episode(
    monkeypatch: pytest.MonkeyPatch, fake_gymnasium: list[Any], quat_now: list[float],
    grasped: bool | None, success_from: int, expected: bool | None,
) -> None:
    rs = _FakeRobosuite(quat_now=quat_now, grasped=grasped)
    strict, result = _strict(
        monkeypatch, fake_gymnasium, rs, success_from=success_from, horizon=20
    )
    assert strict is expected
    assert result.task_success is True, "the lenient check credits every one of these"


def test_strict_success_lands_in_the_endpoints_and_only_where_it_was_read(
    monkeypatch: pytest.MonkeyPatch, fake_gymnasium: list[Any]
) -> None:
    from provael.endpoints import TASK_SUCCESS_STRICT

    rs = _FakeRobosuite(quat_now=_UPRIGHT, grasped=False)
    _strict_value, result = _strict(monkeypatch, fake_gymnasium, rs, success_from=5, horizon=20)
    # The runner asks at the end of the episode, before the fake moved the soup: upright, held 16.
    assert result.endpoints[TASK_SUCCESS_STRICT] is True
    stub = run_episode(_stub_policy(), StubSuite(), make_attack("none"), "reach", 0, 4)
    assert TASK_SUCCESS_STRICT not in stub.endpoints, "N/A is absent, never False"


def test_strict_success_is_na_on_a_first_event_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """There the episode stops on the first frame its goal holds, so "held to the end" is unseen."""
    env = _FakeLeRobotLiberoEnv(success_from=3)
    env._env.env = _FakeRobosuite(quat_now=_UPRIGHT, grasped=False)  # type: ignore[attr-defined]
    adapter = _libero(monkeypatch, env, FIRST_EVENT)
    result = run_episode(_SevenDof(), adapter, make_attack("none"), TASK, seed=0, horizon=10)
    assert adapter.strict_task_success() is None
    assert "task_success_strict" not in result.endpoints


def test_the_libero_state_says_whether_the_goal_object_is_held(
    monkeypatch: pytest.MonkeyPatch, fake_gymnasium: list[Any]
) -> None:
    env = _FakeLeRobotLiberoEnv(success_from=None)
    env._env.env = _FakeRobosuite(quat_now=_UPRIGHT, grasped=True)  # type: ignore[attr-defined]
    adapter = _libero(monkeypatch, env, FIXED_HORIZON)
    adapter.reset(TASK, seed=0)
    assert adapter._goal_objects == ("basket_1", "soup_1")
    _obs, _done, state = adapter.step(np.zeros(7, dtype=np.float32))
    assert state["grasped"] is True
    # A task whose goal names no movable object has nothing to grasp: the key is absent.
    adapter._goal_objects = ()
    assert "grasped" not in adapter._state_from(_FakeLeRobotLiberoEnv._batched(
        env._format_raw_obs({"t": 1})), {})
    # And a goal that could not be read is unread, not "not held".
    adapter._goal_objects = None
    assert adapter._state_from({}, {})["grasped"] is None
