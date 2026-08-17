"""CPU unit tests for the per-task calibrated keep-out zones (WS1).

No simulator: exercises the pure envelope/zone math and the registry fallback that back
``scripts/calibrate_zones.py`` and the per-task predicate selection.
"""

from __future__ import annotations

import warnings

import pytest

from provael.suites import keepout_zones as kz
from provael.suites.keepout_zones import (
    DEFAULT_KEEP_OUT_ZONE,
    KeepOutZone,
    benign_envelope,
    hazard_zone_beside,
    zone_margin,
    zones_for,
)


def test_keepout_zone_contains() -> None:
    z = KeepOutZone(name="t", x=(0.0, 1.0), y=(0.0, 1.0), z=(0.0, 1.0))
    assert z.contains([0.5, 0.5, 0.5]) is True
    assert z.contains([1.5, 0.5, 0.5]) is False
    assert z.contains([0.5, 0.5]) is False  # too short → not contained


def test_benign_envelope_bbox_and_margin() -> None:
    pts = [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0], [0.5, -1.0, 1.0]]
    (xr, yr, zr) = benign_envelope(pts)
    assert xr == (0.0, 1.0)
    assert yr == (-1.0, 2.0)
    assert zr == (0.0, 3.0)
    # margin pads symmetrically
    (xr2, _, _) = benign_envelope(pts, margin=0.1)
    assert xr2 == pytest.approx((-0.1, 1.1))


def test_benign_envelope_skips_invalid_and_raises_on_empty() -> None:
    pts = [None, [0.0, 0.0], [1.0, 1.0, 1.0]]  # None + too-short skipped
    assert benign_envelope(pts) == ((1.0, 1.0), (1.0, 1.0), (1.0, 1.0))
    with pytest.raises(ValueError, match="no valid 3D positions"):
        benign_envelope([None, [0.0, 0.0]])


def test_hazard_zone_is_disjoint_from_benign_envelope() -> None:
    pts = [[0.0, 0.0, 0.0], [0.4, 0.4, 0.4]]
    env = benign_envelope(pts)
    zone = hazard_zone_beside(env, axis="y", side="low", gap=0.05, depth=0.30)
    # No benign point may fall inside the hazard zone (that is the whole point).
    assert all(not zone.contains(p) for p in pts)
    # The zone sits below the envelope's low-y face, separated by the gap.
    assert zone.y[1] == pytest.approx(env[1][0] - 0.05)
    assert zone.y[0] == pytest.approx(env[1][0] - 0.05 - 0.30)
    # high side mirrors it
    zone_hi = hazard_zone_beside(env, axis="y", side="high", gap=0.05, depth=0.30)
    assert zone_hi.y[0] == pytest.approx(env[1][1] + 0.05)


def test_hazard_zone_rejects_bad_axis_or_side() -> None:
    env = ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))
    with pytest.raises(ValueError, match="axis must be"):
        hazard_zone_beside(env, axis="w")
    with pytest.raises(ValueError, match="side must be"):
        hazard_zone_beside(env, side="middle")


def test_zones_for_falls_back_to_default_when_uncalibrated() -> None:
    with pytest.warns(kz.UncalibratedZoneWarning):
        zones = zones_for("libero_object/999")  # not calibrated
    assert zones == [DEFAULT_KEEP_OUT_ZONE]


def test_zones_for_returns_calibrated_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    custom = KeepOutZone(name="calibrated:libero_object/0", x=(0.5, 0.6), y=(-0.9, -0.7), z=(0.0, 0.2))
    monkeypatch.setitem(kz.CALIBRATED_ZONES, "libero_object/0", [custom])
    assert zones_for("libero_object/0") == [custom]


# --------------------------------------------------------------------------------------------- #
# The uncalibrated fallback announces itself (#136)
#
# CALIBRATED_ZONES is empty, so EVERY task has always taken the fallback, and the default box
# overlaps the reachable benign workspace — which is why the published ten-task run's benign arm
# tripped at 4.0% rather than at zero. The zone stays (the calibration is owed and needs GPU
# budget); what changed is that it can no longer be taken silently, and a release can refuse it.
# --------------------------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_warned_tasks() -> None:
    """The warn-once cache is module state; a leaked entry would silently disarm another test."""
    kz._WARNED_TASKS.clear()


def test_calibrated_task_neither_warns_nor_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A calibrated task is the quiet path, in strict mode too — nothing to announce."""
    custom = KeepOutZone(name="calibrated:t", x=(0.5, 0.6), y=(-0.9, -0.7), z=(0.0, 0.2))
    monkeypatch.setitem(kz.CALIBRATED_ZONES, "libero_object/7", [custom])
    assert kz.is_calibrated("libero_object/7") is True
    with warnings.catch_warnings():
        warnings.simplefilter("error", kz.UncalibratedZoneWarning)
        assert zones_for("libero_object/7", strict=True) == [custom]


def test_uncalibrated_warns_once_per_task() -> None:
    """One line per task, not one per episode: a 400-episode run would drown its own warning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        zones_for("libero_object/0")
        zones_for("libero_object/0")
        zones_for("libero_object/1")
    emitted = [w for w in caught if issubclass(w.category, kz.UncalibratedZoneWarning)]
    assert len(emitted) == 2, "expected one warning per distinct task"
    assert "libero_object/0" in str(emitted[0].message)
    # The warning has to say it is a DEFAULT, not merely that something is uncalibrated: the whole
    # failure was a number that looked like every other number.
    assert "UNCALIBRATED" in str(emitted[0].message)
    assert DEFAULT_KEEP_OUT_ZONE.name in str(emitted[0].message)


def test_strict_mode_refuses_an_uncalibrated_zone() -> None:
    with pytest.raises(kz.UncalibratedZoneError, match="no committed calibration"):
        zones_for("libero_object/0", strict=True)


def test_strict_mode_reads_the_env_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Off by default so the honest default stays usable; on in the release gate."""
    monkeypatch.delenv(kz.REQUIRE_CALIBRATED_ENV, raising=False)
    with pytest.warns(kz.UncalibratedZoneWarning):
        assert zones_for("libero_object/0") == [DEFAULT_KEEP_OUT_ZONE]

    monkeypatch.setenv(kz.REQUIRE_CALIBRATED_ENV, "1")
    with pytest.raises(kz.UncalibratedZoneError):
        zones_for("libero_object/2")

    # "0" and empty are explicitly permissive, so unsetting is not the only way back.
    monkeypatch.setenv(kz.REQUIRE_CALIBRATED_ENV, "0")
    with pytest.warns(kz.UncalibratedZoneWarning):
        assert zones_for("libero_object/3") == [DEFAULT_KEEP_OUT_ZONE]


def test_explicit_strict_argument_overrides_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(kz.REQUIRE_CALIBRATED_ENV, "1")
    with pytest.warns(kz.UncalibratedZoneWarning):
        assert zones_for("libero_object/4", strict=False) == [DEFAULT_KEEP_OUT_ZONE]


def test_require_calibrated_is_recorded_in_the_manifest_env() -> None:
    """The gate state has to survive into the evidence, or 'we checked' is unverifiable.

    A manifest FIELD would invalidate every attestation ever issued (see
    EXECUTION_MANIFEST_VERSION), so the allow-list is the designed route.
    """
    from provael.execution import ENV_ALLOWLIST

    assert kz.REQUIRE_CALIBRATED_ENV in ENV_ALLOWLIST


# --------------------------------------------------------------------------------------------- #
# zone_margin: the spatial predicate made continuous, for use as a SEARCH objective
#
# `contains` is the right thing to SCORE and useless to SEARCH — flat everywhere, so a greedy
# hill-climb has nothing to climb until it lands inside by luck. The margin is the same predicate
# with a gradient. The correspondence below is what makes it safe to substitute: if the two ever
# disagreed, an optimized attack would be steered toward a boundary the run does not score.
# --------------------------------------------------------------------------------------------- #

def test_margin_sign_agrees_with_contains_over_a_grid_including_faces() -> None:
    """`margin >= 0` iff `contains` — checked ON the faces, where a search converges."""
    zone = KeepOutZone(name="g", x=(0.0, 1.0), y=(0.0, 1.0), z=(0.0, 1.0))
    steps = [-0.5, -0.001, 0.0, 0.25, 0.5, 1.0, 1.001, 1.5]  # includes both faces exactly
    checked = 0
    for px in steps:
        for py in steps:
            for pz in steps:
                point = [px, py, pz]
                assert (zone_margin(point, [zone]) >= 0.0) is zone.contains(point), point
                checked += 1
    assert checked == len(steps) ** 3  # guard the guard: the loop actually ran


def test_margin_is_monotone_approaching_the_zone() -> None:
    """Strictly increasing as the point closes on the zone — the property the search relies on."""
    zone = KeepOutZone(name="m", x=(1.0, 2.0), y=(-1.0, 1.0), z=(-1.0, 1.0))
    approach = [zone_margin([x, 0.0, 0.0], [zone]) for x in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert approach == sorted(approach)
    assert approach[-1] >= 0.0 > approach[0]  # ends inside, starts outside


def test_margin_takes_the_nearest_of_several_zones() -> None:
    near = KeepOutZone(name="near", x=(1.0, 2.0), y=(-1.0, 1.0), z=(-1.0, 1.0))
    far = KeepOutZone(name="far", x=(9.0, 10.0), y=(-1.0, 1.0), z=(-1.0, 1.0))
    assert zone_margin([0.0, 0.0, 0.0], [near, far]) == zone_margin([0.0, 0.0, 0.0], [near])


def test_margin_reports_no_signal_rather_than_a_tie_at_zero() -> None:
    """A missing pose or no zones must rank BELOW every real candidate, not tie with the boundary.

    Returning 0.0 here would read as 'exactly on the zone face' — the best possible non-violating
    score — so a search with no spatial signal at all would look like a search on the brink of
    success, and would prefer a candidate it knows nothing about over one it measured as far away.
    """
    zone = KeepOutZone(name="z", x=(0.0, 1.0), y=(0.0, 1.0), z=(0.0, 1.0))
    assert zone_margin(None, [zone]) == float("-inf")
    assert zone_margin([0.5, 0.5], [zone]) == float("-inf")  # short vector
    assert zone_margin([0.5, 0.5, 0.5], []) == float("-inf")
