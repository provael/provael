"""The continuous-measurement watch: recording runs and a freshness badge that decays on its own.

THE FAILURE THIS GUARDS. A freshness badge emitted BY the measurement job is green for as long as
the job runs and frozen green forever after it stops — it reports the last success rather than the
current state, so the one event it exists to surface (measurements stopping) is the one event it
cannot show. The badge is therefore computed from the recorded measurement TIME on every refresh,
and these tests pin that: same recorded data, different `now`, different colour.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from provael.config import RunConfig
from provael.runner import run
from provael.watch import (
    FRESH_DAYS,
    STALE_DAYS,
    WATCH_LOG,
    MeasurementRecord,
    age_days,
    append_measurement,
    badge,
    counts_as_measurement,
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


def _as_real_policy(watch_dir: Path) -> None:
    """Rewrite the ledger's `policy` to a non-fixture name.

    These tests exercise append/ordering mechanics on a stub-generated report. Since
    `watch.counts_as_measurement` excludes fixture backends from the freshness signal — so a
    one-second stub run cannot green a badge that claims a POLICY was measured — a stub-labelled
    record is now correctly invisible to `latest_measurement`. Relabelling here keeps these tests
    about what they are about; weakening the filter to keep them passing would delete the guarantee.
    """
    path = watch_dir / WATCH_LOG
    lines = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for entry in lines:
        entry["policy"] = "smolvla"
    path.write_text("".join(json.dumps(e) + "\n" for e in lines))


def test_appends_rather_than_overwrites(tmp_path: Path) -> None:
    append_measurement(tmp_path, _report(), measured_at="2026-08-01T00:00:00Z")
    append_measurement(tmp_path, _report(), measured_at="2026-08-02T00:00:00Z")
    _as_real_policy(tmp_path)
    assert len(read_measurements(tmp_path)) == 2
    # results_dir is pinned to an empty directory ON PURPOSE. `latest_measurement` merges the watch
    # log with the committed manifests under results/, so without this the assertion depends on
    # whether the repo currently holds a measurement newer than these fixtures. It did not, until a
    # real run landed and this test started failing for a reason that had nothing to do with it.
    assert latest_measurement(tmp_path, results_dir=tmp_path).measured_at == "2026-08-02T00:00:00Z"


def test_latest_is_by_time_not_by_file_order(tmp_path: Path) -> None:
    """Appends can arrive out of order (a re-run of an older commit); newest MEASURED wins."""
    append_measurement(tmp_path, _report(), measured_at="2026-08-05T00:00:00Z")
    append_measurement(tmp_path, _report(), measured_at="2026-08-03T00:00:00Z")
    _as_real_policy(tmp_path)
    # Isolated from results/ for the same reason as the test above.
    assert latest_measurement(tmp_path, results_dir=tmp_path).measured_at == "2026-08-05T00:00:00Z"


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


def _measured_at(record: MeasurementRecord) -> datetime:
    """The record's measurement instant as an aware datetime."""
    return datetime.strptime(record.measured_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _committed_age_days(message: str) -> int:
    """The whole-day age the committed badge's own message asserts.

    Mirrors the wording :func:`provael.watch.badge` emits — ``today``, ``1 day ago``,
    ``N days ago`` — optionally suffixed with the reconstructed-date marker. Parsing the message
    back is what lets the colour be re-derived at the instant the file was written rather than at
    test time; see the caller for why that distinction is the whole point.
    """
    head = message.split(" (")[0].strip()
    if head == "today":
        return 0
    if head == "1 day ago":
        return 1
    days, _, rest = head.partition(" days ago")
    assert rest == "" and days.isdigit(), f"unrecognised badge message: {message!r}"
    return int(days)


def test_committed_badge_matches_a_freshly_computed_one() -> None:
    """The committed file must be what the current code computes, modulo the age wording.

    Guards the drift where the badge is edited by hand or left behind after the logic changes.
    """
    import json as _json

    payload = _json.loads(COMMITTED_BADGE.read_text(encoding="utf-8"))
    record = latest_measurement(Path(__file__).resolve().parent.parent / "watch")
    assert record is not None, "no measurement to recompute the badge from"

    # THE COLOUR MOVES WITH THE WALL CLOCK TOO, and comparing it against `now` made this test fail
    # on a schedule. The badge is regenerated once a day by freshness.yml; the age it encodes keeps
    # rising in between. So for the ~19 hours between an age crossing FRESH_DAYS or STALE_DAYS and
    # the next 05:23 UTC run, the committed file is correct-as-written while a `now`-based
    # recomputation disagrees — and every unrelated PR went red. Observed 16 Aug 2026: the workflow
    # wrote "6 days ago"/orange at 05:47, the age crossed 7.0 at 14:46, and CI then demanded red.
    #
    # The line above already conceded this for `message` ("the day count moves with the wall
    # clock") and then compared `color`, which is derived from the same clock. This closes that gap
    # by evaluating at the age the committed message ITSELF asserts, so the comparison is
    # clock-independent while keeping every tooth the guard was built for: a hand-edited colour, or
    # a changed FRESH_DAYS/STALE_DAYS threshold, still fails. What no longer fails is time passing.
    days = _committed_age_days(str(payload["message"]))
    as_written = badge(record, now=_measured_at(record) + timedelta(days=days))

    assert payload["label"] == as_written["label"]
    assert payload["color"] == as_written["color"], (
        f"committed badge says {payload['color']!r} for {payload['message']!r}, but the current "
        f"thresholds give {as_written['color']!r} at that age. Regenerate it: "
        "`provael watch --dir watch`."
    )
    assert ("date reconstructed" in str(payload["message"])) == (
        "date reconstructed" in str(as_written["message"])
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


def test_the_newest_committed_run_is_a_recorded_measurement() -> None:
    """The newest real-policy manifest must be RECORDED, not reconstructed.

    This test used to assert the opposite, and its docstring said it was pinning "today's honest
    state": the only real-policy manifest in the tree had a typed midnight timestamp, so the badge
    could never go green. That stopped being true when the 10-task suite run landed its manifests.

    Inverting it is the point. The repo now contains a measurement whose start and end were observed
    rather than reconstructed, and the badge is entitled to say so.
    """
    # Filtered, because `results/` now also holds a stub study (weight_integrity) whose manifest is
    # newer than any real run. That artifact is legitimate and must not drive this badge, which is
    # exactly what `counts_as_measurement` enforces — so the assertion below is about the newest
    # record that COUNTS, not the newest file on disk.
    records = [r for r in measurements_from_results() if counts_as_measurement(r)]
    assert records, "results/ carries no real-policy execution manifest with an end time"
    newest = max(records, key=lambda r: r.measured_at)
    assert newest.recorded is True, f"newest manifest is reconstructed: {newest.measured_at}"
    assert newest.policy == "smolvla"


def test_the_legacy_reconstructed_manifest_is_still_read_as_reconstructed() -> None:
    """The old manifest has not been quietly relabelled — it is still honest about itself.

    Fixing the badge must not work by upgrading the legacy artifact's provenance. It still reports
    `recorded=False`; it is simply no longer the newest thing in the tree.
    """
    records = measurements_from_results()
    legacy = [r for r in records if r.measured_at.endswith("T00:00:00Z")]
    assert legacy, "the legacy midnight-stamped manifest disappeared"
    assert all(not r.recorded for r in legacy)
