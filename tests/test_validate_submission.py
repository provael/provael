"""CPU tests for leaderboard submission validation (WS4)."""

from __future__ import annotations

from provael.config import RunConfig
from provael.leaderboard import validate_report
from provael.runner import run


def _valid_report():
    return run(RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=4, seed=0))


def test_real_run_report_is_valid() -> None:
    assert validate_report(_valid_report()) == []


def test_asr_out_of_range_is_flagged() -> None:
    bad = _valid_report().model_copy(update={"asr": 2.0})
    assert any("asr" in e for e in validate_report(bad))


def test_successes_exceeding_attempts_is_flagged() -> None:
    rep = _valid_report()
    bad = rep.model_copy(update={"successes": rep.attempts + 5})
    errs = validate_report(bad)
    assert errs  # both the range check and the results-consistency check should fire
    assert any("successes" in e for e in errs)


def test_missing_policy_is_flagged() -> None:
    bad = _valid_report().model_copy(update={"policy": ""})
    assert any("policy" in e for e in validate_report(bad))


def test_empty_results_is_flagged() -> None:
    bad = _valid_report().model_copy(update={"results": []})
    assert any("results" in e for e in validate_report(bad))
