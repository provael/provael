# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The scheduled lane's shape and budget, exercised on the CPU lane before Modal spends anything.

WHY THIS EXISTS. `examples/gpu-ci/modal_provael_gpu.py` used to be a probe whose arithmetic could
not close: fourteen attempts a run on one task, in a version bucket that reset on every release,
toward a published body of 550 attempts over ten tasks. Nothing tested the arithmetic because
there was no arithmetic — a probe has none. Now the lane measures the next shards of a declared
plan (`provael.campaign`, tested in `test_campaign.py`), and what is left to hold here is the
lane's own contract:

1. Its cost, derived from the constants and the plan's shard shape, and whether the ceiling fits
   the credit — hung containers bill until their timeout, so the ceiling is the number that counts.
2. That its rate equals the one `scripts/gpu_arm_plan.py` prices the manual arms with.
3. That the workflow header quotes the derived figures, keeps the good shards before failing on the
   bad ones, regenerates every artifact a shard changes, gates on provenance, and keeps the opt-in
   variable and the concurrency group.

LOADED WITH THE INERT MODAL STUB `scripts/gpu_arm_plan.py` already uses. The example builds its
Modal app at import (it must — `modal run` finds the app by scanning global scope), and modal is
not a test dependency. The stub absorbs the app, the image chain and the decorators, and leaves the
constants and cost functions as plain Python. Nothing from `provael` is imported at the example's
module scope, and a test below holds that: the container re-imports the file against the PINNED
wheel, not this checkout.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest
import yaml

from provael.attacks.registry import resolve_attacks
from provael.campaign import load_plan, shards

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "gpu-ci" / "modal_provael_gpu.py"
WORKFLOW = REPO / ".github" / "workflows" / "gpu-scheduled.yml"
ARM_PLAN = REPO / "scripts" / "gpu_arm_plan.py"


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


@pytest.fixture(scope="module")
def plan():
    return load_plan()


@pytest.fixture(scope="module")
def arms(plan) -> int:
    return len(resolve_attacks(list(plan.attacks)))


def _workflow_steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["gpu-redteam"]["steps"]


def _shell(step: dict) -> str:
    """A step's shell with comment lines stripped, so the incident record cannot satisfy a guard."""
    return "\n".join(
        line for line in str(step.get("run", "")).splitlines() if not line.lstrip().startswith("#")
    )


# --------------------------------------------------------------------------- #
# 1. cost
# --------------------------------------------------------------------------- #


def test_a_shard_fits_one_l4_hour_with_margin(lane: Any, arms: int) -> None:
    """The order the campaign was sized to: expected well inside the hour, ceiling under it."""
    expected = lane.shard_seconds(arms)
    assert expected < 3600 / 1.5, f"a {arms}-arm shard is expected to take {expected}s"
    assert lane.SHARD_TIMEOUT_SECONDS <= 3600
    assert 1.5 * expected <= lane.SHARD_TIMEOUT_SECONDS, (
        f"the timeout ({lane.SHARD_TIMEOUT_SECONDS}s) leaves less than 1.5x over the expected "
        f"{expected}s; one slow episode kills the shard and the money is spent for nothing"
    )
    # Even a shard whose every episode runs the full horizon fits: 0.694 s/step measured on L4.
    worst = lane.SETUP_SECONDS + arms * 280 * 0.694
    assert worst < lane.SHARD_TIMEOUT_SECONDS, f"a full-horizon shard ({worst:.0f}s) would be killed"


def test_the_ceiling_fits_the_credit(lane: Any, plan) -> None:
    """Hung containers bill until their timeout; that worst case must fit the monthly credit."""
    ceiling = lane.ceiling_usd_per_run(plan.shards_per_run) * lane.RUNS_PER_MONTH
    assert ceiling <= lane.MONTHLY_CREDIT_USD, (
        f"{plan.shards_per_run} shards x {lane.SHARD_TIMEOUT_SECONDS}s x {lane.RUNS_PER_MONTH:.2f} "
        f"runs is ${ceiling:.2f}/month against a ${lane.MONTHLY_CREDIT_USD} credit; cut "
        "shardsPerRun in the plan or the timeout"
    )


def test_the_expected_spend_is_under_the_ceiling(lane: Any, plan, arms: int) -> None:
    assert lane.expected_usd_per_run(arms, plan.shards_per_run) < lane.ceiling_usd_per_run(
        plan.shards_per_run
    )


def test_the_campaign_completes_in_a_bounded_number_of_runs(plan) -> None:
    """Sixteen runs is eight weeks at Tuesday+Friday, the figure the workflow header and the plan's
    README quote. The bound exists so a seed bump cannot quietly turn the campaign into a half-year;
    raising it is a decision to be written down in both places, not a side effect."""
    total = len(shards(plan))
    runs = -(-total // plan.shards_per_run)
    assert runs <= 16, f"{total} shards at {plan.shards_per_run} a run is {runs} runs"


def test_the_rate_is_the_one_the_arm_planner_prices_with(lane: Any) -> None:
    """One L4 rate, quoted in two files on purpose and held equal here."""
    tree = ast.parse(ARM_PLAN.read_text(encoding="utf-8"))
    rates = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "L4_USD_PER_HOUR" for t in node.targets)
        and isinstance(node.value, ast.Constant)
    ]
    assert rates == [lane.L4_USD_PER_HOUR]


def test_the_cost_table_is_derived_from_the_constants(lane: Any, plan, arms: int) -> None:
    table = lane.cost_table(arms, plan.shards_per_run)
    assert f"${lane.expected_usd_per_run(arms, plan.shards_per_run):.2f}" in table
    assert f"${lane.ceiling_usd_per_run(plan.shards_per_run) * lane.RUNS_PER_MONTH:.2f}" in table
    assert f"{plan.shards_per_run} (one container each, {arms} episodes per shard)" in table


def test_the_workflow_header_quotes_the_derived_figures(lane: Any, plan, arms: int) -> None:
    """A cost figure in a comment is a claim like any other: the header must match the constants."""
    header = WORKFLOW.read_text(encoding="utf-8")
    expected = lane.expected_usd_per_run(arms, plan.shards_per_run)
    ceiling = lane.ceiling_usd_per_run(plan.shards_per_run)
    for figure in (
        f"${expected:.2f} a run",
        f"${ceiling:.2f} at the",
        f"${expected * lane.RUNS_PER_MONTH:.2f} a month",
        f"${ceiling * lane.RUNS_PER_MONTH:.2f}",
        f"${lane.MONTHLY_CREDIT_USD:.0f}/month credit",
        f"{plan.shards_per_run} shards a run" if plan.shards_per_run != 5 else "Five shards a run",
    ):
        assert figure in header, f"gpu-scheduled.yml no longer quotes {figure!r}; regenerate it"


# --------------------------------------------------------------------------- #
# 2. the container never depends on this checkout
# --------------------------------------------------------------------------- #


def test_nothing_from_provael_is_imported_at_module_scope() -> None:
    """The container re-imports the lane against the pinned wheel; the plan lives in main()."""
    tree = ast.parse(EXAMPLE.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in tree.body
        if (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("provael"))
        or (isinstance(node, ast.Import) and any(a.name.startswith("provael") for a in node.names))
    ]
    assert not offenders, f"module-scope provael import at line(s) {offenders}"


def test_the_container_is_told_everything_it_runs() -> None:
    """`redteam` takes the shard's arguments; it reads no plan and no checkout."""
    tree = ast.parse(EXAMPLE.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "redteam")
    assert [a.arg for a in fn.args.args] == ["shard", "task", "seed", "model", "attacks", "horizon"]


def test_the_image_states_the_repository_for_the_manifest(lane: Any) -> None:
    src = EXAMPLE.read_text(encoding="utf-8")
    assert lane.REPOSITORY == "provael/provael"
    assert '"PROVAEL_REPOSITORY": REPOSITORY' in src


# --------------------------------------------------------------------------- #
# 3. the contract with the workflow
# --------------------------------------------------------------------------- #


def test_the_opt_in_gate_and_the_concurrency_group_stay() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["jobs"]["gpu-redteam"]["if"] == "${{ vars.ENABLE_GPU_SCHEDULED == 'true' }}"
    assert workflow["concurrency"] == {"group": "gpu-scheduled", "cancel-in-progress": True}
    triggers = workflow.get(True) or workflow.get("on")
    assert [s["cron"] for s in triggers["schedule"]] == ["17 4 * * 2,5"]


def test_the_driver_installs_this_checkout_before_reading_the_plan() -> None:
    steps = _workflow_steps()
    install = next(i for i, s in enumerate(steps) if "pip install --quiet -e ." in _shell(s))
    run = next(i for i, s in enumerate(steps) if "modal run" in _shell(s))
    assert install < run


def test_the_ledger_step_gates_on_provenance_before_recording() -> None:
    step = next(s for s in _workflow_steps() if "ledger" in str(s.get("name", "")).lower())
    shell = _shell(step)
    gate = shell.index("scripts/check_provenance.py")
    record = shell.index("provael watch --record")
    assert gate < record, "provenance must be checked BEFORE a shard is recorded"
    assert "for shard in" in shell


def test_the_workflow_keeps_good_shards_and_fails_on_the_bad_ones(lane: Any) -> None:
    """Order matters: commit what landed, THEN fail on what did not."""
    steps = _workflow_steps()
    names = [str(s.get("name", "")) for s in steps]
    keep = names.index("Keep the measurement")
    report = next(i for i, n in enumerate(names) if "failed" in n.lower())
    assert keep < report
    assert lane.FAILED_SHARDS_FILE in steps[report]["run"]


def test_the_keep_step_regenerates_every_artifact_a_shard_changes() -> None:
    step = next(s for s in _workflow_steps() if s.get("name") == "Keep the measurement")
    shell = _shell(step)
    order = [
        shell.index("scripts/combine_campaign.py"),
        shell.index("scripts/gen_measurement_ledger.py"),
        shell.index("make gen-publish-freshness"),
        shell.index("scripts/gen_campaign_progress.py"),
    ]
    assert order == sorted(order), "combine, then ledger, then freshness, then progress"
    added = shell.split("git add", 1)[1].splitlines()[0]
    for artifact in (
        "watch/measurements.json",
        "watch/freshness.json",
        "watch/publish-freshness.json",
        "watch/campaign.json",
    ):
        assert artifact in added, f"{artifact} is regenerated but not committed"
    assert "results/gpu-scheduled/campaign-$version" in shell
