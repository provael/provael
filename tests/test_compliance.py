"""Compliance-evidence export: schema validity, requirement mapping, gap detection, CLI wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from provael.calibration import calibrate_suite
from provael.cli import app
from provael.compliance import (
    REQUIREMENTS,
    ComplianceEntry,
    ComplianceReport,
    to_compliance,
    to_compliance_dict,
    to_compliance_json,
    to_compliance_markdown,
    write_compliance_json,
    write_compliance_markdown,
)
from provael.config import RunConfig
from provael.runner import run
from provael.types import ASRStat, CalibrationMeta, EaiTag, RunReport

runner = CliRunner()

#: The three honest-scope caveats every entry must carry.
SCOPE = ["adversarial-only", "evidence-not-certification", "behavioural-not-worst-case"]


def _base(**override: Any) -> RunReport:
    """A report with a baseline + one attack per EAI family (EAI01/02/05)."""
    fields: dict[str, Any] = {
        "tool_version": "9.9.9",
        "policy": "stub",
        "suite": "stub",
        "attacks": ["none", "roleplay", "decoy_object", "scene_text"],
        "tasks": ["reach"],
        "episodes": 10,
        "horizon": 8,
        "seed": 0,
        "attempts": 40,
        "successes": 11,
        "asr": 0.275,
        "by_attack": {
            "none": ASRStat(attempts=10, successes=0, asr=0.0),
            "roleplay": ASRStat(attempts=10, successes=8, asr=0.8),
            "decoy_object": ASRStat(attempts=10, successes=3, asr=0.3),
            "scene_text": ASRStat(attempts=10, successes=0, asr=0.0),
        },
        "by_task": {"reach": ASRStat(attempts=40, successes=11, asr=0.275)},
        "eai": {
            "roleplay": EaiTag(id="EAI01", name="Policy & instruction jailbreak"),
            "decoy_object": EaiTag(id="EAI02", name="Adversarial perception"),
            "scene_text": EaiTag(id="EAI05", name="Indirect / embodied prompt injection"),
        },
        "results": [],
    }
    fields.update(override)
    return RunReport(**fields)


def _uncalibrated_report() -> RunReport:
    """No calibration and no benign control (the `none` rate isn't surfaced)."""
    return _base(calibrated=False, benign_fpr=None)


def _calibrated_report() -> RunReport:
    """Calibrated predicate with a benign-FPR control of 0%."""
    return _base(
        calibrated=True,
        benign_fpr=0.0,
        calibration={
            "reach": CalibrationMeta(
                predicate="calibrated", kind="scalar", target_fpr=0.05, holdout_fpr=0.0,
                n_benign=20,
            )
        },
    )


def _by_key(cr: ComplianceReport) -> dict[str, ComplianceEntry]:
    return {entry.key: entry for entry in cr.entries}


def test_valid_json_round_trips_and_carries_identity() -> None:
    report = _calibrated_report()
    cr = to_compliance(report)
    # to_compliance_json parses and equals the dict view.
    assert json.loads(to_compliance_json(report)) == to_compliance_dict(report)
    assert cr.tool_version == "9.9.9"
    assert cr.policy == "stub" and cr.suite == "stub"
    assert "Evidence, not certification" in cr.disclaimer
    assert [c.id for c in cr.scope_caveats] == SCOPE
    assert all(c.text for c in cr.scope_caveats)


def test_requirement_mapping_is_complete_and_ordered() -> None:
    cr = to_compliance(_calibrated_report())
    # Every requirement in the catalog appears, in catalog order.
    assert [e.key for e in cr.entries] == [r.key for r in REQUIREMENTS]
    # All frameworks are represented (incl. the D2 additions: CRA + the ISO/IEC AI standards).
    assert {e.framework_id for e in cr.entries} == {
        "eu-ai-act", "eu-machinery", "eu-cra", "iso-10218", "nist", "iec-62443",
        "iso-iec-tr-5469", "iso-42001", "iso-23894",
    }
    for entry in cr.entries:
        assert entry.provael_signal
        assert entry.evidence_refs
        assert entry.caveats == SCOPE  # honest-scope caveats per requirement
        assert entry.status in {"evidence-present", "gap"}


def test_gap_detection_uncalibrated() -> None:
    cr = to_compliance(_uncalibrated_report())
    gaps = {e.key for e in cr.entries if e.status == "gap"}
    # No benign control -> Art.15 gap; uncalibrated -> MEASURE gap; the two structural gaps.
    assert gaps == {
        "eu-ai-act:art15",
        "eu-ai-act:art72",
        "nist-ai-rmf:measure",
        "nist-ai-rmf:manage",
    }
    assert cr.summary == {"evidence-present": 13, "gap": 4}
    # Every gap explains itself; every present entry has no gap reason.
    for entry in cr.entries:
        if entry.status == "gap":
            assert entry.gap_reason
        else:
            assert entry.gap_reason is None


def test_gap_detection_calibrated() -> None:
    cr = to_compliance(_calibrated_report())
    gaps = {e.key for e in cr.entries if e.status == "gap"}
    # Calibrated + control present -> only the two structural (longitudinal/observability) gaps.
    assert gaps == {"eu-ai-act:art72", "nist-ai-rmf:manage"}
    by = _by_key(cr)
    assert by["eu-ai-act:art15"].status == "evidence-present"
    assert by["nist-ai-rmf:measure"].status == "evidence-present"
    assert cr.summary == {"evidence-present": 15, "gap": 2}
    # The measured evidence carries the calibrated control.
    assert cr.result.calibrated is True
    assert cr.result.benign_fpr == 0.0
    assert cr.result.target_fpr == 0.05


def test_transfer_status_tier_is_run_level_and_uses_the_attestation_vocabulary() -> None:
    # D1: the stub run is honestly scaffolding; the markdown surfaces it so an auditor can't misread.
    cr = to_compliance(_calibrated_report())
    assert cr.result.transfer_status == "stub-validated-scaffolding"
    assert "transfer status" in to_compliance_markdown(_calibrated_report())
    # A real policy x real suite flips it to the measured-transfer label (same run-level derivation).
    real = to_compliance(_base(policy="smolvla", suite="libero"))
    assert real.result.transfer_status == "measured-real-transfer"


def test_cra_and_iso_ai_rows_are_present_and_indicative() -> None:
    by = _by_key(to_compliance(_calibrated_report()))
    for key in ("eu-cra:cyber", "iso-iec-tr-5469:ai-safety", "iso-42001:aims", "iso-23894:ai-risk"):
        assert by[key].indicative is True  # D2 rows are scope-flagged indicative
        assert by[key].status == "evidence-present"  # an EAI-tagged attack ran


def test_indicative_flags_match_catalog() -> None:
    by = _by_key(to_compliance(_calibrated_report()))
    assert by["eu-ai-act:art15"].indicative is False  # Article 15 is named explicitly
    assert by["eu-ai-act:art9"].indicative is True  # sub-clause indicative
    assert by["iec-62443:slv"].indicative is True


def test_by_eai_aggregation_and_families() -> None:
    cr = to_compliance(_calibrated_report())
    rows = {row.eai_id: row for row in cr.result.by_eai}
    assert set(rows) == {"EAI01", "EAI02", "EAI05"}
    assert rows["EAI01"].attempts == 10 and rows["EAI01"].successes == 8
    lo, hi = rows["EAI01"].ci95
    assert 0.0 <= lo <= rows["EAI01"].redirection_rate <= hi <= 1.0
    assert cr.result.eai_ids_covered == ["EAI01", "EAI02", "EAI05"]
    # Families resolved from the registry (baseline because `none` ran).
    assert cr.result.attack_families == ["baseline", "injection", "instruction", "visual"]


def test_markdown_renders_key_sections() -> None:
    md = to_compliance_markdown(_calibrated_report())
    assert md.startswith("# Provael — compliance evidence report")
    assert "Evidence, not certification" in md
    assert "## Measured evidence (this run)" in md
    assert "## Evidence summary" in md
    assert "✅ evidence-present" in md and "⚠️ gap" in md
    # Every mapped control and every honest-scope caveat is surfaced.
    for req in REQUIREMENTS:
        assert req.control_id in md
    for caveat in SCOPE:
        assert caveat in md


def test_compliance_is_deterministic(tmp_path: Path) -> None:
    a = write_compliance_json(_calibrated_report(), tmp_path / "a.json")
    b = write_compliance_json(_calibrated_report(), tmp_path / "b.json")
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")
    am = write_compliance_markdown(_calibrated_report(), tmp_path / "a.md")
    bm = write_compliance_markdown(_calibrated_report(), tmp_path / "b.md")
    assert am.read_text(encoding="utf-8") == bm.read_text(encoding="utf-8")


def test_compliance_from_real_calibrated_run() -> None:
    cals = calibrate_suite(
        "stub", "stub", None, list(range(20)), target_fpr=0.05, horizon=8, tool_version="test"
    )
    report = run(
        RunConfig(attacks=["none", "instruction", "visual", "injection"], episodes=6, seed=0), cals
    )
    cr = to_compliance(report)
    assert cr.calibrated is True
    assert cr.result.benign_fpr is not None  # the `none` control ran
    by = {e.key: e.status for e in cr.entries}
    assert by["eu-ai-act:art15"] == "evidence-present"
    assert by["nist-ai-rmf:measure"] == "evidence-present"
    assert by["eu-ai-act:art72"] == "gap"


def test_cli_report_compliance_json_to_file(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--episodes", "2", "--out", str(out)]).exit_code == 0
    target = tmp_path / "report.compliance.json"
    res = runner.invoke(
        app, ["report", "--in", str(out), "--format", "compliance", "--out", str(target)]
    )
    assert res.exit_code == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["entries"]
    assert {e["framework_id"] for e in data["entries"]} >= {"eu-ai-act", "nist"}


def test_cli_report_compliance_md_to_file(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--episodes", "2", "--out", str(out)]).exit_code == 0
    target = tmp_path / "report.compliance.md"
    res = runner.invoke(
        app, ["report", "--in", str(out), "--format", "compliance", "--out", str(target)]
    )
    assert res.exit_code == 0
    assert "compliance evidence report" in target.read_text(encoding="utf-8")


def test_cli_report_compliance_to_stdout(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--episodes", "2", "--out", str(out)]).exit_code == 0
    res = runner.invoke(app, ["report", "--in", str(out), "--format", "compliance"])
    assert res.exit_code == 0
    assert '"entries"' in res.output


def test_cli_attack_format_compliance_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "run"
    res = runner.invoke(
        app,
        ["attack", "--attacks", "instruction", "--episodes", "2", "--out", str(out),
         "--format", "compliance"],
    )
    assert res.exit_code == 0
    assert (out / "report.compliance.json").exists()
