# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The competence gate (P2.2): no attack is read against a policy that cannot do the task.

A 0% attack rate on a policy that fails the task unattacked is not robustness, it is a policy that
does nothing for an attack to change. ``--competence-check N`` runs N benign episodes per task
first and refuses the adversarial arms on a task whose task success falls below the floor. These
tests hold the pass, the refusal, what the refusal leaves running, and that the pre-run never
reaches a rate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.attacks.registry import FAMILIES
from provael.attest import _REPORT_FIELDS_ADDED_IN, report_projection
from provael.cli import app
from provael.config import RunConfig
from provael.report import to_markdown
from provael.runner import CompetenceCheckError, run
from provael.suites import SUITES
from provael.suites.stub import StubSuite
from provael.types import Action, Observation, RunReport, State

runner = CliRunner()

#: The arms every test here runs: the floor, the instruction family and the controls.
ARMS = ["none", "instruction", "control"]


class _FumblingStub(StubSuite):
    """The stub with a second task the policy never completes: competence fails there only."""

    _TASKS = ("reach", "fumble")

    def step(self, action: Action) -> tuple[Observation, bool, State]:
        obs, done, state = super().step(action)
        if self._task == "fumble":
            state = {**state, "task_success": False}
        return obs, done, state


def _run(**overrides: object) -> RunReport:
    config = RunConfig.model_validate(
        {"policy": "stub", "suite": "stub", "attacks": ARMS, "episodes": 2, "seed": 0, **overrides}
    )
    return run(config)


def test_a_competent_policy_is_admitted_and_every_arm_runs() -> None:
    report = _run(competence_check=3)
    check = report.competence
    assert check is not None and (check.episodes_per_task, check.floor) == (3, 0.8)
    reach = check.by_task["reach"]
    assert reach.admitted and reach.refused == []
    assert (reach.task_success.successes, reach.task_success.trials) == (3, 3)
    # The pre-run runs at the seeds after the run's own (0 and 1), never on a scored seed.
    assert [e.seed for e in reach.episodes] == [2, 3, 4]
    assert {r.seed for r in report.results} == {0, 1}
    # ...and enters no rate: the scored episodes are exactly the arms x episodes.
    plain = _run()
    assert report.results == plain.results
    assert report.rates == plain.rates


def test_a_task_the_policy_cannot_do_has_its_adversarial_arms_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(SUITES, "stub", _FumblingStub)
    report = _run(competence_check=3)
    check = report.competence
    assert check is not None
    assert check.by_task["reach"].admitted
    fumble = check.by_task["fumble"]
    assert not fumble.admitted
    assert (fumble.task_success.successes, fumble.task_success.trials) == (0, 3)
    assert fumble.refused == FAMILIES["instruction"]
    ran = {(r.task, r.attack) for r in report.results}
    # The adversarial arms did not run on the refused task; the floor and the controls did, so the
    # benign floor and the release verdict's own competence criterion still see it.
    assert not {("fumble", a) for a in FAMILIES["instruction"]} & ran
    assert {("fumble", a) for a in ["none", *FAMILIES["control"]]} <= ran
    assert {("reach", a) for a in FAMILIES["instruction"]} <= ran
    adversarial = [r for r in report.results if r.scored and r.family == "instruction"]
    assert report.adversarial_attempts == len(adversarial) == 2 * len(FAMILIES["instruction"])
    # The per-task clean task success shows the task the policy cannot do.
    assert report.rates is not None
    clean = report.rates.clean_task_success_by_task
    assert (clean["fumble"].successes, clean["reach"].successes) == (0, 2)


def test_the_floor_is_configurable_and_compared_as_a_point_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(SUITES, "stub", _FumblingStub)
    lenient = _run(competence_check=2, competence_floor=0.0)
    assert lenient.competence is not None
    assert all(row.admitted for row in lenient.competence.by_task.values())


def test_a_suite_with_no_task_success_signal_cannot_be_judged() -> None:
    """`reach` surfaces no task success: the check refuses rather than admitting or refusing."""
    with pytest.raises(CompetenceCheckError, match="no task-success signal"):
        run(RunConfig(policy="stub", suite="reach", attacks=["none", "roleplay"], episodes=1,
                      competence_check=1))


def test_the_check_is_refused_with_resume(tmp_path: Path) -> None:
    config = RunConfig(policy="stub", suite="stub", attacks=ARMS, episodes=1, competence_check=1)
    with pytest.raises(CompetenceCheckError, match="--resume"):
        run(config, ledger_path=tmp_path / "ledger.jsonl")
    assert not (tmp_path / "ledger.jsonl").exists()  # refused before anything ran


def test_no_check_records_none_and_the_field_is_schema_9() -> None:
    report = _run()
    assert report.competence is None
    assert "competence" in _REPORT_FIELDS_ADDED_IN[9]
    checked = _run(competence_check=1)
    older = checked.model_copy(update={"schema_version": 8})
    assert "competence" not in report_projection(older)


def test_report_md_prints_each_task_s_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(SUITES, "stub", _FumblingStub)
    md = to_markdown(_run(competence_check=3))
    section = md.split("## Competence check", 1)[1]
    assert "| reach | 3/3 (100.0%) [44–100%] | admitted | — |" in section
    assert "| fumble | 0/3 (0.0%) [0–56%] | **refused** | roleplay, goal_substitution, paraphrase |" in (
        section
    )
    assert "clean task success (benign arm)" in md


def test_the_cli_takes_the_check_and_its_floor(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["attack", "--policy", "stub", "--suite", "stub", "--episodes", "1",
         "--competence-check", "2", "--competence-floor", "0.5", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    stored = json.loads((out / "report.json").read_text(encoding="utf-8"))["competence"]
    assert (stored["episodes_per_task"], stored["floor"]) == (2, 0.5)
    assert "competence check: 0 of 1 task(s) below the 50% floor" in result.output


def test_the_cli_refuses_a_floor_without_a_check(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["attack", "--competence-floor", "0.5", "--out", str(tmp_path / "run")]
    )
    assert result.exit_code != 0
    assert "--competence-floor applies only with --competence-check" in result.output


def test_shards_that_ran_one_check_combine_and_shards_that_did_not_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from provael.combine import ShardMismatchError, combine_reports

    monkeypatch.setitem(SUITES, "stub", _FumblingStub)
    reach = _run(tasks=["reach"], competence_check=2)
    fumble = _run(tasks=["fumble"], competence_check=2)
    combined = combine_reports([reach, fumble])
    assert combined.competence is not None
    assert set(combined.competence.by_task) == {"reach", "fumble"}
    assert not combined.competence.by_task["fumble"].admitted
    with pytest.raises(ShardMismatchError, match="competence check"):
        combine_reports([reach, _run(tasks=["fumble"])])
    with pytest.raises(ShardMismatchError, match="competence check"):
        combine_reports([reach, _run(tasks=["fumble"], competence_check=3)])


def test_the_pre_run_runs_under_the_run_s_termination_mode() -> None:
    """A fixed-horizon run's pre-run runs to the horizon too, as its benign arm does (P1.4)."""
    report = _run(tasks=["reach"], competence_check=2, horizon=6, termination="fixed-horizon")
    assert report.termination_mode == "fixed-horizon"
    check = report.competence
    assert check is not None
    pre_run = check.by_task["reach"].episodes
    assert [e.steps for e in pre_run] == [6, 6]
    assert {e.termination for e in pre_run} == {"horizon"}
    benign = [r for r in report.results if r.attack == "none" and r.applicable]
    assert benign and all(r.steps == 6 for r in benign)
