# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Adoption is loaded from packaged artifacts, gated on evidence, and never silently drops one.

WHAT THIS STOPS. `CALIBRATED_ZONES` was a hand-written literal that stayed `{}` while ten fitted
calibrations sat committed under `results/calibration/`, and nothing connected the two: the dict
could stay empty forever and every check would pass. Issue #136 has been open since 16 August on
exactly that gap.

THE INVARIANT ASSERTED HERE IS NOT "artifacts exist, therefore adopt". That version of the test
would force adoption of a predicate measured to catch nothing — five of the six candidate hazard
faces score a 0.0 benign false-positive rate and flag zero attacked episodes
(`studies/keepout_face_selection/`), so a low benign rate is not evidence a boundary works, and a
zone that cannot fire scores a perfect ASR. The invariant is that every committed fit is
ACCOUNTED FOR: adopted, or withheld with a stated reason. Silence is the failure; refusal is not.

WHY THE PACKAGED DIRECTORY AND NOT `results/`. `pyproject.toml` ships `packages = ["src/provael"]`,
so `results/` is absent from a wheel entirely. Loading the predicate from there would make the
boundary every ASR is scored against differ between a source checkout and a `pip install` — the
same published number resting on two different predicates depending on how the reader installed
the tool. This repository already learned that in 0.26.0 (`suites/__init__.py`: a probe of
`results/` "answers differently in a checkout and in a wheel, and it fails toward *measured*").
`test_adoption_does_not_depend_on_an_unpackaged_directory` is the guard against repeating it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provael.suites import keepout_zones as kz
from provael.suites.keepout_zones import (
    CALIBRATED_ZONES,
    CALIBRATION_DIR,
    WITHHELD_CALIBRATIONS,
    AdoptedCalibration,
    KeepOutZone,
)

REPO = Path(__file__).resolve().parents[1]
RESULTS_CALIB = REPO / "results" / "calibration"


def _packaged_artifacts() -> list[Path]:
    return sorted(CALIBRATION_DIR.glob("*.json"))


def test_the_packaged_directory_exists_and_ships() -> None:
    """A loader pointed at a missing directory would make every assertion below vacuous."""
    assert CALIBRATION_DIR.is_dir(), f"{CALIBRATION_DIR} is missing"
    assert CALIBRATION_DIR.is_relative_to(REPO / "src" / "provael"), (
        "the adopted calibrations must live inside the package, or a wheel and a checkout disagree "
        "about what predicate a published number was scored against"
    )


def test_every_packaged_fit_is_adopted_or_withheld_with_a_reason() -> None:
    """The drift guard. A committed fit may be refused; it may not be ignored."""
    artifacts = _packaged_artifacts()
    assert artifacts, "no packaged calibration artifacts — the loader has nothing to account for"
    accounted = set(CALIBRATED_ZONES) | set(WITHHELD_CALIBRATIONS)
    for path in artifacts:
        task = json.loads(path.read_text(encoding="utf-8"))["task"]
        assert task in accounted, (
            f"{path.name} declares task {task!r} and the loader neither adopted nor withheld it. "
            "A calibration that is silently dropped is the failure this test exists for."
        )
    for task, held in WITHHELD_CALIBRATIONS.items():
        assert held.reason.strip(), f"{task} is withheld with an empty reason"
        assert task not in CALIBRATED_ZONES, f"{task} is both adopted and withheld"


def test_every_committed_fit_reaches_the_packaged_directory() -> None:
    """`results/calibration/` is where fits are produced; nothing there may go unrepresented.

    This is the other half of the drift guard, and the half that catches the original bug: a GPU run
    commits ten artifacts, nobody promotes them, and the dict stays empty with no signal at all.
    Promotion is a file copy — see `calibrations/README.md` — so a fit that has not been promoted is
    a fit nobody looked at.
    """
    if not RESULTS_CALIB.is_dir():  # pragma: no cover - present in the repo, absent in a wheel
        pytest.skip("results/ is not packaged")
    produced = {
        json.loads(p.read_text(encoding="utf-8"))["task"]
        for p in RESULTS_CALIB.rglob("*.json")
    }
    accounted = set(CALIBRATED_ZONES) | set(WITHHELD_CALIBRATIONS)
    missing = sorted(produced - accounted)
    assert not missing, (
        f"{len(missing)} fit(s) under results/calibration/ are neither adopted nor withheld: "
        f"{missing}. Copy them into {CALIBRATION_DIR.relative_to(REPO)} so the loader can rule on "
        "them — refusing one is fine, losing it is not."
    )


def test_adoption_requires_a_measured_detection_rate(tmp_path: Path) -> None:
    """The gate. A fit that meets its benign target and catches nothing must NOT be adopted.

    This is the case the ten committed `libero_object` fits are in, and adopting them would install
    a predicate that scores a perfect ASR against something it can never flag.
    """
    zone = {"name": "z", "x": [0.0, 1.0], "y": [0.0, 1.0], "z": [0.0, 1.0]}
    base = {"policy": "smolvla", "suite": "libero", "keep_out_zones": [zone], "tool_version": "9.9"}
    cases = {
        "no_fit": {**base, "task": "t/no_fit"},
        "null_rate": {**base, "task": "t/null_rate", "spatial_fit": {"detection_rate": None}},
        "zero_rate": {
            **base, "task": "t/zero_rate",
            "spatial_fit": {"detection_rate": 0.0, "n_adversarial": 12, "face": "y-"},
        },
    }
    for name, doc in cases.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    adopted, withheld = kz._load_calibrations(tmp_path)
    assert adopted == {}, f"adopted {sorted(adopted)} — none of these carries evidence it can fire"
    assert set(withheld) == {"t/no_fit", "t/null_rate", "t/zero_rate"}
    assert "caught none" in withheld["t/zero_rate"].reason


def test_a_fit_that_catches_something_is_adopted_without_a_code_change(tmp_path: Path) -> None:
    """The converse, so the gate above cannot pass by refusing everything.

    Dropping in a file is the entire adoption step — that is the point of loading rather than
    hardcoding, and it is what makes the next GPU run a data change rather than a patch.
    """
    doc = {
        "policy": "smolvla", "suite": "libero", "task": "libero_object/0",
        "tool_version": "0.42.0",
        "keep_out_zones": [{"name": "calibrated", "x": [0.0, 1.0], "y": [0.0, 1.0], "z": [0.0, 1.0]}],
        "spatial_fit": {"detection_rate": 0.5, "n_adversarial": 12, "face": "x+"},
    }
    (tmp_path / "a.json").write_text(json.dumps(doc), encoding="utf-8")
    adopted, withheld = kz._load_calibrations(tmp_path)
    assert withheld == {}
    assert set(adopted) == {"libero_object/0"}
    got = adopted["libero_object/0"]
    assert (got.face, got.detection_rate, got.n_adversarial) == ("x+", 0.5, 12)
    assert got.zones and isinstance(got.zones[0], KeepOutZone)


def test_a_malformed_artifact_never_breaks_import(tmp_path: Path) -> None:
    """`import provael` runs this loader. A stray file must not take the CLI down."""
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "no-task.json").write_text('{"keep_out_zones": []}', encoding="utf-8")
    adopted, withheld = kz._load_calibrations(tmp_path)
    assert adopted == {} and withheld == {}


def test_adoption_does_not_depend_on_an_unpackaged_directory() -> None:
    """The 0.26.0 lesson, applied to the predicate itself.

    If the loader ever reads `results/`, a wheel and a checkout score the same run against different
    boundaries. Asserting the source of the dict is inside the package is the cheapest way to keep
    that from being reintroduced by a well-meaning "just read the real artifacts" change.
    """
    source = CALIBRATION_DIR.resolve()
    assert "results" not in source.parts, (
        f"calibrations load from {source}, which is outside the wheel — a pip install would score "
        "against a different predicate than a checkout"
    )


def test_zones_for_still_falls_back_while_nothing_is_adopted() -> None:
    """Behaviour is unchanged by this wiring: nothing is adopted, so nothing scores differently."""
    if CALIBRATED_ZONES:  # pragma: no cover - true once a real calibration is promoted
        pytest.skip("a calibration has been adopted; this test describes the pre-adoption state")
    with pytest.warns(kz.UncalibratedZoneWarning):
        assert kz.zones_for("libero_object/0") == [kz.DEFAULT_KEEP_OUT_ZONE]


def test_adopted_entries_still_require_their_evidence() -> None:
    """`AdoptedCalibration` must keep refusing to be built without a detection rate."""
    zone = KeepOutZone(name="z", x=(0.0, 1.0), y=(0.0, 1.0), z=(0.0, 1.0))
    with pytest.raises(TypeError):
        AdoptedCalibration(zones=[zone], tool_version="1.0", face="x+")  # type: ignore[call-arg]
