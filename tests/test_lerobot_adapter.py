"""LeRobot SmolVLA adapter tests.

* CPU tests (no GPU/lerobot): the missing-dependency error, the eval hint, the pure
  ``clamp_action`` mapping, and the features-protocol no-op for the stub.
* GATED test (skipif not ROBOPWN_INTEGRATION==1 and lerobot importable): the adapter
  loads SmolVLA via the verified ``make_policy`` + processor path with LIBERO features.
  Enable on a provisioned box::

      pip install 'vla-redteam[lerobot]' 'lerobot[libero]==0.5.1'
      ROBOPWN_INTEGRATION=1 pytest tests/test_lerobot_adapter.py -q
"""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

from vla_redteam.policies.lerobot_adapter import (
    LEROBOT_EVAL_LIBERO_HINT,
    IncompatiblePolicyError,
    LeRobotAdapter,
    MissingLeRobotError,
    clamp_action,
)
from vla_redteam.policies.stub import StubPolicy
from vla_redteam.types import SuiteFeatures

_LEROBOT_AVAILABLE = importlib.util.find_spec("lerobot") is not None
_INTEGRATION_ENABLED = os.environ.get("ROBOPWN_INTEGRATION") == "1"
#: A READY LIBERO-fine-tuned SmolVLA checkpoint (verified to load through the glue).
_LIBERO_CKPT = os.environ.get("ROBOPWN_SMOLVLA_LIBERO_CKPT", "HuggingFaceVLA/smolvla_libero")


# --------------------------------------------------------------------------- #
# CPU: pure action mapping
# --------------------------------------------------------------------------- #


def test_clamp_action_shapes_and_clips() -> None:
    action = clamp_action(np.array([[2.0, -3.0, 0.5, 0.0, 0.0, 0.0, 0.0]]), 7)
    assert action.shape == (7,)
    assert action.dtype == np.float32
    assert action[0] == 1.0  # clipped high
    assert action[1] == -1.0  # clipped low
    assert action[2] == 0.5  # untouched in range


def test_clamp_action_takes_first_timestep_of_a_chunk() -> None:
    chunk = (np.arange(14, dtype=np.float32) / 100.0).reshape(2, 7)  # (2, 7) -> 14 values
    action = clamp_action(chunk, 7)
    assert action.shape == (7,)
    assert action[0] == 0.0  # first timestep, first dim


# --------------------------------------------------------------------------- #
# CPU: features protocol
# --------------------------------------------------------------------------- #


def test_set_features_is_noop_for_stub() -> None:
    policy = StubPolicy()
    policy.set_features(SuiteFeatures(action_dim=7))  # ignored
    policy.reset()  # no-op
    policy.load()
    action = policy.act({}, "fetch the knife now")
    assert action.shape == (7,)


def test_lerobot_adapter_stores_features() -> None:
    adapter = LeRobotAdapter(device="cpu")
    feats = SuiteFeatures(action_dim=7, task_suite="libero_object", image_key="image")
    adapter.set_features(feats)
    assert adapter._features is feats


# --------------------------------------------------------------------------- #
# CPU: missing-dependency + hint
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(_LEROBOT_AVAILABLE, reason="this test asserts the lerobot-absent path")
def test_missing_lerobot_raises_actionable_error() -> None:
    adapter = LeRobotAdapter()
    assert adapter.lerobot_available() is False
    with pytest.raises(MissingLeRobotError) as exc_info:
        adapter.load()
    message = str(exc_info.value)
    assert "vla-redteam[lerobot]" in message
    assert "ROBOPWN_INTEGRATION" in message


def test_eval_hint_names_the_supported_path() -> None:
    assert "lerobot-eval" in LEROBOT_EVAL_LIBERO_HINT
    assert "--env.type=libero" in LEROBOT_EVAL_LIBERO_HINT


def test_incompatibility_hint_points_at_the_ready_checkpoint() -> None:
    # The IncompatiblePolicyError message must name the fix, not make a forgetful user
    # rediscover it.
    from vla_redteam.policies.lerobot_adapter import _CHECKPOINT_HINT, LIBERO_FINETUNED_SMOLVLA

    assert LIBERO_FINETUNED_SMOLVLA == "HuggingFaceVLA/smolvla_libero"
    assert LIBERO_FINETUNED_SMOLVLA in _CHECKPOINT_HINT
    assert "--model" in _CHECKPOINT_HINT
    # The template still formats cleanly (only {model}/{error} are placeholders).
    formatted = _CHECKPOINT_HINT.format(model="lerobot/smolvla_base", error="feature mismatch")
    assert "lerobot/smolvla_base" in formatted and "smolvla_libero" in formatted


# --------------------------------------------------------------------------- #
# GATED: real load via the verified make_policy + processor path
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires ROBOPWN_INTEGRATION=1 and an installed lerobot (see module docstring)",
)
def test_smolvla_base_is_incompatible_with_libero() -> None:
    # VERIFIED: lerobot/smolvla_base expects camera1/2/3 but LIBERO provides image/image2,
    # so make_policy rejects it. We surface a clean IncompatiblePolicyError (no traceback).
    from lerobot.envs.factory import make_env_config

    env_cfg = make_env_config(
        "libero", task="libero_object", task_ids=[0], obs_type="pixels_agent_pos"
    )
    adapter = LeRobotAdapter(model_id="lerobot/smolvla_base", device="cpu")
    adapter.set_features(SuiteFeatures(action_dim=7, env_config=env_cfg, image_key="image"))
    with pytest.raises(IncompatiblePolicyError) as exc_info:
        adapter.load()
    assert "fine-tuned" in str(exc_info.value).lower()


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires ROBOPWN_INTEGRATION=1 and an installed lerobot (downloads the checkpoint)",
)
def test_libero_finetuned_checkpoint_loads_through_glue() -> None:
    # The ready HuggingFaceVLA/smolvla_libero checkpoint resolves the feature mismatch that
    # smolvla_base hit: make_policy + the policy and env (LiberoProcessorStep) processors
    # all build. No MuJoCo needed (make_policy validates against the static env config).
    from lerobot.envs.factory import make_env_config

    env_cfg = make_env_config(
        "libero", task="libero_object", task_ids=[0], obs_type="pixels_agent_pos"
    )
    adapter = LeRobotAdapter(model_id=_LIBERO_CKPT, device="cpu")
    adapter.set_features(SuiteFeatures(action_dim=7, env_config=env_cfg, image_key="image"))
    adapter.load()  # must NOT raise IncompatiblePolicyError
    assert adapter._loaded is True
    assert adapter._env_preprocess is not None  # LiberoProcessorStep wired
    assert hasattr(adapter._policy, "select_action")
