"""Hugging Face Community Evals entries: one per measured arm, honest notes, no wall clock."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from provael.attacks.registry import ATTACKS
from provael.config import RunConfig
from provael.execution import ExecutionManifest
from provael.hf_eval import (
    EVALUATION_FRAMEWORK,
    benchmark_eval_yaml,
    task_id,
    to_eval_results,
    to_eval_results_yaml,
)
from provael.runner import run


def _report():  # noqa: ANN202
    return run(
        RunConfig(
            policy="stub", suite="stub",
            attacks=["none", "instruction", "control", "gradient_patch"], episodes=3, seed=0,
        )
    )


def test_one_entry_per_measured_arm_with_the_floor_in_the_notes() -> None:
    report = _report()
    entries = to_eval_results(report, "provael/stub-redteam")
    measured = {a for a, s in report.by_attack.items() if s.attempts > 0}
    unmeasured = {a for a, s in report.by_attack.items() if s.attempts == 0}
    assert unmeasured == {"gradient_patch"}  # no image, no oracle: omitted, never a 0
    assert {e["dataset"]["task_id"] for e in entries} == {task_id("stub", a) for a in measured}
    by_task = {e["dataset"]["task_id"]: e for e in entries}
    none = by_task[task_id("stub", "none")]
    assert none["notes"].startswith("benign-control;")
    assert 0.0 <= none["value"] <= 1.0
    roleplay = by_task[task_id("stub", "roleplay")]
    assert roleplay["notes"].startswith("adversarial-treatment; unsafe 2/3; 95% Wilson CI [")
    assert "read against the benign-control arm" in roleplay["notes"]
    assert all("verifyToken" not in e for e in entries)
    assert all("date" not in e for e in entries)  # no manifest: no date, never today's


def test_the_manifest_supplies_the_date_and_the_source_is_verbatim() -> None:
    report = _report()
    manifest = ExecutionManifest(
        run_id="r", protocol_version="v1", package_version=report.tool_version,
        report_schema_version=report.schema_version, policy="stub", suite="stub", seeds=1,
        horizon=report.horizon, evidence_state="fixture", release_verdict="x",
        report_digest="d", ended_at="2026-09-14T12:34:56Z",
    )
    entries = to_eval_results(
        report, "provael/stub-redteam", manifest=manifest,
        source_url="https://github.com/provael/provael/tree/main/results/x", user="provael",
    )
    assert all(e["date"] == "2026-09-14" for e in entries)
    assert all(e["source"] == {"url": "https://github.com/provael/provael/tree/main/results/x",
                               "user": "provael"} for e in entries)


def test_yaml_round_trips_and_is_deterministic() -> None:
    report = _report()
    text = to_eval_results_yaml(report, "provael/stub-redteam")
    assert text == to_eval_results_yaml(report, "provael/stub-redteam")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, list) and loaded and set(loaded[0]) >= {"dataset", "value", "notes"}
    assert set(loaded[0]["dataset"]) == {"id", "task_id"}


def test_benchmark_eval_yaml_declares_every_registered_arm() -> None:
    arms = ["none", *sorted(ATTACKS)]
    text = benchmark_eval_yaml("libero", arms, name="Provael LIBERO-Object red team",
                               description="Episode-level unsafe fractions per arm.")
    doc = yaml.safe_load(text)
    assert doc["evaluation_framework"] == EVALUATION_FRAMEWORK == "provael"
    # ``none`` is in the registry too; the benchmark declares it once, in first-appearance order.
    expected = [task_id("libero", a) for a in dict.fromkeys(arms)]
    assert [t["id"] for t in doc["tasks"]] == expected
    assert expected.count("libero--none") == 1 and "none" in ATTACKS
    assert doc["name"] and doc["description"]


def test_benchmark_eval_yaml_declares_each_arm_once() -> None:
    # The registry already carries ``none``; prepending it (as the README's recipe does) once
    # produced a benchmark with ``libero--none`` twice. Order of first appearance is kept.
    text = benchmark_eval_yaml("libero", ["none", "roleplay", "none", "roleplay", "patch"],
                               name="n", description="d")
    ids = [t["id"] for t in yaml.safe_load(text)["tasks"]]
    assert ids == ["libero--none", "libero--roleplay", "libero--patch"]


def test_committed_benchmark_files_declare_each_task_once() -> None:
    root = Path(__file__).resolve().parents[1] / "examples" / "hf-benchmark"
    for eval_yaml in sorted(root.glob("*/eval.yaml")):
        ids = [t["id"] for t in yaml.safe_load(eval_yaml.read_text(encoding="utf-8"))["tasks"]]
        assert len(ids) == len(set(ids)), f"{eval_yaml}: duplicate task ids"
        tasks = eval_yaml.with_name("tasks.jsonl")
        rows = [json.loads(line) for line in tasks.read_text(encoding="utf-8").splitlines() if line]
        keys = [(r["task_id"], r["libero_task"]) for r in rows]
        assert len(keys) == len(set(keys)), f"{tasks}: duplicate rows"
        assert {r["task_id"] for r in rows} <= set(ids), f"{tasks}: task id not in eval.yaml"
