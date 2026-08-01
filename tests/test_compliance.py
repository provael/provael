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
from provael.eai import CATALOG
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
        # The functional-safety standards an accredited AI-safety inspection programme assesses
        # robot software against, plus the in-development Type-C standard for dynamically stable
        # robots. Provael is an input to all three and determines none of them.
        "iec-61508", "iso-13849", "iso-25785",
    }
    for entry in cr.entries:
        assert entry.provael_signal
        assert entry.evidence_refs
        assert entry.caveats == SCOPE  # honest-scope caveats per requirement
        assert entry.status in {"evidence-present", "gap"}


def test_gap_detection_uncalibrated() -> None:
    cr = to_compliance(_uncalibrated_report())
    gaps = {e.key for e in cr.entries if e.status == "gap"}
    # No benign control -> Art.15 gap; uncalibrated -> MEASURE gap; the two structural gaps; and
    # the three rows whose named on-point family (EAI04 / EAI09) did not run in this report.
    assert gaps == {
        "eu-ai-act:art15",
        "eu-ai-act:art72",
        "nist-ai-rmf:measure",
        "nist-ai-rmf:manage",
        "eu-machinery:cyber",
        "iso-10218-1:cyber",
        "nist-ai-100-2:privacy",
        # The three functional-safety rows name EAI04 (the action channel) as their on-point
        # evidence. This report never ran it, so they are gaps — which is the point of the gate:
        # a systematic-capability or PL-validation argument citing an ASR from a run that never
        # touched the action channel would be citing a measurement nobody made.
        "iec-61508:systematic-capability",
        "iso-13849:pl-validation",
        "iso-25785-1:dynamically-stable",
    }
    assert cr.summary == {"evidence-present": 11, "gap": 10}
    # Every gap explains itself; every present entry has no gap reason.
    for entry in cr.entries:
        if entry.status == "gap":
            assert entry.gap_reason
        else:
            assert entry.gap_reason is None


def test_gap_detection_calibrated() -> None:
    cr = to_compliance(_calibrated_report())
    gaps = {e.key for e in cr.entries if e.status == "gap"}
    # Calibrated + control present -> the two structural (longitudinal/observability) gaps, plus
    # the three rows that name EAI04 / EAI09 as their on-point evidence. This report exercises
    # EAI01/02/05 only, so those three assert a measurement no episode produced.
    assert gaps == {
        "eu-ai-act:art72",
        "nist-ai-rmf:manage",
        "eu-machinery:cyber",
        "iso-10218-1:cyber",
        "nist-ai-100-2:privacy",
        # Same EAI04 gate as the uncalibrated case: calibration does not conjure an action-channel
        # measurement. Both Annex I Part A points stay present — they are routing rows, satisfied
        # by adversarial evidence generally rather than by one named family.
        "iec-61508:systematic-capability",
        "iso-13849:pl-validation",
        "iso-25785-1:dynamically-stable",
    }
    by = _by_key(cr)
    assert by["eu-ai-act:art15"].status == "evidence-present"
    assert by["nist-ai-rmf:measure"].status == "evidence-present"
    assert by["eu-machinery:annex-i-part-a-6"].status == "evidence-present"
    assert cr.summary == {"evidence-present": 13, "gap": 8}
    # The gap names the missing family rather than the generic "no EAI-tagged attacks" reason.
    assert "EAI09" in (by["nist-ai-100-2:privacy"].gap_reason or "")
    # The measured evidence carries the calibrated control.
    assert cr.result.calibrated is True
    assert cr.result.benign_fpr == 0.0
    assert cr.result.target_fpr == 0.05


def test_rows_naming_a_family_are_present_once_that_family_actually_ran() -> None:
    """The `required_eai` gate is about the named family, not about EAI evidence in general.

    A row whose `provael_signal` asserts a specific measurement (EAI09 confidentiality leak, EAI04
    action-space integrity) must flip to evidence-present exactly when that family runs — otherwise
    the gate would just be a permanent gap.
    """
    covered = _base(
        calibrated=True,
        benign_fpr=0.0,
        eai={
            "roleplay": EaiTag(id="EAI01", name="Policy & instruction jailbreak"),
            "keepout_hijack": EaiTag(id="EAI04", name="Action-space integrity"),
            "membership_inference": EaiTag(id="EAI09", name="Confidentiality & data leakage"),
        },
    )
    by = _by_key(to_compliance(covered))
    for key in ("eu-machinery:cyber", "iso-10218-1:cyber", "nist-ai-100-2:privacy"):
        assert by[key].status == "evidence-present"
        assert by[key].gap_reason is None


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


def test_machinery_annex_i_part_a_points_are_pinned() -> None:
    """The two Annex I Part A points, cited by number rather than deferred.

    Point 5 is the standalone ML safety COMPONENT; point 6 is the machinery with an EMBEDDED
    self-evolving safety system, which is what an integrator shipping a whole robot places on the
    market. Both are pinned by literal so a future edit cannot quietly renumber them, and both are
    asserted distinct: Part B point 19 is the Article 25(3) sibling and is not interchangeable
    with either — substituting it would route a file down the wrong conformity procedure.
    """
    by = _by_key(to_compliance(_calibrated_report()))
    assert by["eu-machinery:annex-i-part-a"].control_id.endswith("Annex I Part A, point 5")
    assert by["eu-machinery:annex-i-part-a-6"].control_id.endswith("Annex I Part A, point 6")
    for key in ("eu-machinery:annex-i-part-a", "eu-machinery:annex-i-part-a-6"):
        assert "Article 25(2) via Article 6(1)" in by[key].control_id
        assert "CELEX 32023R1230" in by[key].provael_signal


def test_no_control_id_defers_its_clause_to_a_later_verification() -> None:
    """No requirement may ship a clause it has not verified. This prevents the CLASS.

    ``eu-machinery:annex-i-part-a`` shipped for several releases reading "[point reference pending
    verification]", and ``certify._crosswalk`` renders exactly that string as
    ``clause_verification: pending-verification`` in a document whose entire purpose is to be filed
    with a notified body. A placeholder is the right call at the moment of writing and the wrong
    thing to still be shipping a release later — pinning the individual string that was fixed would
    not have caught the next one, so the rule is the assertion.
    """
    offenders = [
        r.key for r in REQUIREMENTS
        if "pending verification" in r.control_id.lower() or "pending" in r.control_id.lower()
    ]
    assert not offenders, (
        f"{offenders} defer their clause reference to a later verification. Resolve the clause "
        f"against the primary text and cite it, or drop the row — a compliance artifact that "
        f"tells an assessor its own citation is unverified is worse than one that omits it."
    )


def test_working_draft_rows_are_indicative() -> None:
    """A standard that is not published yet can only ever be an anticipatory row.

    ISO 25785-1 is an ISO/TC 299 WG 12 Working Draft. Naming it is legitimate positioning — the
    evidence exists ahead of the standard — but a non-indicative row asserts a mapping onto a
    settled clause, and there is no settled clause to map onto. Written as a rule over every row
    so the next in-development standard inherits it.
    """
    for req in REQUIREMENTS:
        if "working draft" in req.control_id.lower() or "not yet published" in req.control_id.lower():
            assert req.indicative is True, (
                f"{req.key} cites an unpublished standard but is not marked indicative"
            )


def test_functional_safety_rows_disclaim_sil_and_performance_level() -> None:
    """IEC 61508 / ISO 13849 rows must refuse the determination they sit next to.

    These two are the rows most likely to be misread, because they are the standards a buyer's
    functional-safety assessor already works in. An ASR is an input to a systematic-capability or
    validation argument; it is not a SIL, not a PL, and not a determination of either. The
    disclaimer is load-bearing sales copy as much as engineering honesty, so it is pinned.
    """
    by = {r.key: r for r in REQUIREMENTS}
    for key in ("iec-61508:systematic-capability", "iso-13849:pl-validation"):
        signal = by[key].provael_signal
        assert "INPUT" in signal, f"{key} must state it is an input, not a determination"
        assert "no SIL" in signal and "makes no functional-safety claim" in signal, (
            f"{key} must disclaim SIL / Performance Level and any functional-safety claim"
        )
        assert by[key].indicative is True
        assert by[key].required_eai == ("EAI04",)
    assert "no Performance Level" in by["iso-13849:pl-validation"].provael_signal


def test_iso_25785_names_the_humanoid_attacks_and_its_own_unpublished_status() -> None:
    """The humanoid row must carry both halves of the honest claim.

    It names three real attacks, and it says the standard is unpublished and the suite is
    stub-validated with no real-model transfer claimed — the same label /for/humanoid-builders
    carries. Either half alone oversells: the attacks without the caveat read as a conformity
    claim, the caveat without the attacks reads as vapour.
    """
    req = {r.key: r for r in REQUIREMENTS}["iso-25785-1:dynamically-stable"]
    for attack in ("balance_spoof", "whole_body_hijack", "stride_freeze"):
        assert attack in req.provael_signal, f"the humanoid row does not name {attack}"
    assert "NOT PUBLISHED" in req.provael_signal
    assert "stub-validated" in req.provael_signal
    assert "no real-model transfer claimed" in req.provael_signal


def test_by_eai_aggregation_and_families() -> None:
    cr = to_compliance(_calibrated_report())
    rows = {row.eai_id: row for row in cr.result.by_eai}

    # ALL ten risks are emitted, not just the three this run exercised. A conformity reader
    # reconciles this table against a clause list, so a risk that is simply absent reads as one
    # with nothing to report — which is the opposite of "we do not test this".
    assert set(rows) == set(CATALOG)
    assert {r for r, row in rows.items() if row.measured} == {"EAI01", "EAI02", "EAI05"}

    assert rows["EAI01"].attempts == 10 and rows["EAI01"].successes == 8
    lo, hi = rows["EAI01"].ci95
    assert 0.0 <= lo <= rows["EAI01"].redirection_rate <= hi <= 1.0

    # An unmeasured risk must never look like a clean 0%: it carries no attempts and says why.
    assert rows["EAI04"].attempts == 0
    assert rows["EAI04"].status == "not exercised by this run"
    assert rows["EAI07"].status == "out of scope for simulation"
    assert rows["EAI10"].status == "process control — not attackable"
    for eai_id in ("EAI07", "EAI10"):
        assert rows[eai_id].coverage != "attacks-implemented"
        assert rows[eai_id].coverage_note, f"{eai_id} must explain its boundary"

    # `eai_ids_covered` keeps its narrower meaning: what THIS run exercised, not what exists.
    assert cr.result.eai_ids_covered == ["EAI01", "EAI02", "EAI05"]
    # Families resolved from the registry (baseline because `none` ran).
    assert cr.result.attack_families == ["baseline", "injection", "instruction", "visual"]


def test_uncovered_risks_are_named_in_the_markdown() -> None:
    """EAI07/EAI10 must appear in the rendered report, with the reason, not just the JSON."""
    md = to_compliance_markdown(_calibrated_report())
    assert "Risks Provael ships no attacks for" in md
    assert "EAI07" in md and "EAI10" in md
    assert "out of scope for simulation" in md
    assert "process control — not attackable" in md


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
