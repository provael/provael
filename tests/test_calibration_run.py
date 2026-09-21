# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""End-to-end calibration on the stub: target FPR, calibrated ASR/CI, fallback, determinism."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael import __version__
from provael.attest import _CALIBRATION_META_FIELDS_ADDED_IN, _report_digest, report_projection
from provael.calibration import (
    Calibration,
    SeedLeakageError,
    binding_status,
    calibrate_one,
    calibrate_suite,
    to_json,
)
from provael.cli import app
from provael.config import RunConfig
from provael.report import load_report
from provael.report import to_markdown as report_markdown
from provael.runner import run

runner = CliRunner()
SEEDS = list(range(20))
#: Rich must not colour the CliRunner's captured output, or substring asserts meet ANSI codes.
_PLAIN = {"NO_COLOR": "1", "TERM": "dumb", "FORCE_COLOR": "", "COLUMNS": "200"}


def _stub_calibration() -> dict:
    return calibrate_suite(
        "stub", "stub", None, SEEDS, target_fpr=0.05, horizon=8, tool_version=__version__
    )


def test_stub_calibration_meets_target_on_tuning_and_eval_splits() -> None:
    # (a) After calibration, the tuning-split FPR is <= target (it was chosen to be), and on the
    # default three-way fit the eval split — never consulted by the choice — is measured too.
    cals = _stub_calibration()
    assert set(cals) == {"reach"}
    cal = cals["reach"]
    assert cal.kind == "scalar"
    assert cal.benign_fpr <= 0.05
    assert cal.split == "three-way"
    assert len(cal.fit_seeds) + len(cal.holdout_seeds) + len(cal.eval_seeds) == cal.n_benign == 20
    assert cal.eval_seeds and not (set(cal.eval_seeds) & (set(cal.fit_seeds) | set(cal.holdout_seeds)))
    assert cal.eval_fpr is not None and cal.binding is not None
    assert cal.binding.valid() == (True, "bound calibration: disjoint splits, eval FPR within target")
    # one applied-seed slot per benign rollout, eval included (the stub does not seed: None each)
    assert len(cal.policy_seeds) == cal.n_benign


def test_stub_calibration_artifact_is_deterministic() -> None:
    # (d) Same seeds -> byte-identical artifact.
    a = _stub_calibration()["reach"]
    b = _stub_calibration()["reach"]
    assert to_json(a) == to_json(b)


def test_calibrated_run_reports_redirection_rate_and_control() -> None:
    # (b) The calibrated predicate flags every language redirection; the benign baseline
    # (none) is the 0% control, recorded as benign_fpr.
    cals = _stub_calibration()
    config = RunConfig(
        policy="stub", suite="stub", attacks=["none", "instruction"], episodes=10, seed=0
    )
    report = run(config, cals)
    assert report.calibrated is True
    assert report.by_attack["roleplay"].asr == 1.0  # danger 0.8 > calibrated threshold 0.0
    assert report.by_attack["none"].asr == 0.0  # benign control
    assert report.benign_fpr == 0.0
    meta = report.calibration["reach"]
    assert meta.predicate == "calibrated" and meta.kind == "scalar"
    assert meta.holdout_fpr is not None and meta.holdout_fpr <= 0.05


def test_default_run_is_unchanged_when_no_calibration() -> None:
    # (c) Fallback: without calibration the default per-seed-threshold predicate is used,
    # so the historical stub ASR is preserved and calibrated=False.
    config = RunConfig(
        policy="stub", suite="stub", attacks=["none", "instruction"], episodes=10, seed=0
    )
    default = run(config)
    assert default.calibrated is False
    assert default.calibration == {}
    assert default.by_attack["roleplay"].successes == 8  # uncalibrated per-seed thresholds
    # An empty calibration map is also a no-op (falls back to default).
    assert run(config, {}).calibrated is False


def test_cli_calibrate_then_attack_with_calib(tmp_path: Path) -> None:
    calib = tmp_path / "calib"
    res = runner.invoke(
        app,
        ["calibrate", "--policy", "stub", "--suite", "stub", "--seeds", "20",
         "--target-fpr", "0.05", "--out", str(calib)],
    )
    assert res.exit_code == 0
    assert (calib / "stub__stub__reach.json").exists()

    out = tmp_path / "run"
    res2 = runner.invoke(
        app,
        ["attack", "--policy", "stub", "--suite", "stub", "--attacks", "none,instruction",
         "--episodes", "10", "--seed", "0", "--calib", str(calib), "--out", str(out)],
    )
    assert res2.exit_code == 0
    report = load_report(out)
    assert report.calibrated is True
    assert report.benign_fpr == 0.0
    assert report.by_attack["roleplay"].asr == 1.0


def test_cli_attack_warns_when_calib_dir_has_no_match(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "run"
    res = runner.invoke(
        app,
        ["attack", "--policy", "stub", "--suite", "stub", "--attacks", "instruction",
         "--episodes", "5", "--calib", str(empty), "--out", str(out)],
    )
    assert res.exit_code == 0  # no match -> falls back to default, does not error
    assert load_report(out).calibrated is False


# --------------------------------------------------------------------------- #
# the three-way split, wired (R2 P0, 21 Sep 2026): eval split, binding, invalidation, no re-fit
# --------------------------------------------------------------------------- #


def test_the_calibrated_run_reports_the_split_the_eval_fpr_and_a_valid_binding() -> None:
    """Schema 7: a bound predicate and a tuned one no longer look the same in `report.json`."""
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4, seed=0),
        _stub_calibration(),
    )
    assert report.schema_version == 7
    meta = report.calibration["reach"]
    assert meta.split == "three-way"
    assert meta.eval_fpr is not None and meta.eval_fpr <= 0.05
    assert meta.binding == "valid"
    assert "calibrated and bound" in report_markdown(report)
    assert "eval split of a three-way fit" in report_markdown(report)


def test_two_way_is_still_available_and_carries_no_binding() -> None:
    cals = calibrate_suite(
        "stub", "stub", None, SEEDS, target_fpr=0.05, horizon=8, tool_version=__version__,
        split="two-way",
    )
    cal = cals["reach"]
    assert cal.split == "two-way" and cal.eval_seeds == [] and cal.eval_fpr is None
    assert cal.binding is None
    assert len(cal.fit_seeds) + len(cal.holdout_seeds) == cal.n_benign == 20
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4, seed=0),
        cals,
    )
    meta = report.calibration["reach"]
    assert meta.split == "two-way" and meta.eval_fpr is None and meta.binding is None
    text = report_markdown(report)
    assert "tuning figure" in text and "two-way fit" in text
    assert "calibrated and bound" not in text


def test_three_way_needs_three_seeds_and_says_so() -> None:
    with pytest.raises(ValueError, match="at least 3 seeds"):
        calibrate_suite(
            "stub", "stub", None, [0, 1], target_fpr=0.05, horizon=8, tool_version=__version__
        )


def test_an_eval_split_failure_is_recorded_as_an_invalid_binding_not_refitted() -> None:
    """The eval FPR may exceed the target. The artifact must then keep the threshold the tuning
    split chose (re-fitting on the eval seeds would turn them into tuning data) and carry an
    invalid binding; a run under it says the predicate is applied but not bound."""
    cal = _stub_calibration()["reach"]
    failed = cal.model_copy(update={"eval_fpr": 0.5})
    assert failed.binding is not None
    failed.binding.achieved_eval_fpr = 0.5
    ok, reason = failed.binding.valid()
    assert ok is False and "exceeds target" in reason
    assert failed.threshold == cal.threshold, "the threshold is never moved to satisfy the eval split"
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4, seed=0),
        {"reach": failed},
    )
    assert report.calibrated is True  # still applied
    meta = report.calibration["reach"]
    assert meta.binding is not None and meta.binding.startswith("invalid: ")
    assert "exceeds target" in meta.binding
    assert "binding INVALID for this run" in report_markdown(report)


def test_a_checkpoint_change_invalidates_the_binding_but_the_predicate_still_applies() -> None:
    cal = _stub_calibration()["reach"]
    assert cal.binding is not None and cal.binding.model is None  # fitted on the adapter default
    status = binding_status(cal, policy="stub", suite="stub", task="reach", model="other-ckpt")
    assert status is not None and status.startswith("invalid: bound to checkpoint")
    assert binding_status(cal, policy="stub", suite="stub", task="reach", model=None) == "valid"
    assert binding_status(cal, policy="stub", suite="stub", task="grasp", model=None) == (
        "invalid: bound to stub/stub/reach, applied to stub/stub/grasp"
    )
    moved = cal.model_copy(deep=True)
    assert moved.binding is not None
    moved.binding.oracle_version = "suite-unsafe-predicate/v0"
    status = binding_status(moved, policy="stub", suite="stub", task="reach", model=None)
    assert status is not None and status.startswith("invalid: eval FPR measured under oracle")


def test_an_artifact_written_before_the_split_field_loads_as_two_way() -> None:
    """Every calibration committed before this version has no `split`, `eval_*` or `binding`
    key; it must load as exactly what it is — a two-way fit — not fail or masquerade as bound."""
    cal = _stub_calibration()["reach"]
    old = json.loads(to_json(cal))
    for key in ("split", "eval_seeds", "eval_fpr", "binding"):
        old.pop(key)
    loaded = Calibration.model_validate(old)
    assert loaded.split == "two-way" and loaded.binding is None and loaded.eval_fpr is None
    assert binding_status(loaded, policy="stub", suite="stub", task="reach", model=None) is None


def test_eval_seeds_that_overlap_the_fit_are_refused() -> None:
    from provael.policies.registry import make_policy
    from provael.suites import make_suite

    policy, suite = make_policy("stub"), make_suite("stub")
    policy.load()
    with pytest.raises(SeedLeakageError, match="overlap"):
        calibrate_one(
            policy, suite, policy_name="stub", suite_name="stub", task="reach",
            fit_seeds=[0, 1, 2], holdout_seeds=[3, 4], eval_seeds=[4, 5],
            target_fpr=0.05, horizon=8, tool_version=__version__,
        )


def test_the_new_calibration_meta_fields_are_stripped_below_schema_7() -> None:
    """Registered in the projection, or a schema-6 report with a calibrated task would digest to
    different bytes under this build and its attestation would read TAMPERED."""
    assert _CALIBRATION_META_FIELDS_ADDED_IN[7] == ("split", "eval_fpr", "binding")
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"], episodes=4, seed=0),
        _stub_calibration(),
    )
    older = report.model_copy(update={"schema_version": 6})
    projected = report_projection(older)["calibration"]["reach"]
    assert not {"split", "eval_fpr", "binding"} & set(projected)
    stripped_meta = older.calibration["reach"].model_copy(
        update={"split": None, "eval_fpr": None, "binding": None}
    )
    without = older.model_copy(update={"calibration": {"reach": stripped_meta}})
    assert _report_digest(older) == _report_digest(without)
    assert {"split", "eval_fpr", "binding"} <= set(report_projection(report)["calibration"]["reach"])


def test_cli_calibrate_prints_the_eval_column_and_two_way_says_none(tmp_path: Path) -> None:
    three = runner.invoke(
        app, ["calibrate", "--seeds", "9", "--out", str(tmp_path / "three")], env=_PLAIN
    )
    assert three.exit_code == 0, three.output
    assert "eval FPR" in three.output
    two = runner.invoke(
        app, ["calibrate", "--seeds", "9", "--split", "two-way", "--out", str(tmp_path / "two")],
        env=_PLAIN,
    )
    assert two.exit_code == 0, two.output
    assert "none (two-way)" in two.output
    written = json.loads((tmp_path / "two" / "stub__stub__reach.json").read_text())
    assert written["split"] == "two-way" and written["binding"] is None
