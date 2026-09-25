# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Every committed run from the cut-over on carries the provenance a published number needs; every
older run's gaps are listed, labelled unknown, and never backfilled.

R08 (19 Sep 2026). `provael.campaign.check_provenance` existed and the scheduled lane ran it, but
nothing applied it to a run a person launched by hand — and every run in `results/` on that date
lacked at least two of the required fields (all ran on <= 0.41.2, before `repository` and the
installed-set lock digest were recorded at all). Two rules follow, and this file holds both:

* A run whose newest ``ended_at`` is on or after :data:`CUT_OVER` must pass `check_provenance` on
  every shard. There is no exemption list for new runs; a new run with a gap fails here, names the
  shard and the field, and the remedy is to re-run with the fields populated, not to add a row.
* A run from before the cut-over appears in :data:`KNOWN_GAPS` with its exact gaps. A gap that
  disappears fails the test too: the only honest way a historical manifest changes is a new
  measurement, so a "fix" that fills a 2026-09-14 manifest with values nobody recorded is caught.

The generated run READMEs render the same state per shard; they are held current here as well.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from provael.campaign import REQUIRED_PROVENANCE, check_provenance, provenance_gaps

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
#: Runs that finish on or after this date must carry complete provenance. Chosen as the day after
#: the box's last 0.41.2-image runs (night2 and dawn, 18 September 2026), which are recorded with
#: their gaps below.
CUT_OVER = "2026-09-20"
#: Historical runs and their exact gaps, per run directory under results/ (a sharded run is one
#: entry). Read as "unknown", never as a value. Adding a run here is only right for a run that
#: predates the cut-over.
KNOWN_GAPS: dict[str, tuple[str, ...]] = {
    "gpu-scheduled/20260906T190346Z": ("commit", "dep_lock_digest", "precision", "repository"),
    "gpu-scheduled/20260911T093546Z": ("commit", "dep_lock_digest", "precision", "repository"),
    "gpu-scheduled/20260915T100635Z": ("commit", "dep_lock_digest", "precision", "repository"),
    "gpu-scheduled/20260918T092846Z": ("commit", "dep_lock_digest", "precision", "repository"),
    "pi05_libero_object_2026-09-18": ("commit", "dep_lock_digest", "precision", "repository"),
    "pi05_libero_object_pilot_2026-09-14": ("commit", "dep_lock_digest", "precision", "repository"),
    "smolvla_libero_10_2026-09-14": ("dep_lock_digest", "precision", "repository"),
    "smolvla_libero_goal_2026-09-14": ("dep_lock_digest", "precision", "repository"),
    "smolvla_libero_object": ("dep_lock_digest", "precision"),
    "smolvla_libero_object_clip_2026-09-14": ("dep_lock_digest", "precision", "repository"),
    "smolvla_libero_object_control": ("commit", "dep_lock_digest", "precision", "repository"),
    "smolvla_libero_object_control_2026-09-14": ("dep_lock_digest", "precision", "repository"),
    "smolvla_libero_object_defense_canonicalization_2026-09-18": (
        "dep_lock_digest", "precision", "repository",
    ),
    "smolvla_libero_object_defense_envelope_2026-09-18": (
        "dep_lock_digest", "precision", "repository",
    ),
    "smolvla_libero_object_families_2026-09-14": ("dep_lock_digest", "precision", "repository"),
    "smolvla_libero_object_suite": ("commit", "dep_lock_digest", "precision", "repository"),
    "smolvla_libero_object_suite_2026-09-14": ("commit", "dep_lock_digest", "precision", "repository"),
    "smolvla_libero_spatial_2026-09-14": ("dep_lock_digest", "precision", "repository"),
    "timing": ("commit", "dep_lock_digest", "precision", "repository"),
    "weight_integrity_stub": ("dep_lock_digest", "precision", "repository"),
}
#: Legacy directories with a report and no execution manifest at all: stub / fixture runs from
#: before the manifest existed. Nothing dates them; nothing publishes them as measurements.
NO_MANIFEST: frozenset[str] = frozenset({
    "cross_arch_transfer/stub", "eai04_action_space_transfer/reach", "optimized_targeted_hijack_stub",
})


def _run_of(manifest_path: Path) -> str:
    rel = manifest_path.relative_to(RESULTS)
    if rel.parts[0] == "gpu-scheduled":
        return "/".join(rel.parts[:-1])
    return rel.parts[0]


def _runs() -> dict[str, list[Path]]:
    """Run directory -> its shard directories (the directories holding a manifest)."""
    runs: dict[str, list[Path]] = {}
    for p in sorted(RESULTS.rglob("execution-manifest.json")):
        runs.setdefault(_run_of(p), []).append(p.parent)
    return runs


def _newest_end(shards: list[Path]) -> str:
    ends = []
    for shard in shards:
        m = json.loads((shard / "execution-manifest.json").read_text(encoding="utf-8"))
        if isinstance(m.get("ended_at"), str):
            ends.append(m["ended_at"])
    return max(ends) if ends else ""


def test_every_run_from_the_cut_over_on_carries_complete_provenance() -> None:
    late = {run: shards for run, shards in _runs().items() if _newest_end(shards)[:10] >= CUT_OVER}
    problems = {run: check_provenance(shards) for run, shards in late.items()}
    problems = {run: gaps for run, gaps in problems.items() if gaps}
    assert not problems, (
        f"runs finished on/after {CUT_OVER} with missing provenance ({', '.join(REQUIRED_PROVENANCE)}): "
        f"{json.dumps(problems, indent=2)}. Re-run with PROVAEL_REPOSITORY / PROVAEL_COMMIT set and a "
        "provael >= 0.42.0 in the image; do not add the run to KNOWN_GAPS."
    )
    for run in late:
        assert run not in KNOWN_GAPS, f"{run} finished after the cut-over and cannot be a known gap"


def test_every_historical_run_is_listed_with_its_exact_gaps() -> None:
    runs = _runs()
    historical = {run for run, shards in runs.items() if _newest_end(shards)[:10] < CUT_OVER}
    assert historical == set(KNOWN_GAPS), (
        "the set of pre-cut-over runs and KNOWN_GAPS differ: "
        f"unlisted={sorted(historical - set(KNOWN_GAPS))}, stale={sorted(set(KNOWN_GAPS) - historical)}"
    )
    for run, expected in KNOWN_GAPS.items():
        actual: set[str] = set()
        for shard in runs[run]:
            m = json.loads((shard / "execution-manifest.json").read_text(encoding="utf-8"))
            actual.update(provenance_gaps(m))
        assert tuple(sorted(actual)) == expected, (
            f"{run}: recorded gaps {expected} but the manifests now show {tuple(sorted(actual))}. A "
            "historical manifest only changes by a new measurement; a filled-in value nobody "
            "recorded is a fabrication, and a new gap is a corruption."
        )


def test_runs_without_a_manifest_are_the_known_legacy_fixtures_only() -> None:
    without = {
        str(d.relative_to(RESULTS)) for d in {p.parent for p in RESULTS.rglob("report.json")}
        if not (d / "execution-manifest.json").exists()
    }
    assert without == set(NO_MANIFEST)
    for rel in without:
        report = json.loads((RESULTS / rel / "report.json").read_text(encoding="utf-8"))
        assert report.get("policy") == "stub" or report.get("suite") in {"stub", "reach", "humanoid"}


_GENERATED_READMES = sorted(
    d for d in RESULTS.iterdir()
    if (d / "README.md").is_file()
    and "## What this does not establish" in (d / "README.md").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("run_dir", _GENERATED_READMES, ids=lambda p: p.name)
def test_generated_run_readmes_are_current_and_state_provenance(run_dir: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/gen_results_readme.py"), str(run_dir), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    text = (run_dir / "README.md").read_text(encoding="utf-8")
    assert "- Required provenance (" in text
    assert "recorded as unknown, not backfilled" in text or "complete on every shard" in text
    assert "derived from these shards" in text
