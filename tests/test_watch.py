"""The continuous-measurement watch: recording runs and a freshness badge that decays on its own.

THE FAILURE THIS GUARDS. A freshness badge emitted BY the measurement job is green for as long as
the job runs and frozen green forever after it stops — it reports the last success rather than the
current state, so the one event it exists to surface (measurements stopping) is the one event it
cannot show. The badge is therefore computed from the recorded measurement TIME on every refresh,
and these tests pin that: same recorded data, different `now`, different colour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from provael.config import RunConfig
from provael.runner import run
from provael.watch import (
    FRESH_DAYS,
    STALE_DAYS,
    age_days,
    append_measurement,
    badge,
    latest_measurement,
    read_measurements,
    write_badge,
)


def _report():
    return run(RunConfig(policy="stub", suite="stub", attacks=["none", "instruction"],
                         episodes=5, seed=0))


def test_records_a_measurement_into_both_ledgers(tmp_path: Path) -> None:
    record = append_measurement(tmp_path, _report())
    assert record.policy == "stub" and record.attempts > 0
    assert (tmp_path / "trials.jsonl").is_file()  # the existing per-trial ledger
    assert len(read_measurements(tmp_path)) == 1  # plus the run-level roll-up


def test_appends_rather_than_overwrites(tmp_path: Path) -> None:
    append_measurement(tmp_path, _report(), measured_at="2026-08-01T00:00:00Z")
    append_measurement(tmp_path, _report(), measured_at="2026-08-02T00:00:00Z")
    assert len(read_measurements(tmp_path)) == 2
    assert latest_measurement(tmp_path).measured_at == "2026-08-02T00:00:00Z"


def test_latest_is_by_time_not_by_file_order(tmp_path: Path) -> None:
    """Appends can arrive out of order (a re-run of an older commit); newest MEASURED wins."""
    append_measurement(tmp_path, _report(), measured_at="2026-08-05T00:00:00Z")
    append_measurement(tmp_path, _report(), measured_at="2026-08-03T00:00:00Z")
    assert latest_measurement(tmp_path).measured_at == "2026-08-05T00:00:00Z"


def test_badge_reddens_on_its_own_as_time_passes(tmp_path: Path) -> None:
    """The whole point: the SAME recorded measurement goes green -> amber -> red with no new data.

    If this ever passes only because something re-recorded a measurement, the badge has stopped
    being a freshness signal and become a record of the last success.
    """
    measured = datetime(2026, 8, 1, tzinfo=UTC)
    record = append_measurement(tmp_path, _report(), measured_at="2026-08-01T00:00:00Z")

    fresh = badge(record, now=measured + timedelta(days=FRESH_DAYS - 1))
    amber = badge(record, now=measured + timedelta(days=STALE_DAYS - 1))
    stale = badge(record, now=measured + timedelta(days=STALE_DAYS + 5))

    assert fresh["color"] == "brightgreen" and fresh["isError"] is False
    assert amber["color"] == "orange" and amber["isError"] is False
    assert stale["color"] == "red" and stale["isError"] is True
    assert "days ago" in str(stale["message"])


def test_never_measured_is_an_error_state_not_a_neutral_one(tmp_path: Path) -> None:
    """An unbacked badge must not read green: it would assert currency it is not checking."""
    payload = badge(None)
    assert payload["message"] == "never"
    assert payload["color"] == "red" and payload["isError"] is True
    assert age_days(None) is None


def test_write_badge_emits_a_valid_shields_endpoint_payload(tmp_path: Path) -> None:
    append_measurement(tmp_path, _report())
    path, payload = write_badge(tmp_path)
    assert path.is_file()
    # The four keys shields.io's endpoint schema requires, plus our explicit cache bound.
    assert payload["schemaVersion"] == 1
    assert payload["label"] == "last measured"
    assert isinstance(payload["message"], str) and payload["message"]
    assert payload["color"] in {"brightgreen", "orange", "red"}
    assert payload["cacheSeconds"] == 3600


def test_the_committed_badge_is_a_valid_payload() -> None:
    """The badge committed at watch/freshness.json is what the README renders — keep it loadable."""
    import json

    committed = Path(__file__).resolve().parent.parent / "watch" / "freshness.json"
    payload = json.loads(committed.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1
    assert payload["label"] == "last measured"
    assert payload["color"] in {"brightgreen", "orange", "red"}
