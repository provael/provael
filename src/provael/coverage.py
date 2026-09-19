# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Coverage counts, derived from the registries and the committed real-model runs.

WHY THIS MODULE EXISTS. Coverage counts are restated in the README, the docs, the Hugging Face
Space and on provael.com, and a restated number is a number that drifts —
``tests/test_counted_claims.py`` exists because "fourteen families" survived a whole release after
the registry moved to fifteen. This module is the one place that computes them, so every surface
can render rather than retype.

THE DISTINCTION THAT IS EASIEST TO GET WRONG, AND WHY IT IS SPELLED OUT HERE.
``len(ATTACKS)`` is the number of registered *attacks*, not *families* (42 today: 39 adversarial
attacks plus the benign baseline and the two harmless-variation controls, grouping into 17
adversarial families, 19 with baseline and control). Reading the dict length as a family count
overstates coverage by more than double, and it is an easy mistake to make from the outside
because the dict is keyed by
attack name. Both numbers are published here, each labelled, precisely so nobody has to guess
which one a bare integer meant.

REGISTERED IS NOT VALIDATED, AND THIS MODULE REFUSES TO PRINT A SINGLE NUMBER.
A count of registered families says what code exists, not what has been measured. On the evidence
that actually ships:

* **Real-policy tested** — families exercised against a real VLA policy in a real simulator. That
  was 3 (``instruction``, ``visual``, ``injection``) from one committed SmolVLA x LIBERO run when
  this module was written, and is 8 since the 14 September 2026 breadth probe — most of them
  measured nulls, which is a measurement, not a gap.
* **Stub-validated only** — the remaining families run on the deterministic CPU fixture and have
  never met a real policy. Registered, runnable, unmeasured against a real model.
* **Real policies tested** — distinct real policies with a committed applicable adversarial
  episode (``realPoliciesTested`` / ``realPolicyNames``). Two since 18 September 2026: SmolVLA and
  π0.5, the latter a three-seed preliminary leg. A policy is not an architecture, and one
  checkpoint is not a survey; the count says how many adapters have a committed arm, nothing more.

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
from provael.attacks.controls import CONTROL_FAMILY
from provael.attacks.registry import ATTACKS
from provael.policies.registry import POLICIES, SCAFFOLDING_POLICIES
from provael.suites import SCAFFOLDING_SUITES, SUITES

#: Families that are registered and runnable but are NOT attacks: the benign FPR baseline and the
#: harmless-variation controls. Both must be subtracted before counting "adversarial families",
#: because a control counted as an attack overstates the surface this tool claims to cover — and
#: that count is quoted in the README, SAFETY.md, the docs and the leaderboard.
NON_ADVERSARIAL_FAMILIES = frozenset({BASELINE_FAMILY, CONTROL_FAMILY})

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
    #: Distinct real policies that received at least one applicable adversarial episode in a
    #: committed run, sorted by adapter name. Derived from the same scan as
    #: :attr:`real_policy_families`, for the same reason: the day a second architecture lands a
    #: committed arm (18 September 2026, ``pi05`` on LIBERO-Object) the count must rise on its
    #: own, and it must not rise for an adapter that is merely registered.
    real_policy_names: tuple[str, ...] = ()
    #: Registered adversarial families never run against a real policy, sorted.
    stub_only_families: tuple[str, ...] = field(default_factory=tuple)
    #: Registered policy adapters DECLARED as scaffolding, sorted. Read from
    #: :data:`~provael.policies.registry.SCAFFOLDING_POLICIES` rather than probed: the note on
    #: :data:`~provael.suites.SCAFFOLDING_SUITES` records why a filesystem probe answers
    #: differently in a checkout and in a wheel, and fails toward "measured".
    scaffolding_policy_names: tuple[str, ...] = field(default_factory=tuple)
    #: Registered suites DECLARED as scaffolding, sorted. Same reasoning.
    scaffolding_suite_names: tuple[str, ...] = field(default_factory=tuple)
    #: Registered defenses whose execution manifest shows them applied on a REAL policy in a
    #: committed run, sorted. Derived from `execution-manifest.json` (`defense`, `policy`), never
    #: from a study page: both shipped defenses carry a study measured on the stub fixture, which
    #: is a protocol exercise and not risk reduction on a real policy. Empty until a real-policy
    #: defended arm is committed.
    real_policy_defense_names: tuple[str, ...] = field(default_factory=tuple)
    #: Committed runs executed on physical hardware. Zero today; the website renders from it.
    hardware_results: int = 0
    #: False when no results directory was found at all — a pip-installed wheel, which does not
    #: package `results/`. Then the evidence counts are NOT "looked and found none"; nothing was
    #: looked at, and saying zero would contradict a published claim. See `evidence_scanned`.
    results_dir_present: bool = True

    @property
    def evidence_scanned(self) -> bool:
        """Whether the run-derived counts mean anything in this context.

        The registry counts (policies, suites, families, attacks) are properties of the installed
        package and are always true. The evidence counts (``real_policy``, ``hardware``) are derived
        by scanning committed runs, which only exist in a source checkout.

        Reported rather than papered over, because the failure is a false contradiction and not a
        crash: an outsider who installs provael to check the README's "3 families with a real-model
        result" and runs `provael coverage` in a wheel gets `real_policy=0` and concludes the README
        overstates. The number is right for their machine and wrong as an answer to their question.
        Found by smoke-testing the 0.32.0 wheel in a clean venv, which is what that step is for.
        """
        return self.results_dir_present

    @property
    def real_policy_tested(self) -> int:
        return len(self.real_policy_families)

    @property
    def real_policies_tested(self) -> int:
        """How many distinct real policies have received an applicable adversarial episode.

        A policy is not an architecture, and one checkpoint is not a survey: two counts here means
        two adapters each ran at least one committed arm, which says nothing about how many seeds,
        arms or tasks either ran. The per-run artifacts carry that.
        """
        return len(self.real_policy_names)

    @property
    def stub_validated_only(self) -> int:
        return len(self.stub_only_families)

    @property
    def real_policy_defenses(self) -> int:
        """Defenses with a committed defended arm on a real policy — not defenses with a study."""
        return len(self.real_policy_defense_names)

    # ── Registered vs runnable ────────────────────────────────────────────────
    # A third convention, and the one consumers kept getting wrong. `policies` and `suites` count
    # what is REGISTERED; some of those are declared scaffolding and have never been run. The
    # counts are properties rather than stored fields so they cannot drift from the name tuples
    # above, exactly as `real_policy_tested` derives from `real_policy_families`.

    @property
    def scaffolding_policies(self) -> int:
        return len(self.scaffolding_policy_names)

    @property
    def runnable_policies(self) -> int:
        return self.policies - self.scaffolding_policies

    @property
    def scaffolding_suites(self) -> int:
        return len(self.scaffolding_suite_names)

    @property
    def runnable_suites(self) -> int:
        return self.suites - self.scaffolding_suites


def _real_policy_families(results_dir: Path = RESULTS_DIR) -> set[str]:
    """Adversarial families with an APPLICABLE episode against a real policy on a real suite.

    Derived rather than declared. A family counts here if it was *exercised* against a real
    policy, whatever the outcome — a measured 0% is a measurement and this project publishes
    nulls as results, so excluding them would undercount the evidence that exists.

    APPLICABLE, since the 14 September 2026 breadth probe, and the distinction is the one
    :mod:`provael.eai` already draws: *untested* is not *no attack surface*. That probe ran every
    runnable family against SmolVLA, and eight of them (``action``, ``authorization``,
    ``backdoor``, ...) came back with every episode marked not applicable — the policy has no
    channel the attack can reach, so nothing was measured. Counting those as "exercised against a
    real policy" would have moved the published figure from 3 families to 16 on the strength of
    runs that measured nothing, which is the overstatement this counter exists to prevent. An
    episode that was not applicable is an absence of a surface, and it stays in the stub-only
    bucket until a real policy actually receives the attack.
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
            if (
                family
                and family not in NON_ADVERSARIAL_FAMILIES
                and result.get("applicable", True) is not False
            ):
                found.add(family)
    return found


def _real_policy_names(results_dir: Path = RESULTS_DIR) -> set[str]:
    """Policies with at least one APPLICABLE adversarial episode against a real suite.

    The same scan as :func:`_real_policy_families`, the same exclusions and the same applicability
    test, collecting the report's ``policy`` instead of each episode's ``family``. Derived, never
    declared, for the same reason: a count of "policies measured" that lived in a constant would
    be edited the day an adapter was registered rather than the day it was run. A scaffolding
    adapter with no committed run does not appear here; a policy whose every committed episode
    was not applicable does not either, because nothing was measured on it.
    """
    found: set[str] = set()
    if not results_dir.is_dir():
        return found
    for report_path in sorted(results_dir.rglob("report.json")):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - a malformed committed report
            continue
        policy = data.get("policy")
        if not policy or policy in FIXTURE_POLICIES or data.get("suite") in FIXTURE_SUITES:
            continue
        for result in data.get("results", []):
            family = result.get("family")
            if (
                family
                and family not in NON_ADVERSARIAL_FAMILIES
                and result.get("applicable", True) is not False
            ):
                found.add(str(policy))
                break
    return found


def _real_policy_defenses(results_dir: Path = RESULTS_DIR) -> set[str]:
    """Defenses applied on a real policy in a committed run, read from the execution manifests.

    The defense identity lives in ``execution-manifest.json`` (``report.json`` deliberately does
    not carry it — see :mod:`provael.execution`), so this is where "was this defense ever run on a
    real policy" can be answered. A study page measured on the stub fixture does not count, for
    the same reason a stub attack result does not: it exercises the protocol, not the policy.
    """
    found: set[str] = set()
    if not results_dir.is_dir():
        return found
    for manifest_path in sorted(results_dir.rglob("execution-manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - a malformed committed manifest
            continue
        defense = data.get("defense")
        if not defense or data.get("policy") in FIXTURE_POLICIES:
            continue
        if data.get("suite") in FIXTURE_SUITES:
            continue
        found.add(str(defense))
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


@dataclass(frozen=True)
class RegistryCounts:
    """The registry-only counts, in the ONE convention every surface uses.

    Adversarial = registered minus the baseline family and the harmless-variation control family.
    :mod:`provael.manifest` used to subtract the baseline alone and published 18 families / 43
    attacks beside this module's 17 / 39; the website then carried a conversion between the two
    conventions. There is one convention now, computed here, and the manifest reads it.
    """

    attacks_total: int
    adversarial_attacks: int
    attacks_baseline: int
    attacks_control: int
    families_total: int
    adversarial_families: int
    families_baseline: int
    families_control: int


def registry_counts() -> RegistryCounts:
    """Count the registry without touching the filesystem (usable from a wheel and a manifest)."""
    by_family: dict[str, int] = {}
    for ctor in ATTACKS.values():
        family = ctor().family
        by_family[family] = by_family.get(family, 0) + 1
    baseline_attacks = by_family.get(BASELINE_FAMILY, 0)
    control_attacks = by_family.get(CONTROL_FAMILY, 0)
    adversarial_families = set(by_family) - NON_ADVERSARIAL_FAMILIES
    return RegistryCounts(
        attacks_total=len(ATTACKS),
        adversarial_attacks=len(ATTACKS) - baseline_attacks - control_attacks,
        attacks_baseline=baseline_attacks,
        attacks_control=control_attacks,
        families_total=len(by_family),
        adversarial_families=len(adversarial_families),
        families_baseline=1 if baseline_attacks else 0,
        families_control=1 if control_attacks else 0,
    )


def coverage(results_dir: Path = RESULTS_DIR) -> Coverage:
    """Compute every published coverage count from the registries and the committed runs."""
    counts = registry_counts()
    families = {ctor().family for ctor in ATTACKS.values()}
    adversarial_families = families - NON_ADVERSARIAL_FAMILIES

    real = _real_policy_families(results_dir) & adversarial_families
    return Coverage(
        attacks_total=counts.attacks_total,
        adversarial_attacks=counts.adversarial_attacks,
        families_total=counts.families_total,
        adversarial_families=counts.adversarial_families,
        policies=len(POLICIES),
        suites=len(SUITES),
        real_policy_families=tuple(sorted(real)),
        real_policy_names=tuple(sorted(_real_policy_names(results_dir))),
        stub_only_families=tuple(sorted(adversarial_families - real)),
        scaffolding_policy_names=tuple(sorted(SCAFFOLDING_POLICIES)),
        scaffolding_suite_names=tuple(sorted(SCAFFOLDING_SUITES)),
        real_policy_defense_names=tuple(sorted(_real_policy_defenses(results_dir))),
        hardware_results=_hardware_runs(results_dir),
        results_dir_present=results_dir.is_dir(),
    )


def coverage_line(cov: Coverage | None = None) -> str:
    """One machine-readable line carrying every count AND its validation state.

    Deliberately not a bare total. ``families=15`` alone reads as fifteen measured families; the
    ``real_policy=3 stub_only=12`` pair is what stops that, and it travels in the same string so a
    consumer cannot pick up the flattering half.
    """
    c = cov or coverage()
    # An unscanned context reports the evidence fields as `unscanned`, never as 0. A consumer that
    # expects an integer breaks loudly here instead of quietly publishing "no family has ever been
    # measured" — which is the contradiction this token exists to prevent.
    real = str(c.real_policy_tested) if c.evidence_scanned else "unscanned"
    stub = str(c.stub_validated_only) if c.evidence_scanned else "unscanned"
    hardware = str(c.hardware_results) if c.evidence_scanned else "unscanned"
    return (
        f"policies={c.policies} suites={c.suites} "
        f"families={c.adversarial_families} attacks={c.adversarial_attacks} "
        f"real_policy={real} stub_only={stub} "
        f"hardware={hardware} "
        f"families_incl_baseline={c.families_total} attacks_incl_baseline={c.attacks_total}"
    )


def coverage_json(cov: Coverage | None = None) -> str:
    """The same facts as JSON, for a build step that would otherwise parse the line."""
    c = cov or coverage()
    return json.dumps(
        {
            "policies": c.policies,
            "runnablePolicies": c.runnable_policies,
            "scaffoldingPolicies": c.scaffolding_policies,
            "scaffoldingPolicyNames": list(c.scaffolding_policy_names),
            "suites": c.suites,
            "runnableSuites": c.runnable_suites,
            "scaffoldingSuites": c.scaffolding_suites,
            "scaffoldingSuiteNames": list(c.scaffolding_suite_names),
            "adversarialFamilies": c.adversarial_families,
            "adversarialAttacks": c.adversarial_attacks,
            "familiesTotal": c.families_total,
            "attacksTotal": c.attacks_total,
            "realPolicyTested": c.real_policy_tested,
            "realPolicyFamilies": list(c.real_policy_families),
            "realPoliciesTested": c.real_policies_tested,
            "realPolicyNames": list(c.real_policy_names),
            "stubValidatedOnly": c.stub_validated_only,
            "stubOnlyFamilies": list(c.stub_only_families),
            "realPolicyDefenses": c.real_policy_defenses,
            "realPolicyDefenseNames": list(c.real_policy_defense_names),
            "hardwareResults": c.hardware_results,
            # The one field a consumer must branch on. False => the three evidence counts above
            # were never scanned and must not be rendered; a wheel does not package `results/`.
            "evidenceScanned": c.evidence_scanned,
            "meaning": (
                "families/attacks count what is REGISTERED. realPolicyTested counts families "
                "exercised against a real policy in a real simulator (a measured 0% counts — this "
                "project publishes nulls). stubValidatedOnly have never met a real model. "
                "Registered is not validated. policies/suites count what is REGISTERED; "
                "runnablePolicies/runnableSuites exclude the adapters and suites DECLARED as "
                "scaffolding, which are implemented and unit-tested but have never been run. "
                "Those two conventions are not interchangeable. realPoliciesTested is a FOURTH "
                "count and is neither of those: it counts distinct real policies that received at "
                "least one applicable adversarial episode in a committed run (realPolicyNames says "
                "which). A scaffolding adapter that has never been run does not count, and a "
                "registered adapter is not a measured one. A policy is not an architecture, and "
                "one checkpoint is not a survey: the per-run artifacts say how many seeds, arms "
                "and tasks each policy actually received. realPolicyDefenses counts defenses with "
                "a committed defended arm on a real policy (realPolicyDefenseNames says which); a "
                "defense whose study was measured on the stub fixture is not one of them."
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
    "RegistryCounts",
    "coverage",
    "coverage_json",
    "coverage_line",
    "registry_counts",
]
