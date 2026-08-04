"""Continuous-measurement watch: a freshness signal that decays on its own.

A point-in-time scan and a continuously-verified claim are different products, and only the second
one is referenceable — a standards body citing "Provael measured X" needs to know whether X was
measured last night or last quarter. The repo already had the raw material (an append-only trial
ledger, a per-checkpoint regression differ) and no way to answer "how old is the newest number?"
without reading JSON by hand. The published board sat a month stale and nothing surfaced it.

WHY THE BADGE COLOUR IS COMPUTED AT REFRESH TIME, NOT AT MEASUREMENT TIME. The obvious design —
have the nightly measurement emit a green badge — fails in exactly the case the badge exists for:
if the nightly dies, nothing regenerates the file, and the badge stays frozen on the last green it
ever wrote. A freshness indicator that cannot go stale-red is worse than none, because it
actively asserts currency it is not checking.

So the age is recomputed on every refresh from the *recorded measurement time*, and the refresh is
a cheap CPU job that runs on its own schedule, independent of whether any measurement happened
(``.github/workflows/freshness.yml``). The badge therefore reddens by itself the moment
measurements stop — which is the only behaviour that makes it worth putting in a README.

The thresholds are days, not runs: "7 releases behind" stopped meaning anything when the release
cadence went daily, and the same trap applies here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from provael.ledger import append_results
from provael.types import RunReport

#: Shields.io endpoint-schema version (the only value shields accepts).
SHIELDS_SCHEMA_VERSION = 1

#: Age thresholds in days. At or under `FRESH_DAYS` the badge is green; past `STALE_DAYS` it is
#: red. Between them it is amber — "nobody has measured this week" is worth seeing before it
#: becomes "nobody has measured this month".
FRESH_DAYS = 2
STALE_DAYS = 7

WATCH_LOG = "watch.jsonl"
BADGE_JSON = "freshness.json"


class MeasurementRecord(BaseModel):
    """One completed measurement — the run-level unit the ledger's trial records roll up into."""

    measured_at: str = Field(..., description="UTC ISO-8601 (…Z) when the run was measured.")
    policy: str
    suite: str
    tool_version: str
    attempts: int
    successes: int
    asr: float
    #: The run's own commit/id, so a badge can be traced back to the artifact behind it.
    commit: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def append_measurement(
    watch_dir: Path, report: RunReport, *, measured_at: str | None = None, commit: str | None = None
) -> MeasurementRecord:
    """Append ``report`` to the trial ledger and to the run-level watch log.

    Both, deliberately: the trial ledger is the resumable per-episode record and stays the source
    of truth for what ran, while the watch log is the roll-up a freshness check can read without
    replaying every trial. The trial ledger is appended through
    :func:`provael.ledger.append_results` rather than a second writer, so there is one format for
    trial history.
    """
    watch_dir.mkdir(parents=True, exist_ok=True)
    append_results(watch_dir / "trials.jsonl", report.results)
    record = MeasurementRecord(
        measured_at=measured_at or _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        policy=report.policy,
        suite=report.suite,
        tool_version=report.tool_version,
        attempts=report.attempts,
        successes=report.successes,
        asr=report.asr,
        commit=commit,
    )
    line = json.dumps(record.model_dump(), sort_keys=True, separators=(",", ":"))
    with (watch_dir / WATCH_LOG).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return record


def read_measurements(watch_dir: Path) -> list[MeasurementRecord]:
    """Every recorded measurement, oldest first. Missing/blank log reads as no measurements."""
    path = watch_dir / WATCH_LOG
    if not path.is_file():
        return []
    records = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            records.append(MeasurementRecord.model_validate_json(raw))
    return records


def latest_measurement(watch_dir: Path) -> MeasurementRecord | None:
    """The newest measurement by ``measured_at`` (not by file order — appends can interleave)."""
    records = read_measurements(watch_dir)
    return max(records, key=lambda r: r.measured_at) if records else None


def age_days(record: MeasurementRecord | None, *, now: datetime | None = None) -> float | None:
    """Whole-and-fractional days since ``record`` was measured; ``None`` when never measured."""
    if record is None:
        return None
    measured = datetime.fromisoformat(record.measured_at.replace("Z", "+00:00"))
    return max(0.0, ((now or _now()) - measured).total_seconds() / 86400.0)


def badge(record: MeasurementRecord | None, *, now: datetime | None = None) -> dict[str, object]:
    """A shields.io *endpoint* payload for the last-measured age.

    Rendered by pointing shields at the published file::

        https://img.shields.io/endpoint?url=<raw url to freshness.json>

    ``isError`` is set past :data:`STALE_DAYS` so the badge reads as a failure, not a fact: at that
    point the README's implicit claim ("this is continuously verified") has stopped being true.
    """
    age = age_days(record, now=now)
    if age is None:
        return {
            "schemaVersion": SHIELDS_SCHEMA_VERSION,
            "label": "last measured",
            "message": "never",
            "color": "red",
            "isError": True,
        }
    days = int(age)
    message = "today" if days == 0 else ("1 day ago" if days == 1 else f"{days} days ago")
    color = "brightgreen" if age <= FRESH_DAYS else ("orange" if age <= STALE_DAYS else "red")
    return {
        "schemaVersion": SHIELDS_SCHEMA_VERSION,
        "label": "last measured",
        "message": message,
        "color": color,
        "isError": age > STALE_DAYS,
        # Shields caches endpoint responses; 1h keeps the badge honest without hammering the host.
        "cacheSeconds": 3600,
    }


def write_badge(watch_dir: Path, *, now: datetime | None = None) -> tuple[Path, dict[str, object]]:
    """Recompute the freshness badge from the recorded measurements and write it."""
    watch_dir.mkdir(parents=True, exist_ok=True)
    payload = badge(latest_measurement(watch_dir), now=now)
    path = watch_dir / BADGE_JSON
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path, payload


__all__ = [
    "BADGE_JSON",
    "FRESH_DAYS",
    "STALE_DAYS",
    "WATCH_LOG",
    "MeasurementRecord",
    "append_measurement",
    "read_measurements",
    "latest_measurement",
    "age_days",
    "badge",
    "write_badge",
]
