# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The registered/runnable split must stay tied to the declarations it is derived from.

WHY THIS EXISTS. `watch/registry.json` published `policies` and `suites` as bare integers, and the
code has always known better: `SCAFFOLDING_POLICIES` and `SCAFFOLDING_SUITES` declare which entries
are registered but have never been run, and `list-policies` / `list-suites` already render that.
`coverage_json()` did not export it, so a consumer wanting the runnable number had nowhere to read
it and typed one instead. www.provael.com published "5 suites" beside a registry saying 6 — the
same drift the artifact was built to end, one convention over.

WHAT IS ASSERTED, and each of these is a way the split could rot quietly:

1. The parts sum to the whole, for policies and for suites. A scaffolding entry removed from the
   dict but left in the artifact, or vice versa, breaks the arithmetic before it reaches a reader.
2. The exported NAME lists equal the source dicts exactly. Counts that agree while the names have
   drifted is the worse failure, because a consumer rendering "which ones" would be wrong while
   every total still added up.
3. The committed artifact agrees with a fresh computation. `make gen-registry` is the only way
   this file should ever change.
4. Nothing is derived by probing the filesystem. `SCAFFOLDING_SUITES` records why: `docs/` and
   `results/` are not packaged, so a probe answers differently in a checkout and in a wheel, and
   it fails toward "measured". A wheel must report the same split as a source tree.
"""

from __future__ import annotations

import json
from pathlib import Path

from provael.coverage import coverage, coverage_json
from provael.policies.registry import POLICIES, SCAFFOLDING_POLICIES
from provael.suites import SCAFFOLDING_SUITES, SUITES

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "watch" / "registry.json"


def test_policy_split_sums_to_the_registered_total() -> None:
    c = coverage()
    assert c.runnable_policies + c.scaffolding_policies == c.policies == len(POLICIES)


def test_suite_split_sums_to_the_registered_total() -> None:
    c = coverage()
    assert c.runnable_suites + c.scaffolding_suites == c.suites == len(SUITES)


def test_scaffolding_names_match_the_declarations_exactly() -> None:
    """Counts agreeing while names drift is the failure a reader would actually see."""
    c = coverage()
    assert set(c.scaffolding_policy_names) == set(SCAFFOLDING_POLICIES)
    assert set(c.scaffolding_suite_names) == set(SCAFFOLDING_SUITES)


def test_scaffolding_names_are_registered_at_all() -> None:
    """A declared scaffolding entry that is not in the registry would make runnable exceed total."""
    assert set(SCAFFOLDING_POLICIES) <= set(POLICIES), (
        f"{sorted(set(SCAFFOLDING_POLICIES) - set(POLICIES))} declared scaffolding but not "
        "registered — the subtraction in runnable_policies would understate the real count"
    )
    assert set(SCAFFOLDING_SUITES) <= set(SUITES), (
        f"{sorted(set(SCAFFOLDING_SUITES) - set(SUITES))} declared scaffolding but not registered"
    )


def test_exported_json_carries_the_split() -> None:
    data = json.loads(coverage_json())
    for key in (
        "runnablePolicies",
        "scaffoldingPolicies",
        "scaffoldingPolicyNames",
        "runnableSuites",
        "scaffoldingSuites",
        "scaffoldingSuiteNames",
    ):
        assert key in data, f"coverage_json() no longer exports {key}"
    assert data["runnablePolicies"] + data["scaffoldingPolicies"] == data["policies"]
    assert data["runnableSuites"] + data["scaffoldingSuites"] == data["suites"]
    assert data["scaffoldingPolicyNames"] == sorted(SCAFFOLDING_POLICIES)
    assert data["scaffoldingSuiteNames"] == sorted(SCAFFOLDING_SUITES)


def test_committed_artifact_agrees_with_a_fresh_computation() -> None:
    """`make gen-registry` is the only thing that may change watch/registry.json."""
    assert ARTIFACT.is_file(), f"{ARTIFACT} is missing. Run `make gen-registry`."
    committed = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    fresh = json.loads(coverage_json())
    for key, value in fresh.items():
        if key == "meaning":
            continue  # prose, carried by the generator's own note rather than asserted here
        assert committed.get(key) == value, (
            f"watch/registry.json says {key}={committed.get(key)!r}, the registry computes "
            f"{value!r}. Run `make gen-registry` and commit the result."
        )


def test_the_split_does_not_depend_on_the_filesystem() -> None:
    """A wheel does not package `results/`; the split must not change when it is absent.

    `SCAFFOLDING_SUITES` records this as the lesson the policy side learned in 0.26.0: a probe
    answers differently in a checkout and in a wheel, and it fails toward "measured". The evidence
    counts legitimately go unscanned without `results/`; the registered/runnable split must not.
    """
    absent = coverage(results_dir=REPO / "definitely-not-a-directory")
    present = coverage()
    assert absent.evidence_scanned is False, "the fixture path exists; pick another"
    assert (absent.runnable_policies, absent.scaffolding_policies) == (
        present.runnable_policies,
        present.scaffolding_policies,
    )
    assert (absent.runnable_suites, absent.scaffolding_suites) == (
        present.runnable_suites,
        present.scaffolding_suites,
    )
