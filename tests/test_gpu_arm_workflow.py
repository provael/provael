# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""`.github/workflows/gpu-arm.yml` and the example's STAGES must name the same arms.

WHY THIS EXISTS. The workflow offers a `stage` dropdown and the example defines the stages. Those
are two copies of one fact — the shape this repo keeps getting bitten by — and here the failure is
expensive rather than merely wrong: an option naming a stage the example does not define fails
AFTER the runner has spun up, and an option silently dropped means a stage nobody can dispatch.

It also runs the cost estimator for every offered arm. That estimator was a heredoc inside the
workflow for one draft and carried two bugs — walking for `ast.Assign` when `STAGES` is an
`AnnAssign`, and reading `.items` off an `ast.Dict` — either of which would have raised in the one
step whose purpose is to speak before money is spent. Lifting it into `scripts/gpu_arm_plan.py`
only helps if something exercises it, so this does, on the CPU lane, with no modal installed.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "gpu-arm.yml"
EXAMPLE = REPO / "examples" / "gpu-ci" / "modal_libero_suite.py"

_spec = importlib.util.spec_from_file_location(
    "gpu_arm_plan", REPO / "scripts" / "gpu_arm_plan.py"
)
assert _spec and _spec.loader
plan_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_module)


def _offered_stages() -> list[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses the unquoted key `on:` as the boolean True. Accept either, so quoting it later
    # does not break this guard.
    trigger = workflow.get("on", workflow.get(True))
    options = trigger["workflow_dispatch"]["inputs"]["stage"]["options"]
    assert isinstance(options, list) and options, "the stage input offers no options"
    return [str(option) for option in options]


def test_every_offered_stage_exists() -> None:
    """A dropdown option the example does not define fails after the runner has already started."""
    defined = set(plan_module.stages())
    unknown = sorted(set(_offered_stages()) - defined)
    assert not unknown, (
        f"gpu-arm.yml offers stage(s) {unknown} that examples/gpu-ci/modal_libero_suite.py does "
        f"not define. It defines {sorted(defined)}."
    )


def test_the_expensive_stages_are_reachable() -> None:
    """A stage that exists but is not offered can only be run from someone's laptop.

    That is the state issue #171 was stuck in: the `calibrate` run it needs was designed, costed
    and committed, and could be started by exactly one person on one machine.
    """
    offered = set(_offered_stages())
    for required in ("calibrate", "eai04-redirect"):
        assert required in offered, (
            f"gpu-arm.yml no longer offers {required!r}. Removing it does not remove the stage — "
            f"it removes everyone's ability to run it without a configured laptop."
        )


@pytest.mark.parametrize("stage", _offered_stages())
def test_the_cost_estimate_renders_for_every_offered_stage(stage: str) -> None:
    """The estimator must not raise on the one path that runs before anything is billed."""
    rendered = plan_module.plan(stage)
    assert f"`{stage}`" in rendered
    assert "hard ceiling" in rendered
    assert "$" in rendered


def test_the_estimator_refuses_an_unknown_stage() -> None:
    """Failing loudly beats printing a ceiling of $0.00 for a stage that does not exist."""
    with pytest.raises(SystemExit):
        plan_module.plan("no-such-stage")


def test_the_ceiling_is_shards_times_timeout_times_rate() -> None:
    """Pin the arithmetic, so a plausible-looking wrong number cannot ship.

    A cost ceiling is a claim like any other in this repo, and it is the one a maintainer reads
    right before deciding to spend. `eai04-redirect` is 10 shards x 1.5 h x $0.7992 = $11.99.
    """
    cfg = plan_module.stages()["eai04-redirect"]
    shards = len(cfg["tasks"].split(","))
    expected = shards * (int(cfg["timeout"]) / 3600) * plan_module.L4_USD_PER_HOUR
    assert shards == 10
    assert round(expected, 2) == 11.99
    assert f"~${expected:,.2f}" in plan_module.plan("eai04-redirect")


#: A stage row of the example's cost table: indented, the stage name, then its task count and "x".
_ROW = re.compile(r"^\s+([a-z0-9-]+)\s+\d+\s+x\s")

#: A ceiling line under a stage row: "hard ceiling ~$12 (10 x 1.5 h timeout)". `whitebox-pilot`
#: writes its rate where the word "timeout" sits ("(2 x 2.50 h x $0.7992,"), so the pattern stops
#: at the hours and reads both forms.
_CEILING = re.compile(r"hard ceiling ~\$(\d+(?:\.\d+)?)\s+\((\d+) x (\d+(?:\.\d+)?) h\b")


def _table_ceilings() -> list[tuple[str, str, int, str]]:
    """``(stage, dollars, shards, hours)`` for every ceiling line in the example's cost table.

    Parsed rather than imported, like the rest of this file's reads of the example: the CPU lane
    has no modal. A ceiling line belongs to the nearest stage row above it, which is how the table
    is laid out.
    """
    doc = ast.get_docstring(ast.parse(EXAMPLE.read_text(encoding="utf-8"))) or ""
    found: list[tuple[str, str, int, str]] = []
    stage: str | None = None
    for line in doc.splitlines():
        row = _ROW.match(line)
        if row:
            stage = row.group(1)
        ceiling = _CEILING.search(line)
        if ceiling:
            assert stage is not None, f"a ceiling line sits above every stage row: {line.strip()!r}"
            found.append((stage, ceiling.group(1), int(ceiling.group(2)), ceiling.group(3)))
    return found


def test_every_ceiling_line_in_the_cost_table_says_what_its_stage_costs() -> None:
    """A ceiling line restates the stage's timeout, shard count and the L4 rate, so check all three.

    WHY. The `calibrate` row said `hard ceiling ~$8  (10 x 1 h timeout)` after the stage's timeout
    had moved to 5,400 s, while the plan step printed ~$11.99 (#136, 19 October 2026). The plan
    step is right by construction because it reads the stage; the table is a hand copy, and a cost
    ceiling is the number a maintainer reads right before deciding to spend. The dollar figure is
    compared at the precision the line writes it, so "~$12" passes for $11.99 and "~$8" does not.
    """
    stages = plan_module.stages()
    ceilings = _table_ceilings()
    assert ceilings, "the cost table has no ceiling lines; _CEILING no longer matches the table"
    wrong: list[str] = []
    for stage, dollars, shards, hours in ceilings:
        assert stage in stages, f"the cost table prices {stage!r}, which STAGES does not define"
        cfg = stages[stage]
        timeout = int(cfg["timeout"])
        expected_shards = len(cfg["tasks"].split(","))
        ceiling = expected_shards * (timeout / 3600) * plan_module.L4_USD_PER_HOUR
        if float(hours) * 3600 != timeout:
            wrong.append(f"{stage}: the table says {hours} h; the stage's timeout is {timeout} s")
        if shards != expected_shards:
            wrong.append(f"{stage}: the table says {shards} shards; the stage has {expected_shards}")
        if round(ceiling, len(dollars.partition(".")[2])) != float(dollars):
            wrong.append(
                f"{stage}: the table says ~${dollars}; "
                f"`python scripts/gpu_arm_plan.py {stage}` prints ~${ceiling:,.2f}"
            )
    assert not wrong, "the cost table disagrees with STAGES:\n" + "\n".join(wrong)
