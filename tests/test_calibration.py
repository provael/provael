"""Calibration core: Wilson CI, seed split, scalar/spatial fitting, model, artifact IO."""

from __future__ import annotations

from pathlib import Path

import pytest

from provael.calibration import (
    Calibration,
    artifact_name,
    fit_scalar_threshold,
    fit_spatial_zone,
    load_calibrations,
    save_calibration,
    split_seeds,
    to_json,
    wilson_ci,
)
from provael.suites.keepout_zones import KeepOutZone


def test_wilson_ci_brackets_point_estimate() -> None:
    low, high = wilson_ci(8, 10)
    assert low < 0.8 < high
    assert round(low, 2) == 0.49
    assert round(high, 2) == 0.94


def test_wilson_ci_edges() -> None:
    assert wilson_ci(0, 0) == (0.0, 0.0)
    low, high = wilson_ci(0, 10)
    assert low == 0.0 and 0.25 < high < 0.31
    low, high = wilson_ci(10, 10)
    assert high == pytest.approx(1.0) and 0.69 < low < 0.73


def test_split_seeds_is_deterministic_and_requires_two() -> None:
    fit, holdout = split_seeds(list(range(10)))
    assert fit == [0, 1, 2, 3, 4, 5, 6] and holdout == [7, 8, 9]
    assert fit + holdout == list(range(10))  # no overlap, full cover
    with pytest.raises(ValueError):
        split_seeds([0])


def test_fit_scalar_threshold_hits_target_on_spread() -> None:
    scores = [i / 10 for i in range(10)]  # 0.0 .. 0.9
    threshold, fpr = fit_scalar_threshold(scores, scores, target_fpr=0.2)
    # Tightest t with <=20% of holdout strictly above it: 0.7 leaves {0.8, 0.9} = 20%.
    assert threshold == pytest.approx(0.7)
    assert fpr <= 0.2


def test_fit_scalar_threshold_degenerate_benign_is_clean() -> None:
    # The stub's benign danger is constant 0 -> threshold 0, FPR 0, and any positive
    # attack danger is flagged (strict >).
    threshold, fpr = fit_scalar_threshold([0.0] * 7, [0.0] * 3, target_fpr=0.05)
    assert threshold == 0.0 and fpr == 0.0
    assert Calibration(
        policy="stub", suite="stub", task="reach", kind="scalar",
        threshold=threshold, target_fpr=0.05, benign_fpr=fpr, n_benign=10,
    ).is_unsafe({"danger": 0.6})
    assert not Calibration(
        policy="stub", suite="stub", task="reach", kind="scalar",
        threshold=threshold, target_fpr=0.05, benign_fpr=fpr, n_benign=10,
    ).is_unsafe({"danger": 0.0})


def test_fit_spatial_zone_keeps_benign_out() -> None:
    # Benign EE clustered in a small box; the hazard zone is placed disjoint from it.
    benign = [[[0.0, 0.0, 0.0], [0.01, 0.0, 0.0]] for _ in range(6)]
    envelope, zones, fpr = fit_spatial_zone(benign[:4], benign[4:], target_fpr=0.05)
    assert len(envelope) == 3 and len(zones) == 1
    assert fpr <= 0.05
    # A benign point is NOT in the hazard zone; a point inside the zone IS.
    zone = zones[0]
    assert not zone.contains([0.0, 0.0, 0.0])
    inside = [(zone.x[0] + zone.x[1]) / 2, (zone.y[0] + zone.y[1]) / 2, (zone.z[0] + zone.z[1]) / 2]
    assert zone.contains(inside)


def test_calibration_spatial_is_unsafe() -> None:
    zone = KeepOutZone(name="hz", x=(1.0, 2.0), y=(1.0, 2.0), z=(1.0, 2.0))
    cal = Calibration(
        policy="smolvla", suite="libero", task="libero_object/0", kind="spatial",
        keep_out_zones=[zone], target_fpr=0.05, benign_fpr=0.0, n_benign=10,
    )
    assert cal.is_unsafe({"ee_pos": [1.5, 1.5, 1.5]})
    assert not cal.is_unsafe({"ee_pos": [0.0, 0.0, 0.0]})
    assert not cal.is_unsafe({"ee_pos": None})


def test_artifact_round_trip_and_determinism(tmp_path: Path) -> None:
    cal = Calibration(
        policy="stub", suite="stub", task="reach", kind="scalar",
        threshold=0.0, target_fpr=0.05, benign_fpr=0.0, n_benign=10,
        fit_seeds=[0, 1, 2], holdout_seeds=[3, 4],
    )
    path = save_calibration(cal, tmp_path)
    assert path.name == artifact_name("stub", "stub", "reach") == "stub__stub__reach.json"
    # Byte-deterministic.
    assert to_json(cal) == to_json(cal)
    # Round-trips and is discoverable by (policy, suite).
    loaded = load_calibrations(tmp_path, "stub", "stub")
    assert set(loaded) == {"reach"}
    assert loaded["reach"].threshold == 0.0
    assert load_calibrations(tmp_path, "other", "stub") == {}


def test_artifact_name_sanitizes_task() -> None:
    assert artifact_name("smolvla", "libero", "libero_object/0") == "smolvla__libero__libero_object_0.json"
