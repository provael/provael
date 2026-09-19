"""The reference delivery pack is current, digest-bound to its shards, and traces every number.

R08 (19 Sep 2026). `examples/delivery-pack/smolvla-libero-object-2026-09-14/` is what a paid
assessment hands over, generated from the published body by `scripts/gen_delivery_pack.py`. These
tests hold it to three properties: regenerating it on a clean tree is a no-op; every digest it
records is the sha256 of the file it names, so editing a shard invalidates the pack; and every
aggregate number it states is the sum of the shards it points at.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_delivery_pack.py"
PACK = ROOT / "examples" / "delivery-pack" / "smolvla-libero-object-2026-09-14"
RUN = ROOT / "results" / "smolvla_libero_object_suite_2026-09-14"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_committed_pack_is_current() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True, cwd=ROOT
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for name in (
        "README.md", "decision.json", "evidence-manifest.json", "report.scorecard.md",
        "test-report.md", "shards.txt", "REPRODUCE.md", "retest.md",
    ):
        assert (PACK / name).is_file(), name


def test_every_recorded_digest_is_the_files_sha256() -> None:
    for line in (PACK / "shards.txt").read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        assert _sha256(ROOT / rel) == digest, rel
    # The manifest's shard digests are schema-aware projections (provael.combine.shard_digests),
    # so a consumer can verify a shard with any later provael; shards.txt is the raw file sha256.
    from provael.execution import report_digest
    from provael.report import load_report

    manifest = json.loads((PACK / "evidence-manifest.json").read_text(encoding="utf-8"))
    assert manifest["shards"] == 10 and len(manifest["source_reports"]) == 10
    for entry in manifest["source_reports"]:
        assert report_digest(load_report(RUN / entry["path"])) == entry["sha256"], entry["path"]


def test_editing_a_shard_invalidates_the_pack(tmp_path: Path) -> None:
    """The property a customer relies on: a changed byte and the recorded digest disagree."""
    copy = tmp_path / "run"
    shutil.copytree(RUN, copy)
    target = copy / "libero_object_3" / "report.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["successes"] = data["successes"] + 1
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    recorded = next(
        line.split("  ", 1)[0]
        for line in (PACK / "shards.txt").read_text(encoding="utf-8").splitlines()
        if line.endswith("libero_object_3/report.json")
    )
    assert _sha256(target) != recorded


def test_every_aggregate_number_traces_to_the_shards() -> None:
    manifest = json.loads((PACK / "evidence-manifest.json").read_text(encoding="utf-8"))
    per_attack = {row["attack"]: row for row in manifest["per_attack"]}
    sums: dict[str, list[int]] = {}
    for shard in sorted(RUN.glob("libero_object_*/report.json")):
        report = json.loads(shard.read_text(encoding="utf-8"))
        for attack, stat in report["by_attack"].items():
            acc = sums.setdefault(attack, [0, 0])
            acc[0] += stat["successes"]
            acc[1] += stat["attempts"]
    for attack, (successes, attempts) in sums.items():
        assert (per_attack[attack]["successes"], per_attack[attack]["attempts"]) == (successes, attempts)
    assert (per_attack["roleplay"]["successes"], per_attack["roleplay"]["attempts"]) == (42, 50)
    readme = (PACK / "README.md").read_text(encoding="utf-8")
    assert "| `roleplay` | adversarial-treatment | 42/50 (84.0%)" in readme


def test_the_pack_states_its_decision_and_its_gaps_honestly() -> None:
    decision = json.loads((PACK / "decision.json").read_text(encoding="utf-8"))
    assert decision["verdict"] == "fail" and decision["protocol"] == "smolvla-libero-object-pilot"
    manifest = json.loads((PACK / "evidence-manifest.json").read_text(encoding="utf-8"))
    assert manifest["release_verdict"] == "fail"
    assert manifest["acceptance_protocol"]["name"] == "smolvla-libero-object-pilot"
    readme = (PACK / "README.md").read_text(encoding="utf-8")
    assert "**FAIL** under protocol" in readme
    assert "not backfilled" in readme  # the 0.41.2 provenance gaps are stated, not filled
    assert "No signature" in readme
    scorecard = (PACK / "report.scorecard.md").read_text(encoding="utf-8")
    assert "Release verdict: ❌ FAIL" in scorecard
    retest = (PACK / "retest.md").read_text(encoding="utf-8")
    assert "Overlapping intervals do not show equivalence" in retest
    assert "Baseline tool version 0.32.0; candidate 0.41.2" in retest
