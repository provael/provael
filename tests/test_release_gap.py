"""The published-measurement window: the staleness signal the age badge cannot see.

WHY A SECOND WINDOW. `STALE_DAYS` asks when ANYTHING was last measured, and a one-episode timing
probe satisfies it. On 8 September 2026 a $0.06 probe put `watch/freshness.json` at "today" while
the published 44/50 headline was still the ten-task suite measured nine minors earlier. A reader
running `provael doctor` saw a green freshness row and had no way to learn that.

www.provael.com has carried this on every page — "the published result was measured with v0.32.0,
9 releases ago" — and the CLI could not say it. These tests pin the rule that makes the two agree.

THE PART THAT IS EASY TO GET WRONG is which record represents "the published measurement". The
newest one is the obvious choice and it is the wrong one, for exactly the reason above.
"""

from __future__ import annotations

from provael.watch import (
    STALE_AFTER_RELEASES,
    MeasurementRecord,
    campaigns,
    displacement,
    published_measurement,
    releases_behind,
    task_suite_of,
)

TEN_TASKS = tuple(f"libero_object/{i}" for i in range(10))


def _rec(
    version: str,
    attempts: int,
    measured_at: str,
    policy: str = "smolvla",
    tasks: tuple[str, ...] | None = None,
    suite: str = "libero",
) -> MeasurementRecord:
    return MeasurementRecord(
        policy=policy, suite=suite, tool_version=version,
        attempts=attempts, successes=0, asr=0.0,
        measured_at=measured_at, recorded=True, commit="abc1234", tasks=tasks,
    )


def test_a_tiny_probe_does_not_displace_a_large_campaign() -> None:
    """The regression this exists for, in miniature.

    A 350-episode campaign at 0.32.0 and a 1-episode probe at 0.40.0: the published number rests on
    the campaign, so that is the version a reader needs. Returning the probe's version would report
    0.40.0 and read as reassuring while being useless.
    """
    records = [
        _rec("0.40.0", 1, "2026-09-08T09:28:27Z"),
        *[_rec("0.32.0", 35, f"2026-08-09T09:4{i}:00Z") for i in range(10)],
    ]
    got = published_measurement(records)
    assert got is not None and got.tool_version == "0.32.0"


def test_a_genuinely_larger_run_at_a_newer_version_closes_the_gap() -> None:
    """The converse: the rule must not pin the past. No threshold edit should be needed."""
    records = [
        *[_rec("0.32.0", 35, f"2026-08-09T09:4{i}:00Z") for i in range(10)],
        *[_rec("0.42.0", 50, f"2026-10-01T09:4{i}:00Z") for i in range(10)],
    ]
    got = published_measurement(records)
    assert got is not None and got.tool_version == "0.42.0"


def test_equal_campaigns_break_toward_the_newer_version() -> None:
    """Two equally sized campaigns means the older is no longer the only thing carrying the claim."""
    records = [
        _rec("0.32.0", 100, "2026-08-09T09:40:00Z"),
        _rec("0.41.0", 100, "2026-09-08T09:40:00Z"),
    ]
    got = published_measurement(records)
    assert got is not None and got.tool_version == "0.41.0"


def test_a_fixture_run_is_not_a_published_measurement() -> None:
    """A stub backend executes real attacks in a second; it must never carry a published claim."""
    records = [_rec("0.41.0", 500, "2026-09-08T09:40:00Z", policy="stub"),
               _rec("0.32.0", 35, "2026-08-09T09:40:00Z")]
    got = published_measurement(records)
    assert got is not None and got.tool_version == "0.32.0", (
        "a 500-episode stub run outweighed a real 35-episode one — countsAsMeasurement was not applied"
    )


def test_no_real_measurement_reports_none_rather_than_a_zero_gap() -> None:
    """Nothing measured is not the same as measured-and-current, and zero is the reassuring answer."""
    assert published_measurement([]) is None


def test_release_gap_counts_minors() -> None:
    assert releases_behind("0.32.0", "0.41.0") == 9
    assert releases_behind("0.41.0", "0.41.0") == 0
    assert releases_behind("0.40.0", "0.41.0") == 1


def test_an_unparseable_version_reports_unknown_not_zero() -> None:
    """A gap of zero is the reassuring answer, so it must never be the fallback for a bad input."""
    assert releases_behind("weird", "0.41.0") is None
    assert releases_behind("0.32.0", "") is None


def test_a_measurement_ahead_of_the_release_clamps_to_zero() -> None:
    """Measuring on an unreleased build is ahead, not stale — a negative gap would render absurdly."""
    assert releases_behind("0.42.0", "0.41.0") == 0


def test_the_window_matches_the_one_the_site_publishes() -> None:
    """Two repos hold this threshold. If they drift, the CLI and the site disagree in public.

    The site's copy lives in `src/lib/freshness.ts` as `STALE_AFTER_RELEASES = 2`. There is no
    import across the two, so this is a pinned literal and a stated risk rather than a guarantee —
    see the constant's own note in `watch.py`.
    """
    assert STALE_AFTER_RELEASES == 2


def test_the_committed_ledger_is_past_the_window_today() -> None:
    """The live state, asserted so a re-measurement that closes the gap is noticed rather than assumed."""
    from provael import __version__

    got = published_measurement()
    assert got is not None, "no real measurement is committed"
    gap = releases_behind(got.tool_version, __version__)
    assert gap is not None
    assert gap > STALE_AFTER_RELEASES, (
        f"the published measurement (v{got.tool_version}) is now {gap} release(s) behind "
        f"{__version__}, within the {STALE_AFTER_RELEASES}-release window. If a real re-measurement "
        "landed, update this test and the CHANGELOG — the gap closing is news."
    )


# --------------------------------------------------------------------------- #
# the body rule: what a re-measurement has to be before its size counts
# --------------------------------------------------------------------------- #
#
# The size-only rule summed attempts per exact version. It was right about probes and wrong about
# the two things a scheduled lane does: it re-pins on every release, so its bucket reset before it
# could accumulate; and it ran one task, so even an accumulated bucket would have been a different
# measurement from the ten-task headline it was meant to refresh. These tests pin the stricter rule.


def _campaign(version: str, per_shard: int, day: str, tasks=TEN_TASKS) -> list[MeasurementRecord]:
    """Ten shards, one per task, at one version — the shape of the committed 0.32.0 body."""
    return [
        _rec(version, per_shard, f"{day}T09:4{i}:00Z", tasks=(task,))
        for i, task in enumerate(tasks)
    ]


def test_a_longer_run_on_fewer_tasks_does_not_displace_a_ten_task_campaign() -> None:
    """The hole in the size-only rule, closed.

    600 attempts on one task at 0.42.0 against 550 across ten tasks at 0.32.0. The old rule took the
    bigger bucket; a reader would then have been told the ten-task headline was measured with 0.42.0
    by a run that never touched nine of its tasks.
    """
    records = [
        *_campaign("0.32.0", 55, "2026-08-09"),
        _rec("0.42.0", 600, "2026-10-01T09:40:00Z", tasks=("libero_object/0",)),
    ]
    got = published_measurement(records)
    assert got is not None and got.tool_version == "0.32.0"


def test_a_re_measurement_of_every_task_at_least_as_large_displaces_it() -> None:
    """The converse, and the thing the scheduled lane is now built to produce."""
    records = [
        *_campaign("0.32.0", 55, "2026-08-09"),
        *_campaign("0.41.2", 55, "2026-10-20"),  # equal size, newer: the tie goes to it
    ]
    got = published_measurement(records)
    assert got is not None and got.tool_version == "0.41.2"


def test_a_body_accumulates_across_runs_at_one_version() -> None:
    """Slices land two a week; the body they build is one campaign, not twelve probes."""
    slices = [
        _rec("0.41.2", 45, f"2026-10-{day:02d}T04:30:00Z", tasks=TEN_TASKS[:5] if day % 2 else TEN_TASKS[5:])
        for day in range(1, 14)
    ]
    (body,) = campaigns(slices)
    assert body.attempts == 45 * 13
    assert body.runs == 13
    assert body.tasks == TEN_TASKS
    assert body.measured_at == "2026-10-13T04:30:00Z"


def test_a_body_never_spans_versions() -> None:
    """`provael.combine` refuses shards at different tool versions; the body rule must agree.

    Pooling 0.41.2 with 0.42.0 would produce a number no evidence manifest can be built over and
    no site can re-pin. The two stay separate bodies, and neither reaches the published one alone.
    """
    records = [
        *_campaign("0.32.0", 55, "2026-08-09"),
        *_campaign("0.41.2", 30, "2026-10-01"),
        *_campaign("0.42.0", 30, "2026-10-10"),
    ]
    versions = {b.tool_version: b.attempts for b in campaigns(records)}
    assert versions == {"0.32.0": 550, "0.41.2": 300, "0.42.0": 300}
    got = published_measurement(records)
    assert got is not None and got.tool_version == "0.32.0"


def test_the_challenger_is_the_newer_body_nearest_to_superseding() -> None:
    """A covering body beats a bigger narrow one: only the covering one can ever displace."""
    records = [
        *_campaign("0.32.0", 55, "2026-08-09"),
        _rec("0.42.0", 600, "2026-10-01T09:40:00Z", tasks=("libero_object/0",)),
        *_campaign("0.43.0", 10, "2026-10-10"),
    ]
    standing = displacement(records)
    assert standing is not None and standing.challenger is not None
    assert standing.challenger.tool_version == "0.43.0"
    assert standing.attempts_needed == 450
    assert standing.tasks_missing == ()


def test_the_challenger_reports_what_it_still_lacks() -> None:
    """Both deficits, because the lane has to close both and a reader should see which is open."""
    records = [
        *_campaign("0.32.0", 55, "2026-08-09"),
        _rec("0.41.2", 14, "2026-09-11T09:35:46Z", tasks=("libero_object/0",)),
        _rec("0.41.2", 14, "2026-09-15T10:06:35Z", tasks=("libero_object/0",)),
    ]
    standing = displacement(records)
    assert standing is not None and standing.challenger is not None
    assert standing.challenger.attempts == 28
    assert standing.attempts_needed == 550 - 28
    assert standing.tasks_missing == TEN_TASKS[1:]


def test_no_newer_body_means_no_challenger_rather_than_a_zero_deficit() -> None:
    """A deficit of zero reads as "done"; the absence of a challenger must not be rendered as one."""
    standing = displacement(_campaign("0.32.0", 55, "2026-08-09"))
    assert standing is not None
    assert standing.challenger is None
    assert standing.attempts_needed is None
    assert standing.tasks_missing is None


def test_a_different_policy_is_a_different_lineage() -> None:
    """A body at another policy cannot supersede this one, however large — it measures something else."""
    records = [
        *_campaign("0.32.0", 55, "2026-08-09"),
        *_campaign("0.42.0", 70, "2026-10-01"),
    ]
    records[-1] = _rec("0.42.0", 70, "2026-10-01T09:49:00Z", policy="pi05", tasks=TEN_TASKS)
    standing = displacement(records)
    assert standing is not None
    # The 0.42.0 smolvla body is short one shard (nine tasks); the pi05 record is another lineage.
    assert standing.published.tool_version == "0.32.0"
    assert standing.challenger is not None and standing.challenger.policy == "smolvla"


SPATIAL_TASKS = tuple(f"libero_spatial/{i}" for i in range(10))


def test_a_different_libero_task_suite_is_a_different_lineage() -> None:
    """LIBERO Spatial, Goal and 10 runs at 0.41.2 neither join nor raise the Object body.

    The 14 September 2026 ledger: the ten-task Object suite plus its control at 0.41.2, and ten
    Spatial nulls the same night. Pooled by (policy, suite, version) alone those would have made
    one 33-task body that every future Object re-measurement had to re-run in full. The adapter
    refuses to run two task suites as one job ("one run is one suite"), so the body is keyed the
    same way: Spatial is its own lineage, the Object body supersedes the 0.32.0 Object body on its
    own, and the Spatial body's attempts appear in neither.
    """
    records = [
        *_campaign("0.32.0", 55, "2026-08-09"),
        *_campaign("0.41.2", 56, "2026-09-14"),
        *_campaign("0.41.2", 6, "2026-09-14", tasks=SPATIAL_TASKS),
    ]
    bodies = campaigns(records)
    assert {(b.task_suite, b.tool_version, b.attempts) for b in bodies} == {
        ("libero_object", "0.32.0", 550),
        ("libero_object", "0.41.2", 560),
        ("libero_spatial", "0.41.2", 60),
    }
    standing = displacement(records)
    assert standing is not None
    assert standing.published.task_suite == "libero_object"
    assert standing.published.tool_version == "0.41.2"
    assert standing.published.attempts == 560
    assert standing.published.tasks == TEN_TASKS
    assert standing.challenger is None


def test_a_task_suite_is_read_off_the_task_ids() -> None:
    assert task_suite_of(("libero_object/0", "libero_object/7")) == "libero_object"
    assert task_suite_of(("libero_10/2",)) == "libero_10"
    assert task_suite_of(None) is None
    assert task_suite_of(()) is None
    # Bare ids carry no task suite; a list that mixes two is not one run's, and gets none either.
    assert task_suite_of(("3", "4")) is None
    assert task_suite_of(("libero_object/0", "libero_spatial/0")) is None
    assert task_suite_of(("libero_object/0", "3")) is None


def test_the_committed_ledger_has_a_challenger_that_cannot_yet_displace() -> None:
    """The live state: the canary body exists, is newer, and is short on both axes.

    Asserted structurally rather than by number, because every scheduled run changes the numbers
    and this test must stay true while the lane does its job. What must NOT change without a
    deliberate edit here: that a challenger exists at all, and that it is not yet the published
    measurement. The day it is, the site re-pins and this test is rewritten — that is the news.
    """
    standing = displacement()
    assert standing is not None
    assert standing.published.tool_version == "0.32.0"
    assert standing.published.tasks == TEN_TASKS
    assert standing.challenger is not None, "no re-measurement is committed at a newer version"
    assert standing.attempts_needed is not None and standing.attempts_needed > 0
