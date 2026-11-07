# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The GPU-extras audit fails on what its reviewed allow-list does not account for.

That lane could not fail until November 2026: `continue-on-error` kept it green while it printed 13
advisories in torch, transformers, diffusers and friends, so a new one never stopped a merge. These
tests pin the checker it now hands its JSON to, and the wiring that makes the checker the verdict.

No test touches the network. Every report is a fixture and every date is passed in.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tomllib
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "check_audit_allowlist", REPO / "scripts" / "check_audit_allowlist.py"
)
assert _spec and _spec.loader
caa = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = caa  # dataclasses resolve their module through sys.modules
_spec.loader.exec_module(caa)

FIXTURES = REPO / "tests" / "fixtures" / "pip_audit"
CLEAN = FIXTURES / "clean.json"
NEW_ADVISORY = FIXTURES / "new_advisory.json"
ALLOWLIST = FIXTURES / "allowlist.toml"
EXPIRED = FIXTURES / "expired.toml"
TODAY = date(2026, 11, 7)
TODAY_ARG = TODAY.isoformat()


def run(
    report: Path | str, allowlist: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[str]]:
    """Run the CLI as the lane does; return its exit code and its stdout lines."""
    code = caa.main([str(report), "--allowlist", str(allowlist), "--today", TODAY_ARG])
    return code, capsys.readouterr().out.splitlines()


def entry(**overrides: Any) -> str:
    """One TOML table for an advisory clean.json does not report, unless overridden."""
    fields: dict[str, Any] = {
        "id": "PYSEC-2026-4217",
        "package": "fsspec",
        "version": "2026.2.0",
        "reason": "Fixture.",
        "reachable": "no",
        "review_by": "2027-01-05",
        **overrides,
    }
    lines = ["[[advisory]]"]
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        elif key == "review_by":
            lines.append(f"{key} = {value}")
        else:
            lines.append(f"{key} = {json.dumps(value)}")
    return "\n".join(lines)


def passing_list(*extra: str) -> dict[str, Any]:
    """The allow-list that passes clean.json, plus extra tables."""
    return tomllib.loads("\n".join([ALLOWLIST.read_text("utf-8"), *extra]))


def list_file(tmp_path: Path, *extra: str) -> Path:
    """The same list on disk, for the tests that go through the CLI."""
    path = tmp_path / "allowlist.toml"
    path.write_text("\n".join([ALLOWLIST.read_text("utf-8"), *extra]), "utf-8")
    return path


def report_text(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


# ── the five cases the lane exists for ───────────────────────────────────────


def test_every_id_listed_and_in_date_passes(capsys: pytest.CaptureFixture[str]) -> None:
    code, lines = run(CLEAN, ALLOWLIST, capsys)
    assert code == 0
    assert len(lines) == 1
    # Two advisories, though clean.json prints PYSEC-2026-40 twice.
    assert lines[0].startswith("2 advisories in 2 packages")
    assert "2027-01-05" in lines[0]


def test_an_id_not_on_the_list_fails_and_names_the_id_and_the_package(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, lines = run(NEW_ADVISORY, ALLOWLIST, capsys)
    assert code != 0
    assert len(lines) == 1
    assert "PYSEC-2026-4217" in lines[0]
    assert "fsspec" in lines[0]
    assert "2026.6.0" in lines[0], "the line says whether a fix exists"


def test_a_review_by_in_the_past_fails(capsys: pytest.CaptureFixture[str]) -> None:
    code, lines = run(CLEAN, EXPIRED, capsys)
    assert code != 0
    assert len(lines) == 1
    assert "PYSEC-2026-139" in lines[0]
    assert "2026-11-06 has passed" in lines[0]


def test_a_listed_id_the_audit_no_longer_reports_is_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = run(CLEAN, list_file(tmp_path, entry()), capsys)
    assert code != 0
    assert len(lines) == 1
    assert "PYSEC-2026-4217" in lines[0]
    assert "stale" in lines[0]


def test_an_entry_with_reachable_yes_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    allowlist = list_file(tmp_path, entry(reachable="yes"))
    code, lines = run(NEW_ADVISORY, allowlist, capsys)
    assert code != 0
    assert len(lines) == 1
    assert "PYSEC-2026-4217" in lines[0]
    assert 'reachable = "yes"' in lines[0]


# ── the matching rules ───────────────────────────────────────────────────────


def test_an_entry_keeps_matching_when_the_feed_relabels_the_id() -> None:
    """The list says GHSA, the audit prints PYSEC: the same advisory, so no new line."""
    allowlist = tomllib.loads(
        ALLOWLIST.read_text("utf-8").replace("PYSEC-2026-40", "GHSA-98h9-4798-4q5v")
    )
    assert caa.check(report_text(CLEAN), allowlist, TODAY) == []


def test_a_version_bump_reads_as_a_new_advisory_and_a_stale_entry() -> None:
    """A bump changes the code the reason was written against, so somebody has to re-read it."""
    report = report_text(CLEAN)
    report["dependencies"][1]["version"] = "2.11.0"
    allowlist = tomllib.loads(ALLOWLIST.read_text("utf-8"))
    problems = caa.check(report, allowlist, TODAY)
    assert sorted(problems) == [
        "PYSEC-2026-139 torch 2.10.0: stale, the audit no longer reports it; remove the entry",
        "PYSEC-2026-139 torch 2.11.0: not on the allow-list (fixed in: none)",
    ]


def test_the_same_id_on_another_package_is_not_covered() -> None:
    report = report_text(CLEAN)
    report["dependencies"][1]["name"] = "torchvision"
    problems = caa.check(report, tomllib.loads(ALLOWLIST.read_text("utf-8")), TODAY)
    assert any("torchvision" in line and "not on the allow-list" in line for line in problems)


def test_package_names_compare_by_their_canonical_form() -> None:
    allowlist = tomllib.loads(ALLOWLIST.read_text("utf-8").replace('"diffusers"', '"Diffusers"'))
    assert caa.check(report_text(CLEAN), allowlist, TODAY) == []


# ── in_feed = false: real, reviewed, and invisible to the audit ──────────────


def test_an_id_no_feed_carries_is_not_stale() -> None:
    assert caa.check(report_text(CLEAN), passing_list(entry(in_feed=False)), TODAY) == []


def test_an_id_no_feed_carried_fails_once_the_audit_reports_it() -> None:
    problems = caa.check(report_text(NEW_ADVISORY), passing_list(entry(in_feed=False)), TODAY)
    assert len(problems) == 1
    assert "PYSEC-2026-4217" in problems[0]
    assert "reports it now" in problems[0]


def test_an_id_no_feed_carries_still_has_to_be_reviewed() -> None:
    table = entry(in_feed=False, review_by="2026-11-01")
    problems = caa.check(report_text(CLEAN), passing_list(table), TODAY)
    assert len(problems) == 1
    assert "has passed" in problems[0]


# ── the review clock ─────────────────────────────────────────────────────────


def test_the_review_date_itself_still_passes(capsys: pytest.CaptureFixture[str]) -> None:
    """`has passed` means the day after, so a date is good through the end of that day."""
    code = caa.main(
        [str(CLEAN), "--allowlist", str(ALLOWLIST), "--today", date(2027, 1, 5).isoformat()]
    )
    capsys.readouterr()
    assert code == 0
    code = caa.main(
        [str(CLEAN), "--allowlist", str(ALLOWLIST), "--today", date(2027, 1, 6).isoformat()]
    )
    capsys.readouterr()
    assert code != 0


def test_a_review_date_over_sixty_days_out_fails() -> None:
    sixty = (TODAY + timedelta(days=60)).isoformat()
    sixty_one = (TODAY + timedelta(days=61)).isoformat()
    assert caa.check(report_text(NEW_ADVISORY), passing_list(entry(review_by=sixty)), TODAY) == []
    problems = caa.check(report_text(NEW_ADVISORY), passing_list(entry(review_by=sixty_one)), TODAY)
    assert len(problems) == 1
    assert "over 60 days" in problems[0]


# ── a malformed list fails closed, in one line each ──────────────────────────


@pytest.mark.parametrize("missing", ["id", "package", "version", "reason", "reachable", "review_by"])
def test_an_entry_missing_a_field_fails(missing: str) -> None:
    problems = caa.check(report_text(CLEAN), passing_list(entry(**{missing: None})), TODAY)
    assert len(problems) == 1
    assert f"missing {missing}" in problems[0]


def test_a_review_by_that_is_not_a_date_fails() -> None:
    problems = caa.check(report_text(CLEAN), passing_list(entry(review_by='"soon"')), TODAY)
    assert len(problems) == 1
    assert "must be a TOML date" in problems[0]


def test_an_unknown_reachable_value_fails() -> None:
    problems = caa.check(report_text(NEW_ADVISORY), passing_list(entry(reachable="maybe")), TODAY)
    assert len(problems) == 1
    assert "reachable must be one of" in problems[0]


def test_the_same_entry_twice_fails() -> None:
    problems = caa.check(report_text(NEW_ADVISORY), passing_list(entry(), entry()), TODAY)
    assert len(problems) == 1
    assert "listed 2 times" in problems[0]


# ── a report that checked nothing is not a pass ──────────────────────────────


def test_a_missing_report_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """What a pip-audit crash leaves behind, since the lane ignores its exit status."""
    code, lines = run(tmp_path / "audit-extras.json", ALLOWLIST, capsys)
    assert code != 0
    assert len(lines) == 1
    assert "cannot read the audit report" in lines[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", "cannot read the audit report"),
        ("{not json", "cannot read the audit report"),
        ("{}", "lists no dependencies"),
        ('{"dependencies": []}', "lists no dependencies"),
        ("[1, 2]", "not pip-audit JSON"),
        ('{"dependencies": [{"version": "1.0"}]}', "not pip-audit JSON"),
    ],
)
def test_a_report_that_is_not_an_audit_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, expected: str
) -> None:
    report = tmp_path / "audit-extras.json"
    report.write_text(text, "utf-8")
    code, lines = run(report, ALLOWLIST, capsys)
    assert code != 0
    assert len(lines) == 1
    assert expected in lines[0]


def test_an_empty_report_does_not_read_as_every_entry_being_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One line saying what happened, not a stale line per entry to read past."""
    report = tmp_path / "audit-extras.json"
    report.write_text('{"dependencies": []}', "utf-8")
    _, lines = run(report, ALLOWLIST, capsys)
    assert len(lines) == 1


def test_a_dependency_pip_audit_skipped_fails() -> None:
    report = report_text(CLEAN)
    report["dependencies"].append({"name": "some-pkg", "skip_reason": "Dependency not found"})
    problems = caa.check(report, tomllib.loads(ALLOWLIST.read_text("utf-8")), TODAY)
    assert len(problems) == 1
    assert "some-pkg" in problems[0]
    assert "skipped" in problems[0]


def test_an_unreadable_allowlist_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = run(CLEAN, tmp_path / "absent.toml", capsys)
    assert code != 0
    assert "cannot read the allow-list" in lines[0]
    broken = tmp_path / "broken.toml"
    broken.write_text("[[advisory", "utf-8")
    code, lines = run(CLEAN, broken, capsys)
    assert code != 0
    assert "cannot read the allow-list" in lines[0]


def test_the_report_can_come_from_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(NEW_ADVISORY.read_text("utf-8")))
    code = caa.main(["--allowlist", str(ALLOWLIST), "--today", TODAY_ARG])
    assert code != 0
    assert "PYSEC-2026-4217" in capsys.readouterr().out


# ── the committed list and the wiring ────────────────────────────────────────


def _committed() -> dict[str, Any]:
    return tomllib.loads(caa.DEFAULT_ALLOWLIST.read_text("utf-8"))


def test_the_committed_list_is_well_formed() -> None:
    """Dated as of its own earliest review, so this cannot go red on a calendar day: the lane can."""
    allowlist = _committed()
    earliest = min(raw["review_by"] for raw in allowlist["advisory"])
    entries, problems = caa.parse_allowlist(allowlist, earliest)
    assert problems == []
    assert entries


def test_the_committed_list_holds_no_reachable_advisory() -> None:
    for raw in _committed()["advisory"]:
        assert raw["reachable"] in caa.LISTABLE, raw["id"]


def test_the_policyserver_justification_survives_on_the_list() -> None:
    by_id = {raw["id"]: raw for raw in _committed()["advisory"]}
    entry_ = by_id["GHSA-f7vj-73pm-m822"]
    assert "no gRPC/PolicyServer is ever started" in entry_["reason"]
    assert entry_["reachable"] == "no"
    assert entry_["in_feed"] is False


def _lane() -> dict[str, Any]:
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    return next(
        step
        for step in workflow["jobs"]["audit"]["steps"]
        if step.get("name") == "Audit GPU extras (allow-listed)"
    )


def test_the_lane_can_fail() -> None:
    assert "continue-on-error" not in _lane()


def test_the_lane_hands_pip_audits_json_to_the_checker() -> None:
    run_ = _lane()["run"]
    assert "pip-audit==2.10.1" in run_, "the pinned version stays"
    assert "--progress-spinner off" in run_
    assert "--format json" in run_
    assert "--ignore-vuln" not in run_, "known ids live on the list now"
    assert "scripts/check_audit_allowlist.py" in run_


def test_nothing_can_swallow_the_checkers_verdict() -> None:
    """pip-audit may exit 1 here, so `|| true` is on it. On the checker it would end the gate."""
    lines = [line.strip() for line in _lane()["run"].splitlines() if line.strip()]
    assert "scripts/check_audit_allowlist.py" in lines[-1]
    assert "||" not in lines[-1]
    assert not any("set +e" in line for line in lines)


def test_the_lane_still_refuses_a_vacuous_export() -> None:
    assert "'^torch=='" in _lane()["run"]
