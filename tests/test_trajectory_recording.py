# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every episode that records an outcome must also record the trajectory behind it (#136).

WHY THIS IS A HARD FAILURE AND NOT A WARNING. The calibration input was being computed on every
step and discarded on every run, which is the reason #136 is *unfixable* rather than merely
unfixed: the blocker was never GPU budget for the fit, it was that the data the fit consumes did
not exist. A warning would let that state return silently the first time a suite forgot to surface
the signal, and the loss is not recoverable after the fact — the run is over and the poses are
gone. So a missing trajectory fails the run.

The counts must MATCH, not merely both be non-zero: a run that records ten outcomes and nine
trajectories has silently dropped an episode from the calibration set, and the episode it drops is
disproportionately likely to be the interesting one (the loop breaks on the unsafe step).
"""

from __future__ import annotations

import pytest

from provael.config import RunConfig
from provael.runner import run
from provael.types import Trajectory

_SPATIAL = {"policy": "stub", "suite": "reach", "attacks": ["none", "instruction"], "episodes": 3}
_SCALAR = {"policy": "stub", "suite": "stub", "attacks": ["none", "instruction"], "episodes": 3}


def _report(**overrides: object):  # noqa: ANN202 - test helper
    return run(RunConfig(**{**_SPATIAL, **overrides}))  # type: ignore[arg-type]


def test_every_recorded_episode_carries_a_trajectory() -> None:
    report = _report()
    outcomes = [r for r in report.results if r.applicable]
    assert outcomes, "no applicable episodes to check"
    missing = [f"{r.task}/{r.attack}/{r.seed}" for r in outcomes if r.trajectory is None]
    assert not missing, (
        f"{len(missing)} episode(s) recorded an outcome with no trajectory: {missing[:5]}. "
        "The calibration input is being discarded again — see #136."
    )


def test_outcome_and_trajectory_counts_match_exactly() -> None:
    report = _report()
    outcomes = [r for r in report.results if r.applicable]
    with_traj = [r for r in outcomes if r.trajectory is not None]
    assert len(with_traj) == len(outcomes)


def test_trajectory_length_matches_the_steps_actually_executed() -> None:
    """A trajectory shorter than the episode means samples were dropped mid-run."""
    for r in _report().results:
        if r.trajectory is None:
            continue
        assert r.trajectory.shape[0] == r.steps, (
            f"{r.task}/{r.attack}/{r.seed}: {r.steps} steps executed but "
            f"{r.trajectory.shape[0]} poses recorded"
        )


def test_the_violating_step_is_in_the_trajectory() -> None:
    """The step that breaks the envelope is the most informative sample in the whole episode.

    The runner breaks out of the loop on the unsafe step, so a sample taken after that check would
    be missing from exactly the episodes a calibration most wants to look at.
    """
    successes = [r for r in _report().results if r.success and r.trajectory is not None]
    if not successes:
        pytest.skip("no successful episode in this fixture to check")
    for r in successes:
        assert r.steps_to_success is not None
        assert r.trajectory is not None
        assert r.trajectory.shape[0] >= r.steps_to_success


def test_benign_episodes_are_recorded_too() -> None:
    """The BENIGN arm is the one the calibration actually needs; recording only attacks is useless."""
    benign = [r for r in _report().results if r.attack == "none"]
    assert benign, "no benign episodes in the fixture"
    assert all(r.trajectory is not None for r in benign)


def test_recording_is_on_by_default_with_no_flag() -> None:
    """Gated on nothing. An opt-in flag recreates the pre-0.35.0 loss the first time it is forgotten."""
    report = run(RunConfig(**_SPATIAL))  # type: ignore[arg-type]
    assert any(r.trajectory is not None for r in report.results)


def test_spatial_suite_records_three_dimensions() -> None:
    for r in _report().results:
        if r.trajectory is not None:
            assert r.trajectory.shape[1] == 3, "a spatial suite must record x, y, z"


def test_scalar_suite_records_one_dimension() -> None:
    """A scalar-danger suite still records, at width 1, so a reader can tell the kinds apart."""
    report = run(RunConfig(**_SCALAR))  # type: ignore[arg-type]
    traj = [r.trajectory for r in report.results if r.trajectory is not None]
    assert traj, "scalar suite recorded nothing"
    assert all(t.shape[1] == 1 for t in traj)


def test_trajectory_survives_a_serialisation_round_trip() -> None:
    """It has to survive report.json, or it is not in the artifact a calibration would read."""
    report = _report()
    restored = type(report).model_validate_json(report.model_dump_json())
    pairs = [
        (a.trajectory, b.trajectory)
        for a, b in zip(report.results, restored.results, strict=True)
    ]
    assert pairs
    for original, round_tripped in pairs:
        assert (original is None) == (round_tripped is None)
        if original is not None and round_tripped is not None:
            assert original.decode() == round_tripped.decode()


def test_encoding_is_deterministic() -> None:
    """The determinism contract covers the artifact, and the trajectory is now part of it."""
    samples = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert Trajectory.encode(samples).data == Trajectory.encode(samples).data


def test_a_ragged_trajectory_is_rejected() -> None:
    with pytest.raises(ValueError, match="2-D"):
        Trajectory.encode([[0.1, 0.2, 0.3], [0.4, 0.5]])


def test_a_payload_disagreeing_with_its_shape_is_rejected() -> None:
    """A truncated blob must fail loudly rather than silently yield a shorter trajectory."""
    good = Trajectory.encode([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
    lying = Trajectory(shape=(9, 3), data=good.data)
    with pytest.raises(ValueError, match="payload"):
        lying.decode()


# --------------------------------------------------------------------------- #
# named channels (schema 9, P1.5): a reader never infers the stride
# --------------------------------------------------------------------------- #

_POSE = ("x", "y", "z", "qx", "qy", "qz", "qw", "gripper_opening")


def test_every_new_trajectory_names_its_channels() -> None:
    assert {tuple(r.trajectory.channels or ()) for r in _report().results if r.trajectory} == {
        ("x", "y", "z")
    }
    scalar = run(RunConfig(**_SCALAR))  # type: ignore[arg-type]
    assert {tuple(r.trajectory.channels or ()) for r in scalar.results if r.trajectory} == {
        ("danger",)
    }


def test_named_channels_round_trip_and_are_read_by_name() -> None:
    rows = [[0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0, 0.08], [0.4, 0.5, 0.6, 0.0, 0.0, 0.7, 0.7, 0.01]]
    traj = Trajectory.encode(rows, channels=_POSE)
    restored = Trajectory.model_validate_json(traj.model_dump_json())
    assert restored.channels == list(_POSE) and restored.channel_names() == _POSE
    flat = [v for row in restored.decode() for v in row]
    assert flat == pytest.approx([v for row in rows for v in row])
    assert [v for (v,) in restored.columns("gripper_opening")] == pytest.approx([0.08, 0.01])
    xyz = [v for row in restored.calibration_signal() for v in row]
    assert xyz == pytest.approx([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])


def test_an_old_three_channel_trajectory_still_decodes() -> None:
    """Every trajectory before schema 9 names nothing; its width says what it is."""
    legacy = Trajectory(**Trajectory.encode([[0.1, 0.2, 0.3]]).model_dump(exclude={"channels"}))
    assert legacy.channels is None and legacy.channel_names() == ("x", "y", "z")
    assert legacy.calibration_signal() == legacy.decode()
    scalar = Trajectory(**Trajectory.encode([[0.7]]).model_dump(exclude={"channels"}))
    assert scalar.channel_names() == ("danger",)
    odd = Trajectory(**Trajectory.encode([[1.0, 2.0]]).model_dump(exclude={"channels"}))
    with pytest.raises(ValueError, match="no known layout"):
        odd.channel_names()


def test_a_committed_trajectory_from_before_schema_9_reads_as_it_did() -> None:
    from pathlib import Path

    from provael.report import load_report

    shard = Path(__file__).resolve().parents[1] / "results" / (
        "smolvla_libero_object_suite_2026-09-14/libero_object_0"
    )
    report = load_report(shard)
    traj = next(r.trajectory for r in report.results if r.trajectory is not None)
    assert traj.channels is None and traj.shape[1] == 3
    assert traj.calibration_signal() == traj.decode()


def test_channels_must_name_every_column_once() -> None:
    with pytest.raises(ValueError, match="channel"):
        Trajectory.encode([[0.1, 0.2, 0.3]], channels=("x", "y"))
    with pytest.raises(ValueError, match="repeat"):
        Trajectory.encode([[0.1, 0.2]], channels=("x", "x"))
    with pytest.raises(ValueError, match="no channel"):
        Trajectory.encode([[0.1, 0.2, 0.3]], channels=("x", "y", "z")).columns("qw")


def test_the_projection_strips_channels_from_a_report_that_declares_less() -> None:
    """A schema-8 report's trajectories digest as they always did; a schema-9 one keeps them."""
    from provael.attest import report_projection

    report = _report()
    projected = report_projection(report)
    assert projected["results"][0]["trajectory"]["channels"] == ["x", "y", "z"]
    older = report_projection(report.model_copy(update={"schema_version": 8}))
    assert "channels" not in older["results"][0]["trajectory"]


def test_a_libero_step_records_position_orientation_and_gripper() -> None:
    import math

    import numpy as np

    from provael.suites.libero import LIBERO_TRAJECTORY_CHANNELS, LiberoSuiteAdapter

    adapter = LiberoSuiteAdapter()
    obs = {"robot_state": {
        "eef": {"pos": np.array([[0.1, 0.2, 0.9]]), "quat": np.array([[0.0, 0.0, 0.0, 1.0]])},
        "gripper": {"qpos": np.array([[0.03, -0.03]])},
    }}
    state = adapter._state_from(obs, {})
    assert adapter.trajectory_channels() == LIBERO_TRAJECTORY_CHANNELS == _POSE
    assert adapter.trajectory_sample(state) == pytest.approx([0.1, 0.2, 0.9, 0, 0, 0, 1, 0.06])
    # An orientation or opening that could not be read is NaN in its column, never a guess.
    del obs["robot_state"]["eef"]["quat"], obs["robot_state"]["gripper"]
    sample = adapter.trajectory_sample(adapter._state_from(obs, {}))
    assert sample is not None and sample[:3] == pytest.approx([0.1, 0.2, 0.9])
    assert all(math.isnan(v) for v in sample[3:])
    # No position, no row: the step is dropped from the trajectory, as it always was.
    assert adapter.trajectory_sample(adapter._state_from({}, {})) is None
