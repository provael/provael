"""CPU unit tests for the per-task calibrated keep-out zones (WS1).

No simulator: exercises the pure envelope/zone math and the registry fallback that back
``scripts/calibrate_zones.py`` and the per-task predicate selection.
"""

from __future__ import annotations

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
    zones = zones_for("libero_object/999")  # not calibrated
    assert zones == [DEFAULT_KEEP_OUT_ZONE]


def test_zones_for_returns_calibrated_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    custom = KeepOutZone(name="calibrated:libero_object/0", x=(0.5, 0.6), y=(-0.9, -0.7), z=(0.0, 0.2))
    monkeypatch.setitem(kz.CALIBRATED_ZONES, "libero_object/0", [custom])
    assert zones_for("libero_object/0") == [custom]


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
