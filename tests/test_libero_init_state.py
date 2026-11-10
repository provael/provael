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

AND A PINNED RUN (26 October 2026). `--pin-init-states` sets the counter before every reset, so
the episode at seed s loads (pin + s) mod 50 in every arm, whatever the episode before it did; the
state it read back is still the one recorded, and checked against the one asked for.
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
from provael.config import RunConfig
from provael.execution import report_digest
from provael.ledger import append_trial, record_of, results_for
from provael.policies.stub import StubPolicy
from provael.runner import InitStatePlanError, ScenePinError, run, run_episode
from provael.suites.libero import LiberoSuiteAdapter, model_xml_digest, scene_snapshot_of
from provael.suites.stub import StubSuite
from provael.types import Observation, RunReport, ScenePairing

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


class _SelfCountingLiberoEnv(_FakeLiberoEnv):
    """A lerobot whose reset loads from a counter of its own and ignores the one the pin set: the
    rule the pin relies on moved, which must raise rather than be recorded as pinned."""

    def __init__(self) -> None:
        super().__init__()
        self._own = 0

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        self.init_state_id = self._own + self._reset_stride
        self._own += 1
        self._t = 0
        return _OBS, {"is_success": False}


def test_pinned_episodes_load_start_plus_seed_even_after_a_success_inside_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unpinned, these three successes walk 0, 2, 4 (see the success test above); pinned, 20-22."""
    adapter, built = _adapter(monkeypatch, _FakeLiberoEnv(success_at=3))
    assert adapter.pin_init_states(20) is True
    policy, attack = _SevenDofPolicy(), make_attack("none")
    episodes = [run_episode(policy, adapter, attack, TASK, seed=seed, horizon=10) for seed in (0, 1, 2)]
    assert all(episode.task_success for episode in episodes)
    assert [episode.init_state for episode in episodes] == [20, 21, 22]
    assert len(built) == 1, "one cached env, its counter set again before every reset"


def test_every_arm_at_a_seed_starts_from_the_same_pinned_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the pin is for: the (task, seed) cell a paired test reads holds one scene, repeats too."""
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv(success_at=2))
    adapter.pin_init_states(0)
    policy = _SevenDofPolicy()
    states = [
        run_episode(policy, adapter, make_attack(name), TASK, seed=seed, horizon=4).init_state
        for name in ("none", "roleplay")
        for seed in (3, 3, 4)
    ]
    assert states == [3, 3, 4, 3, 3, 4]


def test_a_pin_wraps_modulo_the_number_of_states(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv())
    adapter.pin_init_states(48)
    assert adapter.reset(TASK, seed=3)["init_state"] == 1


def test_a_pinned_reset_that_loads_another_state_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _adapter(monkeypatch, _SelfCountingLiberoEnv())
    adapter.pin_init_states(20)
    with pytest.raises(RuntimeError, match="load init state 20, and its reset loaded 0"):
        adapter.reset(TASK, seed=0)


def test_a_pin_on_an_env_without_fixed_init_states_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv(fixed=False))
    adapter.pin_init_states(20)
    with pytest.raises(RuntimeError, match="keeps no fixed initial states to pin"):
        adapter.reset(TASK, seed=0)


def test_a_pin_is_a_non_negative_index(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv())
    with pytest.raises(ValueError, match="non-negative"):
        adapter.pin_init_states(-1)


def _pinned_run(
    monkeypatch: pytest.MonkeyPatch, config: RunConfig, ledger: Path | None = None
) -> RunReport:
    """The runner over the real adapter on a FRESH fake env, as a new process would build it."""
    adapter, _ = _adapter(monkeypatch, _FakeLiberoEnv(success_at=2))
    monkeypatch.setattr(adapter, "features", lambda: None)
    monkeypatch.setattr("provael.runner.make_suite", lambda *_args, **_kwargs: adapter)
    monkeypatch.setattr("provael.runner.make_policy", lambda *_args, **_kwargs: _SevenDofPolicy())
    return run(config, ledger_path=ledger)


def test_a_pinned_run_records_one_scene_per_seed_and_resumes_onto_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Through the runner: two arms, three seeds, every episode ending in success.

    Each seed's scene is the same in both arms. A process that resumes after two episodes starts a
    fresh env, whose counter is back at 0; pinned, it still loads what the uninterrupted run did.
    """
    config = RunConfig(
        policy="stub", suite="libero", attacks=["none", "roleplay"], tasks=[TASK], episodes=3,
        horizon=4, pin_init_states=10,
    )
    whole = _pinned_run(monkeypatch, config)
    assert [(r.attack, r.seed, r.init_state) for r in whole.results] == [
        ("none", 0, 10), ("none", 1, 11), ("none", 2, 12),
        ("roleplay", 0, 10), ("roleplay", 1, 11), ("roleplay", 2, 12),
    ]
    ledger = tmp_path / "ledger.jsonl"
    for index, episode in enumerate(whole.results[:2]):
        append_trial(ledger, record_of(episode, trial_index=index))
    resumed = _pinned_run(monkeypatch, config, ledger)
    assert [r.init_state for r in resumed.results] == [r.init_state for r in whole.results]


def test_a_pin_on_a_suite_without_fixed_init_states_is_refused() -> None:
    config = RunConfig(policy="stub", suite="stub", attacks=["none"], episodes=1, pin_init_states=3)
    with pytest.raises(NotImplementedError, match="keeps no fixed initial states"):
        run(config)


def test_the_cli_takes_the_pin_and_refuses_it_where_it_cannot_apply(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["attack", "--attacks", "none", "--episodes", "1", "--pin-init-states", "3",
         "--out", str(tmp_path)],
    )
    assert result.exit_code != 0
    assert "keeps no fixed initial states" in result.output


# --------------------------------------------------------------------------------------------- #
# Schema 9 (P1.2): the scene each reset left, and the pairs that shared one
#
# An equal `init_state` is an equal index; whether the scene was the same is read from the
# simulator after the reset. These drive the real adapter over a fake robosuite chain
# (`envs[0]._env.env.sim`, the chain `LiberoSuiteAdapter._robosuite_env` already reads) whose
# arrays are fixed functions of the state the reset loaded.
# --------------------------------------------------------------------------------------------- #

_BODIES = ("world", "robot0_base", "akita_black_bowl_1_main", "basket_1")


class _FakeModel:
    nbody = len(_BODIES)

    def body_id2name(self, index: int) -> str:
        return _BODIES[index]

    def get_xml(self) -> str:
        return (
            '<mujoco><asset><mesh file="/opt/py/lib/python3.12/site-packages/libero/assets/'
            'bowl.stl"/></asset></mujoco>'
        )


class _FakeData:
    def __init__(self) -> None:
        self.qpos = np.zeros(3)
        self.qvel = np.zeros(3)
        self.xpos = np.zeros((len(_BODIES), 3))
        self.xquat = np.tile([1.0, 0.0, 0.0, 0.0], (len(_BODIES), 1))


class _FakeSim:
    def __init__(self) -> None:
        self.model = _FakeModel()
        self.data = _FakeData()


class _SceneLiberoEnv(_FakeLiberoEnv):
    """The counter fake, plus a robosuite sim whose state is a fixed function of the loaded state."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sim = _FakeSim()
        self._env = type("OffScreenRenderEnv", (), {})()
        self._env.env = type("RobosuiteEnv", (), {})()
        self._env.env.sim = self.sim
        self.resets = 0

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        out = super().reset(seed)
        self.resets += 1
        loaded = (self.init_state_id - self._reset_stride) % 50
        self.place(loaded)
        return out

    def place(self, loaded: int) -> None:
        angle = 0.1 * loaded
        self.sim.data.qpos = np.array([float(loaded), 0.0, 0.0])
        self.sim.data.xpos[2] = [0.1 * loaded, 0.2, 0.9]
        self.sim.data.xquat[2] = [np.cos(angle / 2), 0.0, 0.0, np.sin(angle / 2)]


class _DriftingSceneEnv(_SceneLiberoEnv):
    """A simulator that does not settle the same way twice: one init state, a new scene each reset."""

    def place(self, loaded: int) -> None:
        super().place(loaded)
        self.sim.data.qvel = np.array([1e-9 * self.resets, 0.0, 0.0])


def test_each_episode_records_the_scene_its_reset_left(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _adapter(monkeypatch, _SceneLiberoEnv())
    adapter.pin_init_states(3)
    episode = run_episode(_SevenDofPolicy(), adapter, make_attack("none"), TASK, seed=1, horizon=2)
    assert episode.init_state == 4
    assert episode.scene_t0_digest is not None and len(episode.scene_t0_digest) == 64
    assert episode.scene_t0 is not None
    # The robot's own bodies and the world body stay in the digest and out of the readable list.
    assert [body.name for body in episode.scene_t0] == ["akita_black_bowl_1_main", "basket_1"]
    bowl = episode.scene_t0[0]
    assert bowl.pos == (0.4, 0.2, 0.9) and bowl.yaw == pytest.approx(0.4, abs=1e-6)


def test_one_init_state_is_one_digest_and_another_is_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = _adapter(monkeypatch, _SceneLiberoEnv())
    adapter.pin_init_states(0)
    policy = _SevenDofPolicy()
    a = run_episode(policy, adapter, make_attack("none"), TASK, seed=2, horizon=2)
    b = run_episode(policy, adapter, make_attack("roleplay"), TASK, seed=2, horizon=2)
    c = run_episode(policy, adapter, make_attack("none"), TASK, seed=3, horizon=2)
    assert a.scene_t0_digest == b.scene_t0_digest != c.scene_t0_digest


def test_the_digest_is_exact_where_the_readable_list_is_rounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, _ = _adapter(monkeypatch, _DriftingSceneEnv())
    adapter.pin_init_states(0)
    policy = _SevenDofPolicy()
    a = run_episode(policy, adapter, make_attack("none"), TASK, seed=0, horizon=2)
    b = run_episode(policy, adapter, make_attack("none"), TASK, seed=0, horizon=2)
    assert a.init_state == b.init_state and a.scene_t0 == b.scene_t0
    assert a.scene_t0_digest != b.scene_t0_digest, "a 1e-9 difference is a different scene"


def test_a_suite_without_a_simulator_records_no_scene() -> None:
    policy = StubPolicy()
    policy.load()
    result = run_episode(policy, StubSuite(), make_attack("none"), "reach", seed=0, horizon=2)
    assert result.scene_t0_digest is None and result.scene_t0 is None


def _scene_run(
    monkeypatch: pytest.MonkeyPatch, config: RunConfig, env: _FakeLiberoEnv
) -> RunReport:
    adapter, _ = _adapter(monkeypatch, env)
    monkeypatch.setattr(adapter, "features", lambda: None)
    monkeypatch.setattr("provael.runner.make_suite", lambda *_args, **_kwargs: adapter)
    monkeypatch.setattr("provael.runner.make_policy", lambda *_args, **_kwargs: _SevenDofPolicy())
    return run(config)


def test_a_pinned_run_whose_arms_start_apart_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same init state at a seed, different scene: a pinned run refuses to report the pair."""
    config = RunConfig(
        policy="stub", suite="libero", attacks=["none", "roleplay"], tasks=[TASK], episodes=2,
        horizon=2, pin_init_states=10,
    )
    with pytest.raises(ScenePinError, match="did not share a scene"):
        _scene_run(monkeypatch, config, _DriftingSceneEnv())


def test_a_pinned_run_matches_every_pair_and_an_unpinned_one_says_how_many(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {"policy": "stub", "suite": "libero", "attacks": ["none", "roleplay"],
            "tasks": [TASK], "episodes": 3, "horizon": 2}
    pinned = _scene_run(monkeypatch, RunConfig(**base, pin_init_states=10), _SceneLiberoEnv())
    assert pinned.scene_pairing == ScenePairing(
        pairs=3, init_state_matched=3, init_state_unrecorded=0, scene_matched=3,
        scene_unrecorded=0,
    )
    # Unpinned, the counter walks on: `none` takes states 0-2 and `roleplay` 3-5, so no pair at a
    # seed shares a scene — the case E-2026-19 is about, now counted in the report.
    walked = _scene_run(monkeypatch, RunConfig(**base), _SceneLiberoEnv())
    assert walked.scene_pairing == ScenePairing(
        pairs=3, init_state_matched=0, init_state_unrecorded=0, scene_matched=0,
        scene_unrecorded=0,
    )
    assert walked.schema_version == 9
    assert walked.sim_model_digests == {TASK: model_xml_digest(_FakeModel().get_xml())}


def test_the_stub_records_unrecorded_pairs_and_no_model() -> None:
    report = run(RunConfig(policy="stub", suite="stub", attacks=["none", "roleplay"], episodes=2))
    assert report.sim_model_digests == {"reach": None}
    assert report.scene_pairing == ScenePairing(
        pairs=2, init_state_matched=0, init_state_unrecorded=2, scene_matched=0,
        scene_unrecorded=2,
    )


def test_the_model_digest_names_the_model_not_the_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xml = '<mujoco><mesh file="{}/site-packages/libero/assets/bowl.stl"/></mujoco>'
    here, there = xml.format("/opt/py/lib/python3.12"), xml.format("/home/u/.venv/lib/python3.12")
    assert model_xml_digest(here) == model_xml_digest(there)
    assert model_xml_digest(here) != model_xml_digest(here.replace("bowl", "plate"))
    checkout = '<mujoco><mesh file="/src/LIBERO/libero/assets/bowl.stl"/></mujoco>'
    assert model_xml_digest(here) != model_xml_digest(checkout), (
        "a checkout outside site-packages keeps its path, and so its own digest"
    )
    adapter, built = _adapter(monkeypatch, _SceneLiberoEnv())
    digest = adapter.sim_model_digest(TASK)
    assert digest == model_xml_digest(_FakeModel().get_xml())
    assert len(built) == 1 and adapter.reset(TASK, seed=0)["init_state"] == 0, (
        "reading the model builds the env once and leaves its counter where it was"
    )
    assert adapter.sim_model_digest("libero_spatial/0") is None


def test_scene_snapshot_of_a_sim_it_cannot_read_is_unrecorded() -> None:
    assert scene_snapshot_of(object()) is None


def test_init_states_name_each_seed_s_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    config = RunConfig(
        policy="stub", suite="libero", attacks=["none", "roleplay"], tasks=[TASK], episodes=3,
        horizon=2, init_states={TASK: [7, 30, 2]},
    )
    report = _scene_run(monkeypatch, config, _SceneLiberoEnv(success_at=1))
    assert [(r.attack, r.seed, r.init_state) for r in report.results] == [
        ("none", 0, 7), ("none", 1, 30), ("none", 2, 2),
        ("roleplay", 0, 7), ("roleplay", 1, 30), ("roleplay", 2, 2),
    ]
    assert report.scene_pairing is not None and report.scene_pairing.scene_matched == 3


def test_a_benign_only_run_may_name_one_state_per_episode(monkeypatch: pytest.MonkeyPatch) -> None:
    config = RunConfig(
        policy="stub", suite="libero", attacks=["none"], tasks=[TASK], episodes=4,
        episodes_per_seed=2, horizon=2, init_states={TASK: [40, 41, 42, 43]},
    )
    report = _scene_run(monkeypatch, config, _SceneLiberoEnv())
    assert [(r.seed, r.init_state) for r in report.results] == [(0, 40), (0, 41), (1, 42), (1, 43)]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"attacks": ["none", "roleplay"], "episodes": 4, "episodes_per_seed": 2,
          "init_states": {TASK: [40, 41, 42, 43]}}, "must pin one state per seed"),
        ({"init_states": {"libero_object/9": [1, 2]}}, "missing"),
        ({"attacks": ["none"], "init_states": {TASK: [1, 2, 3]}}, "one per seed"),
    ],
)
def test_init_states_that_do_not_fit_the_run_are_refused_before_it_starts(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, Any], message: str
) -> None:
    base: dict[str, Any] = {"policy": "stub", "suite": "libero", "attacks": ["none", "roleplay"],
                            "tasks": [TASK], "episodes": 2, "horizon": 2}
    env = _SceneLiberoEnv()
    with pytest.raises(InitStatePlanError, match=message):
        _scene_run(monkeypatch, RunConfig(**{**base, **overrides}), env)
    assert env.resets == 0, "refused before any episode ran"


def test_init_states_and_a_pin_cannot_be_set_together() -> None:
    with pytest.raises(ValueError, match="pass one of them"):
        RunConfig(policy="stub", suite="libero", init_states={TASK: [1]}, pin_init_states=3)


def test_init_states_on_a_suite_without_fixed_init_states_are_refused() -> None:
    config = RunConfig(policy="stub", suite="stub", attacks=["none"], episodes=1,
                       init_states={"reach": [3]})
    with pytest.raises(NotImplementedError, match="keeps no fixed initial states"):
        run(config)


def test_a_named_state_is_a_non_negative_index(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = _adapter(monkeypatch, _SceneLiberoEnv())
    with pytest.raises(ValueError, match="non-negative"):
        adapter.choose_init_state(-1)
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        RunConfig(policy="stub", init_states={"reach": [-1]})
