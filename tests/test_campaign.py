# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The scheduled campaign: its plan, its shards, its combined artifact and its progress.

WHAT THIS PINS, in the order `provael.campaign`'s docstring states it:

1. The plan is modelled on the published campaign's own shape — read out of the committed shards
   the plan names, never guessed — and sized so the completed campaign exceeds the published body's
   attempts. A results PR that grows that body past the plan fails here; the remedy is a seed bump
   in the same PR.
2. Shards are seed-major, selection is a pure function of the committed tree, a re-run of a slot
   that already landed selects the shards after it, and a complete campaign selects nothing.
3. The combined artifact is never `report.json`, never a ledger row, says `complete: false` in its
   own words while shards are missing, carries every shard's digest, and is refused when a shard
   lacks the four required provenance fields.
4. Progress is derived from the plan, the shards and the cron — no wall-clock field — and the
   projected completion is anchored on the newest shard, not on now.

And an END-TO-END RUN ON THE CPU STUB PATH (`PROVAEL_INTEGRATION` unset): a two-shard stub plan is
measured shard by shard through the real CLI, combined, and regenerated twice, to confirm shard
selection, combination and ledger regeneration are deterministic and idempotent on a re-run. The
GPU plan cannot run here; the machinery around it can, and this is where it is proven.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.attacks.registry import resolve_attacks
from provael.campaign import (
    CAMPAIGN_JSON,
    DESIGNATION_COMPLETE,
    DESIGNATION_IN_PROGRESS,
    PLAN_PATH,
    REQUIRED_PROVENANCE,
    CampaignPlan,
    IncompleteProvenanceError,
    campaign_dir,
    check_provenance,
    combine_campaign,
    done_shards,
    load_plan,
    next_shards,
    progress,
    provenance_gaps,
    render_campaign,
    runs_per_week,
    shard_id,
    shards,
    write_campaign,
)
from provael.cli import app
from provael.watch import (
    EXECUTION_MANIFEST,
    REPORT,
    displacement,
    measurements_from_results,
)

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()


# --------------------------------------------------------------------------- #
# 1. the plan is the published campaign's shape, read from its artifacts
# --------------------------------------------------------------------------- #


def _incumbent_reports(plan: CampaignPlan) -> list[dict]:
    reports = []
    for rel in plan.modelled_on.artifact_paths:
        root = REPO / rel
        assert root.is_dir(), f"the plan names {rel}, which is not a committed directory"
        for path in sorted(root.glob(f"*/{REPORT}")):
            reports.append(json.loads(path.read_text(encoding="utf-8")))
    assert reports, "the plan's modelledOn.artifactPaths hold no shards"
    return reports


def test_the_plan_names_the_committed_campaign_it_is_modelled_on() -> None:
    plan = load_plan()
    standing = displacement()
    assert standing is not None
    assert plan.modelled_on.tool_version == standing.published.tool_version
    reports = _incumbent_reports(plan)
    assert {r["tool_version"] for r in reports} == {plan.modelled_on.tool_version}


def test_the_plan_matches_the_incumbent_shape_field_by_field() -> None:
    """Same checkpoint, suite, horizon and tasks; every arm it ran; at least as many seeds."""
    plan = load_plan()
    reports = _incumbent_reports(plan)
    assert {r["policy"] for r in reports} == {plan.policy}
    assert {r["model"] for r in reports} == {plan.model}
    assert {r["suite"] for r in reports} == {plan.suite}
    assert {r["horizon"] for r in reports} == {plan.horizon}
    assert sorted({t for r in reports for t in r["tasks"]}) == sorted(plan.tasks)
    incumbent_arms = {a for r in reports for a in r["attacks"]}
    plan_arms = {a.name for a in resolve_attacks(list(plan.attacks))}
    assert incumbent_arms <= plan_arms, f"the plan drops {sorted(incumbent_arms - plan_arms)}"
    assert plan.seeds >= max(r["seeds"] for r in reports)


def test_the_completed_campaign_exceeds_the_published_body() -> None:
    """Sized against the incumbent's own not-applicable pattern, not against a hoped-for count.

    `mcp_tool_desc` is not applicable to SmolVLA in every committed shard (it has no tool channel),
    so a cell yields one attempt fewer than it has arms. The bound below applies that rate to the
    plan and requires the result to EXCEED the published attempts — a tie would displace under the
    rule (newer wins), but the order was to exceed, and a single extra not-applicable arm must not
    turn the campaign into a tie.
    """
    plan = load_plan()
    standing = displacement()
    assert standing is not None
    reports = _incumbent_reports(plan)
    never_applicable = {
        a
        for a in {a for r in reports for a in r["attacks"]}
        if all(
            not x.get("applicable", True)
            for r in reports
            for x in r["results"]
            if x["attack"] == a
        )
    }
    arms = {a.name for a in resolve_attacks(list(plan.attacks))}
    attempts_per_cell = len(arms - never_applicable)
    planned_attempts = attempts_per_cell * len(plan.tasks) * plan.seeds
    assert planned_attempts > standing.published.attempts, (
        f"{planned_attempts} planned attempts ({attempts_per_cell} per cell x {len(plan.tasks)} "
        f"tasks x {plan.seeds} seeds) do not exceed the published {standing.published.attempts} "
        f"(v{standing.published.tool_version}). If new runs at that version grew the body, raise "
        "`seeds` in studies/scheduled_campaign/plan.json in the same PR and say so in its note; a "
        "campaign that cannot supersede is a probe with a plan."
    )


def test_the_plan_is_committed_where_a_reader_can_date_it() -> None:
    assert PLAN_PATH.is_file()
    assert PLAN_PATH.is_relative_to(REPO / "studies")


# --------------------------------------------------------------------------- #
# 2. shards and selection
# --------------------------------------------------------------------------- #


def _plan(tmp_path: Path, **over) -> CampaignPlan:
    base = {
        "id": "stub-smoke",
        "policy": "stub",
        "model": "stub",
        "suite": "stub",
        "tasks": ["reach"],
        "attacks": ["none", "instruction"],
        "seeds": 2,
        "horizon": 20,
        "shardsPerRun": 1,
        "modelledOn": {"toolVersion": "0.0.0", "artifactPaths": []},
    }
    base.update(over)
    return CampaignPlan.model_validate(base)


def test_shards_are_seed_major() -> None:
    plan = load_plan()
    ids = [s.id for s in shards(plan)]
    assert ids[: len(plan.tasks)] == [shard_id(t, 0) for t in plan.tasks]
    assert ids[len(plan.tasks)] == shard_id(plan.tasks[0], 1)
    assert len(ids) == len(set(ids)) == len(plan.tasks) * plan.seeds


def test_shard_ids_are_directory_safe() -> None:
    assert "/" not in shard_id("libero_object/3", 2)
    assert shard_id("libero_object/3", 2) == "libero_object_3__seed2"


def test_selection_is_a_pure_function_of_the_tree(tmp_path: Path) -> None:
    plan = _plan(tmp_path, tasks=["a", "b", "c"], seeds=2, shardsPerRun=2)
    directory = tmp_path / "campaign-x"
    assert [s.id for s in next_shards(plan, directory)] == ["a__seed0", "b__seed0"]
    (directory / "a__seed0").mkdir(parents=True)
    (directory / "a__seed0" / REPORT).write_text("{}")
    first = next_shards(plan, directory)
    assert first == next_shards(plan, directory)
    assert [s.id for s in first] == ["b__seed0", "c__seed0"]


def test_a_landed_shard_is_never_selected_again(tmp_path: Path) -> None:
    """The no-op re-run: a slot that already landed selects the shards after it."""
    plan = _plan(tmp_path, tasks=["a", "b"], seeds=1, shardsPerRun=5)
    directory = tmp_path / "campaign-x"
    for name in ("a__seed0", "b__seed0"):
        (directory / name).mkdir(parents=True)
        (directory / name / REPORT).write_text("{}")
    assert next_shards(plan, directory) == []
    assert [s.id for s in done_shards(plan, directory)] == ["a__seed0", "b__seed0"]


def test_a_missed_run_costs_a_week_not_correctness(tmp_path: Path) -> None:
    """Nothing depends on which slot ran: the tree says what is done, the plan says what is next."""
    plan = _plan(tmp_path, tasks=["a", "b", "c", "d"], seeds=1, shardsPerRun=2)
    directory = tmp_path / "campaign-x"
    (directory / "c__seed0").mkdir(parents=True)  # landed out of order (a manual run, say)
    (directory / "c__seed0" / REPORT).write_text("{}")
    assert [s.id for s in next_shards(plan, directory)] == ["a__seed0", "b__seed0"]


def test_the_campaign_directory_is_named_for_the_pinned_release(tmp_path: Path) -> None:
    assert campaign_dir("0.42.0", tmp_path) == tmp_path / "gpu-scheduled" / "campaign-0.42.0"


# --------------------------------------------------------------------------- #
# 3. provenance and the combined artifact
# --------------------------------------------------------------------------- #


def test_provenance_gaps_read_the_values_not_only_the_admission() -> None:
    complete = {
        "repository": "provael/provael",
        "commit": "abc1234",
        "dep_lock_digest": "installed:sha256:" + "0" * 64,
        "precision": "fp32",
        "missing_fields": ["accelerator"],
    }
    assert provenance_gaps(complete) == []
    admitted = {**complete, "missing_fields": ["commit"]}
    assert provenance_gaps(admitted) == ["commit"]
    blank = {**complete, "repository": "   "}
    assert provenance_gaps(blank) == ["repository"]
    assert provenance_gaps({}) == list(REQUIRED_PROVENANCE)


def test_the_committed_scheduled_manifests_are_exactly_what_the_gate_refuses() -> None:
    """The bug, as committed: every scheduled-lane manifest lacks all four. None would pass."""
    lane_dirs = sorted(
        p.parent for p in (REPO / "results" / "gpu-scheduled").glob(f"*/{EXECUTION_MANIFEST}")
    )
    assert lane_dirs, "no committed scheduled-lane run to check the gate against"
    problems = check_provenance(lane_dirs)
    assert set(problems) == {str(d) for d in lane_dirs}
    for gaps in problems.values():
        assert gaps == list(REQUIRED_PROVENANCE)


def _fake_shard(directory: Path, shard: str, report: dict, manifest: dict) -> None:
    (directory / shard).mkdir(parents=True, exist_ok=True)
    (directory / shard / REPORT).write_text(json.dumps(report), encoding="utf-8")
    (directory / shard / EXECUTION_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")


def _stub_shard_via_cli(directory: Path, plan: CampaignPlan) -> str:
    """Run the NEXT shard of ``plan`` through the real CLI into ``directory``; return its id."""
    todo = next_shards(plan, directory, 1)
    assert todo, "the campaign is already complete"
    shard = todo[0]
    result = runner.invoke(
        app,
        [
            "attack", "--policy", plan.policy, "--suite", plan.suite,
            "--tasks", shard.task, "--attacks", plan.attacks_arg, "--seeds", "1",
            "--seed", str(shard.seed), "--horizon", str(plan.horizon),
            "--out", str(directory / shard.id),
        ],
    )
    assert result.exit_code == 0, result.output
    return shard.id


def test_the_combined_artifact_is_never_report_json_and_never_a_ledger_row(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    directory = tmp_path / "gpu-scheduled" / "campaign-0.0.0"
    _stub_shard_via_cli(directory, plan)
    out = write_campaign(plan, directory)
    assert out is not None and out.name == CAMPAIGN_JSON and out.name != REPORT
    assert not (directory / REPORT).exists()
    # The ledger sees exactly the shard, dated by the shard's manifest — and not the campaign.
    rows = measurements_from_results(tmp_path)
    assert len(rows) == 1
    assert rows[0].attempts == json.loads((directory / "reach__seed0" / REPORT).read_text())["attempts"]


def test_a_partial_campaign_says_so_in_its_own_words(tmp_path: Path) -> None:
    plan = _plan(tmp_path)  # two seeds, one task: two shards
    directory = tmp_path / "gpu-scheduled" / "campaign-0.0.0"
    _stub_shard_via_cli(directory, plan)
    content = combine_campaign(plan, directory)
    assert content is not None
    assert content["complete"] is False
    assert content["designation"] == DESIGNATION_IN_PROGRESS
    assert content["shardsDone"] == 1 and content["shardsTotal"] == 2
    assert content["shardsMissing"] == ["reach__seed1"]
    assert content["report"]["preliminary"] is True, "a partial campaign must be preliminary"
    assert [s["path"] for s in content["shards"]] == ["reach__seed0/report.json"]
    assert all(len(s["sha256"]) == 64 for s in content["shards"])


def test_a_complete_campaign_is_complete_and_not_a_wall_clock(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    directory = tmp_path / "gpu-scheduled" / "campaign-0.0.0"
    _stub_shard_via_cli(directory, plan)
    _stub_shard_via_cli(directory, plan)
    assert next_shards(plan, directory) == []
    content = combine_campaign(plan, directory)
    assert content is not None
    assert content["complete"] is True
    assert content["designation"] == DESIGNATION_COMPLETE
    assert content["shardsMissing"] == []
    assert content["report"]["seeds"] == 2
    assert content["report"]["attempts"] == sum(
        json.loads((directory / s / REPORT).read_text())["attempts"]
        for s in ("reach__seed0", "reach__seed1")
    )
    assert not {"generatedAt", "generated_at", "renderedAt", "now"} & set(content)
    assert render_campaign(content) == render_campaign(combine_campaign(plan, directory))


def test_a_shard_without_provenance_blocks_the_combination(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    directory = tmp_path / "gpu-scheduled" / "campaign-0.0.0"
    shard = _stub_shard_via_cli(directory, plan)
    manifest_path = directory / shard / EXECUTION_MANIFEST
    manifest = json.loads(manifest_path.read_text())
    manifest["commit"] = None
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(IncompleteProvenanceError, match="commit"):
        combine_campaign(plan, directory)
    assert not (directory / CAMPAIGN_JSON).exists()


def test_a_shard_the_plan_does_not_name_is_refused(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    directory = tmp_path / "gpu-scheduled" / "campaign-0.0.0"
    shard = _stub_shard_via_cli(directory, plan)
    stray = directory / "reach__seed9"
    stray.mkdir()
    for name in (REPORT, EXECUTION_MANIFEST):
        stray.joinpath(name).write_text((directory / shard / name).read_text())
    with pytest.raises(ValueError, match="reach__seed9"):
        combine_campaign(plan, directory)


def test_an_empty_campaign_writes_nothing(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    directory = tmp_path / "gpu-scheduled" / "campaign-0.0.0"
    directory.mkdir(parents=True)
    assert combine_campaign(plan, directory) is None
    assert write_campaign(plan, directory) is None


# --------------------------------------------------------------------------- #
# 4. progress
# --------------------------------------------------------------------------- #


def test_runs_per_week_reads_the_shapes_this_repo_writes() -> None:
    assert runs_per_week("17 4 * * 2,5") == 2
    assert runs_per_week("17 4 * * *") == 7
    assert runs_per_week("17 4 * * 1-5") == 5
    with pytest.raises(ValueError):
        runs_per_week("17 4 * * */2")
    with pytest.raises(ValueError):
        runs_per_week("not a cron")


def test_progress_before_the_first_shard_projects_no_date(tmp_path: Path) -> None:
    plan = _plan(tmp_path, seeds=4, shardsPerRun=1)
    state = progress(
        plan, "0.0.0", cron="17 4 * * 2,5", attempts_to_displace=550, published_with="0.32.0",
        results_dir=tmp_path,
    )
    assert state["banked"] == {
        "attempts": 0, "shardsDone": 0, "shardsRemaining": 4, "lastShardEndedAt": None,
    }
    assert state["projected"] == {"runsRemaining": 4, "completion": None}
    assert state["target"] == {"attemptsToDisplace": 550, "publishedWith": "0.32.0"}
    assert state["complete"] is False


def test_progress_is_anchored_on_the_newest_shard_not_on_now(tmp_path: Path) -> None:
    plan = _plan(tmp_path, tasks=["a", "b", "c", "d"], seeds=1, shardsPerRun=1)
    directory = campaign_dir("0.0.0", tmp_path)
    _fake_shard(directory, "a__seed0", {"attempts": 7}, {"ended_at": "2026-09-22T05:10:00Z"})
    _fake_shard(directory, "b__seed0", {"attempts": 8}, {"ended_at": "2026-09-25T05:10:00Z"})
    state = progress(
        plan, "0.0.0", cron="17 4 * * 2,5", attempts_to_displace=550, published_with="0.32.0",
        results_dir=tmp_path,
    )
    assert state["banked"]["attempts"] == 15
    assert state["banked"]["shardsDone"] == 2 and state["banked"]["shardsRemaining"] == 2
    assert state["banked"]["lastShardEndedAt"] == "2026-09-25T05:10:00Z"
    # two runs left at two a week = seven days after the newest shard
    assert state["projected"] == {"runsRemaining": 2, "completion": "2026-10-02"}


def test_progress_of_a_complete_campaign_dates_its_completion(tmp_path: Path) -> None:
    plan = _plan(tmp_path, tasks=["a"], seeds=1, shardsPerRun=1)
    directory = campaign_dir("0.0.0", tmp_path)
    _fake_shard(directory, "a__seed0", {"attempts": 7}, {"ended_at": "2026-09-22T05:10:00Z"})
    state = progress(
        plan, "0.0.0", cron="17 4 * * 2,5", attempts_to_displace=5, published_with="0.32.0",
        results_dir=tmp_path,
    )
    assert state["complete"] is True
    assert state["projected"] == {"runsRemaining": 0, "completion": "2026-09-22"}


# --------------------------------------------------------------------------- #
# the end-to-end smoke on the CPU stub path
# --------------------------------------------------------------------------- #


def test_stub_campaign_end_to_end_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    """Selection, combination and ledger regeneration, twice, with `PROVAEL_INTEGRATION` unset."""
    assert not os.environ.get("PROVAEL_INTEGRATION"), "this smoke runs the CPU stub path only"
    plan = _plan(tmp_path)
    directory = campaign_dir("0.0.0", tmp_path)

    first = _stub_shard_via_cli(directory, plan)
    assert first == "reach__seed0"
    assert check_provenance([directory / first]) == {}
    campaign_after_one = render_campaign(combine_campaign(plan, directory))
    ledger_after_one = [r.model_dump() for r in measurements_from_results(tmp_path)]

    # A re-run of the slot selects the NEXT shard, never the one that landed.
    second = _stub_shard_via_cli(directory, plan)
    assert second == "reach__seed1"
    assert next_shards(plan, directory) == []

    # Regenerating twice on an unchanged tree is byte-identical, for both derived views.
    once = render_campaign(combine_campaign(plan, directory))
    twice = render_campaign(combine_campaign(plan, directory))
    assert once == twice
    assert once != campaign_after_one
    rows_a = [r.model_dump() for r in measurements_from_results(tmp_path)]
    rows_b = [r.model_dump() for r in measurements_from_results(tmp_path)]
    assert rows_a == rows_b
    assert len(rows_a) == 2 and len(ledger_after_one) == 1
    assert json.loads(once)["complete"] is True
