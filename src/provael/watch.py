# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
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
from collections.abc import Sequence
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

#: Minor releases the PUBLISHED measurement may fall behind the current version before it is stale.
#:
#: A SECOND WINDOW, MEASURING SOMETHING THE AGE WINDOW CANNOT. `STALE_DAYS` asks when anything was
#: last measured; a one-episode timing probe satisfies it. This asks whether the number a reader is
#: actually shown was measured against code that still exists. The two came apart on 8 September
#: 2026: a $0.06 probe put the badge at "today" while the published 44/50 result was nine minors
#: old, and only this window could say so.
#:
#: PUBLISHED, so a consumer reads the rule instead of keeping a copy. `watch/release.json` carries
#: it as `staleAfterReleases`, and `test_release_artifact.py` fails if the two disagree.
#: www.provael.com held its own `STALE_AFTER_RELEASES = 2` in TypeScript for exactly as long as
#: there was nothing to read — one policy constant in two repositories, where a disagreement is
#: invisible from both sides because neither can see the other.
STALE_AFTER_RELEASES = 2

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
    #: The task ids the run covered, from the report's own ``tasks`` field, sorted and
    #: de-duplicated. ``None`` when no report could be read. Coverage is what a re-measurement has
    #: to match before its size counts — see :func:`displacement` — so it travels with the record
    #: rather than being re-derived by every consumer from ``report.json``.
    tasks: tuple[str, ...] | None = None


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
        tasks=tuple(sorted(set(report.tasks))),
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
        tasks: tuple[str, ...] | None = None
        if report.is_file():
            try:
                r = json.loads(report.read_text(encoding="utf-8"))
                attempts, successes = int(r.get("attempts", 0)), int(r.get("successes", 0))
                asr = float(r.get("asr", 0.0))
                raw_tasks = r.get("tasks")
                if isinstance(raw_tasks, list):
                    tasks = tuple(sorted({str(t) for t in raw_tasks}))
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
                tasks=tasks,
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


def _minor(version: str) -> tuple[int, int] | None:
    """``"0.32.0"`` -> ``(0, 32)``. ``None`` for anything that is not ``major.minor[.patch]``."""
    parts = version.split(".")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _semver(version: str) -> tuple[int, int, int]:
    """``"0.41.2"`` -> ``(0, 41, 2)``; an unparseable version sorts oldest, never newest.

    Oldest, because every rule below breaks ties toward the NEWER version and "newer" is the
    reassuring answer. A version string nobody can parse must not win a tie by accident.
    """
    parts = version.split(".")
    try:
        nums = [int(x) for x in parts[:3]]
    except ValueError:
        return (0, 0, 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def task_suite_of(tasks: Sequence[str] | None) -> str | None:
    """The one ``<task suite>/`` prefix a run's tasks share — ``"libero_object"`` — or ``None``.

    LIBERO is four benchmarks behind one adapter, and the adapter refuses a task list that names
    more than one of them (:func:`provael.suites.libero.suite_and_ids_from_tasks`: "one run is one
    suite"). The task id carries which one, so a body of runs carries it too. ``None`` when the
    tasks are unknown, carry no prefix (``stub``, ``reach``), or — against the adapter's own rule —
    mix prefixes; a ``None`` lineage is compared only with other ``None`` lineages.
    """
    if not tasks:
        return None
    prefixes = {t.rsplit("/", 1)[0] for t in tasks if "/" in t}
    if len(prefixes) != 1 or any("/" not in t for t in tasks):
        return None
    return prefixes.pop()


class Campaign(BaseModel):
    """One body of measurement: every real recorded run at one lineage and tool version.

    A lineage is a policy, a suite and — where the task ids carry one — a task suite:
    ``smolvla`` x ``libero`` x ``libero_object``. This is the unit the published-measurement rule
    reasons about, and it is a *version's* body on purpose. :mod:`provael.combine` refuses to pool
    shards whose ``tool_version`` differs, because a rate over two builds describes a run that
    never happened — so a body that could be cited, re-pinned by www.provael.com, or turned into
    an evidence manifest is by construction a body at one version. Accumulating across versions
    would produce a number nothing can stand behind; accumulating at one version is a campaign,
    and that is what the scheduled lane builds.

    WHY THE TASK SUITE IS PART OF THE KEY. On 14 September 2026 SmolVLA was measured on LIBERO
    Object, Spatial, Goal and 10 in one night, all at 0.41.2. Keyed by (policy, suite, version)
    alone, those four benchmarks pooled into one 794-attempt body over 33 tasks at four horizons,
    and every future re-measurement of the ten-task Object headline would have had to re-run all
    33 to supersede it — a bar no plan could state a horizon for, and one the LIBERO adapter
    itself refuses to run as one job. The adapter's rule ("one run is one suite") is the honest
    unit: a Spatial null is not part of the Object campaign, and does not raise its bar.
    """

    policy: str
    suite: str
    #: The ``<task suite>/`` prefix every task of the body shares (:func:`task_suite_of`), or
    #: ``None`` when the suite's task ids carry none.
    task_suite: str | None = None
    tool_version: str
    #: Summed over the body's runs. ``attempts`` is the report's own count of applicable episodes
    #: across every arm, controls included — the same figure every run publishes about itself.
    attempts: int
    successes: int
    #: How many runs (committed report directories) the body is made of.
    runs: int
    #: Sorted union of the task ids its runs covered; ``None`` when no run recorded any.
    tasks: tuple[str, ...] | None
    #: The instant of the body's newest run — the record that represents it.
    measured_at: str

    @property
    def lineage(self) -> tuple[str, str, str | None]:
        """What a body is a measurement *of*: policy, suite, task suite."""
        return (self.policy, self.suite, self.task_suite)

    def covers(self, other: Campaign) -> bool:
        """Whether this body re-measures what ``other`` measured.

        Same lineage, and every task ``other`` covered. A body whose tasks are unknown cannot be
        shown to cover anything, and a body nothing is recorded for is covered by anything at the
        same lineage — there is nothing to protect.
        """
        if self.lineage != other.lineage:
            return False
        if not other.tasks:
            return True
        return self.tasks is not None and set(other.tasks) <= set(self.tasks)

    def tasks_missing(self, other: Campaign) -> tuple[str, ...]:
        """The tasks ``other`` covered that this body has not — what it still has to run."""
        return tuple(t for t in (other.tasks or ()) if t not in set(self.tasks or ()))

    def supersedes(self, other: Campaign) -> bool:
        """Whether this body displaces ``other`` as the published measurement.

        Covers it, and is at least as large — with an exact tie going to the newer version, since
        two equally sized campaigns means the older one is no longer the only thing carrying the
        claim. A probe cannot displace a campaign; neither can a larger run on fewer tasks, which
        is the case the size-only rule got wrong: a single-task run of any length is a different
        measurement from a ten-task one, not a bigger version of it.
        """
        if not self.covers(other) or self.attempts < other.attempts:
            return False
        return self.attempts > other.attempts or _semver(self.tool_version) > _semver(
            other.tool_version
        )


class Displacement(BaseModel):
    """The published measurement, the body closest to displacing it, and what that body lacks.

    Published so the lane that produces the challenger can be read against the number it has to
    reach. Before this, a reader could see that the published measurement was nine minors old and
    that a canary ran twice a week, and had no way to learn that the canary was accumulating
    fourteen attempts a run toward a body it structurally could not reach — its version bucket
    reset on every release.
    """

    published: Campaign
    #: The newer body at the published measurement's lineage that is nearest to superseding it —
    #: covering bodies first, then the largest, then the newest. ``None`` when nothing newer at
    #: that lineage has been measured.
    challenger: Campaign | None
    #: Attempts the challenger still needs before its size alone would displace the published
    #: body (a tie displaces, because the challenger is newer). ``None`` without a challenger.
    attempts_needed: int | None
    #: Tasks the published body covered that the challenger has not yet run. ``None`` without a
    #: challenger; empty when coverage is already met and only size remains.
    tasks_missing: tuple[str, ...] | None


def campaigns(records: Sequence[MeasurementRecord]) -> list[Campaign]:
    """Real, recorded records grouped into bodies by (lineage, tool version), oldest first.

    Fixture runs and reconstructed timestamps are excluded here, once, so no caller can build a
    body out of a stub run or date one from a typed midnight.
    """
    groups: dict[tuple[str, str, str | None, str], list[MeasurementRecord]] = {}
    for r in records:
        if counts_as_measurement(r) and r.recorded:
            key = (r.policy, r.suite, task_suite_of(r.tasks), r.tool_version)
            groups.setdefault(key, []).append(r)
    bodies: list[Campaign] = []
    for (policy, suite, task_suite, version), runs in groups.items():
        known = [r.tasks for r in runs if r.tasks is not None]
        tasks = tuple(sorted({t for ts in known for t in ts})) if known else None
        bodies.append(
            Campaign(
                policy=policy,
                suite=suite,
                task_suite=task_suite,
                tool_version=version,
                attempts=sum(r.attempts for r in runs),
                successes=sum(r.successes for r in runs),
                runs=len(runs),
                tasks=tasks,
                measured_at=max(r.measured_at for r in runs),
            )
        )
    bodies.sort(key=lambda b: (_semver(b.tool_version), b.policy, b.suite, b.task_suite or ""))
    return bodies


def displacement(
    records: Sequence[MeasurementRecord] | None = None,
    *,
    results_dir: Path = RESULTS_DIR,
) -> Displacement | None:
    """What a reader is shown, and what it would take to replace it.

    THE RULE. Among real recorded bodies (:func:`campaigns`), the published measurement is the
    largest body that no other body supersedes (:meth:`Campaign.supersedes`): to supersede is to
    re-measure the same lineage (policy, suite, task suite) over every task the body covered,
    with at least as many attempts. Where more than one body is unsuperseded — two measurements
    of different things — the broadest wins, then the largest, then the newest.

    WHAT CHANGED, AND IN WHICH DIRECTION. The rule used to sum attempts per exact version and take
    the largest bucket. That was right about probes and wrong in two ways that only show up once a
    lane runs on a schedule. A bucket keyed by exact version resets on every release, so a canary
    that re-pins each release accumulates toward nothing; and a bucket counts a single-task run
    and a ten-task run in the same unit, so a long enough run on one task would have displaced the
    ten-task headline. The new rule is stricter, never looser: nothing that displaced under the
    old rule fails to under this one except a body that does not cover what it would replace.

    The first problem is not solved here and cannot be — see :class:`Campaign` for why a body is
    one version's. It is solved by the lane holding its pin until the body at that pin supersedes
    the published one (``examples/gpu-ci/modal_provael_gpu.py``), and this function publishes how
    far along that is.

    Returns ``None`` when nothing real has been measured, which is not the same as a gap of zero.
    """
    real = records if records is not None else measurements_from_results(results_dir)
    bodies = campaigns(real)
    if not bodies:
        return None
    standing = [b for b in bodies if not any(o is not b and o.supersedes(b) for o in bodies)]
    published = max(
        standing,
        key=lambda b: (len(b.tasks or ()), b.attempts, _semver(b.tool_version)),
    )
    newer = [
        b
        for b in bodies
        if b.lineage == published.lineage
        and _semver(b.tool_version) > _semver(published.tool_version)
    ]
    challenger = (
        max(newer, key=lambda b: (b.covers(published), b.attempts, _semver(b.tool_version)))
        if newer
        else None
    )
    return Displacement(
        published=published,
        challenger=challenger,
        attempts_needed=(
            None if challenger is None else max(0, published.attempts - challenger.attempts)
        ),
        tasks_missing=None if challenger is None else challenger.tasks_missing(published),
    )


def published_measurement(
    records: Sequence[MeasurementRecord] | None = None,
    *,
    results_dir: Path = RESULTS_DIR,
) -> MeasurementRecord | None:
    """The real-model measurement a reader is actually shown — the published body, not the newest.

    WHY NOT THE NEWEST. :func:`latest_measurement` answers "when was anything last measured", and a
    one-episode timing probe answers it. On 8 September 2026 a $0.06 probe made the freshness badge
    read "today" while the published 44/50 headline was still the ten-task suite fitted nine minors
    earlier. Reporting the newest record's version would have said 0.40.0 and been useless — worse
    than useless, because it would have looked reassuring.

    So: the newest record of the published body (:func:`displacement`) represents it. A campaign
    of 350 episodes is what a published rate rests on; a probe cannot displace it, a longer run on
    fewer tasks cannot displace it, and a genuinely bigger re-measurement of the same tasks at a
    newer version closes the gap on its own without anyone editing a threshold.

    Returns ``None`` when nothing real has been measured, which is not the same as a gap of zero.
    """
    real = [
        r
        for r in (records if records is not None else measurements_from_results(results_dir))
        if counts_as_measurement(r) and r.recorded
    ]
    standing = displacement(real)
    if standing is None:
        return None
    body = standing.published
    # The full lineage, not (policy, suite, version): the LIBERO-10 shards that finished on the
    # morning of 18 September 2026 were newer than the Object body's newest run and shared its
    # policy, suite and version, and would have been returned as the record representing a body
    # they are not part of.
    return max(
        (
            r
            for r in real
            if (r.policy, r.suite, task_suite_of(r.tasks), r.tool_version)
            == (body.policy, body.suite, body.task_suite, body.tool_version)
        ),
        key=lambda r: r.measured_at,
    )


def releases_behind(measured_with: str, current: str) -> int | None:
    """Minor releases between the version a result was measured with and the current one.

    ``None`` when either version is unparseable, so an odd string reports "unknown" rather than
    silently scoring zero — a gap of zero is the reassuring answer and must never be the fallback.
    Negative gaps clamp to 0: a measurement taken on an unreleased build is ahead, not stale.
    """
    a, b = _minor(measured_with), _minor(current)
    if a is None or b is None:
        return None
    return max(0, (b[0] - a[0]) * 1000 + (b[1] - a[1]))


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
    # The colour is derived from the SAME whole-day count the message states, not from the
    # fractional age. At age 2.3 the old rule wrote "2 days ago" in orange: a reader saw a day
    # count inside the fresh window painted stale, and the guard that recomputes the badge at the
    # age the message asserts (tests/test_watch.py) read 2 days as green and failed every PR for the
    # ~17 hours until the count ticked over — observed 14 Sep 2026 on the badge committed 13 Sep.
    # A badge whose two halves disagree is wrong whichever half a reader trusts.
    if record.recorded:
        message = when
        color = "brightgreen" if days <= FRESH_DAYS else ("orange" if days <= STALE_DAYS else "red")
    else:
        # The date is a reconstruction, so it is reported with its provenance and capped at amber.
        # A reader who sees a green badge is entitled to assume the timestamp was observed.
        message = f"{when} (date reconstructed)"
        color = "orange" if days <= STALE_DAYS else "red"
    return {
        "schemaVersion": SHIELDS_SCHEMA_VERSION,
        "label": "last measured",
        "message": message,
        "color": color,
        "isError": days > STALE_DAYS,
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
    "STALE_AFTER_RELEASES",
    "published_measurement",
    "releases_behind",
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
