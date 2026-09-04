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

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "gpu-arm.yml"

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
