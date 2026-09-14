"""Hugging Face Community Evals entries: one per measured arm, honest notes, no wall clock."""

from __future__ import annotations

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
    assert [t["id"] for t in doc["tasks"]] == [task_id("libero", a) for a in arms]
    assert doc["name"] and doc["description"]
