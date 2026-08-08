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
    MeasurementRecord,
    age_days,
    append_measurement,
    badge,
    latest_measurement,
    measurements_from_results,
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


# --------------------------------------------------------------------------------------------- #
# The badge must never make a FALSE claim. That is a different requirement from "must never be red".
#
# This badge shipped reading "never", in red, on a project with a published 10/10 real-policy
# result — because it read only the nightly's log and the nightly has never run. "Never" is the
# defect: it contradicts the flagship claim.
#
# The fix is NOT to forbid the red state. A freshness indicator that cannot report staleness is
# worse than none — it asserts currency it is not checking, which is the argument in this module's
# own docstring. The newest measurement really is over two months old, so red is the truthful
# reading and the README carries it. What is forbidden is the badge saying "never" while an
# artifact exists, or claiming a precision the artifact does not have.
# --------------------------------------------------------------------------------------------- #

COMMITTED_BADGE = Path(__file__).resolve().parent.parent / "watch" / "freshness.json"


def test_committed_badge_never_says_never_while_a_measurement_exists() -> None:
    """The exact false state this badge shipped in. A measurement happened; say so."""
    import json as _json

    payload = _json.loads(COMMITTED_BADGE.read_text(encoding="utf-8"))
    have_measurement = bool(measurements_from_results())
    assert have_measurement, "no committed run manifest carries an end time — fixture assumption broke"
    assert payload["message"] != "never", (
        "the badge says 'never' while results/ carries a measured run. Regenerate it: "
        "`provael watch --dir watch`."
    )


def test_committed_badge_matches_a_freshly_computed_one() -> None:
    """The committed file must be what the current code computes, modulo the age wording.

    Guards the drift where the badge is edited by hand or left behind after the logic changes.
    """
    import json as _json

    payload = _json.loads(COMMITTED_BADGE.read_text(encoding="utf-8"))
    fresh = badge(latest_measurement(Path(__file__).resolve().parent.parent / "watch"))
    assert payload["label"] == fresh["label"]
    assert payload["color"] == fresh["color"]
    # The day count moves with the wall clock, so compare the provenance marker rather than the age.
    assert ("date reconstructed" in str(payload["message"])) == (
        "date reconstructed" in str(fresh["message"])
    )


def test_a_reconstructed_timestamp_can_never_read_green() -> None:
    """Green asserts an observed instant. The only committed manifest reconstructs its date."""
    from datetime import timedelta

    measured = datetime(2026, 8, 8, tzinfo=UTC)
    rec = MeasurementRecord(
        measured_at="2026-08-08T00:00:00Z", recorded=False, policy="smolvla", suite="libero",
        tool_version="0.1.0", attempts=70, successes=17, asr=0.24,
    )
    # Same day — a RECORDED measurement here would be brightgreen.
    assert badge(rec, now=measured)["color"] == "orange"
    recorded = rec.model_copy(update={"recorded": True})
    assert badge(recorded, now=measured)["color"] == "brightgreen"
    # And it still goes red once genuinely stale, rather than being pinned amber forever.
    assert badge(rec, now=measured + timedelta(days=STALE_DAYS + 1))["color"] == "red"


def test_reconstructed_is_detected_from_the_manifests_own_tells() -> None:
    """Identical start/end, exact midnight, or legacy-unverified — any one is enough."""
    from provael.watch import _is_recorded

    assert _is_recorded({"started_at": "2026-08-08T10:00:00Z", "ended_at": "2026-08-08T11:30:00Z"})
    assert not _is_recorded({"evidence_state": "legacy-unverified",
                             "started_at": "2026-08-08T10:00:00Z", "ended_at": "2026-08-08T11:30:00Z"})
    assert not _is_recorded({"started_at": "2026-06-06T00:00:00Z", "ended_at": "2026-06-06T00:00:00Z"})
    assert not _is_recorded({"started_at": "2026-06-05T23:00:00Z", "ended_at": "2026-06-06T00:00:00Z"})
    assert not _is_recorded({"started_at": "x"})  # no end time at all


def test_the_committed_run_is_read_as_reconstructed() -> None:
    """Pins today's honest state: the one real-policy manifest is not a recorded timestamp."""
    records = measurements_from_results()
    assert records, "results/ carries no execution manifest with an end time"
    newest = max(records, key=lambda r: r.measured_at)
    assert newest.recorded is False
    assert newest.policy == "smolvla"
