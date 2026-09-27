# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""CycloneDX ML-BOM export (E4): structure, honesty properties, determinism, CLI wiring.

The BOM is also validated against the official CycloneDX 1.6 JSON schema, vendored unmodified in
``tests/fixtures/cyclonedx-1.6`` (see its README), because a schema-invalid BOM is rejected by the
consumers it exists for: Dependency-Track refused the numeric metric values this exporter once
emitted, and nothing here noticed.
"""

from __future__ import annotations

import copy
import json
import re
import uuid
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7
from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.mlbom import (
    ML_BOM_JSON,
    SERIAL_NAMESPACE,
    serial_number,
    to_ml_bom,
    to_ml_bom_json,
)
from provael.report import load_report
from provael.runner import run

runner = CliRunner()


def _report(attacks: list[str] | None = None):  # noqa: ANN202 - test helper
    return run(RunConfig(
        policy="stub", suite="stub",
        attacks=attacks or ["none", "instruction", "action"], episodes=10, seed=0,
    ))


def _model_component(bom: dict) -> dict:
    component = bom["metadata"]["component"]
    assert component["type"] == "machine-learning-model"
    return component


SCHEMA_DIR = Path(__file__).resolve().parent / "fixtures" / "cyclonedx-1.6"
REPO = Path(__file__).resolve().parent.parent


def _validator() -> Any:
    """A draft-07 validator for the CycloneDX 1.6 BOM schema, with its two referenced schemas."""
    schemas = {
        name: json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        for name in ("bom-1.6.schema.json", "spdx.schema.json", "jsf-0.82.schema.json")
    }
    registry: Registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s, default_specification=DRAFT7)) for s in schemas.values()
    )
    return jsonschema.Draft7Validator(
        schemas["bom-1.6.schema.json"],
        registry=registry,
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )


def _schema_errors(bom: dict) -> list[str]:
    return [f"{list(e.absolute_path)}: {e.message}" for e in _validator().iter_errors(bom)]


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


@pytest.mark.parametrize(
    "report",
    [
        pytest.param(lambda: _report(), id="stub-with-benign-control"),
        pytest.param(lambda: _report(attacks=["instruction"]), id="stub-no-control"),
        pytest.param(
            lambda: load_report(REPO / "results" / "smolvla_libero_object" / "report.json"),
            id="committed-real-policy-run",
        ),
    ],
)
def test_ml_bom_validates_against_the_cyclonedx_1_6_schema(report: Any) -> None:
    assert _schema_errors(to_ml_bom(report())) == []


def test_the_schema_check_is_live() -> None:
    """Guard the guard: the validator must reject the exact defect ``_metric_str`` exists for."""
    bom = to_ml_bom(_report())
    broken = copy.deepcopy(bom)
    metrics = broken["metadata"]["component"]["modelCard"]["quantitativeAnalysis"]
    metrics["performanceMetrics"][0]["value"] = 0.9  # a JSON number, where 1.6 requires a string
    assert _schema_errors(broken), "a numeric metric value passed the schema check"
    broken = copy.deepcopy(bom)
    broken["serialNumber"] = "not-a-uuid"
    assert _schema_errors(broken), "a malformed serialNumber passed the schema check"


def test_the_serial_is_a_deterministic_uuid5_of_the_report() -> None:
    bom = to_ml_bom(_report())
    serial = bom["serialNumber"]
    assert re.fullmatch(r"urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", serial)
    assert serial == serial_number(_report()), "the same report must get the same serial"
    assert serial != to_ml_bom(_report(attacks=["instruction"]))["serialNumber"]
    # Fixed forever: a new namespace would re-serial every BOM emitted for an unchanged report.
    expected_namespace = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/provael/provael#ml-bom")
    assert expected_namespace == SERIAL_NAMESPACE


def test_the_bom_describes_the_policy_and_names_provael_as_the_tool() -> None:
    """``metadata.component`` is what the BOM describes: the policy under test, never the tool."""
    report = _report()
    bom = to_ml_bom(report)
    subject = bom["metadata"]["component"]
    assert subject["name"] == report.policy and subject["bom-ref"] == f"policy:{report.policy}"
    tools = bom["metadata"]["tools"]["components"]
    assert tools == [{"type": "application", "name": "provael", "version": report.tool_version}]
    refs: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "bom-ref" in node:
                refs.append(node["bom-ref"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(bom)
    assert len(refs) == len(set(refs)), f"bom-refs must be unique across the BOM: {refs}"

