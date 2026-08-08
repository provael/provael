"""Coverage counts, derived from the registries and the committed real-model runs.

WHY THIS MODULE EXISTS. Coverage counts are restated in the README, the docs, the Hugging Face
Space and on provael.com, and a restated number is a number that drifts —
``tests/test_counted_claims.py`` exists because "fourteen families" survived a whole release after
the registry moved to fifteen. This module is the one place that computes them, so every surface
can render rather than retype.

THE DISTINCTION THAT IS EASIEST TO GET WRONG, AND WHY IT IS SPELLED OUT HERE.
``len(ATTACKS)`` is **29**. That is 29 registered *attacks*, not 29 *families*: the registry holds
28 adversarial attacks plus one benign control, and those 28 group into **15 adversarial
families** (16 including the baseline). Reading the dict length as a family count overstates
coverage by 14, and it is an easy mistake to make from the outside because the dict is keyed by
attack name. Both numbers are published here, each labelled, precisely so nobody has to guess
which one a bare integer meant.

REGISTERED IS NOT VALIDATED, AND THIS MODULE REFUSES TO PRINT A SINGLE NUMBER.
A count of registered families says what code exists, not what has been measured. On the evidence
that actually ships:

* **Real-policy tested** — families exercised against a real VLA policy in a real simulator. That
  is 3 (``instruction``, ``visual``, ``injection``), from one committed SmolVLA x LIBERO run — and
  two of those three returned **honest nulls**, which is a measurement, not a gap.
* **Stub-validated only** — the remaining families run on the deterministic CPU fixture and have
  never met a real policy. Registered, runnable, unmeasured against a real model.

A consumer that prints only "15 families" invites a reader to assume 15 measured families. So
:func:`coverage` returns the breakdown and :func:`coverage_line` renders all of it on one line.
The real-policy set is **derived from the committed run reports**, not hardcoded, so it rises on
its own the day another family is measured and cannot be inflated by editing a constant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.registry import ATTACKS
from provael.policies.registry import POLICIES
from provael.suites import SUITES

#: Committed run reports scanned for real-policy evidence. A directory, not a list of files, so a
#: new committed run is picked up by existing here rather than by being added to a constant.
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"

#: Policy adapters that are deterministic fixtures rather than real models. A run driven by one of
#: these is scaffolding no matter which suite it used.
FIXTURE_POLICIES = frozenset({"stub"})
#: Suites that compute their state arithmetically rather than simulating. Same reasoning: a real
#: policy on a fixture suite is not a real-policy measurement.
FIXTURE_SUITES = frozenset({"stub", "reach", "humanoid"})

#: Where physical-robot runs land. Counted rather than declared, so provael.com's sim-to-real claim
#: moves the day a run appears instead of waiting on a docs edit. See results/hardware/README.md.
HARDWARE_DIR_NAME = "hardware"


@dataclass(frozen=True)
class Coverage:
    """The counts, with the validation state attached rather than left to the caller."""

    attacks_total: int
    adversarial_attacks: int
    families_total: int
    adversarial_families: int
    policies: int
    suites: int
    #: Families exercised against a real policy in a real simulator, sorted.
    real_policy_families: tuple[str, ...] = ()
    #: Registered adversarial families never run against a real policy, sorted.
    stub_only_families: tuple[str, ...] = field(default_factory=tuple)
    #: Committed runs executed on physical hardware. Zero today; the website renders from it.
    hardware_results: int = 0

    @property
    def real_policy_tested(self) -> int:
        return len(self.real_policy_families)

    @property
    def stub_validated_only(self) -> int:
        return len(self.stub_only_families)


def _real_policy_families(results_dir: Path = RESULTS_DIR) -> set[str]:
    """Adversarial families that appear in a committed run whose policy AND suite are both real.

    Derived rather than declared. A family counts here if it was *exercised* against a real
    policy, whatever the outcome — a measured 0% is a measurement and this project publishes
    nulls as results, so excluding them would undercount the evidence that exists.
    """
    found: set[str] = set()
    if not results_dir.is_dir():
        return found
    for report_path in sorted(results_dir.rglob("report.json")):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - a malformed committed report
            continue
        if data.get("policy") in FIXTURE_POLICIES or data.get("suite") in FIXTURE_SUITES:
            continue
        for result in data.get("results", []):
            family = result.get("family")
            if family and family != BASELINE_FAMILY:
                found.add(family)
    return found


def _hardware_runs(results_dir: Path = RESULTS_DIR) -> int:
    """Count committed runs under ``results/hardware/``.

    A run counts when it carries a ``report.json`` — the README in that directory is not a run. The
    count is derived rather than declared precisely so nobody has to remember to update a number
    when the first physical result lands.
    """
    hardware = results_dir / HARDWARE_DIR_NAME
    if not hardware.is_dir():
        return 0
    return sum(1 for _ in hardware.rglob("report.json"))


def coverage(results_dir: Path = RESULTS_DIR) -> Coverage:
    """Compute every published coverage count from the registries and the committed runs."""
    families = {ctor().family for ctor in ATTACKS.values()}
    adversarial_families = families - {BASELINE_FAMILY}
    adversarial_attacks = [n for n, ctor in ATTACKS.items() if ctor().family != BASELINE_FAMILY]

    real = _real_policy_families(results_dir) & adversarial_families
    return Coverage(
        attacks_total=len(ATTACKS),
        adversarial_attacks=len(adversarial_attacks),
        families_total=len(families),
        adversarial_families=len(adversarial_families),
        policies=len(POLICIES),
        suites=len(SUITES),
        real_policy_families=tuple(sorted(real)),
        stub_only_families=tuple(sorted(adversarial_families - real)),
        hardware_results=_hardware_runs(results_dir),
    )


def coverage_line(cov: Coverage | None = None) -> str:
    """One machine-readable line carrying every count AND its validation state.

    Deliberately not a bare total. ``families=15`` alone reads as fifteen measured families; the
    ``real_policy=3 stub_only=12`` pair is what stops that, and it travels in the same string so a
    consumer cannot pick up the flattering half.
    """
    c = cov or coverage()
    return (
        f"policies={c.policies} suites={c.suites} "
        f"families={c.adversarial_families} attacks={c.adversarial_attacks} "
        f"real_policy={c.real_policy_tested} stub_only={c.stub_validated_only} "
        f"hardware={c.hardware_results} "
        f"families_incl_baseline={c.families_total} attacks_incl_baseline={c.attacks_total}"
    )


def coverage_json(cov: Coverage | None = None) -> str:
    """The same facts as JSON, for a build step that would otherwise parse the line."""
    c = cov or coverage()
    return json.dumps(
        {
            "policies": c.policies,
            "suites": c.suites,
            "adversarialFamilies": c.adversarial_families,
            "adversarialAttacks": c.adversarial_attacks,
            "familiesTotal": c.families_total,
            "attacksTotal": c.attacks_total,
            "realPolicyTested": c.real_policy_tested,
            "realPolicyFamilies": list(c.real_policy_families),
            "stubValidatedOnly": c.stub_validated_only,
            "stubOnlyFamilies": list(c.stub_only_families),
            "hardwareResults": c.hardware_results,
            "meaning": (
                "families/attacks count what is REGISTERED. realPolicyTested counts families "
                "exercised against a real policy in a real simulator (a measured 0% counts — this "
                "project publishes nulls). stubValidatedOnly have never met a real model. "
                "Registered is not validated."
            ),
        },
        indent=2,
        sort_keys=True,
    )


__all__ = [
    "Coverage",
    "FIXTURE_POLICIES",
    "FIXTURE_SUITES",
    "RESULTS_DIR",
    "HARDWARE_DIR_NAME",
    "coverage",
    "coverage_json",
    "coverage_line",
]
