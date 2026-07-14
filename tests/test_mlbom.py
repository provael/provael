"""CycloneDX ML-BOM export (E4): structure, honesty properties, determinism, CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.mlbom import ML_BOM_JSON, to_ml_bom, to_ml_bom_json
from provael.runner import run

runner = CliRunner()


def _report(attacks: list[str] | None = None):  # noqa: ANN202 - test helper
    return run(RunConfig(
        policy="stub", suite="stub",
        attacks=attacks or ["none", "instruction", "action"], episodes=10, seed=0,
    ))


def _model_component(bom: dict) -> dict:
    return next(c for c in bom["components"] if c["type"] == "machine-learning-model")


def test_ml_bom_is_cyclonedx_with_asr_metric_and_ci() -> None:
    bom = to_ml_bom(_report())
    assert bom["bomFormat"] == "CycloneDX" and bom["specVersion"] == "1.6"
    model = _model_component(bom)
    metrics = model["modelCard"]["quantitativeAnalysis"]["performanceMetrics"]
    asr = next(m for m in metrics if m["type"] == "attack-success-rate")
    assert "confidenceInterval" in asr  # the Wilson CI travels with the point estimate
    # The benign control ran -> its FPR is a metric too.
    assert any(m["type"] == "benign-false-positive-rate" for m in metrics)


def test_ml_bom_carries_the_transfer_tier_and_ai_act_pointer() -> None:
    bom = to_ml_bom(_report())
    meta_props = {p["name"]: p["value"] for p in bom["metadata"]["properties"]}
    assert meta_props["provael:transfer-status"] == "stub-validated-scaffolding"
    assert "Art. 11" in meta_props["provael:ai-act-art11"]
    model_props = {p["name"]: p["value"] for p in _model_component(bom)["properties"]}
    assert model_props["provael:transfer-status"] == "stub-validated-scaffolding"


def test_ml_bom_omits_benign_metric_without_a_control() -> None:
    bom = to_ml_bom(_report(attacks=["instruction"]))  # no `none` baseline
    metrics = _model_component(bom)["modelCard"]["quantitativeAnalysis"]["performanceMetrics"]
    assert all(m["type"] != "benign-false-positive-rate" for m in metrics)


def test_ml_bom_is_deterministic() -> None:
    assert to_ml_bom_json(_report()) == to_ml_bom_json(_report())


def test_ml_bom_cli_writes_file_and_stdout(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(
        app, ["attack", "--attacks", "instruction", "--episodes", "2", "--out", str(out),
              "--format", "mlbom"]
    ).exit_code == 0
    assert (out / ML_BOM_JSON).is_file()
    res = runner.invoke(app, ["report", "--in", str(out), "--format", "mlbom"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["bomFormat"] == "CycloneDX"
