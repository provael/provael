"""The policy's own sampler is seeded, recorded, and required of a stochastic submission.

The leaderboard carried a caveat that SmolVLA's flow-matching sampler is "one draw, not a
constant". That is not a property of flow matching — it is a property of nobody having seeded it.
`suite.reset(task, seed)` has always seeded the ENVIRONMENT and every episode recorded that seed;
nothing ever seeded the POLICY, so the denoising noise came from wherever the process's torch RNG
happened to be. Two rows at the same commit were therefore not comparable, which is most of what a
leaderboard is for.

What is testable on CPU is the CONTRACT — the runner calls the hook, the episode records what the
adapter reports it applied, a stochastic adapter must state an answer, and a submission without one
is refused. The numerical effect on a GPU is not testable here and is not claimed here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from provael.attest import _RESULT_FIELDS_ADDED_IN, report_projection
from provael.config import RunConfig
from provael.leaderboard import POLICY_SEED_SCHEMA, validate_report, validate_warnings
from provael.policies.base import PolicyAdapter
from provael.policies.registry import POLICIES
from provael.report import load_report
from provael.runner import run
from provael.types import Action, Observation

_GOLDEN = {"policy": "stub", "suite": "stub", "attacks": ["none", "instruction"], "episodes": 3}


class _RecordingPolicy(PolicyAdapter):
    """A stub-shaped adapter that remembers every seed the runner handed it."""

    name = "recording"
    stochastic = True

    def __init__(self, applied: bool = True) -> None:
        self.seen: list[int] = []
        self._applied = applied
        self._dim = 0

    def load(self) -> None:
        return None

    def seed(self, seed: int) -> int | None:
        self.seen.append(seed)
        return seed if self._applied else None

    def set_features(self, features: object) -> None:
        self._dim = int(getattr(features, "action_dim", 0) or 0)

    def act(self, observation: Observation, instruction: str) -> Action:
        import numpy as np

        # The fixture suites decode hazard/flag signals from fixed channel positions, so the
        # action has to be the suite's width or scoring refuses it. All zeros = a benign action.
        return np.zeros(self._dim or 11, dtype=float)


def test_every_stochastic_adapter_states_an_answer_about_seeding() -> None:
    """Inherited silence and a considered "cannot" look identical in a result file.

    A stochastic adapter that does not override `seed` records `policy_seed: null` on every
    episode with no explanation anywhere — indistinguishable from openpi, which genuinely cannot
    seed a remote process and says so. Only one of those is a decision.
    """
    unstated = []
    for name, factory in POLICIES.items():
        cls = factory if isinstance(factory, type) else type(factory)
        if not getattr(cls, "stochastic", False):
            continue
        if cls.seed is PolicyAdapter.seed:
            unstated.append(name)
    assert not unstated, (
        f"stochastic adapter(s) {sorted(unstated)} inherit PolicyAdapter.seed unchanged. Override "
        "it — seeding the sampler, or returning None with the reason it cannot be seeded."
    )


def test_the_runner_seeds_the_policy_with_the_same_seed_as_the_environment() -> None:
    from provael.attacks.registry import make_attack
    from provael.runner import run_episode
    from provael.suites.stub import StubSuite

    policy = _RecordingPolicy()
    suite = StubSuite()
    features = suite.features()
    if features is not None:
        policy.set_features(features)
    policy.load()
    result = run_episode(policy, suite, make_attack("none"), suite.tasks()[0], 7, horizon=4)
    assert policy.seen == [7], "the policy was not seeded, or not with the episode seed"
    assert result.seed == 7
    assert result.policy_seed == 7


def test_the_episode_records_what_the_adapter_applied_not_what_was_asked() -> None:
    """An adapter that cannot seed must not be able to make a report claim it was seeded."""
    from provael.attacks.registry import make_attack
    from provael.runner import run_episode
    from provael.suites.stub import StubSuite

    policy = _RecordingPolicy(applied=False)
    suite = StubSuite()
    features = suite.features()
    if features is not None:
        policy.set_features(features)
    policy.load()
    result = run_episode(policy, suite, make_attack("none"), suite.tasks()[0], 7, horizon=4)
    assert policy.seen == [7], "the hook still has to be called"
    assert result.policy_seed is None, "a refused seed was recorded as applied"


def test_a_deterministic_policy_is_not_asked_for_a_seed_it_does_not_need() -> None:
    report = run(RunConfig(**_GOLDEN, seed=0))
    assert report.stochastic is False
    assert all(r.policy_seed is None for r in report.results)
    assert validate_report(report) == []


def test_a_stochastic_submission_without_a_policy_seed_is_refused() -> None:
    report = run(RunConfig(**_GOLDEN, seed=0)).model_copy(
        update={"stochastic": True, "schema_version": POLICY_SEED_SCHEMA}
    )
    errors = validate_report(report)
    assert errors and "policy_seed" in errors[0]
    assert "one draw" in errors[0]


def test_a_stochastic_submission_with_a_policy_seed_is_admitted() -> None:
    report = run(RunConfig(**_GOLDEN, seed=0))
    seeded = [r.model_copy(update={"policy_seed": r.seed}) for r in report.results]
    report = report.model_copy(
        update={"stochastic": True, "schema_version": POLICY_SEED_SCHEMA, "results": seeded}
    )
    assert validate_report(report) == []


def test_a_pre_schema_5_report_is_warned_about_rather_than_refused() -> None:
    """Refusing history would make the submission gate red from the day it landed.

    `validate_submission.py` runs over all of `results/` on any PR that touches it, and every
    committed SmolVLA report predates the field. A permanently-red gate reports nothing; a named,
    non-fatal advisory does.
    """
    real = load_report(Path("results/smolvla_libero_object_suite/libero_object_4/report.json"))
    assert real.stochastic and real.schema_version < POLICY_SEED_SCHEMA
    assert validate_report(real) == [], "a historical artifact must not fail the gate"
    warnings = validate_warnings(real)
    assert warnings and "one draw" in warnings[0]


def test_policy_seed_is_stripped_from_a_report_that_predates_it() -> None:
    """Registered in the projection, or every attestation ever issued verifies as tampered."""
    assert "policy_seed" in _RESULT_FIELDS_ADDED_IN[POLICY_SEED_SCHEMA]
    real = load_report(Path("results/smolvla_libero_object_suite/libero_object_4/report.json"))
    projection = report_projection(real)
    assert all("policy_seed" not in r for r in projection["results"])


def test_the_seed_participates_in_the_leaderboard_inputs_digest() -> None:
    """`inputs_digest` feeds the board signature, so a differing seed must change it.

    This was already true and had no test, which is the same as being true by accident.
    """
    from provael.leaderboard import _inputs_digest

    real = load_report(Path("results/smolvla_libero_object_suite/libero_object_4/report.json"))
    base = _inputs_digest([real])
    assert _inputs_digest([real.model_copy(update={"seed": real.seed + 1})]) != base
    moved = [r.model_copy(update={"seed": r.seed + 100}) for r in real.results]
    assert _inputs_digest([real.model_copy(update={"results": moved})]) != base


@pytest.mark.parametrize("policy_name", ["smolvla", "openvla"])
def test_the_torch_backed_adapters_seed_via_the_documented_lever(policy_name: str) -> None:
    """They must call torch.manual_seed and return the seed — checked by source, not by running.

    Neither lerobot nor an OpenVLA checkpoint is installed in the CPU environment, so the
    numerical effect is out of reach here and is explicitly not claimed. What can be checked is
    that the lever is the documented one and that the return value is the seed rather than a
    hardcoded truth.
    """
    module = {
        "smolvla": "src/provael/policies/lerobot_adapter.py",
        "openvla": "src/provael/policies/openvla_adapter.py",
    }[policy_name]
    source = Path(module).read_text(encoding="utf-8")
    seed_body = source.split("def seed(self, seed: int) -> int | None:", 1)[1].split("\n    def ")[0]
    assert "torch.manual_seed(seed)" in seed_body
    assert "torch.cuda.manual_seed_all(seed)" in seed_body
    assert "return seed" in seed_body
