"""The scheduled lane's plan and budget, exercised on the CPU lane before Modal spends anything.

WHY THIS EXISTS. `examples/gpu-ci/modal_provael_gpu.py` used to be a canary whose arithmetic could
not close: fourteen attempts a run on one task, in a version bucket that reset on every release,
toward a published body of 550 attempts over ten tasks. Nothing tested the arithmetic because
there was no arithmetic — a canary has none. Now the lane plans a slice of a campaign from the
committed tree, and every piece of that plan is a pure function that can be wrong on a laptop
before it is wrong at $0.80 an hour:

1. Which cells are already measured, read from `report.json` files at the campaign pin.
2. Which cells come next — seed-major, so a partial campaign is the first k seeds over all ten
   tasks, the shape `provael.combine` can pool and an evidence manifest can be built over.
3. What a run costs, derived from the constants, and whether the ceiling fits the credit.
4. That `ARMS` — the episodes-per-cell figure the cost rests on — equals what the registry
   actually expands `ATTACKS` to, so a new control arm moves the bill instead of hiding in it.

LOADED WITH THE INERT MODAL STUB `scripts/gpu_arm_plan.py` already uses. The example builds its
Modal app at import (it must — `modal run` finds the app by scanning global scope), and modal is
not a test dependency. The stub absorbs the app, the image chain and the decorators, and leaves the
plan functions and constants as plain Python.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
import yaml

from provael.attacks.registry import resolve_attacks

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "gpu-ci" / "modal_provael_gpu.py"
WORKFLOW = REPO / ".github" / "workflows" / "gpu-scheduled.yml"


class _Inert:
    """Absorbs every attribute access, call and decoration, and returns more of itself."""

    def __getattr__(self, _name: str) -> _Inert:
        return self

    def __call__(self, *_args: Any, **_kwargs: Any) -> _Inert:
        return self


@pytest.fixture(scope="module")
def lane() -> Any:
    stub = types.ModuleType("modal")
    for name in ("App", "Image", "Volume", "NetworkFileSystem", "Secret", "Mount"):
        setattr(stub, name, _Inert())
    saved = sys.modules.get("modal")
    sys.modules["modal"] = stub
    try:
        spec = importlib.util.spec_from_file_location("modal_provael_gpu_under_test", EXAMPLE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = saved
    return module


def _report(lane: Any, tasks: list[str], seed: int, seeds: int, **over: Any) -> dict[str, Any]:
    base = {
        "tool_version": lane.PROVAEL_PIN,
        "model": lane.CKPT,
        "policy": "smolvla",
        "suite": "libero",
        "tasks": tasks,
        "seed": seed,
        "seeds": seeds,
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# 1. which cells are already measured
# --------------------------------------------------------------------------- #


def test_cells_are_read_per_task_and_per_seed(lane: Any) -> None:
    """`seed` is the base and episode i used seed + i, so `seeds` widens the cell range."""
    used = lane.cells_measured([_report(lane, ["libero_object/0"], seed=0, seeds=2)])
    assert used == {("libero_object/0", 0), ("libero_object/0", 1)}


def test_only_this_pin_this_checkpoint_this_suite_counts(lane: Any) -> None:
    """The body rule sums per version, policy and suite; a cell elsewhere is another body."""
    reports = [
        _report(lane, ["libero_object/3"], 0, 1, tool_version="0.32.0"),
        _report(lane, ["libero_object/4"], 0, 1, model="lerobot/smolvla_base"),
        _report(lane, ["libero_object/5"], 0, 1, policy="pi05"),
        _report(lane, ["libero_object/6"], 0, 1, suite="metaworld"),
        _report(lane, ["libero_object/7"], 0, 1),
    ]
    assert lane.cells_measured(reports) == {("libero_object/7", 0)}


def test_a_manual_arm_at_the_pin_is_credited_not_duplicated(lane: Any) -> None:
    """A ten-task `full` stage at the campaign pin already measured seeds 0-4 of every task."""
    reports = [_report(lane, [task], 0, 5) for task in lane.TASKS]
    used = lane.cells_measured(reports)
    assert len(used) == 50
    assert lane.next_cells(used)[0] == ("libero_object/0", 5)


def test_malformed_reports_are_skipped_rather_than_fatal(lane: Any) -> None:
    tasks_not_a_list = {**_report(lane, ["libero_object/0"], 0, 1), "tasks": "libero_object/0"}
    seed_not_an_int = {**_report(lane, ["libero_object/1"], 0, 1), "seed": "0"}
    reports = [
        tasks_not_a_list,
        seed_not_an_int,
        {"tool_version": lane.PROVAEL_PIN},
        _report(lane, ["libero_object/2"], 0, 1),
    ]
    assert lane.cells_measured(reports) == {("libero_object/2", 0)}


def test_the_committed_tree_is_read_the_way_the_ledger_reads_it(lane: Any) -> None:
    """Every committed report is readable by the driver, and cells at the pin are found there."""
    reports = lane.committed_reports(REPO / "results")
    assert reports, "no report.json under results/ — the plan would start every campaign from zero"
    assert all(isinstance(r, dict) for r in reports)
    used = lane.cells_measured(reports)
    at_pin = [r for r in reports if r.get("tool_version") == lane.PROVAEL_PIN]
    assert bool(used) == bool(
        [r for r in at_pin if r.get("model") == lane.CKPT and r.get("suite") == "libero"]
    )


def test_an_absent_results_dir_plans_from_zero(lane: Any, tmp_path: Path) -> None:
    assert lane.committed_reports(tmp_path / "nowhere") == []
    assert lane.plan(tmp_path / "nowhere") == [(task, 0) for task in lane.TASKS[: lane.TASKS_PER_RUN]]


# --------------------------------------------------------------------------- #
# 2. which cells come next
# --------------------------------------------------------------------------- #


def test_the_grid_is_walked_seed_major(lane: Any) -> None:
    """Finish seed 0 across all ten tasks before touching seed 1."""
    used = {(task, 0) for task in lane.TASKS[:7]}
    assert lane.next_cells(used) == [
        ("libero_object/7", 0),
        ("libero_object/8", 0),
        ("libero_object/9", 0),
        ("libero_object/0", 1),
    ]


def test_a_lost_shard_is_re_planned_next_time(lane: Any) -> None:
    """A cell that never landed is the first thing the next run does — no resume file needed."""
    used = {(task, 0) for task in lane.TASKS} - {("libero_object/4", 0)}
    assert lane.next_cells(used)[0] == ("libero_object/4", 0)


def test_the_plan_is_a_pure_function_of_the_tree(lane: Any, tmp_path: Path) -> None:
    """Same tree, same plan — the property that lets the committed tree be the only ledger."""
    for i, task in enumerate(lane.TASKS[:3]):
        shard = tmp_path / f"run{i}"
        shard.mkdir()
        (shard / "report.json").write_text(json.dumps(_report(lane, [task], 0, 1)))
    first = lane.plan(tmp_path)
    assert first == lane.plan(tmp_path)
    assert first[0] == ("libero_object/3", 0)
    assert len(first) == lane.TASKS_PER_RUN


def test_the_committed_tree_plans_a_full_slice_today(lane: Any) -> None:
    """The live plan: exactly TASKS_PER_RUN cells, none of them already measured at the pin."""
    used = lane.cells_measured(lane.committed_reports(REPO / "results"))
    cells = lane.next_cells(used)
    assert len(cells) == lane.TASKS_PER_RUN
    assert not set(cells) & used
    assert all(task in lane.TASKS for task, _ in cells)


# --------------------------------------------------------------------------- #
# 3. what it costs, and 4. the arm count the cost rests on
# --------------------------------------------------------------------------- #


def test_arms_equals_what_the_registry_expands_attacks_to(lane: Any) -> None:
    """The bill is ARMS x cells; a control arm added to the registry must move it, not hide in it."""
    expanded = resolve_attacks(lane.ATTACKS.split(","))
    assert len(expanded) == lane.ARMS, (
        f"ATTACKS={lane.ATTACKS!r} expands to {len(expanded)} arms "
        f"({[a.name for a in expanded]}) but ARMS is {lane.ARMS}; the cost table is wrong by "
        f"the difference on every cell"
    )


def test_the_campaign_covers_what_the_published_body_covers(lane: Any) -> None:
    """A slice of the wrong tasks or arms accumulates toward a body that can never supersede."""
    from provael.watch import displacement

    standing = displacement()
    assert standing is not None
    assert set(standing.published.tasks or ()) <= set(lane.TASKS)
    # Every arm the published body ran is in the campaign's arm set (the campaign may add arms).
    published_arms: set[str] = set()
    for report in lane.committed_reports(REPO / "results"):
        if report.get("tool_version") == standing.published.tool_version and report.get(
            "policy"
        ) == standing.published.policy:
            published_arms.update(str(a) for a in report.get("attacks", []))
    campaign_arms = {a.name for a in resolve_attacks(lane.ATTACKS.split(","))}
    assert published_arms <= campaign_arms, (
        f"the published body ran {sorted(published_arms - campaign_arms)} and the campaign does not"
    )


def test_the_ceiling_fits_the_credit(lane: Any) -> None:
    """Hung containers bill until their timeout; that worst case must fit the monthly credit."""
    assert lane.CEILING_USD_PER_MONTH <= lane.MONTHLY_CREDIT_USD, (
        f"{lane.TASKS_PER_RUN} cells x {lane.SHARD_TIMEOUT_SECONDS}s x {lane.RUNS_PER_MONTH:.2f} "
        f"runs is ${lane.CEILING_USD_PER_MONTH:.2f}/month against a ${lane.MONTHLY_CREDIT_USD} "
        "credit; cut TASKS_PER_RUN or the timeout"
    )
    assert lane.EXPECTED_USD_PER_MONTH < lane.CEILING_USD_PER_MONTH


def test_the_timeout_holds_the_expected_shard_with_headroom(lane: Any) -> None:
    """A truncated shard writes no report.json, so a timeout set at the expectation records nothing."""
    assert lane.SHARD_TIMEOUT_SECONDS >= 1.5 * lane.SHARD_SECONDS, (
        f"a shard is expected to take {lane.SHARD_SECONDS}s and the timeout is "
        f"{lane.SHARD_TIMEOUT_SECONDS}s; one slow episode kills the cell and the money is spent"
    )


def test_the_cost_table_is_derived_from_the_constants(lane: Any) -> None:
    table = lane.cost_table()
    assert f"${lane.EXPECTED_USD_PER_RUN:.2f}" in table
    assert f"${lane.CEILING_USD_PER_MONTH:.2f}" in table
    assert str(lane.TASKS_PER_RUN) in table


def test_the_workflow_header_quotes_the_derived_figures(lane: Any) -> None:
    """A cost figure in a comment is a claim like any other: the header must match the constants."""
    header = WORKFLOW.read_text(encoding="utf-8")
    for figure in (
        f"${lane.EXPECTED_USD_PER_RUN:.2f} a run",
        f"${lane.CEILING_USD_PER_RUN:.2f} at the",
        f"${lane.EXPECTED_USD_PER_MONTH:.2f} a month",
        f"${lane.CEILING_USD_PER_MONTH:.2f}",
        f"${lane.MONTHLY_CREDIT_USD:.0f}/month credit",
    ):
        assert figure in header, f"gpu-scheduled.yml no longer quotes {figure!r}; regenerate it"


# --------------------------------------------------------------------------- #
# the contract with the workflow
# --------------------------------------------------------------------------- #


def test_the_workflow_keeps_good_shards_and_fails_on_the_bad_ones(lane: Any) -> None:
    """Order matters: commit what landed, THEN fail on what did not."""
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gpu-redteam"]["steps"]
    names = [str(s.get("name", "")) for s in steps]
    keep = next(i for i, n in enumerate(names) if n == "Keep the measurement")
    report = next(i for i, n in enumerate(names) if "failed" in n.lower())
    assert keep < report, "the failure step must run after the good shards are committed"
    assert lane.FAILED_SHARDS_FILE in steps[report]["run"]


def test_the_workflow_regenerates_the_artifact_every_slice_changes() -> None:
    """publish-freshness.json now carries the challenger; a slice that skips it reds main."""
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gpu-redteam"]["steps"]
    keep = next(s for s in steps if s.get("name") == "Keep the measurement")["run"]
    shell = "\n".join(line for line in keep.splitlines() if not line.lstrip().startswith("#"))
    assert "gen_publish_freshness_artifact.py" in shell
    assert "watch/publish-freshness.json" in shell.split("git add", 1)[1].splitlines()[0]


def test_the_ledger_step_records_every_shard() -> None:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gpu-redteam"]["steps"]
    ledger = next(s for s in steps if "ledger" in str(s.get("name", "")).lower())["run"]
    shell = "\n".join(line for line in ledger.splitlines() if not line.lstrip().startswith("#"))
    assert "for report in" in shell and "provael watch --record" in shell
