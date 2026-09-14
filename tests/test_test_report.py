"""The clause-7.8-shaped test report: every field present, honest blanks, no wall clock."""

from __future__ import annotations

import json
from pathlib import Path

from provael.config import RunConfig
from provael.execution import ExecutionManifest
from provael.report import to_json
from provael.runner import run
from provael.test_report import (
    BLANK,
    EXECUTION_MANIFEST_JSON,
    load_manifest,
    to_test_report_markdown,
    write_test_report,
)
from provael.types import RunReport

_SECTIONS = [
    "## 1. Identification (7.8.2.1 a–e, j)",
    "## 2. Item under test (7.8.2.1 g, h)",
    "## 3. Method (7.8.2.1 f, k)",
    "## 4. Dates and location of the activity (7.8.2.1 c, i)",
    "## 5. Conditions (7.8.3.1 a)",
    "## 6. Results (7.8.2.1 m)",
    "## 7. Measurement uncertainty (7.8.3.1 c)",
    "## 8. Deviations, additions and exclusions (7.8.2.1 n)",
    "## 9. Statement of conformity (7.8.3.1 b)",
    "## 10. Scope of the results (7.8.2.1 l)",
    "## 11. External providers (7.8.2.1 p)",
    "## 12. Evidence state and verdict (7.8.3.1 e)",
    "## 13. Authorisation (7.8.2.1 o)",
    "## Annex A — clause map",
]


def _report() -> RunReport:
    return run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction", "control"], episodes=3, seed=0))


def test_every_clause_section_is_present_and_the_blanks_are_conspicuous() -> None:
    text = to_test_report_markdown(_report())
    for section in _SECTIONS:
        assert section in text, section
    assert "not an accredited laboratory" in text
    assert "No statement of conformity" in text
    assert text.count(BLANK) >= 5  # issuer, reviewer, customer, date of issue, authorisation x2
    assert "not recorded (no execution manifest)" in text


def test_roles_are_named_and_a_control_never_reads_as_an_attack() -> None:
    text = to_test_report_markdown(_report())
    assert "| `none` | benign-control | benign baseline — the floor |" in text
    assert "harmless-variation | control — enters neither the ASR nor the floor |" in text
    assert "adversarial-treatment | adversarial treatment |" in text


def test_it_is_deterministic_and_carries_no_wall_clock() -> None:
    import datetime as dt

    report = _report()
    a, b = to_test_report_markdown(report), to_test_report_markdown(report)
    assert a == b
    # No wall-clock value enters: the date of issue is the signatory's, and the only dates in the
    # document are the manifest's (absent here) and the clause map's verification dates.
    assert dt.date.today().isoformat() not in a
    assert "**Date of issue:** " + BLANK in a


def test_the_manifest_fills_provenance_and_the_deviations(tmp_path: Path) -> None:
    report = _report()
    manifest = ExecutionManifest(
        run_id="run-1", protocol_version="provael-redteam/v1", package_version=report.tool_version,
        report_schema_version=report.schema_version, policy="stub", suite="stub", seeds=1,
        horizon=report.horizon, attacks=list(report.attacks), evidence_state="fixture",
        release_verdict="not-releasable", report_digest="deadbeef", started_at="2026-09-14T10:00:00Z",
        ended_at="2026-09-14T10:05:00Z", hardware="arm64; cpu=8; gpu=unknown", operator="an operator",
        deviations=["two episodes replayed from a ledger"], skipped_checks=["verify-checkpoint"],
    )
    text = to_test_report_markdown(report, manifest)
    assert "run `run-1`" in text and "`deadbeef`" in text
    assert "`2026-09-14T10:00:00Z`" in text and "arm64; cpu=8; gpu=unknown" in text
    assert "an operator — *not an accredited laboratory*" in text
    assert "- two episodes replayed from a ledger" in text
    assert "`verify-checkpoint`" in text
    assert "**Reviewed by:** " + BLANK in text  # the field the manifest left empty stays blank
    # and the CLI-side loader finds it beside report.json
    out_dir = tmp_path / "run"
    out_dir.mkdir()
    (out_dir / "report.json").write_text(to_json(report), encoding="utf-8")
    assert load_manifest(out_dir) is None
    (out_dir / EXECUTION_MANIFEST_JSON).write_text(
        json.dumps(manifest.model_dump(mode="json")), encoding="utf-8"
    )
    loaded = load_manifest(out_dir)
    assert loaded is not None and loaded.run_id == "run-1"
    written = write_test_report(report, out_dir / "test-report.md", loaded)
    assert written.read_text(encoding="utf-8") == text
