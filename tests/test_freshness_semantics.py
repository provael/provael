"""What "freshest measurement" means, pinned — because it was just misread (#136-adjacent).

THE MISREADING THIS EXISTS TO STOP. The badge went red, and the natural reading was "the badge is
broken, a ten-task run landed on 2026-08-17". It did not. The commit that day (eaba9c7) rebuilt
the leaderboard from artifacts already in the tree and touched ZERO files under results/. A
republication is not a measurement, and the badge was right.

That is the same distinction Leaderboard.is_restamp() draws on the board side: re-running a
generator moves generated_at while every row still carries the measurement it always had. The
failure mode here is worse than a wrong number, because the obvious "fix" — dating freshness from
a commit, a file mtime, or a board's generated_at — would turn the badge permanently green while
the measurements aged. A freshness signal that cannot go stale is not a freshness signal.

So: the age of the newest MEASUREMENT is the newest execution-manifest timestamp under results/.
report.json cannot supply it and must not be made to: it is deterministic by contract and
deliberately carries no wall-clock, which is exactly why the manifest exists.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from provael.watch import measurements_from_results

_ROOT = Path(__file__).resolve().parent.parent
_RESULTS = _ROOT / "results"
_BADGE = _ROOT / "watch" / "freshness.json"


def test_freshness_reads_execution_manifests_not_commits_or_mtimes() -> None:
    """The newest measurement must be traceable to a manifest timestamp in the tree."""
    measurements = measurements_from_results(_RESULTS)
    assert measurements, "no measurements discovered under results/"
    newest = max(str(m.measured_at) for m in measurements)
    stamps: set[str] = set()
    for path in _RESULTS.rglob("execution-manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for key in ("ended_at", "started_at", "measured_at"):
            value = manifest.get(key)
            if value:
                stamps.add(str(value))
    assert newest in stamps, (
        f"the newest measurement {newest} is not any committed execution manifest's timestamp — "
        "freshness has started reading something that is not a measurement"
    )


def test_report_json_carries_no_timestamp_to_date_a_measurement_from() -> None:
    """Pins WHY the manifest is the source: report.json is deterministic and has no clock.

    If this ever fails, someone has put a wall-clock into the report, which breaks the determinism
    contract and quietly offers freshness a tempting wrong answer.
    """
    reports = list(_RESULTS.rglob("report.json"))
    assert reports, "no committed reports to check"
    clockish = {"measured_at", "generated_at", "started_at", "finished_at", "timestamp"}
    for path in reports:
        keys = set(json.loads(path.read_text(encoding="utf-8")))
        assert not (keys & clockish), f"{path.name} carries a wall-clock field: {keys & clockish}"


def test_a_republication_does_not_count_as_a_measurement() -> None:
    """The board's rebuild stamp must never be newer-than-or-equal to what freshness reports.

    Stated as a property rather than a date: the leaderboard is regenerated from committed reports
    routinely, and if freshness ever tracked that, the badge would refresh itself on every rebuild.
    """
    board = json.loads((_ROOT / "leaderboard" / "results" / "leaderboard.json").read_text("utf-8"))
    generated_at = board.get("generated_at")
    newest = max(str(m.measured_at) for m in measurements_from_results(_RESULTS))
    if generated_at:
        assert newest != generated_at, (
            "the newest 'measurement' equals the board's rebuild stamp — freshness is dating "
            "itself from a republication"
        )


def test_the_committed_badge_is_not_green_while_the_measurements_are_old() -> None:
    """The badge may be red. What it may not be is green when the newest measurement is stale.

    Deliberately one-sided: this asserts the badge cannot UNDERSTATE staleness. A repo whose whole
    claim is that its instrumentation can be trusted about itself does not get to round its own
    freshness in the flattering direction.
    """
    if not _BADGE.exists():  # pragma: no cover - the badge is committed
        return
    badge = json.loads(_BADGE.read_text(encoding="utf-8"))
    newest = max(str(m.measured_at) for m in measurements_from_results(_RESULTS))
    age_days = (datetime.now(UTC) - datetime.fromisoformat(newest.replace("Z", "+00:00"))).days
    if age_days > 7:
        assert badge.get("color") != "green", (
            f"newest measurement is {age_days} days old but the badge renders green"
        )
