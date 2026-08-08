"""The coverage counter: one source for every published count, with validation attached.

THE MISTAKE THIS GUARDS AGAINST, WHICH HAS ALREADY BEEN MADE ONCE FROM THE OUTSIDE.
`len(ATTACKS)` is 29 and it is tempting to read that as 29 families. It is not: 28 adversarial
attacks plus one benign control, grouping into 15 adversarial families. A reader who takes the
dict length as a family count overstates coverage by 14 — an error in the direction that flatters
the project, which is the direction this repo is least willing to be wrong in. Both numbers are
therefore published, each labelled, and asserted distinct below.

THE SECOND GUARD IS THE ONE THAT MATTERS MORE. Registered is not validated. A single "15" invites
a reader to assume fifteen measured families when three have met a real policy. The breakdown must
travel with the total in every rendering, and `test_line_never_reports_a_total_without_its_breakdown`
is what stops a future edit from emitting the flattering half alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.registry import ATTACKS
from provael.cli import app
from provael.coverage import Coverage, coverage, coverage_json, coverage_line

runner = CliRunner()


def test_counts_match_the_registries_exactly() -> None:
    c = coverage()
    families = {ctor().family for ctor in ATTACKS.values()}
    assert c.attacks_total == len(ATTACKS)
    assert c.families_total == len(families)
    assert c.adversarial_families == len(families - {BASELINE_FAMILY})
    assert c.adversarial_attacks == len(
        [n for n, ctor in ATTACKS.items() if ctor().family != BASELINE_FAMILY]
    )


def test_attacks_and_families_are_not_the_same_number() -> None:
    """The distinction the whole module exists to make legible.

    If these ever coincide the module still works, but the docstrings warning about the confusion
    would have gone stale — so this asserts the situation they describe still holds.
    """
    c = coverage()
    assert c.adversarial_attacks > c.adversarial_families
    assert c.attacks_total == c.adversarial_attacks + 1  # exactly one benign control
    assert c.families_total == c.adversarial_families + 1


def test_registered_is_partitioned_into_real_policy_and_stub_only() -> None:
    """Every adversarial family lands in exactly one bucket — no double count, no gap."""
    c = coverage()
    assert set(c.real_policy_families) & set(c.stub_only_families) == set()
    assert c.real_policy_tested + c.stub_validated_only == c.adversarial_families


def test_real_policy_families_are_derived_from_committed_runs_not_hardcoded(tmp_path: Path) -> None:
    """Point it at an empty results tree and the real-policy count must fall to zero.

    This is what makes the number honest: it rises when a run lands and cannot be inflated by
    editing a constant. If someone replaces the scan with a literal, this fails.
    """
    empty = coverage(results_dir=tmp_path)
    assert empty.real_policy_tested == 0
    assert empty.stub_validated_only == empty.adversarial_families


def test_a_fixture_run_never_counts_as_real_policy_evidence(tmp_path: Path) -> None:
    """The stub policy on the stub suite is scaffolding, however many families it exercises."""
    run = tmp_path / "fixture"
    run.mkdir()
    (run / "report.json").write_text(
        json.dumps(
            {
                "policy": "stub",
                "suite": "stub",
                "results": [{"family": "instruction", "success": True}],
            }
        ),
        encoding="utf-8",
    )
    assert coverage(results_dir=tmp_path).real_policy_tested == 0


def test_the_committed_run_supplies_exactly_the_families_it_exercised() -> None:
    """Pins today's honest state: three families have met a real policy, twelve have not.

    Two of the three returned measured nulls. They are counted, because a measured 0% is a
    measurement and this project publishes nulls as results — excluding them would undercount the
    evidence that actually exists.
    """
    c = coverage()
    assert c.real_policy_families == ("injection", "instruction", "visual")
    assert c.real_policy_tested == 3


def test_line_never_reports_a_total_without_its_breakdown() -> None:
    """A total alone reads as a measured total. The pair must be in the same string."""
    line = coverage_line()
    assert "families=" in line
    assert "real_policy=" in line and "stub_only=" in line
    # And the two spellings of the count are both present and labelled, never a bare integer.
    assert "attacks=" in line and "attacks_incl_baseline=" in line


def test_json_carries_the_meaning_field() -> None:
    payload = json.loads(coverage_json())
    assert payload["adversarialFamilies"] == coverage().adversarial_families
    assert "Registered is not validated" in payload["meaning"]


def test_cli_prints_both_forms() -> None:
    plain = runner.invoke(app, ["coverage"])
    assert plain.exit_code == 0 and "real_policy=" in plain.output.replace("\n", "")
    as_json = runner.invoke(app, ["coverage", "--json"])
    assert as_json.exit_code == 0
    assert json.loads(as_json.output)["policies"] == coverage().policies


def test_coverage_is_a_frozen_value() -> None:
    """A caller must not be able to edit a count after it was derived."""
    import dataclasses

    import pytest

    c = coverage()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.adversarial_families = 99  # type: ignore[misc]
    assert isinstance(c, Coverage)


# --------------------------------------------------------------------------------------------- #
# The README restates the breakdown in prose. Prose drifts — that is the whole reason
# tests/test_counted_claims.py exists — so the restatement is pinned to the counter here rather
# than trusted. This is the "no hardcoded coverage count outside the registry" guard: a literal
# may appear in prose, but only if it still equals what the registries compute.
# --------------------------------------------------------------------------------------------- #

README = Path(__file__).resolve().parent.parent / "README.md"


def test_readme_breakdown_matches_the_counter() -> None:
    text = README.read_text(encoding="utf-8")
    c = coverage()
    expected = [
        f"**{c.adversarial_families} adversarial families registered,",
        f"{c.real_policy_tested} exercised against a real policy**",
        f"**{c.stub_validated_only} stub-validated only**",
        f"**{c.adversarial_attacks} adversarial attacks**",
    ]
    missing = [e for e in expected if e not in text]
    assert not missing, (
        "README's coverage breakdown no longer matches `provael coverage`. Re-run it and update "
        f"the prose; missing: {missing}"
    )


def test_readme_never_calls_the_attack_total_a_family_count() -> None:
    """The specific error this module documents: 29 is attacks, never families.

    Cheap to assert and it pins the one confusion that has already been made from outside the
    project — a reader taking `len(ATTACKS)` for a family count overstates coverage by 14.
    """
    text = README.read_text(encoding="utf-8")
    c = coverage()
    for wrong in (
        f"{c.attacks_total} families",
        f"{c.attacks_total} adversarial families",
        f"{c.adversarial_attacks} families",
        f"{c.adversarial_attacks} adversarial families",
    ):
        assert wrong not in text, f"README calls an ATTACK count a FAMILY count: {wrong!r}"


# --- The counts mean different things in a checkout and in a wheel ---------------------------------
#
# Found by smoke-testing the 0.32.0 wheel in a clean venv: `provael coverage` printed
# `real_policy=0 stub_only=15` where the repo prints `real_policy=3 stub_only=12`. A wheel does not
# package `results/`, so there was nothing to derive the evidence counts from — and zero is the one
# answer that reads as a finding rather than an absence.
#
# The damage is specific. An outsider installs provael to check the README's "3 families with a
# real-model result", runs the command the README points at, sees 0, and concludes the project
# overstates its evidence. The number was right about their machine and wrong about their question.
# Registry counts (policies, suites, families, attacks) are properties of the package and stay
# correct either way; only the run-derived fields are affected.


def test_a_wheel_reports_unscanned_rather_than_zero(tmp_path: Path) -> None:
    absent = tmp_path / "no-such-results"
    cov = coverage(results_dir=absent)
    assert not cov.evidence_scanned
    line = coverage_line(cov)
    assert "real_policy=unscanned" in line, line
    assert "stub_only=unscanned" in line, line
    assert "hardware=unscanned" in line, line
    assert "real_policy=0" not in line, (
        "a context that never looked is reporting zero — the exact false contradiction this guards"
    )


def test_a_wheel_still_reports_the_registry_counts(tmp_path: Path) -> None:
    """Only the evidence fields go unscanned. The registry is in the package, so it is knowable."""
    cov = coverage(results_dir=tmp_path / "absent")
    line = coverage_line(cov)
    assert f"families={cov.adversarial_families}" in line
    assert f"policies={cov.policies}" in line
    assert cov.adversarial_families > 0 and cov.policies > 0


def test_a_checkout_scans_and_reports_integers() -> None:
    """The repo has results/, so the same fields must be numbers — not the unscanned token."""
    cov = coverage()
    assert cov.evidence_scanned, "the repo's results/ directory is missing"
    line = coverage_line(cov)
    assert "unscanned" not in line, line
    assert f"real_policy={cov.real_policy_tested}" in line


def test_the_json_carries_the_flag_a_consumer_must_branch_on(tmp_path: Path) -> None:
    """Website/Space builds parse the JSON; they need one boolean, not a heuristic on the counts."""
    scanned = json.loads(coverage_json(coverage()))
    unscanned = json.loads(coverage_json(coverage(results_dir=tmp_path / "absent")))
    assert scanned["evidenceScanned"] is True
    assert unscanned["evidenceScanned"] is False
