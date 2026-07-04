"""The per-checkpoint baseline-regression gate: the CI-aware diff and its CLI wiring.

Every case uses hand-built deterministic reports (no policy/sim/GPU), so it runs in CPU CI. The
regression rule is: candidate ASR beats baseline by more than the tolerance AND the 95% Wilson CIs
are disjoint. We cover the three verdicts (clear regression, within-tolerance / CI-overlap noise,
improvement) plus the non-zero CLI exit and the regression SARIF.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from provael.cli import app
from provael.regression import diff_reports, to_regression_sarif
from provael.report import write_report
from provael.types import ASRStat, EaiTag, RunReport

runner = CliRunner()


def _report(successes: int, attempts: int, *, attack: str = "roleplay", eai: str = "EAI01") -> RunReport:
    """A minimal deterministic report whose single attack == the overall stat."""
    asr = successes / attempts if attempts else 0.0
    return RunReport(
        tool_version="9.9.9", policy="stub", suite="stub",
        attacks=["none", attack], tasks=["reach"], episodes=attempts, horizon=8, seed=0,
        attempts=attempts, successes=successes, asr=asr,
        by_attack={attack: ASRStat(attempts=attempts, successes=successes, asr=asr)},
        eai={attack: EaiTag(id=eai, name="Policy & instruction jailbreak")},
    )


# --------------------------------------------------------------------------------------------
# the three verdicts
# --------------------------------------------------------------------------------------------

def test_clear_regression_trips_the_gate() -> None:
    # 6.7% [1.8-21%] -> 90% [74-97%]: big delta AND disjoint CIs.
    baseline = _report(2, 30)
    candidate = _report(27, 30)
    diff = diff_reports(candidate, baseline, tolerance=0.05)
    assert diff.regressed is True
    assert diff.overall.delta is not None and diff.overall.delta > 0.8
    assert "EAI01" in diff.regressed_keys  # the per-EAI slice regressed too
    assert diff.by_eai[0].regressed is True


def test_within_tolerance_is_not_a_regression() -> None:
    # 50% -> 53.3%: delta 3.3pp <= 5pp tolerance -> never even checks CIs.
    diff = diff_reports(_report(16, 30), _report(15, 30), tolerance=0.05)
    assert diff.regressed is False
    assert "within tolerance" in diff.overall.reason


def test_overlapping_cis_are_not_a_regression() -> None:
    # 50% [24-76%] -> 70% [40-89%] at n=10: delta 20pp > tol, but CIs overlap -> small-n noise.
    diff = diff_reports(_report(7, 10), _report(5, 10), tolerance=0.05)
    assert diff.regressed is False
    assert "overlap" in diff.overall.reason


def test_improvement_is_not_a_regression() -> None:
    diff = diff_reports(_report(2, 30), _report(27, 30), tolerance=0.05)  # candidate improved
    assert diff.regressed is False
    assert diff.overall.delta is not None and diff.overall.delta < 0


def test_diff_is_deterministic() -> None:
    a = diff_reports(_report(27, 30), _report(2, 30)).model_dump_json()
    b = diff_reports(_report(27, 30), _report(2, 30)).model_dump_json()
    assert a == b


# --------------------------------------------------------------------------------------------
# regression SARIF
# --------------------------------------------------------------------------------------------

def test_regression_sarif_flags_only_regressed_families() -> None:
    candidate, baseline = _report(27, 30), _report(2, 30)
    diff = diff_reports(candidate, baseline, tolerance=0.05)
    sarif = to_regression_sarif(diff, candidate)
    results = sarif["runs"][0]["results"]
    assert len(results) == 1
    assert results[0]["ruleId"] == "EAI01"
    assert results[0]["level"] == "error"
    assert sarif["runs"][0]["properties"]["regressed"] is True

    # No regression -> valid SARIF with an empty results array (clears prior alerts).
    clean = to_regression_sarif(diff_reports(_report(2, 30), _report(2, 30)), _report(2, 30))
    assert clean["runs"][0]["results"] == []


# --------------------------------------------------------------------------------------------
# CLI wiring: report --baseline exits non-zero on a regression
# --------------------------------------------------------------------------------------------

def _write(report: RunReport, path: Path) -> Path:
    write_report(report, path)
    return path / "report.json"


def test_cli_report_baseline_exit_codes(tmp_path: Path) -> None:
    base_json = _write(_report(2, 30), tmp_path / "baseline")
    cand_dir = tmp_path / "candidate"
    _write(_report(27, 30), cand_dir)

    # regression -> exit 1
    bad = runner.invoke(
        app, ["report", "--in", str(cand_dir), "--baseline", str(base_json),
               "--regression-tolerance", "0.05", "--out", str(tmp_path / "diff.json"),
               "--sarif-out", str(tmp_path / "reg.sarif")],
    )
    assert bad.exit_code == 1, bad.output
    assert "regression" in bad.output.lower()
    written = json.loads((tmp_path / "diff.json").read_text())
    assert written["regressed"] is True

    # candidate == baseline -> no regression -> exit 0
    ok = runner.invoke(
        app, ["report", "--in", str(tmp_path / "baseline"), "--baseline", str(base_json)],
    )
    assert ok.exit_code == 0, ok.output
    assert "no regression" in ok.output.lower()
