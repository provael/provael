# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Each LIBERO episode records the fixed initial state its reset loaded, read from the env.

WHY THIS EXISTS. Under lerobot 0.5.1 the seed does not pick a LIBERO episode's starting scene: a
reset counter does (``lerobot/envs/libero.py``: ``init_state_id`` starts at the sub-env's
``episode_index``, each ``reset`` loads ``_init_states[init_state_id % len]`` and adds the stride,
and ``step`` resets again when an episode ends in success). Until report schema 8 nothing recorded
which scene ran, so the calibrate plan step could place only a task's first episode (#136). These
tests drive the real adapter over a fake of that counter, so no simulator is needed: the adapter
must read the state back from the env, never work it out from the seed or the episode order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from typer.testing import CliRunner

from provael import __version__
from provael.attacks.registry import make_attack
from provael.calibration import calibrate_one, calibrate_suite, collect_benign_signals
from provael.campaign import check_provenance
from provael.cli import app
from provael.execution import report_digest
from provael.ledger import append_trial, record_of, results_for
from provael.policies.stub import StubPolicy
from provael.runner import run_episode
from provael.suites.libero import LiberoSuiteAdapter
from provael.suites.stub import StubSuite
from provael.types import Observation, RunReport

REPO = Path(__file__).resolve().parents[1]
TASK = "libero_object/0"

#: One batched lerobot observation, end effector well clear of the default keep-out box.
_OBS: dict[str, Any] = {
    "pixels": {"image": np.zeros((1, 8, 8, 3), dtype=np.uint8)},
    "robot_state": {"eef": {"pos": np.array([[0.0, 0.0, 1.0]])}},
}


class _FakeLiberoEnv:
    """lerobot 0.5.1's ``LiberoEnv`` counter and nothing else (libero.py:148-151, 296-302, 322-348).

    ``success_at`` ends every episode in task success at that step, and ``step`` then resets
    itself, exactly as lerobot's does, which is the reset a seed-based guess would miss.
    """

    def __init__(self, *, fixed: bool = True, success_at: int | None = None) -> None:
        self._init_states: list[list[float]] | None = [[0.0]] * 50 if fixed else None
        self._reset_stride = 1
        self.init_state_id = 0
        self.success_at = success_at
        self.task_description = "pick up the alphabet soup and place it in the basket"
        self._t = 0

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        if self._init_states is not None:
            self.init_state_id += self._reset_stride
        self._t = 0
        return _OBS, {"is_success": False}

    def step(self, _action: npt.NDArray[Any]) -> tuple[Any, float, bool, bool, dict[str, Any]]:
        self._t += 1
        success = self._t == self.success_at
        info: dict[str, Any] = {"is_success": success}
        if success:
            info["final_info"] = {"is_success": True}
            self.reset()
        return _OBS, 0.0, success, False, info


class _FakeVectorEnv:
    """The slice of gymnasium's ``SyncVectorEnv`` the adapter calls, over one sub-env."""

    def __init__(self, env: _FakeLiberoEnv) -> None:
        self.envs = [env]

    def reset(self, seed: list[int]) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.envs[0].reset(seed=seed[0])

    def step(self, actions: npt.NDArray[Any]) -> tuple[Any, ...]:
        obs, reward, terminated, truncated, info = self.envs[0].step(actions[0])
        return obs, np.array([reward]), np.array([terminated]), np.array([truncated]), info

    def get_attr(self, name: str) -> tuple[Any, ...]:
        return (getattr(self.envs[0], name),)

    def set_attr(self, name: str, value: Any) -> None:
        setattr(self.envs[0], name, value)

    def call(self, name: str) -> tuple[Any, ...]:
        value = getattr(self.envs[0], name)
        return (value() if callable(value) else value,)


def _adapter(
    monkeypatch: pytest.MonkeyPatch, env: _FakeLiberoEnv
) -> tuple[LiberoSuiteAdapter, list[_FakeVectorEnv]]:
    """The real adapter, with lerobot's presence and its env factory stood in for."""
    monkeypatch.setattr(LiberoSuiteAdapter, "lerobot_available", staticmethod(lambda: True))
    adapter = LiberoSuiteAdapter(task_ids=(0,))
    built: list[_FakeVectorEnv] = []

    def build(_task_id: int) -> _FakeVectorEnv:
        built.append(_FakeVectorEnv(env))
        return built[-1]

    monkeypatch.setattr(adapter, "_build_env", build)
    return adapter, built


class _SevenDofPolicy(StubPolicy):
    """The stub, emitting a zero 7-DoF action so the LIBERO adapter can execute it."""

    def act(self, observation: Observation, instruction: str) -> npt.NDArray[np.float32]:
        return np.zeros(7, dtype=np.float32)


def test_a_fresh_env_records_zero_and_the_next_reset_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv())
    assert adapter.reset(TASK, seed=7)["init_state"] == 0
    # Same seed again, a different scene: the counter moved, the seed did not pick it.
    assert adapter.reset(TASK, seed=7)["init_state"] == 1


def test_a_reset_after_a_success_inside_step_shows_in_the_next_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """lerobot's own ``step`` resets on success, so the next episode starts one state further."""
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv(success_at=3))
    policy, attack = _SevenDofPolicy(), make_attack("none")
    first = run_episode(policy, adapter, attack, TASK, seed=0, horizon=10)
    second = run_episode(policy, adapter, attack, TASK, seed=1, horizon=10)
    assert first.task_success is True and first.steps == 3
    assert (first.init_state, second.init_state) == (0, 2)


def test_an_episode_that_does_not_end_in_success_uses_one_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv())
    policy, attack = _SevenDofPolicy(), make_attack("none")
    first = run_episode(policy, adapter, attack, TASK, seed=0, horizon=4)
    second = run_episode(policy, adapter, attack, TASK, seed=1, horizon=4)
    assert (first.init_state, second.init_state) == (0, 1)


def test_an_offset_moves_where_a_fresh_env_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _FakeLiberoEnv()
    adapter, built = _adapter(monkeypatch, env)
    assert adapter.start_init_states_at(30) is True
    assert adapter.reset(TASK, seed=0)["init_state"] == 30
    assert adapter.reset(TASK, seed=1)["init_state"] == 31
    assert len(built) == 1, "the offset is set once, on the fresh env, not before every reset"


def test_an_env_without_fixed_init_states_records_none(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv(fixed=False))
    assert adapter.reset(TASK, seed=0)["init_state"] is None


def test_a_suite_without_fixed_init_states_records_none_on_the_episode() -> None:
    policy = StubPolicy()
    policy.load()
    result = run_episode(policy, StubSuite(), make_attack("none"), "reach", seed=0, horizon=2)
    assert result.init_state is None


def test_a_resumed_run_replays_the_init_state_it_recorded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The reason to record it at all: a resumed process restarts the counter, the ledger does not."""
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv())
    policy, attack = _SevenDofPolicy(), make_attack("none")
    run_episode(policy, adapter, attack, TASK, seed=0, horizon=2)
    episode = run_episode(policy, adapter, attack, TASK, seed=1, horizon=2)
    ledger = tmp_path / "ledger.jsonl"
    append_trial(ledger, record_of(episode, trial_index=1))
    replayed = results_for([("none", TASK, 1)], ledger)[("none", TASK, 1)]
    assert replayed.init_state == episode.init_state == 1


def test_a_record_without_init_state_is_read_exactly_as_before() -> None:
    """A committed report from before schema 8 loads, digests and passes provenance as it did.

    The headline shard is schema 5. Its records carry no `init_state`, so they load as None, the
    schema-aware projection drops the field for a report that declares less than 8 (it is
    registered in `attest._RESULT_FIELDS_ADDED_IN`), so the digest its execution manifest binds
    still matches, and the provenance check reports the same gaps it always has. Nothing rewrites
    a committed result.
    """
    shard = REPO / "results" / "smolvla_libero_object_suite_2026-09-14" / "libero_object_0"
    raw = json.loads((shard / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((shard / "execution-manifest.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] < 8
    assert all("init_state" not in record for record in raw["results"])
    report = RunReport.model_validate(raw)
    assert all(result.init_state is None for result in report.results)
    assert report_digest(report) == manifest["report_digest"]
    assert check_provenance([shard]) == {
        str(shard): ["repository", "commit", "dep_lock_digest", "precision"]
    }


class _CountingSuite(StubSuite):
    """The stub, reporting a fixed initial state per reset the way LIBERO's counter does."""

    def __init__(self) -> None:
        super().__init__()
        self.next_state = 40

    def reset(self, task: str, seed: int) -> Observation:
        observation = super().reset(task, seed)
        observation["init_state"] = self.next_state
        self.next_state += 1
        return observation


def test_a_calibration_records_the_init_state_of_every_rollout() -> None:
    """In `policy_seeds` order: fit, tuning, eval, then the attacked arm at the tuning seeds."""
    policy = StubPolicy()
    policy.load()
    cal = calibrate_one(
        policy, _CountingSuite(), policy_name="stub", suite_name="stub", task="reach",
        fit_seeds=[0, 1], holdout_seeds=[2, 3], eval_seeds=[4], target_fpr=0.5, horizon=3,
        tool_version=__version__, attack=make_attack("roleplay"),
    )
    assert cal.init_states == [40, 41, 42, 43, 44, 45, 46]
    assert len(cal.init_states) == len(cal.policy_seeds)


def test_the_benign_collector_records_init_states_only_when_asked() -> None:
    policy = StubPolicy()
    policy.load()
    states: list[int | None] = []
    episodes, applied = collect_benign_signals(
        policy, _CountingSuite(), "reach", [0, 1], horizon=2, init_states=states
    )
    assert states == [40, 41]
    assert len(episodes) == len(applied) == 2


def test_an_offset_on_a_suite_without_fixed_init_states_is_refused() -> None:
    with pytest.raises(ValueError, match="keeps none"):
        calibrate_suite(
            "stub", "stub", None, [0, 1, 2], target_fpr=0.5, horizon=2,
            tool_version=__version__, init_state_offset=3,
        )


def test_the_cli_takes_the_offset_and_refuses_it_where_it_cannot_apply(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["calibrate", "--seeds", "3", "--init-state-offset", "3", "--out", str(tmp_path)]
    )
    assert result.exit_code != 0
    assert "keeps none" in result.output
