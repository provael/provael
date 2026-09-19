"""The watch/ artifacts agree with each other and with the code that derives them.

R07 (19 Sep 2026): the consumption surface already existed; what drifted was the consumption. One
small test holds the counts, the selected run and the metric semantics together — rather than many
tests asserting exact marketing sentences — so a regenerated artifact that disagrees with its
sibling fails here, and regenerating on a clean tree is a no-op.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from provael.coverage import coverage, coverage_json
from provael.watch import task_suite_of

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "watch"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((WATCH / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_registry_json_is_the_coverage_counter_output() -> None:
    on_disk = {k: v for k, v in _load("registry.json").items() if k not in ("$schema", "note")}
    assert on_disk == json.loads(coverage_json())
    cov = coverage()
    assert on_disk["adversarialFamilies"] == cov.adversarial_families == 17
    assert on_disk["adversarialAttacks"] == cov.adversarial_attacks == 39
    assert on_disk["realPolicyNames"] == ["pi05", "smolvla"]
    assert on_disk["realPolicyDefenses"] == 0  # no real-policy defended arm committed yet


def test_the_ledger_has_one_row_per_committed_manifest_and_carries_the_new_facts() -> None:
    ledger = _load("measurements.json")
    manifests = [
        p for p in sorted((ROOT / "results").rglob("execution-manifest.json"))
        if json.loads(p.read_text(encoding="utf-8")).get("ended_at")
    ]
    assert ledger["measurementCount"] == len(ledger["measurements"]) == len(manifests)
    required = {
        "model", "adversarialSuccesses", "adversarialAttempts", "benignSuccesses", "benignAttempts",
        "calibrated", "evidenceState", "intervalMethod", "published",
    }
    for row in ledger["measurements"]:
        assert required <= set(row), row["artifactPath"]
        assert row["intervalMethod"] == "wilson-score-95 (episode-level)"
        if row["adversarialAttempts"] is not None and row["adversarialSuccesses"] is not None:
            assert 0 <= row["adversarialSuccesses"] <= row["adversarialAttempts"]


def test_the_ledgers_published_rows_are_the_publish_freshness_body() -> None:
    ledger = _load("measurements.json")
    freshness = _load("publish-freshness.json")
    lineage = ledger["publishedLineage"]
    assert lineage is not None
    published = freshness["published"]
    assert lineage["toolVersion"] == freshness["measuredWith"]
    assert lineage["attempts"] == published["attempts"]
    assert lineage["runs"] == published["runs"] == lineage["rows"]
    rows = [r for r in ledger["measurements"] if r["published"]]
    assert len(rows) == lineage["runs"]
    for row in rows:
        assert (row["policy"], row["suite"], row["toolVersion"]) == (
            lineage["policy"], lineage["suite"], lineage["toolVersion"]
        )
        assert task_suite_of(tuple(row["tasks"])) == lineage["taskSuite"]
    assert sum(r["attempts"] for r in rows) == lineage["attempts"]


def test_a_newer_run_outside_the_body_is_not_marked_published() -> None:
    """The 18 September LIBERO-10 and pi05 rows are newer than the Object body and not in it."""
    ledger = _load("measurements.json")
    outside = [
        r for r in ledger["measurements"]
        if r["artifactPath"].startswith(("results/smolvla_libero_10_2026-09-14", "results/pi05_"))
    ]
    assert outside and all(r["published"] is False for r in outside)


@pytest.mark.parametrize(
    "script",
    ["gen_registry_artifact.py", "gen_measurement_ledger.py", "gen_publish_freshness_artifact.py",
     "gen_release_artifact.py", "gen_campaign_progress.py"],
)
def test_regenerating_on_a_clean_tree_is_a_no_op(script: str) -> None:
    """No generator writes a wall-clock value, so `--check` means current, not recently written."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
