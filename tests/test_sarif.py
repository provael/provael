"""SARIF 2.1.0 export: structure, ASR->level mapping, determinism, and CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.runner import run
from provael.sarif import level_for_asr, to_sarif, to_sarif_json, write_sarif
from provael.types import ASRStat, EaiTag, RunReport

runner = CliRunner()


def _synthetic_report() -> RunReport:
    """A report with one attack per severity band (error / warning / note) + baseline."""
    return RunReport(
        tool_version="9.9.9",
        policy="stub",
        suite="stub",
        attacks=["none", "roleplay", "decoy_object", "scene_text"],
        tasks=["reach"],
        episodes=10,
        horizon=8,
        seed=0,
        attempts=40,
        successes=11,
        asr=0.275,
        by_attack={
            "none": ASRStat(attempts=10, successes=0, asr=0.0),
            "roleplay": ASRStat(attempts=10, successes=8, asr=0.8),  # -> error
            "decoy_object": ASRStat(attempts=10, successes=3, asr=0.3),  # -> warning
            "scene_text": ASRStat(attempts=10, successes=0, asr=0.0),  # -> note
        },
        by_task={"reach": ASRStat(attempts=40, successes=11, asr=0.275)},
        eai={
            "roleplay": EaiTag(id="EAI01", name="Policy & instruction jailbreak"),
            "decoy_object": EaiTag(id="EAI02", name="Adversarial perception"),
            "scene_text": EaiTag(id="EAI05", name="Indirect / embodied prompt injection"),
        },
        results=[],
    )


def _results_by_attack(sarif: dict[str, object]) -> dict[str, dict[str, object]]:
    run0 = sarif["runs"][0]  # type: ignore[index]
    return {r["properties"]["attack"]: r for r in run0["results"]}  # type: ignore[index,union-attr]


def test_level_for_asr_bands() -> None:
    assert level_for_asr(1.0) == "error"
    assert level_for_asr(0.5) == "error"
    assert level_for_asr(0.49) == "warning"
    assert level_for_asr(0.0001) == "warning"
    assert level_for_asr(0.0) == "note"


def test_sarif_is_valid_json_and_has_tool_identity() -> None:
    sarif = to_sarif(_synthetic_report())
    # Round-trips through JSON unchanged.
    assert json.loads(to_sarif_json(_synthetic_report())) == sarif
    assert sarif["version"] == "2.1.0"
    assert "$schema" in sarif
    driver = sarif["runs"][0]["tool"]["driver"]  # type: ignore[index]
    assert driver["name"] == "Provael"
    assert driver["version"] == "9.9.9"


def test_sarif_rules_are_the_eai_ids_used() -> None:
    sarif = to_sarif(_synthetic_report())
    rules = sarif["runs"][0]["tool"]["driver"]["rules"]  # type: ignore[index]
    ids = sorted(r["id"] for r in rules)
    assert ids == ["EAI01", "EAI02", "EAI05"]
    for rule in rules:
        assert rule["name"]
        assert rule["shortDescription"]["text"]
        assert "docs/TOP10.md#" in rule["helpUri"]


def test_sarif_levels_track_asr_and_baseline_excluded() -> None:
    sarif = to_sarif(_synthetic_report())
    results = _results_by_attack(sarif)
    # Baseline control has no EAI id -> no result row.
    assert "none" not in results
    assert results["roleplay"]["level"] == "error"
    assert results["decoy_object"]["level"] == "warning"
    assert results["scene_text"]["level"] == "note"


def test_sarif_result_ruleid_index_message_and_fingerprint() -> None:
    sarif = to_sarif(_synthetic_report())
    run0 = sarif["runs"][0]  # type: ignore[index]
    rules = run0["tool"]["driver"]["rules"]
    results = _results_by_attack(sarif)

    rp = results["roleplay"]
    assert rp["ruleId"] == "EAI01"
    # ruleIndex must point back at the matching rule.
    assert rules[rp["ruleIndex"]]["id"] == "EAI01"
    assert rp["message"]["text"] == "roleplay: ASR 80.0% (8/10) on stub/stub"
    fp = rp["partialFingerprints"]["provaelAttack/v1"]
    assert isinstance(fp, str) and len(fp) == 16


def test_sarif_is_deterministic(tmp_path: Path) -> None:
    a = write_sarif(_synthetic_report(), tmp_path / "a.sarif")
    b = write_sarif(_synthetic_report(), tmp_path / "b.sarif")
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_sarif_from_real_run_tags_three_families() -> None:
    report = run(
        RunConfig(attacks=["none", "instruction", "visual", "injection"], episodes=2, seed=0)
    )
    sarif = to_sarif(report)
    ids = sorted({r["ruleId"] for r in sarif["runs"][0]["results"]})  # type: ignore[index]
    assert ids == ["EAI01", "EAI02", "EAI05"]
    attacks = set(_results_by_attack(sarif))
    assert "none" not in attacks
    assert {"roleplay", "patch", "scene_text"} <= attacks


def test_cli_report_format_sarif_to_file(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--episodes", "2", "--out", str(out)]).exit_code == 0
    sarif = tmp_path / "report.sarif"
    res = runner.invoke(app, ["report", "--in", str(out), "--format", "sarif", "--out", str(sarif)])
    assert res.exit_code == 0
    data = json.loads(sarif.read_text(encoding="utf-8"))
    assert data["version"] == "2.1.0"


def test_cli_report_format_sarif_to_stdout(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--episodes", "2", "--out", str(out)]).exit_code == 0
    res = runner.invoke(app, ["report", "--in", str(out), "--format", "sarif"])
    assert res.exit_code == 0
    assert '"version": "2.1.0"' in res.output


def test_cli_attack_sarif_out_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "run"
    sarif = tmp_path / "custom.sarif"
    res = runner.invoke(
        app,
        ["attack", "--attacks", "instruction", "--episodes", "2", "--out", str(out),
         "--sarif-out", str(sarif)],
    )
    assert res.exit_code == 0
    assert sarif.exists()
    data = json.loads(sarif.read_text(encoding="utf-8"))
    assert data["runs"][0]["tool"]["driver"]["name"] == "Provael"


def test_cli_attack_format_sarif_writes_into_out_dir(tmp_path: Path) -> None:
    out = tmp_path / "run"
    res = runner.invoke(
        app,
        ["attack", "--attacks", "instruction", "--episodes", "2", "--out", str(out),
         "--format", "sarif"],
    )
    assert res.exit_code == 0
    assert (out / "report.sarif").exists()
