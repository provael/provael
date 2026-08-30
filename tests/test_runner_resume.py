"""Resume: a run interrupted and restarted must produce the report it would have produced anyway.

WHY THIS FILE EXISTS. `provael.ledger` shipped complete and tested but was wired into nothing —
only `watch.py` imported it — so `provael attack` could not resume, and a 25-hour run killed at
hour 19 lost nineteen hours. Sharding was the only survivability mechanism. That is what made the
cheap interruptible GPU tiers unusable: the ones with the deepest discount give no eviction notice.

WHAT THE INTERESTING TEST IS. Not "resume skips completed trials" — the ledger already proved that
in isolation. It is that the RESUMED REPORT EQUALS THE UNINTERRUPTED ONE, field for field, in
order. `RunReport.results` carries fifteen per-episode fields and `provael attest` digests the
report, so a resume that dropped `steps` or re-ordered the list would emit a different digest for
the same experiment — unattestable evidence, produced silently, which is the failure this project
exists to prevent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provael.config import RunConfig
from provael.ledger import LedgerReplayError, read_ledger, results_for
from provael.runner import run


def _cfg(**over: object) -> RunConfig:
    base: dict[str, object] = {
        "policy": "stub", "suite": "reach", "attacks": ["none", "instruction"],
        "episodes": 3, "horizon": 4, "seed": 0,
    }
    base.update(over)
    return RunConfig(**base)  # type: ignore[arg-type]


def test_resumed_report_is_identical_to_the_uninterrupted_one(tmp_path: Path) -> None:
    """The whole point. Half the run, then resume, must equal running it straight through."""
    reference = run(_cfg())

    ledger = tmp_path / "trials.jsonl"
    # Simulate a kill: run to completion against a ledger, then truncate it to the first half and
    # resume. Truncation is exactly what a preemption leaves behind.
    run(_cfg(), ledger_path=ledger)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(reference.results), "one ledger line per episode"
    half = len(lines) // 2
    ledger.write_text("\n".join(lines[:half]) + "\n", encoding="utf-8")

    resumed = run(_cfg(), ledger_path=ledger)

    assert resumed.model_dump() == reference.model_dump(), (
        "a resumed report must be identical, not merely equivalent — attest digests this object"
    )
    # And the order is the plan's, not done-first-then-new.
    assert [ (r.task, r.attack, r.seed) for r in resumed.results ] == \
           [ (r.task, r.attack, r.seed) for r in reference.results ]


def test_resume_to_completion_is_idempotent_and_reruns_nothing(tmp_path: Path) -> None:
    ledger = tmp_path / "trials.jsonl"
    first = run(_cfg(), ledger_path=ledger)
    written = len(ledger.read_text(encoding="utf-8").splitlines())
    second = run(_cfg(), ledger_path=ledger)
    assert second.model_dump() == first.model_dump()
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == written, (
        "a fully-resumed run must append nothing; a growing ledger means episodes were re-measured"
    )


def test_ledger_is_written_incrementally_so_a_kill_loses_one_episode(tmp_path: Path) -> None:
    """Appended BEFORE the next episode starts — otherwise a kill loses the whole batch."""
    ledger = tmp_path / "trials.jsonl"
    report = run(_cfg(), ledger_path=ledger)
    records = read_ledger(ledger)
    assert len(records) == len(report.results)
    assert all(r.result is not None for r in records), "every record must be replayable"
    # The embedded result is the real one, not a seven-field shadow of it.
    assert records[0].result is not None
    assert records[0].result.model_dump() == report.results[0].model_dump()


def test_no_ledger_means_no_file_io(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    run(_cfg())
    assert set(tmp_path.iterdir()) == before, "run() writes nothing unless ledger_path is given"


def test_resume_refuses_repeats_at_one_seed(tmp_path: Path) -> None:
    """(attack, task, seed) cannot distinguish repeats, so resume would silently under-run."""
    with pytest.raises(ValueError, match="episodes_per_seed"):
        run(_cfg(episodes=4, episodes_per_seed=2), ledger_path=tmp_path / "l.jsonl")


def test_thin_legacy_record_is_refused_not_silently_dropped(tmp_path: Path) -> None:
    """A pre-`result` ledger line cannot be replayed; dropping it would shrink the denominator."""
    ledger = tmp_path / "trials.jsonl"
    run(_cfg(), ledger_path=ledger)
    lines = ledger.read_text(encoding="utf-8").splitlines()
    thin = json.loads(lines[0])
    thin.pop("result")
    ledger.write_text(json.dumps(thin) + "\n", encoding="utf-8")
    with pytest.raises(LedgerReplayError, match="predate the embedded result"):
        run(_cfg(), ledger_path=ledger)


def test_results_for_ignores_trials_outside_the_plan(tmp_path: Path) -> None:
    """A ledger from a wider run must not leak episodes into a narrower one."""
    ledger = tmp_path / "trials.jsonl"
    wide = run(_cfg(attacks=["none", "instruction"], episodes=3), ledger_path=ledger)
    narrow_plan = [("none", r.task, r.seed) for r in wide.results if r.attack == "none"]
    replay = results_for(narrow_plan, ledger)
    assert set(replay) == set(narrow_plan)
    assert all(k[0] == "none" for k in replay)
