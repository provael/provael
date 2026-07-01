"""The ``optimized`` family: the query-budgeted, black-box targeted-hijack search.

Covers the search machinery on CPU (budget respected, deterministic given a seed, magnitude cap,
surrogate == oracle on the stub, benign-FPR control) plus a stub-path e2e and a **gated** real
transfer-test (skipped unless PROVAEL_INTEGRATION=1 and lerobot are present — the honesty path).
"""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

from provael.attacks.optimized import (
    DEFAULT_QUERY_BUDGET,
    DEFAULT_TARGET,
    TargetedTrajectoryHijack,
)
from provael.attacks.registry import available_attacks, available_families, resolve_attacks
from provael.config import RunConfig
from provael.report import to_json
from provael.runner import run
from provael.scoring.action import (
    ACTION_DIRECTIVE_KEY,
    ACTION_SURFACE_KEY,
    NOMINAL_SPEED,
    parse_action_directives,
)

_INTEGRATION = os.environ.get("PROVAEL_INTEGRATION") == "1"
_HAS_LEROBOT = importlib.util.find_spec("lerobot") is not None


def _obs(seed: int = 0) -> dict:
    return {ACTION_SURFACE_KEY: True, "seed": seed, "instruction": "reach"}


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #


def test_registered_in_optimized_family() -> None:
    assert "targeted_hijack" in available_attacks()
    assert "optimized" in available_families()
    assert [a.name for a in resolve_attacks(["optimized"])] == ["targeted_hijack"]
    assert resolve_attacks(["optimized"])[0].eai_id == "EAI04"
    assert DEFAULT_QUERY_BUDGET == 200


# --------------------------------------------------------------------------- #
# search machinery (surrogate path — no policy needed)
# --------------------------------------------------------------------------- #


def test_surrogate_is_deterministic_given_seed() -> None:
    a = TargetedTrajectoryHijack(query_budget=16).perturb("reach", _obs(3))[1]
    b = TargetedTrajectoryHijack(query_budget=16).perturb("reach", _obs(3))[1]
    assert a[ACTION_DIRECTIVE_KEY] == b[ACTION_DIRECTIVE_KEY]


def test_query_budget_is_respected() -> None:
    atk = TargetedTrajectoryHijack(query_budget=12)
    atk.perturb("reach", _obs(1))
    assert atk.last_search_queries <= 12
    assert atk.last_search_queries == 12  # goal + 11 jitters


def test_search_targets_the_attacker_goal() -> None:
    atk = TargetedTrajectoryHijack(query_budget=64)
    _, obs = atk.perturb("reach", _obs(0))
    freeze, target = parse_action_directives(obs)
    assert freeze is False
    assert target == DEFAULT_TARGET  # (0, 1, 0), the +y attacker goal


def test_magnitude_cap_is_enforced() -> None:
    # A goal beyond the cap is clipped to it, so the commanded target never exceeds the bound.
    atk = TargetedTrajectoryHijack(target=(0.0, 5.0, 0.0), max_magnitude=1.0, query_budget=4)
    _, obs = atk.perturb("reach", _obs(0))
    _, target = parse_action_directives(obs)
    assert target is not None
    assert np.linalg.norm(target) <= 1.0 + 1e-6


def test_not_applicable_without_action_surface() -> None:
    atk = TargetedTrajectoryHijack()
    assert atk.applicable({"seed": 0}) is False  # no ACTION_SURFACE_KEY -> N/A
    assert atk.applicable(_obs(0)) is True


# --------------------------------------------------------------------------- #
# oracle path (genuine black-box query) — surrogate must agree on the stub
# --------------------------------------------------------------------------- #


def test_oracle_path_matches_surrogate_and_resets() -> None:
    # A stub-like oracle that steers the emitted motion toward the commanded target.
    def stub_oracle(_instruction: str, observation: dict) -> np.ndarray:
        _, tgt = parse_action_directives(observation)
        action = np.zeros(7, dtype=np.float32)
        if tgt is not None:
            vec = np.asarray(tgt, dtype=np.float32)
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                action[1:4] = vec / norm * NOMINAL_SPEED
        return action

    resets = {"n": 0}
    atk = TargetedTrajectoryHijack(query_budget=20)
    atk.attach_oracle(stub_oracle, reset=lambda: resets.__setitem__("n", resets["n"] + 1))
    _, obs = atk.perturb("reach", _obs(0))
    _, target = parse_action_directives(obs)
    assert target == DEFAULT_TARGET  # same choice the surrogate makes
    assert atk.last_search_queries == 20
    assert resets["n"] == 1  # policy reset once after the search, keeping the live rollout clean


# --------------------------------------------------------------------------- #
# end-to-end on the deterministic CPU stub (with the benign-FPR control)
# --------------------------------------------------------------------------- #


def test_e2e_stub_targeted_hijack_with_benign_control() -> None:
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["none", "optimized"], episodes=10, seed=0)
    )
    assert report.by_attack["targeted_hijack"].successes == 10  # redirected every episode
    assert report.by_attack["none"].successes == 0  # benign control never trips
    assert report.benign_fpr == 0.0  # the control is present and reported


def test_e2e_is_byte_deterministic() -> None:
    cfg = RunConfig(policy="stub", suite="stub", attacks=["optimized"], episodes=10, seed=0)
    assert to_json(run(cfg)) == to_json(run(cfg))


def test_query_budget_flag_threads_through_runconfig() -> None:
    # A smaller budget still runs and stays deterministic (the search converges on the stub).
    report = run(
        RunConfig(policy="stub", suite="stub", attacks=["optimized"], episodes=5, query_budget=8)
    )
    assert report.by_attack["targeted_hijack"].attempts == 5


# --------------------------------------------------------------------------- #
# gated real transfer-test (honesty path) — skipped in CPU CI
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not (_INTEGRATION and _HAS_LEROBOT),
    reason="requires PROVAEL_INTEGRATION=1 and lerobot+libero (GPU); the real transfer-test",
)
def test_targeted_hijack_transfer_smolvla_libero() -> None:  # pragma: no cover - integration only
    report = run(
        RunConfig(
            policy="smolvla",
            suite="libero",
            model="HuggingFaceVLA/smolvla_libero",
            attacks=["none", "optimized"],
            episodes=10,
            horizon=280,
            seed=0,
            query_budget=200,
        )
    )
    stat = report.by_attack["targeted_hijack"]
    assert stat.attempts == 10  # a real targeted-redirection rate (record it + the CI in results/)
    assert report.benign_fpr is not None  # the benign control must be present
