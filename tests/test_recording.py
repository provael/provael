# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Recording-only episode observation: the report cannot move, and the camera model is proven.

The promise :mod:`provael.recording` makes is that a recorder — even one that keeps stepping past
the verdict — changes nothing a run measures. The first tests are the guard on that promise: the
same episode with and without a recorder yields the same result, byte for byte, through
``run_episode`` and through ``run``. The rest pin the steps past the verdict (where they stop, what
they may not touch), the exact action comparison behind the identical-actions check, the projection
and its proof, and the LIBERO camera rig against a fake robosuite simulator (LIBERO itself does not
install on the CPU build).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from provael.attacks.baseline import NoOpAttack
from provael.attacks.instruction import RolePlayAttack
from provael.config import RunConfig
from provael.defenses.base import Defense
from provael.policies.stub import StubPolicy
from provael.recording import (
    ActionLog,
    CameraProjection,
    Segmentation,
    check_projection,
    compare_actions,
)
from provael.report import to_json
from provael.runner import NonFiniteActionError, run, run_episode
from provael.suites.keepout_zones import DEFAULT_KEEP_OUT_ZONE
from provael.suites.stub import StubSuite
from provael.types import IMAGE_KEY, Action, Observation, State

#: The scripted step at which the tail suite's end-effector enters the keep-out box.
EXIT_STEP = 5
#: How far the end-effector moves along x per roleplay step; it starts half a step past
#: ``EXIT_STEP - 1`` increments short of the box's near face (x = 0.10), so step EXIT_STEP enters.
_STRIDE = 0.06
_START_X = DEFAULT_KEEP_OUT_ZONE.x[0] - (EXIT_STEP - 0.5) * _STRIDE


class _TailSuite(StubSuite):
    """LIBERO-shaped: the keep-out predicate fires mid-episode and the episode does NOT end there.

    The end-effector walks one fixed increment per step toward the default keep-out box when the
    instruction is the roleplay sentence (the stub policy's danger channel is high), and enters it
    at :data:`EXIT_STEP`; the benign arm never enters it. ``done_at`` makes the suite end the
    episode at that step, as LIBERO does on task success.
    """

    name = "tail_test"
    _TASKS = ("reach",)

    def __init__(self, done_at: int | None = None) -> None:
        super().__init__()
        self.done_at = done_at
        self._pos = np.zeros(3)

    def reset(self, task: str, seed: int) -> Observation:
        obs = super().reset(task, seed)
        self._pos = np.array([_START_X, -0.25, 0.15])
        return {**obs, IMAGE_KEY: np.zeros((8, 8, 3), dtype=np.uint8)}

    def step(self, action: Action) -> tuple[Observation, bool, State]:
        obs, _done, state = super().step(action)
        if float(np.asarray(action)[0]) >= 0.5:
            self._pos = self._pos + np.array([_STRIDE, 0.0, 0.0])
        frame = np.full((8, 8, 3), self._step % 256, dtype=np.uint8)
        done = self.done_at is not None and self._step >= self.done_at
        return ({**obs, IMAGE_KEY: frame}, done,
                {**state, "ee_pos": [float(v) for v in self._pos]})

    def is_unsafe(self, state: State) -> bool:
        return DEFAULT_KEEP_OUT_ZONE.contains(state.get("ee_pos") or [])


def _episode(recorder: Any = None, *, done_at: int | None = None, horizon: int = 12,
             attack: Any = None, defense: Any = None, audit: list[dict[str, str]] | None = None,
             policy: Any = None) -> Any:
    pol = policy if policy is not None else StubPolicy()
    pol.load()
    return run_episode(
        pol, _TailSuite(done_at=done_at), attack or RolePlayAttack(), "reach", 0, horizon,
        recorder=recorder, defense=defense, audit_sink=audit,
    )


# -- the report cannot move ----------------------------------------------------------------------


def test_a_recorder_that_plays_past_the_verdict_leaves_the_result_byte_identical() -> None:
    plain = _episode()
    log = ActionLog(continue_past_verdict=True)
    recorded = _episode(log)
    assert plain.success and plain.steps_to_success == EXIT_STEP and plain.steps == EXIT_STEP
    assert recorded.model_dump_json() == plain.model_dump_json()
    assert len(log.steps) == 12  # the episode kept going for the recorder alone


def test_run_writes_the_same_report_with_and_without_a_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from provael import suites

    monkeypatch.setitem(suites.SUITES, "tail_test", _TailSuite)
    config = RunConfig(policy="stub", suite="tail_test", attacks=["roleplay"], episodes=1,
                       seed=0, horizon=12)
    logs: list[ActionLog] = []

    def factory(task: str, seed: int, attack: str) -> ActionLog:
        logs.append(ActionLog(continue_past_verdict=True))
        return logs[-1]

    assert to_json(run(config, recorder_factory=factory)) == to_json(run(config))
    assert len(logs) == 1 and logs[0].verdict_step == EXIT_STEP and logs[0].ended_by == "horizon"


def test_run_refuses_a_recorder_on_a_multi_episode_unpinned_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from provael import suites

    monkeypatch.setitem(suites.SUITES, "tail_test", _TailSuite)
    config = RunConfig(policy="stub", suite="tail_test", attacks=["roleplay"], episodes=2,
                       seed=0, horizon=4)
    with pytest.raises(ValueError, match="pin_init_states"):
        run(config, recorder_factory=lambda t, s, a: ActionLog())


# -- the steps past the verdict ------------------------------------------------------------------


def test_the_recorder_sees_scored_steps_then_recording_only_steps() -> None:
    log = ActionLog(continue_past_verdict=True)
    _episode(log, horizon=10)
    assert log.steps == list(range(1, 11))
    assert log.scored == [True] * EXIT_STEP + [False] * (10 - EXIT_STEP)
    assert log.unsafe[EXIT_STEP - 1] is True  # the verdict step, as scored
    assert log.ended_by == "horizon" and log.verdict_step == EXIT_STEP


def test_recording_stops_where_the_suite_ends_the_episode() -> None:
    log = ActionLog(continue_past_verdict=True)
    result = _episode(log, done_at=8, horizon=20)
    assert result.steps == EXIT_STEP
    assert log.steps[-1] == 8 and log.ended_by == "done"


def test_a_recorder_that_does_not_continue_stops_at_the_verdict() -> None:
    log = ActionLog(continue_past_verdict=False)
    _episode(log, horizon=10)
    assert log.steps == list(range(1, EXIT_STEP + 1)) and log.ended_by == "verdict"


def test_a_benign_episode_records_to_the_horizon_with_every_step_scored() -> None:
    log = ActionLog(continue_past_verdict=True)
    result = _episode(log, attack=NoOpAttack(), horizon=7)
    assert not result.success and result.steps == 7
    assert log.scored == [True] * 7 and log.ended_by == "horizon"


class _NanAfter(StubPolicy):
    """The stub policy, emitting NaN from step ``after + 1`` on."""

    def __init__(self, after: int) -> None:
        super().__init__()
        self.after = after
        self.calls = 0

    def act(self, observation: Observation, instruction: str) -> Action:
        self.calls += 1
        action = super().act(observation, instruction)
        return np.full_like(action, np.nan) if self.calls > self.after else action


def test_a_nan_past_the_verdict_stops_the_recording_and_keeps_the_scored_episode() -> None:
    log = ActionLog(continue_past_verdict=True)
    result = _episode(log, policy=_NanAfter(after=EXIT_STEP + 2), horizon=12)
    assert result.success and result.steps == EXIT_STEP
    assert log.ended_by == "non-finite action" and log.steps[-1] == EXIT_STEP + 2


def test_a_nan_inside_the_scored_episode_still_refuses_to_score() -> None:
    with pytest.raises(NonFiniteActionError):
        _episode(ActionLog(), policy=_NanAfter(after=2))
    assert issubclass(NonFiniteActionError, ValueError)  # callers catching ValueError still do


class _PassThrough(Defense):
    """Applies everywhere, audits every step, changes nothing: only the audit trail is tested."""

    name = "pass_through_test"

    def apply(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        return instruction, observation


def test_steps_past_the_verdict_write_no_defense_audit_line() -> None:
    audit: list[dict[str, str]] = []
    result = _episode(ActionLog(continue_past_verdict=True), horizon=10,
                      defense=_PassThrough(), audit=audit)
    assert result.steps_to_success == EXIT_STEP
    assert audit, "the defense applies to this suite, so the scored steps are audited"
    assert max(int(row["step"]) for row in audit) <= EXIT_STEP


def test_an_inapplicable_attack_still_finishes_the_recorder() -> None:
    class _Inapplicable(RolePlayAttack):
        def applicable(self, observation: Observation) -> bool:
            return False

    log = ActionLog()
    result = _episode(log, attack=_Inapplicable())
    assert result.applicable is False and log.ended_by == "not applicable" and log.steps == []


# -- the exact action comparison -----------------------------------------------------------------


def _log(steps: list[int], actions: list[list[float]]) -> dict[str, Any]:
    return {"steps": steps, "actions": actions}


def test_compare_actions_is_exact_and_names_the_first_differing_step() -> None:
    a = _log([1, 2, 3], [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
    assert compare_actions(a, a).identical
    b = _log([1, 2, 3], [[0.1, 0.2], [0.3, 0.4 + 1e-12], [0.5, 0.6]])
    diff = compare_actions(a, b)
    assert not diff.identical and diff.first_differing_step == 2
    assert diff.max_abs_difference_at_first is not None
    assert 0 < diff.max_abs_difference_at_first < 1e-9
    assert "first differing step 2" in diff.summary()


def test_compare_actions_refuses_to_line_up_different_lengths_or_steps() -> None:
    a = _log([1, 2, 3], [[0.0], [0.0], [0.0]])
    shorter = compare_actions(a, _log([1, 2], [[0.0], [0.0]]))
    assert not shorter.identical and shorter.first_differing_step is None
    assert "different lengths" in shorter.summary()
    skipped = compare_actions(a, _log([1, 3, 4], [[0.0], [0.0], [0.0]]))
    assert not skipped.identical and skipped.first_differing_step == 2


# -- the projection and its proof ----------------------------------------------------------------


def _camera(width: int = 200, height: int = 100) -> CameraProjection:
    # Camera at (2, 0, 0) looking down -x: right = +y? Build MuJoCo axes: back = +x, up = +z.
    # right = up x back = (0,0,1) x (1,0,0) = (0,1,0).
    rot = ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    return CameraProjection("cam", width, height, (2.0, 0.0, 0.0), rot, 90.0)


def test_projection_follows_mujocos_pinhole() -> None:
    cam = _camera()
    (u, v), = cam.project([(0.0, 0.0, 0.0)])[0].tolist()
    assert (u, v) == pytest.approx((100.0, 50.0))  # straight ahead -> the image centre
    assert cam.focal_px == pytest.approx(50.0)  # 0.5 * 100 / tan(45 deg)
    (ur, _), = cam.project([(0.0, 1.0, 0.0)])[0].tolist()
    (_, vu), = cam.project([(0.0, 0.0, 1.0)])[0].tolist()
    assert ur == pytest.approx(100 + 25.0) and vu == pytest.approx(50 - 25.0)  # right is +u, up is -v
    _, front = cam.project([(3.0, 0.0, 0.0)])
    assert not front[0]  # behind the camera


def test_projection_scales_and_round_trips() -> None:
    cam = _camera()
    big = cam.scaled(400, 200)
    (u, v), = big.project([(0.0, 1.0, 1.0)])[0].tolist()
    (u0, v0), = cam.project([(0.0, 1.0, 1.0)])[0].tolist()
    assert (u, v) == pytest.approx((2 * u0, 2 * v0))
    assert CameraProjection.from_json_dict(cam.to_json_dict()) == cam


def _scene(cam: CameraProjection, *, n: int = 10) -> Segmentation:
    """Disks drawn where ``cam`` puts each object, as a renderer's segmentation would."""
    ids = np.full((cam.height, cam.width), -1, dtype=np.int32)
    centres: dict[int, tuple[float, float, float]] = {}
    for gid in range(n):
        y = -0.8 + 1.6 * gid / (n - 1)
        z = 0.35 * math.sin(gid * 1.7)
        centres[gid] = (0.0, y, z)
        (u, v), = cam.project([centres[gid]])[0].tolist()
        yy, xx = np.mgrid[0:cam.height, 0:cam.width]
        ids[(xx + 0.5 - u) ** 2 + (yy + 0.5 - v) ** 2 <= 9.0 ** 2] = gid
    return Segmentation("cam", ids, centres)


def test_the_proof_passes_a_right_mapping_and_fails_a_mirrored_one() -> None:
    cam = _camera(400, 200)
    seg = _scene(cam)
    good = check_projection(cam, seg)
    assert good.passed, good.reason
    assert good.geoms_considered >= 8 and good.hits == good.geoms_considered
    assert good.mirrored_hits <= 3 and good.flipped_hits <= 3
    # The same objects segmented from a mirrored camera: right axis flipped.
    mirrored = CameraProjection("cam", 400, 200, cam.position,
                                ((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)), 90.0)
    bad = check_projection(mirrored, seg)
    assert not bad.passed


def test_the_proof_refuses_too_few_objects_and_the_wrong_size() -> None:
    cam = _camera(400, 200)
    few = check_projection(cam, _scene(cam, n=4))
    assert not few.passed and "at least 8" in few.reason
    wrong = check_projection(cam.scaled(200, 100), _scene(cam))
    assert not wrong.passed and "segmentation is 400x200" in wrong.reason


# -- the LIBERO camera rig, against a fake robosuite simulator ----------------------------------


class _FakeModel:
    ncam = 3
    nq = 2
    nv = 2
    cam_fovy = np.array([45.0, 60.0, 30.0])
    cam_sensorsize = np.zeros((3, 2))

    def camera_id2name(self, i: int) -> str:
        return ("agentview", "frontview", "robot0_eye_in_hand")[i]

    def camera_name2id(self, name: str) -> int:
        return ("agentview", "frontview", "robot0_eye_in_hand").index(name)

    def geom_id2name(self, g: int) -> str:
        return f"g{g}"


class _FakeData:
    def __init__(self) -> None:
        self.cam_xpos = np.array([[1.0, 0.0, 1.0], [2.0, 0.0, 1.0], [0.0, 0.0, 0.0]])
        self.cam_xmat = np.tile(np.eye(3).reshape(-1), (3, 1))
        self.geom_xpos = np.array([[0.0, 0.0, 0.0], [0.1, 0.2, 0.3]])


class _FakeSim:
    def __init__(self) -> None:
        self.model, self.data = _FakeModel(), _FakeData()
        self.state = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        self.calls: list[str] = []

    def get_state(self) -> Any:
        sim = self

        class _State:
            def flatten(self) -> Any:
                return sim.state

        return _State()

    def set_state_from_flattened(self, value: Any) -> None:
        self.calls.append("set")
        self.state = np.array(value)

    def forward(self) -> None:
        self.calls.append("forward")

    def render(self, width: int, height: int, *, camera_name: str,
               segmentation: bool = False) -> Any:
        self.calls.append(f"render:{camera_name}:{segmentation}")
        if segmentation:
            seg = np.full((height, width, 2), -1, dtype=np.int32)
            seg[0, :] = (5, 1)  # the readout's FIRST row is the image's bottom row
            seg[-1, :] = (6, 0)  # not a geom (objtype 6): must not count
            return seg
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[0, :, 0] = int(self.state[0]) + 10  # tag the bottom row with the restored time
        return img


def _libero_with(sim: _FakeSim | None) -> Any:
    from provael.suites.libero import LiberoSuiteAdapter

    adapter = LiberoSuiteAdapter()
    adapter._robosuite_env = lambda: None if sim is None else type("RS", (), {"sim": sim})()  # type: ignore[method-assign]
    return adapter


def test_the_libero_rig_lists_cameras_and_snapshots_by_copy() -> None:
    sim = _FakeSim()
    source = _libero_with(sim).video_source()
    assert source.cameras() == ["agentview", "frontview", "robot0_eye_in_hand"]
    snap = source.snapshot()
    sim.state[0] = 99.0
    assert snap[0] == 0.0 and snap.dtype == np.float64  # a copy, not a view of live state


def test_the_libero_rig_restores_each_snapshot_and_returns_upright_frames() -> None:
    sim = _FakeSim()
    source = _libero_with(sim).video_source()
    frames = list(source.render([np.array([7.0, 0, 0, 0, 0])], ["agentview", "frontview"], 4, 3))
    assert sim.calls[:2] == ["set", "forward"]  # state restored and forwarded before rendering
    assert set(frames[0]) == {"agentview", "frontview"}
    img = frames[0]["agentview"]
    assert img.shape == (3, 4, 3) and int(img[-1, 0, 0]) == 17  # readout row 0 is now the bottom


def test_the_libero_rig_refuses_a_snapshot_from_another_model() -> None:
    source = _libero_with(_FakeSim()).video_source()
    with pytest.raises(ValueError, match="different model"):
        list(source.render([np.zeros(3)], ["agentview"], 4, 3))


def test_the_libero_rig_projection_reads_fovy_position_and_axes() -> None:
    source = _libero_with(_FakeSim()).video_source()
    proj = source.projection("frontview", 64, 48)
    assert proj is not None and proj.fovy_deg == 60.0 and proj.position == (2.0, 0.0, 1.0)
    assert proj.rotation == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def test_the_libero_rig_segmentation_keeps_geoms_and_flips_rows() -> None:
    source = _libero_with(_FakeSim()).video_source()
    seg = source.segmentation(np.zeros(5), "agentview", 4, 3)
    assert seg is not None
    assert (seg.ids[-1] == 1).all() and (seg.ids[0] == -1).all()  # geom 1 on the bottom row
    assert seg.centers == {1: (0.1, 0.2, 0.3)} and seg.names == {1: "g1"}


def test_the_libero_rig_refuses_to_record_without_its_simulator() -> None:
    source = _libero_with(None).video_source()
    with pytest.raises(RuntimeError, match="did not resolve"):
        source.cameras()


def test_a_suite_without_a_renderer_offers_no_video_source() -> None:
    assert StubSuite().video_source() is None
