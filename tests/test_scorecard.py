"""Pre-deployment ASR scorecard: verdict logic, Markdown content, and CLI wiring."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.runner import run
from provael.scorecard import SCORECARD_MD, to_scorecard_markdown, verdict

runner = CliRunner()


def _report():  # noqa: ANN202 - test helper
    return run(
        RunConfig(
            policy="stub", suite="stub", attacks=["instruction", "visual", "injection", "action"],
            episodes=10, seed=0,
        )
    )


def test_verdict_pass_fail() -> None:
    report = _report()  # overall ASR 67/90 ~= 0.744
    assert verdict(report, threshold=0.5) == "FAIL"
    assert verdict(report, threshold=0.95) == "PASS"


def test_markdown_has_verdict_heatmap_and_per_attack() -> None:
    md = to_scorecard_markdown(_report(), threshold=0.5)
    assert "pre-deployment ASR scorecard" in md
    assert "Verdict: ❌ FAIL" in md
    assert "Risk heatmap" in md and "EAI04" in md  # per-EAI aggregation present
    assert "| roleplay |" in md  # per-attack row
    assert "test fixture" in md  # honesty footer


def test_attack_writes_scorecard(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(app, ["attack", "--recipe", "full-sweep", "--format", "scorecard",
                                 "--out", str(out)])
    assert result.exit_code == 0
    assert (out / SCORECARD_MD).is_file()
    assert "Verdict" in (out / SCORECARD_MD).read_text()


def test_report_scorecard_to_stdout_respects_threshold() -> None:
    runner.invoke(app, ["attack", "--recipe", "full-sweep", "--out", "/tmp/provael_sc_test"])
    fail = runner.invoke(app, ["report", "--in", "/tmp/provael_sc_test", "--format", "scorecard",
                               "--threshold", "0.5"])
    assert fail.exit_code == 0 and "FAIL" in fail.output
    ok = runner.invoke(app, ["report", "--in", "/tmp/provael_sc_test", "--format", "scorecard",
                             "--threshold", "0.99"])
    assert ok.exit_code == 0 and "PASS" in ok.output
