"""Determinism: the same seed produces an identical report; different seeds differ."""

from __future__ import annotations

from pathlib import Path

from provael.config import RunConfig
from provael.report import to_json, write_report
from provael.runner import run


def test_same_seed_identical_report() -> None:
    config = RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=10, seed=0)
    first = run(config)
    second = run(config)
    assert first.model_dump() == second.model_dump()
    assert to_json(first) == to_json(second)


def test_different_seed_differs() -> None:
    a = run(RunConfig(episodes=10, seed=0))
    b = run(RunConfig(episodes=10, seed=1))
    assert to_json(a) != to_json(b)


def test_report_bytes_independent_of_output_path(tmp_path: Path) -> None:
    # The report must not embed the output directory (or any wall-clock value),
    # so two identical runs to different folders yield byte-identical report.json.
    config_a = RunConfig(episodes=10, seed=0, out=tmp_path / "a")
    config_b = RunConfig(episodes=10, seed=0, out=tmp_path / "b")
    json_a, _ = write_report(run(config_a), config_a.out)
    json_b, _ = write_report(run(config_b), config_b.out)
    assert json_a.read_text(encoding="utf-8") == json_b.read_text(encoding="utf-8")


def test_repeated_full_runs_are_stable() -> None:
    config = RunConfig(episodes=10, seed=0)
    dumps = {to_json(run(config)) for _ in range(3)}
    assert len(dumps) == 1
