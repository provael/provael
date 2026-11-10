# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The RDA export example writes every executed step's action, and says what its pairs share.

`examples/rda-export/rda_export.py` hands committed LIBERO runs to an outside data-quality tool
(RDA) for a paired test. Two things decide whether that test means anything: every per-step action
must come through unchanged under the right (task, seed, arm) key, and the file must say that a
pair shares a task and a seed, not a starting scene (E-2026-19).

`tests/fixtures/two_episode_libero_shard` is a hand-built two-episode shard, not a measurement. The
committed runs are read in place to hold the README's statements about them.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from provael.report import load_report

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "rda-export"
SCRIPT = EXAMPLE / "rda_export.py"
FIXTURE_RUN = ROOT / "tests" / "fixtures" / "two_episode_libero_shard"
OBJECT_SUITE = "smolvla_libero_object_suite_2026-09-14"
LIBERO_10 = "smolvla_libero_10_2026-09-14"


@pytest.fixture(scope="module")
def example() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_rda_export_example", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def committed(example: ModuleType) -> dict[str, dict[str, Any]]:
    """The export of each default run, built once."""
    return {run.name: example.export_run(run) for run in example.DEFAULT_RUNS}


def _run_copy(tmp_path: Path, edit: Callable[[dict[str, Any]], None]) -> Path:
    """A copy of the fixture run with ``edit`` applied to its one shard's parsed report."""
    run = tmp_path / "run"
    shutil.copytree(FIXTURE_RUN, run)
    path = run / "libero_object_0" / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    edit(report)
    path.write_text(json.dumps(report), encoding="utf-8")
    return run


def test_each_episode_comes_through_field_by_field(example: ModuleType) -> None:
    export = example.export_run(FIXTURE_RUN)
    by_key = {(e["task"], e["seed"], e["arm"]): e for e in export["episodes"]}
    report = load_report(FIXTURE_RUN / "libero_object_0")
    assert set(by_key) == {(r.task, r.seed, r.attack) for r in report.results}
    for r in report.results:
        entry = by_key[(r.task, r.seed, r.attack)]
        assert entry["actions"] == [d.action for d in r.decisions]
        assert entry["steps"] == r.steps == len(entry["actions"])
        assert (entry["envelope_exit"], entry["exit_step"]) == (r.success, r.steps_to_success)
        assert entry["task_success"] is r.task_success
        assert entry["init_state"] is None
        assert entry["horizon"] == report.horizon
        assert entry["role"] == report.roles[r.attack]
    benign = by_key[("libero_object/0", 0, "none")]
    attacked = by_key[("libero_object/0", 0, "roleplay")]
    assert (benign["ended_by"], benign["exit_step"]) == ("task_success", None)
    assert (attacked["ended_by"], attacked["exit_step"]) == ("envelope_exit", 3)
    assert export["coverage"] == {
        "episodes_in_shards": 2, "episodes_exported": 2, "steps_exported": 7, "excluded": [],
    }


def test_the_written_file_says_pairs_are_matched_on_task_and_seed_only(
    example: ModuleType, tmp_path: Path
) -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE_RUN), "--out", str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Pairs are matched on task and seed only" in proc.stdout
    text = (tmp_path / "two_episode_libero_shard.rda.json").read_text(encoding="utf-8")
    written = json.loads(text)
    pairing = written["pairing"]
    assert (pairing["matched_on"], pairing["pairs"], pairing["key"]) == (
        "task and seed only", 1, ["task", "seed"])
    for phrase in ("not a starting scene", "E-2026-19", "record no init_state"):
        assert phrase in pairing["statement"]
    assert text.index('"pairing"') < text.index('"episodes"'), "the caveat must come first"
    assert written == json.loads(json.dumps(example.export_run(FIXTURE_RUN)))


def test_equal_recorded_init_states_are_called_a_match(
    example: ModuleType, tmp_path: Path
) -> None:
    def record(report: dict[str, Any]) -> None:
        report["schema_version"] = 8
        for result in report["results"]:
            result["init_state"] = 7

    export = example.export_run(_run_copy(tmp_path, record))
    assert export["pairing"]["matched_on"] == "task, seed and init state"
    assert {e["init_state"] for e in export["episodes"]} == {7}


def test_unequal_recorded_init_states_stay_task_and_seed_only(
    example: ModuleType, tmp_path: Path
) -> None:
    def record(report: dict[str, Any]) -> None:
        report["schema_version"] = 8
        for result in report["results"]:
            result["init_state"] = 7 if result["attack"] == "none" else 9

    pairing = example.export_run(_run_copy(tmp_path, record))["pairing"]
    assert pairing["matched_on"] == "task and seed only"
    assert "not every pair recorded one equal state" in pairing["statement"]


def _flag_an_early_step(report: dict[str, Any]) -> None:
    report["results"][1]["decisions"][0]["unsafe"] = True


def _drop_a_step(report: dict[str, Any]) -> None:
    del report["results"][0]["decisions"][1]


def _narrow_an_action(report: dict[str, Any]) -> None:
    report["results"][0]["decisions"][0]["action"] = [0.0] * 6


def _calibrate(report: dict[str, Any]) -> None:
    report["calibrated"] = True


def _another_suite(report: dict[str, Any]) -> None:
    report["suite"] = "stub"


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (_flag_an_early_step, "do not match the exit verdict"),
        (_drop_a_step, "not steps 1 to"),
        (_narrow_an_action, "width"),
        (_calibrate, "calibrated"),
        (_another_suite, "LIBERO runs only"),
    ],
)
def test_a_shard_the_export_would_misdescribe_is_refused(
    example: ModuleType, tmp_path: Path, edit: Callable[[dict[str, Any]], None], message: str
) -> None:
    with pytest.raises(example.ExportError, match=message):
        example.export_run(_run_copy(tmp_path, edit))


def test_the_defaults_are_the_two_runs_the_readme_names(example: ModuleType) -> None:
    readme = (EXAMPLE / "README.md").read_text(encoding="utf-8")
    for run in example.DEFAULT_RUNS:
        assert run.is_dir()
        assert f"(../../results/{run.name}/)" in readme
    assert [run.name for run in example.DEFAULT_RUNS] == [OBJECT_SUITE, LIBERO_10]


def test_the_committed_runs_export_every_executed_step(
    committed: dict[str, dict[str, Any]],
) -> None:
    for name, export in committed.items():
        shards = sorted((ROOT / "results" / name).glob("*/report.json"))
        ran = [r for p in shards for r in json.loads(p.read_text(encoding="utf-8"))["results"]
               if r["applicable"]]
        coverage = export["coverage"]
        assert coverage["episodes_exported"] == len(ran)
        assert coverage["steps_exported"] == sum(len(r["decisions"]) for r in ran)
        assert len(export["source"]["shards"]) == len(shards)
        attacked = [e for e in export["episodes"] if e["arm"] != "none"]
        assert export["pairing"]["pairs"] == len(attacked)
        assert export["pairing"]["matched_on"] == "task and seed only"


def test_what_the_readme_says_about_the_committed_runs(
    committed: dict[str, dict[str, Any]],
) -> None:
    for export in committed.values():
        assert all(e["init_state"] is None for e in export["episodes"])
        assert {e["ended_by"] for e in export["episodes"]} <= {
            "envelope_exit", "task_success", "horizon"}
        assert export["not_exported"][0]["reason"].startswith("0.0 on every episode")
        assert "E-2026-21" in export["not_exported"][2]["reason"]
    assert [x["arm"] for x in committed[OBJECT_SUITE]["coverage"]["excluded"]] == ["mcp_tool_desc"]
    assert any(e["envelope_exit"] for e in committed[OBJECT_SUITE]["episodes"])
    assert committed[LIBERO_10]["coverage"]["excluded"] == []
    assert not any(e["envelope_exit"] for e in committed[LIBERO_10]["episodes"])
