"""`watch/measurements.json` must stay current, deterministic, and honest about its own dates.

WHAT THIS GUARDS. The ledger is the artifact www.provael.com's /status/ page joins its published
claims onto, so a stale or wrong row there dates a number incorrectly on a page whose entire
purpose is dating numbers. Four separate ways that can go wrong, one test each:

1. The committed file drifts from what the generator would write.
2. The two directory walks that get paired by index desynchronise, silently attaching every row to
   the wrong artifact.
3. `newestRealMeasuredAt` disagrees with `watch/freshness.json`, so the badge and the ledger tell a
   reader different things about the same project.
4. A wall-clock value leaks in and the artifact stops being reproducible.

(2) is the subtle one and the reason the pairing is asserted rather than commented. Matching on the
timestamp instead looked obviously safer and was not: the five `weight_integrity_stub` shards all
finished inside the same second and three share an instant exactly, so a match-on-instant lookup
found multiple candidates and returned no artifact link for any of them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from provael.watch import measurements_from_results

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "watch" / "measurements.json"
FRESHNESS = REPO / "watch" / "freshness.json"


def _generator():
    """Load the generator by path — `scripts/` is not an importable package."""
    spec = importlib.util.spec_from_file_location(
        "gen_measurement_ledger", REPO / "scripts" / "gen_measurement_ledger.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ledger() -> dict:
    assert LEDGER.is_file(), f"{LEDGER} is missing. Run `make gen-measurement-ledger`."
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_committed_ledger_is_current() -> None:
    """The same rule `--check` enforces, so a stale ledger fails the suite and not only CI."""
    assert _generator().main(["--check"]) == 0, (
        "watch/measurements.json is stale. Run `make gen-measurement-ledger` and commit the result."
    )


def test_row_count_matches_the_records_it_renders(ledger: dict) -> None:
    """A row per measurement, no more and no fewer."""
    assert len(ledger["measurements"]) == len(measurements_from_results(REPO / "results"))
    assert ledger["measurementCount"] == len(ledger["measurements"])


def test_every_row_points_at_an_artifact_that_exists(ledger: dict) -> None:
    """The pairing-by-index correspondence, asserted rather than trusted.

    If the generator's walk ever diverges from `measurements_from_results`, rows keep rendering and
    every artifact link silently points at the wrong run. A path that does not exist is the cheapest
    detectable symptom of that.
    """
    for row in ledger["measurements"]:
        path = row["artifactPath"]
        assert path, f"row measured {row['measuredAt']} has no artifactPath"
        assert (REPO / path / "execution-manifest.json").is_file(), (
            f"{path} carries no execution manifest, so the ledger's walks have desynchronised and "
            "every row may be attached to the wrong artifact"
        )


def test_rows_agree_with_their_own_manifests(ledger: dict) -> None:
    """Each row's instant must match the manifest in the directory it names."""
    for row in ledger["measurements"]:
        manifest = json.loads(
            (REPO / row["artifactPath"] / "execution-manifest.json").read_text(encoding="utf-8")
        )
        assert manifest.get("ended_at") == row["measuredAt"], (
            f"{row['artifactPath']} ended at {manifest.get('ended_at')} but the ledger dates it "
            f"{row['measuredAt']} — the index pairing is off by at least one row"
        )


def test_newest_real_measurement_agrees_with_the_badge(ledger: dict) -> None:
    """The ledger and `watch/freshness.json` must not tell a reader different currencies."""
    badge = json.loads(FRESHNESS.read_text(encoding="utf-8")).get("measuredAt")
    assert ledger["newestRealMeasuredAt"] == badge, (
        f"ledger says the newest real measurement is {ledger['newestRealMeasuredAt']} and the "
        f"freshness badge says {badge}. Both derive from the same manifests, so a disagreement "
        "means one of them was hand-edited."
    )


def test_a_fixture_run_never_counts_as_a_measurement(ledger: dict) -> None:
    """A stub run executes real attacks in a second; letting it refresh freshness is the bug."""
    for row in ledger["measurements"]:
        if row["policy"] == "stub":
            assert row["countsAsMeasurement"] is False, (
                f"{row['artifactPath']} is a stub run marked as counting — it would refresh a "
                "freshness claim having re-measured nothing"
            )


def test_reconstructed_dates_are_flagged(ledger: dict) -> None:
    """An exact-midnight instant is a typed date, and must never present as an observed one."""
    for row in ledger["measurements"]:
        if row["measuredAt"].endswith("T00:00:00Z"):
            assert row["recorded"] is False, (
                f"{row['artifactPath']} ends at exact midnight, which is a day-granularity "
                "reconstruction, but the ledger presents it as a recorded instant"
            )


def test_ledger_is_deterministic() -> None:
    """Rendering twice must be byte-identical, or the artifact carries a wall-clock value."""
    gen = _generator()
    assert gen.render() == gen.render()
    assert "generatedAt" not in gen.render(), "a wall-clock field would break reproducibility"
