"""OSCAL assessment-results export: structure, determinism, and CLI wiring."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.oscal import to_oscal, to_oscal_json
from provael.runner import run

runner = CliRunner()


def _report():  # noqa: ANN202 - test helper
    return run(
        RunConfig(
            policy="stub", suite="stub", attacks=["instruction", "visual", "injection", "action"],
            episodes=10, seed=0,
        )
    )


def test_oscal_structure() -> None:
    doc = to_oscal(_report())
    ar = doc["assessment-results"]
    assert isinstance(ar, dict)
    result = ar["results"][0]  # type: ignore[index]
    assert len(result["observations"]) == 9  # one per attack
    assert len(result["risks"]) == 4  # EAI01/02/04/05
    assert result["findings"][0]["title"] == "Adversarial Attack Success Rate"
    assert ar["metadata"]["oscal-version"] == "1.1.2"  # type: ignore[index]


def test_oscal_finding_carries_transfer_status_prop() -> None:
    # D1: the run-level honesty tier surfaces as an OSCAL prop so a GRC consumer can't misread
    # stub scaffolding as a real-transfer measurement.
    doc = to_oscal(_report())
    finding = doc["assessment-results"]["results"][0]["findings"][0]  # type: ignore[index]
    props = {p["name"]: p["value"] for p in finding["props"]}
    assert props["transfer-status"] == "stub-validated-scaffolding"


def test_oscal_is_deterministic() -> None:
    # Stable uuid5 ids + no clock => byte-identical for a deterministic run.
    assert to_oscal_json(_report()) == to_oscal_json(_report())


def test_oscal_cli_stdout_and_file(tmp_path) -> None:  # noqa: ANN001
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--recipe", "full-sweep", "--format", "oscal",
                               "--out", str(out)]).exit_code == 0
    assert (out / "report.oscal.json").is_file()
    res = runner.invoke(app, ["report", "--in", str(out), "--format", "oscal"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["assessment-results"]["results"]  # valid JSON to stdout
