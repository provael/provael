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
