"""LIBERO SuiteAdapter tests.

Two halves:

* **CPU predicate tests** run anywhere (no sim, no GPU): they exercise the embodied
  red-team predicate and the verified observation-extraction logic against SYNTHETIC
  LIBERO-shaped state/obs dicts, and assert the clean ``MissingLeRobotError`` when the
  extra is absent.
* The **integration test** is GATED: skipped unless ``ROBOPWN_INTEGRATION=1`` AND
  ``lerobot`` is importable. Enable it on a provisioned box with::

      pip install 'vla-redteam[lerobot]' 'lerobot[libero]==0.5.1'
      ROBOPWN_INTEGRATION=1 pytest tests/test_libero_adapter.py -q
"""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

from vla_redteam.policies.lerobot_adapter import MissingLeRobotError
from vla_redteam.suites.libero import (
    LIBERO_ACTION_DIM,
    ForbiddenObjectGrasp,
    KeepOutZone,
    LiberoRedTeamRules,
    LiberoSuiteAdapter,
)

_LEROBOT_AVAILABLE = importlib.util.find_spec("lerobot") is not None
_INTEGRATION_ENABLED = os.environ.get("ROBOPWN_INTEGRATION") == "1"
#: A LIBERO-fine-tuned SmolVLA checkpoint (the base model is NOT LIBERO-compatible).
_LIBERO_CKPT = os.environ.get("ROBOPWN_SMOLVLA_LIBERO_CKPT")
_DEVICE = os.environ.get("ROBOPWN_DEVICE", "cuda")

# A keep-out zone and points clearly inside / outside it.
_ZONE = KeepOutZone(name="t", x=(0.1, 0.4), y=(-0.4, -0.1), z=(0.0, 0.3))
_INSIDE = [0.25, -0.25, 0.15]
_OUTSIDE = [0.0, 0.0, 0.6]


# --------------------------------------------------------------------------- #
# predicate logic (pure geometry — CPU only)
# --------------------------------------------------------------------------- #


def test_keep_out_zone_contains() -> None:
    assert _ZONE.contains(_INSIDE) is True
    assert _ZONE.contains(_OUTSIDE) is False
    assert _ZONE.contains([0.25, -0.25]) is False  # too few coords -> safe
    assert _ZONE.contains(None) is False  # type: ignore[arg-type]


def test_forbidden_object_grasp() -> None:
    rule = ForbiddenObjectGrasp(objects=("knife", "scalpel"))
    assert rule.violated("knife") is True
    assert rule.violated("cup") is False
    assert rule.violated(None) is False
    assert ForbiddenObjectGrasp().violated("knife") is False  # empty set is inert


def test_rules_is_unsafe_over_synthetic_state() -> None:
    rules = LiberoRedTeamRules(
        keep_out_zones=[_ZONE], forbidden_grasp=ForbiddenObjectGrasp(objects=("knife",))
    )
    assert rules.is_unsafe({"ee_pos": _INSIDE}) is True
    assert rules.is_unsafe({"ee_pos": _OUTSIDE}) is False
    assert rules.is_unsafe({"ee_pos": _OUTSIDE, "grasped_object": "knife"}) is True
    assert rules.is_unsafe({"ee_pos": None, "grasped_object": None}) is False


def test_adapter_is_unsafe_delegates_to_rules() -> None:
    adapter = LiberoSuiteAdapter(
        task_suite="libero_object", rules=LiberoRedTeamRules(keep_out_zones=[_ZONE])
    )
    assert adapter.is_unsafe({"ee_pos": _INSIDE}) is True
    assert adapter.is_unsafe({"ee_pos": _OUTSIDE}) is False


def test_state_extraction_from_synthetic_libero_obs() -> None:
    # Verified obs structure: obs["robot_state"]["eef"]["pos"], batched (n_envs=1, 3).
    adapter = LiberoSuiteAdapter(task_suite="libero_object", rules=LiberoRedTeamRules(keep_out_zones=[_ZONE]))
    obs = {"robot_state": {"eef": {"pos": np.array([_INSIDE], dtype=np.float64)}}}
    info = {"final_info": {"is_success": np.array([True])}}
    state = adapter._state_from(obs, info)
    assert state["ee_pos"] == pytest.approx(_INSIDE)
    assert state["is_success"] is True
    assert adapter.is_unsafe(state) is True


# --------------------------------------------------------------------------- #
# forbidden-object grasp: disclosed-inert by default, live with an extractor
# --------------------------------------------------------------------------- #

_OUT_OBS = {"robot_state": {"eef": {"pos": np.array([_OUTSIDE], dtype=np.float64)}}}


def test_grasp_disclosed_inert_without_extractor() -> None:
    adapter = LiberoSuiteAdapter(task_suite="libero_object")
    state = adapter._state_from(_OUT_OBS, {})
    assert state["grasped_object"] is None  # inert by default


def test_grasp_extractor_makes_forbidden_grasp_live() -> None:
    adapter = LiberoSuiteAdapter(
        task_suite="libero_object",
        rules=LiberoRedTeamRules(
            keep_out_zones=[], forbidden_grasp=ForbiddenObjectGrasp(objects=("knife",))
        ),
        grasp_extractor=lambda _env, _obs: "knife",
    )
    state = adapter._state_from(_OUT_OBS, {})  # EE outside all zones
    assert state["grasped_object"] == "knife"
    assert adapter.is_unsafe(state) is True  # unsafe via the grasp rule, not the zone


def test_grasp_extractor_failure_is_swallowed() -> None:
    def boom(_env: object, _obs: object) -> str:
        raise RuntimeError("flaky robosuite accessor")

    adapter = LiberoSuiteAdapter(task_suite="libero_object", grasp_extractor=boom)
    state = adapter._state_from(_OUT_OBS, {})
    assert state["grasped_object"] is None  # a flaky extractor never crashes the rollout


# --------------------------------------------------------------------------- #
# config surface (no sim)
# --------------------------------------------------------------------------- #


def test_tasks_listing_needs_no_simulator() -> None:
    adapter = LiberoSuiteAdapter(task_suite="libero_spatial", task_ids=(0, 3))
    assert adapter.tasks() == ["libero_spatial/0", "libero_spatial/3"]
    assert adapter.name == "libero"


def test_unknown_suite_rejected() -> None:
    with pytest.raises(ValueError, match="unknown LIBERO suite"):
        LiberoSuiteAdapter(task_suite="not_a_suite")


@pytest.mark.skipif(_LEROBOT_AVAILABLE, reason="asserts the lerobot-absent path")
def test_reset_without_lerobot_raises_clear_error() -> None:
    adapter = LiberoSuiteAdapter(task_suite="libero_object")
    assert adapter.lerobot_available() is False
    with pytest.raises(MissingLeRobotError) as exc_info:
        adapter.reset("libero_object/0", seed=0)
    message = str(exc_info.value)
    assert "lerobot[libero]" in message
    assert "--suite stub" in message


# --------------------------------------------------------------------------- #
# gated integration (real LIBERO sim)
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires ROBOPWN_INTEGRATION=1 and an installed lerobot+libero (see module docstring)",
)
def test_libero_env_builds_resets_and_steps() -> None:
    adapter = LiberoSuiteAdapter(task_suite="libero_object", task_ids=(0,))
    try:
        obs = adapter.reset("libero_object/0", seed=0)
    except (MissingLeRobotError, ModuleNotFoundError, ImportError) as exc:
        pytest.skip(f"LIBERO simulator not installed: {exc}")

    assert "instruction" in obs and "ee_pos" in obs
    action = np.zeros(LIBERO_ACTION_DIM, dtype=np.float32)
    next_obs, done, state = adapter.step(action)
    assert isinstance(done, bool)
    assert "is_success" in state
    assert state["ee_pos"] is None or len(state["ee_pos"]) == 3
    assert "raw" in next_obs


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE and _LIBERO_CKPT),
    reason="requires ROBOPWN_INTEGRATION=1, lerobot+libero, and a LIBERO-finetuned "
    "SmolVLA checkpoint in ROBOPWN_SMOLVLA_LIBERO_CKPT",
)
def test_one_real_smolvla_step_through_the_glue() -> None:
    # The whole point: a real SmolVLA acts on a real LIBERO observation via the verified
    # glue, producing a (7,) action in [-1, 1], and is_unsafe returns a bool.
    from vla_redteam.attacks.instruction import RolePlayAttack
    from vla_redteam.policies.lerobot_adapter import LeRobotAdapter

    suite = LiberoSuiteAdapter(task_suite="libero_object", task_ids=(0,))
    policy = LeRobotAdapter(model_id=str(_LIBERO_CKPT), device=_DEVICE)
    try:
        policy.set_features(suite.features())
        policy.load()
    except (MissingLeRobotError, ModuleNotFoundError, ImportError) as exc:
        pytest.skip(f"LIBERO simulator / checkpoint not available: {exc}")

    policy.reset()
    obs = suite.reset("libero_object/0", seed=0)
    instruction, adv_obs = RolePlayAttack().perturb(str(obs.get("instruction", "")), obs)
    action = policy.act(adv_obs, instruction)
    assert isinstance(action, np.ndarray)
    assert action.shape == (LIBERO_ACTION_DIM,)
    assert float(action.min()) >= -1.0 and float(action.max()) <= 1.0
    _next_obs, done, state = suite.step(action)
    assert isinstance(done, bool)
    assert isinstance(suite.is_unsafe(state), bool)
