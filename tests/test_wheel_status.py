"""The packaged policy status needs no `results/` directory, and says the same thing as the checkout.

R13 (19 Sep 2026): the acceptance check for a release is that an installed wheel runs the quickstart
and lists the correct policy evidence. A wheel packages neither `results/` nor `docs/`, so any
status that were probed from either would flip on install (the 0.26.0 `list-defenses` incident).
This test simulates the wheel's view — a results directory that does not exist — and asserts the
declared statuses and the coverage counter's evidence flag behave as the installed package must.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from provael.cli import app
from provael.coverage import coverage
from provael.policies.registry import (
    MEASURED_POLICIES,
    STATUS_MEASURED,
    STATUS_SCAFFOLDING,
    STATUS_UNRUN,
    available_policies,
    policy_status,
)


def test_policy_status_is_declared_and_needs_no_results_directory(tmp_path: Path) -> None:
    """The same answers whether or not results/ exists — MEASURED_POLICIES is declared, not probed."""
    assert not (tmp_path / "results").exists()
    assert policy_status("smolvla") == STATUS_MEASURED
    assert policy_status("pi05") == STATUS_MEASURED
    assert policy_status("pi0") == STATUS_UNRUN
    assert policy_status("openvla") == STATUS_SCAFFOLDING
    assert set(MEASURED_POLICIES) == {"smolvla", "pi05"}


def test_coverage_in_a_wheel_reports_unscanned_not_zero(tmp_path: Path) -> None:
    cov = coverage(results_dir=tmp_path / "results")  # a wheel has no results/
    assert cov.evidence_scanned is False
    assert cov.real_policy_names == () and cov.real_policies_tested == 0
    assert cov.adversarial_families == 17 and cov.adversarial_attacks == 39  # registry counts hold
    from provael.coverage import coverage_line

    line = coverage_line(cov)
    assert "real_policy=unscanned" in line and "stub_only=unscanned" in line


def test_list_policies_shows_the_declared_evidence_for_both_measured_backends() -> None:
    result = CliRunner().invoke(app, ["list-policies"])
    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    for name in available_policies():
        assert name in flat
    assert "PRELIMINARY" in flat  # pi05's scope travels with its status
    assert flat.count("measured") >= 2
