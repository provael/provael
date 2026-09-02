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

#: Committed run directories scanned for a real measurement timestamp. See
#: docs/standards/last-measured.md for the definition this implements.
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"

#: An execution manifest declaring this evidence state had its provenance reconstructed after the
#: fact rather than recorded by the run. Its timestamps are day-granularity at best.
LEGACY_STATE = "legacy-unverified"

#: Shields.io endpoint-schema version (the only value shields accepts).
SHIELDS_SCHEMA_VERSION = 1

#: Age thresholds in days. At or under `FRESH_DAYS` the badge is green; past `STALE_DAYS` it is
#: red. Between them it is amber — "nobody has measured this week" is worth seeing before it
#: becomes "nobody has measured this month".
FRESH_DAYS = 2
STALE_DAYS = 7

WATCH_LOG = "watch.jsonl"
BADGE_JSON = "freshness.json"

#: The two artifact names a completed run writes, named ONCE so the reader here and the writer in
#: :func:`provael.cli._emit_execution_manifest` cannot drift apart.
#:
#: They were previously string literals in both halves. Both were correct and the badge still went
#: stale for two months, because agreeing on a NAME does not guarantee both files are present: a
#: suite result was committed with ten ``report.json`` files and zero manifests, and since the
#: report is deterministic and deliberately carries no timestamp, those measurements were invisible
#: to this module. ``tests/test_watch_artifact_binding.py`` asserts every committed report ships its
#: manifest, and that the count this module sees matches the count on disk.
REPORT = "report.json"
EXECUTION_MANIFEST = "execution-manifest.json"


class MeasurementRecord(BaseModel):
    """One completed measurement — the run-level unit the ledger's trial records roll up into."""

    measured_at: str = Field(..., description="UTC ISO-8601 (…Z) when the run was measured.")
    #: False when the manifest's timestamp was reconstructed rather than recorded by the run —
    #: identical start/end, exact midnight, or a `legacy-unverified` evidence state. A
    #: reconstructed timestamp can never earn a green badge; see docs/standards/last-measured.md.
    recorded: bool = True
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


def _is_recorded(manifest: dict[str, object]) -> bool:
    """Whether a manifest's timestamp was RECORDED by the run rather than reconstructed later.

    Two tells, either of which means the value is a day-granularity reconstruction and must not be
    presented as a measurement instant (see docs/standards/last-measured.md):

    * ``evidence_state`` is ``legacy-unverified`` — the manifest says so itself.
    * ``ended_at`` lands on exact midnight UTC — a date that was typed, not observed.

    ``started_at == ended_at`` is deliberately NOT a tell, though it looks like one. Manifests are
    stamped at second granularity, so any run finishing in under a second — every CPU stub run —
    legitimately records identical instants. Treating that as reconstruction would misclassify the
    fastest and most reproducible runs in the project as the least trustworthy. Caught by the
    sim-to-real dry-run asserting its own artifact shape, which is what that assertion is for.
    """
    if manifest.get("evidence_state") == LEGACY_STATE:
        return False
    ended = manifest.get("ended_at")
    if not isinstance(ended, str) or not ended:
        return False
    return not ended.endswith("T00:00:00Z")


def measurements_from_results(results_dir: Path = RESULTS_DIR) -> list[MeasurementRecord]:
    """Measurements read from committed execution manifests.

    The execution manifest is the ONLY artifact that can answer this. ``report.json`` deliberately
    carries no timestamp — the determinism contract makes a report a pure function of its config, so
    the same seed yields byte-identical bytes — which is the right trade and also means a report can
    never source this badge. The manifest exists precisely to hold runtime provenance.

    Each record carries ``recorded``, so a caller cannot accidentally treat a reconstructed date as
    a measured instant.
    """
    out: list[MeasurementRecord] = []
    if not results_dir.is_dir():
        return out
    for path in sorted(results_dir.rglob(EXECUTION_MANIFEST)):
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - malformed committed artifact
            continue
        ended = m.get("ended_at")
        if not isinstance(ended, str) or not ended:
            continue  # a manifest with no end time measures nothing this badge can report
        report = path.parent / REPORT
        attempts = successes = 0
        asr = 0.0
        if report.is_file():
            try:
                r = json.loads(report.read_text(encoding="utf-8"))
                attempts, successes = int(r.get("attempts", 0)), int(r.get("successes", 0))
                asr = float(r.get("asr", 0.0))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):  # pragma: no cover
                pass
        out.append(
            MeasurementRecord(
                measured_at=ended,
                recorded=_is_recorded(m),
                policy=str(m.get("policy", "unknown")),
                suite=str(m.get("suite", "unknown")),
                tool_version=str(m.get("package_version", "unknown")),
                attempts=attempts,
                successes=successes,
                asr=asr,
                commit=m.get("commit") if isinstance(m.get("commit"), str) else None,
            )
        )
    return out


#: Backends that are FIXTURES, not policies. A run against one of these is not a measurement of
#: anything this badge claims to track.
FIXTURE_POLICIES: frozenset[str] = frozenset({"stub"})


def counts_as_measurement(record: MeasurementRecord) -> bool:
    """Whether a record may refresh the freshness signal.

    ONLY A REAL-POLICY RUN COUNTS, and this function exists because the alternative was available
    and tempting. The badge asks "when was a policy last red-teamed". A run against the
    deterministic ``stub`` satisfies the letter of that — the stub is a registered policy and such a
    run does execute attacks against it — takes under a second on CPU, and would turn the badge
    green today with nothing re-measured.

    That is the same error as rebuilding the leaderboard and calling it a measurement, which this
    module's own docstring already refuses. `docs/standards/last-measured.md` wrote the refusal down
    on 21 August; this is the code that enforces it, added the moment a stub study was committed
    under `results/` and the badge silently went from "11 days ago" to "today".

    A fixture run is still a real artifact and still belongs under `results/`. It just cannot be the
    thing that says a policy was measured.
    """
    return record.policy not in FIXTURE_POLICIES


def latest_measurement(
    watch_dir: Path, *, results_dir: Path = RESULTS_DIR
) -> MeasurementRecord | None:
    """The newest measurement by ``measured_at``, across the watch log AND committed runs.

    Both sources, because they answer the same question at different times. The watch log is what a
    nightly appends going forward; the committed manifests are the measurements that already
    happened. Reading only the log is why this badge shipped saying "never" on a project with a
    published 10/10 result — the log was empty because the nightly has never run, and the badge
    reported that as "nothing was ever measured", which is false.
    """
    records = [
        r
        for r in (*read_measurements(watch_dir), *measurements_from_results(results_dir))
        if counts_as_measurement(r)
    ]
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

    THREE STATES, AND THE MIDDLE ONE IS THE POINT. See docs/standards/last-measured.md for the
    definition; the colour rules follow from it:

    * **No measurement anywhere** — "never", red, ``isError``. Reserved for the genuine case. This
      badge shipped in that state on a project with a published 10/10 real-policy result, because it
      read only the nightly's log and the nightly has never run. "Never" contradicting the flagship
      claim is a worse error than an imprecise date.
    * **Reconstructed timestamp** — the date, marked, and **never green**. Green would assert a
      precision the artifact does not have: the one committed real-policy manifest reconstructs its
      provenance after the fact (identical start/end at exact midnight, ``legacy-unverified``).
      Amber while fresh, red once genuinely stale.
    * **Recorded timestamp** — the ordinary age ladder, green when fresh.

    ``isError`` past :data:`STALE_DAYS` makes the badge read as a failure rather than a fact:
    at that point the README's implicit "continuously verified" has stopped being true.
    """
    age = age_days(record, now=now)
    if age is None or record is None:
        return {
            "schemaVersion": SHIELDS_SCHEMA_VERSION,
            "label": "last measured",
            "message": "never",
            "color": "red",
            "isError": True,
        }
    days = int(age)
    when = "today" if days == 0 else ("1 day ago" if days == 1 else f"{days} days ago")
    if record.recorded:
        message = when
        color = "brightgreen" if age <= FRESH_DAYS else ("orange" if age <= STALE_DAYS else "red")
    else:
        # The date is a reconstruction, so it is reported with its provenance and capped at amber.
        # A reader who sees a green badge is entitled to assume the timestamp was observed.
        message = f"{when} (date reconstructed)"
        color = "orange" if age <= STALE_DAYS else "red"
    return {
        "schemaVersion": SHIELDS_SCHEMA_VERSION,
        "label": "last measured",
        "message": message,
        "color": color,
        "isError": age > STALE_DAYS,
        # Shields caches endpoint responses; 1h keeps the badge honest without hammering the host.
        "cacheSeconds": 3600,
        # Not for shields, which ignores unknown keys. `message` is a rendered human string
        # ("22 days ago"), and provael.com was parsing it to decide whether to fail its own build —
        # its freshness module says so in its header, and calls an ISO timestamp here the right
        # long-term fix. A structural fact carried as prose is one wording change away from an
        # unparseable age, and the consumer closed that failure by throwing. This gives it the
        # date instead. Consumers should prefer `measuredAt` and keep `message` for display.
        "measuredAt": record.measured_at,
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
    "LEGACY_STATE",
    "MeasurementRecord",
    "RESULTS_DIR",
    "measurements_from_results",
    "append_measurement",
    "read_measurements",
    "latest_measurement",
    "age_days",
    "badge",
    "write_badge",
]
