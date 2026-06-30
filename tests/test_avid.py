"""AVID export: record structure, determinism, and the `export` CLI command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from provael.avid import to_avid, to_avid_json
from provael.cli import app
from provael.config import RunConfig
from provael.runner import run

runner = CliRunner()


def _report():  # noqa: ANN202 - test helper
    return run(
        RunConfig(
            policy="stub", suite="stub", attacks=["instruction", "visual", "injection", "action"],
            episodes=10, seed=0,
        )
    )


def test_avid_record_structure() -> None:
    rec = to_avid(_report())
    assert rec["data_type"] == "AVID"
    assert rec["affects"]["artifacts"][0]["name"] == "stub"  # type: ignore[index]
    metrics = rec["metrics"][0]  # type: ignore[index]
    assert metrics["results"]["attempts"] == 90
    assert "Security" in rec["impact"]["avid"]["risk_domain"]  # type: ignore[index]


def test_avid_is_deterministic() -> None:
    assert to_avid_json(_report()) == to_avid_json(_report())


def test_export_cli_stdout_and_file(tmp_path) -> None:  # noqa: ANN001
    out = tmp_path / "run"
    runner.invoke(app, ["attack", "--recipe", "full-sweep", "--out", str(out)])
    res = runner.invoke(app, ["export", "--in", str(out), "--format", "avid"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["data_type"] == "AVID"
    target = tmp_path / "out.avid.json"
    assert runner.invoke(app, ["export", "--in", str(out), "--out", str(target)]).exit_code == 0
    assert target.is_file()
