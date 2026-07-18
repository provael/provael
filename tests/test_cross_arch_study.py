"""Cross-architecture transfer study: deterministic CPU-stub run, honest pending rows, CLI + writer.

All CPU, no GPU/network: the stub leg is measured deterministically; the real SmolVLA/π0 legs are
gated and must show as ``pending`` here. The study reuses the shipped runner + scoring, so the stub
numbers must match the canonical stub decomposition (the 47/70 canary).
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from provael.cli import app
from provael.studies.cross_arch import (
    ARCHITECTURES,
    BATTERY,
    FAMILIES,
    SUMMARY_JSON,
    build_study,
    merge_reports,
    run_arch,
    summary_json,
    write_study,
)

runner = CliRunner()


def _rows_by_arch(summary):  # noqa: ANN001, ANN202 - test helper
    out: dict[str, dict[str, object]] = {}
    for row in summary.rows:
        out.setdefault(row.architecture, {})[row.family] = row
    return out


def test_battery_is_the_three_shared_families_plus_control() -> None:
    assert BATTERY == ["none", "instruction", "visual", "injection"]
    assert FAMILIES == ["instruction", "visual", "injection"]
    assert {a.key for a in ARCHITECTURES} == {"stub", "smolvla", "pi0"}


def test_stub_measured_reals_pending_on_cpu() -> None:
    summary, reports = build_study()
    assert set(reports) == {"stub"}  # only the deterministic stub runs on CPU
    by = _rows_by_arch(summary)
    for family in FAMILIES:
        assert by["stub"][family].status == "measured"
        assert by["smolvla"][family].status == "pending"
        assert by["pi0"][family].status == "pending"
    # The pending reason names the gate honestly (no fabricated number).
    assert "PROVAEL_INTEGRATION=1" in by["pi0"]["instruction"].note
    assert "openpi" in by["pi0"]["instruction"].note


def test_measured_rows_carry_wilson_ci_and_benign_control() -> None:
    summary, _ = build_study()
    row = _rows_by_arch(summary)["stub"]["instruction"]
    assert row.asr is not None and row.ci95_low is not None and row.ci95_high is not None
    assert row.ci95_low <= row.asr <= row.ci95_high
    assert row.benign_fpr == 0.0  # the `none` control never trips on the stub
    assert row.matched_benign_fpr == 0.0


def test_stub_numbers_match_the_canonical_decomposition() -> None:
    # Reuses the shipped runner+scoring, so the stub battery must reproduce the 47/70 canary split:
    # instruction 21/30, visual 14/20, injection 12/20 (sum 47/70).
    by = _rows_by_arch(build_study()[0])["stub"]
    assert (by["instruction"].successes, by["instruction"].attempts) == (21, 30)
    assert (by["visual"].successes, by["visual"].attempts) == (14, 20)
    assert (by["injection"].successes, by["injection"].attempts) == (12, 20)
    total = sum(by[f].successes for f in FAMILIES), sum(by[f].attempts for f in FAMILIES)
    assert total == (47, 70)


def test_summary_is_byte_deterministic() -> None:
    assert summary_json(build_study()[0]) == summary_json(build_study()[0])
    assert summary_json(build_study(seed=0)[0]) != summary_json(build_study(seed=1)[0])


def test_real_arches_are_gated_off_here() -> None:
    # Without PROVAEL_INTEGRATION + the extras, run_arch returns None for the real backends.
    reals = [a for a in ARCHITECTURES if a.extra is not None]
    for arch in reals:
        assert run_arch(arch) is None
    stub = next(a for a in ARCHITECTURES if a.key == "stub")
    assert run_arch(stub) is not None  # the stub always runs


def test_merge_reports_combines_and_marks_missing_pending() -> None:
    _, reports = build_study()  # {"stub": <report>}
    merged = merge_reports(reports)
    by = _rows_by_arch(merged)
    assert by["stub"]["instruction"].status == "measured"
    assert by["smolvla"]["instruction"].status == "pending"  # no report supplied -> pending


def test_write_study_emits_deterministic_summary_and_report(tmp_path: Path) -> None:
    summary, reports = build_study()
    out = write_study(summary, reports, tmp_path / "study")
    summary_path = out / SUMMARY_JSON
    assert summary_path.is_file()
    doc = json.loads(summary_path.read_text())
    assert doc["format"] == "provael-cross-arch-study/v1"
    assert (out / "stub" / "report.json").is_file()  # the measured stub RunReport
    # Deterministic: re-writing yields identical summary bytes.
    out2 = write_study(*build_study(), tmp_path / "study2")
    assert (out2 / SUMMARY_JSON).read_bytes() == summary_path.read_bytes()


def test_cli_study_cross_arch_prints_table() -> None:
    result = runner.invoke(app, ["study", "cross-arch"])
    assert result.exit_code == 0
    assert "Cross-architecture transfer" in result.output
    assert "pending" in result.output  # the real legs are honestly pending


def test_cli_study_cross_arch_writes_when_out_given(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(app, ["study", "cross-arch", "--out", str(out)])
    assert result.exit_code == 0
    assert (out / SUMMARY_JSON).is_file()
