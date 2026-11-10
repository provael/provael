# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""LeRobot SmolVLA adapter tests.

* CPU tests (no GPU/lerobot): the missing-dependency error, the eval hint, the pure
  ``clamp_action`` mapping, and the features-protocol no-op for the stub.
* GATED test (skipif not PROVAEL_INTEGRATION==1 and lerobot importable): the adapter
  loads SmolVLA via the verified ``make_policy`` + processor path with LIBERO features.
  Enable on a provisioned box::

      pip install 'provael[lerobot]' 'lerobot[libero]==0.5.1'
      PROVAEL_INTEGRATION=1 pytest tests/test_lerobot_adapter.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pytest

from provael.policies.lerobot_adapter import (
    LEROBOT_EVAL_LIBERO_HINT,
    IncompatiblePolicyError,
    LeRobotAdapter,
    MissingLeRobotError,
    clamp_action,
)
from provael.policies.stub import ACTION_DIM as STUB_ACTION_DIM
from provael.policies.stub import StubPolicy
from provael.types import DeployedPolicy, SuiteFeatures

_LEROBOT_AVAILABLE = importlib.util.find_spec("lerobot") is not None
_INTEGRATION_ENABLED = os.environ.get("PROVAEL_INTEGRATION") == "1"
#: A READY LIBERO-fine-tuned SmolVLA checkpoint (verified to load through the glue).
_LIBERO_CKPT = os.environ.get("PROVAEL_SMOLVLA_LIBERO_CKPT", "HuggingFaceVLA/smolvla_libero")


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
    assert action.shape == (STUB_ACTION_DIM,)  # the stub's own fixture width, not the passed dim


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
    assert "provael[lerobot]" in message
    assert "PROVAEL_INTEGRATION" in message


def test_eval_hint_names_the_supported_path() -> None:
    assert "lerobot-eval" in LEROBOT_EVAL_LIBERO_HINT
    assert "--env.type=libero" in LEROBOT_EVAL_LIBERO_HINT


def test_incompatibility_hint_points_at_the_ready_checkpoint() -> None:
    # The IncompatiblePolicyError message must name the fix, not make a forgetful user
    # rediscover it.
    from provael.policies.lerobot_adapter import _CHECKPOINT_HINT, LIBERO_FINETUNED_SMOLVLA

    assert LIBERO_FINETUNED_SMOLVLA == "HuggingFaceVLA/smolvla_libero"
    assert LIBERO_FINETUNED_SMOLVLA in _CHECKPOINT_HINT
    assert "--model" in _CHECKPOINT_HINT
    # The template still formats cleanly (only {model}/{error} are placeholders).
    formatted = _CHECKPOINT_HINT.format(model="lerobot/smolvla_base", error="feature mismatch")
    assert "lerobot/smolvla_base" in formatted and "smolvla_libero" in formatted


# --------------------------------------------------------------------------- #
# CPU: the runtime identity, resolved over a fake LeRobot pipeline (schema 9, P1.1)
# --------------------------------------------------------------------------- #

#: Every DeployedPolicy field the adapter resolves at load. The fake below sets each one, so a
#: field the adapter forgets to read comes back None and fails the test by name.
_RESOLVED_FIELDS = (
    "policy_class", "checkpoint", "action_unnormaliser", "controller_convention",
    "input_normaliser", "preprocessor_digest", "postprocessor_digest", "weights_digest",
    "rename_map", "camera_keys", "denoising_steps", "control_rate_hz",
    "temporal_ensemble_coeff", "discrete_state_input",
)


class _Tensor:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def detach(self) -> _Tensor:
        return self

    def cpu(self) -> _Tensor:
        return self

    def tolist(self) -> list[float]:
        return list(self._values)


class NormalizerProcessorStep:
    def get_config(self) -> dict[str, object]:
        return {"norm_map": {"ACTION": "MEAN_STD", "STATE": "MEAN_STD", "VISUAL": "IDENTITY"}}

    def state_dict(self) -> dict[str, _Tensor]:
        return {"observation.state.mean": _Tensor([0.1]), "observation.state.std": _Tensor([1.0])}


class UnnormalizerProcessorStep:
    def get_config(self) -> dict[str, object]:
        return {"norm_map": {"ACTION": "MEAN_STD"}}

    def state_dict(self) -> dict[str, _Tensor]:
        return {"action.mean": _Tensor([0.0]), "action.std": _Tensor([2.0])}


class RenameObservationsProcessorStep:
    def get_config(self) -> dict[str, object]:
        return {"rename_map": {"observation.images.top": "observation.images.image"}}


class _Pipeline:
    def __init__(self, *steps: object) -> None:
        self.steps = list(steps)


class _FakeConfig:
    """The attributes lerobot 0.5.1's policy configs carry, plus the two no SmolVLA has."""

    chunk_size = 50
    n_action_steps = 1
    num_steps = 10
    temporal_ensemble_coeff = 0.01
    discrete_state_input = False
    image_features = {"observation.images.image": None, "observation.images.image2": None}


class SmolVLAPolicy:
    config = _FakeConfig()


def _local_checkpoint(root: Path) -> Path:
    root.mkdir(parents=True)
    for name, state in (("policy_preprocessor.json", "pre.safetensors"),
                        ("policy_postprocessor.json", "post.safetensors")):
        (root / name).write_text(json.dumps({"steps": [{"state_file": state}]}), encoding="utf-8")
        (root / state).write_bytes(state.encode())
    (root / "model.safetensors").write_bytes(b"weights")
    return root


def test_identity_over_a_fake_pipeline_fills_every_field(tmp_path: Path) -> None:
    """The CPU twin of the gated load below: every field resolved, nothing invented."""
    ckpt = _local_checkpoint(tmp_path / "ckpt")
    adapter = LeRobotAdapter(model_id=str(ckpt), device="cpu")
    adapter.set_features(SuiteFeatures(action_dim=7, fps=20, image_key="image"))
    adapter._preprocess = _Pipeline(RenameObservationsProcessorStep(), NormalizerProcessorStep())
    adapter._postprocess = _Pipeline(UnnormalizerProcessorStep())
    adapter._env_postprocess = _Pipeline()
    resolved = adapter._resolve_identity(SmolVLAPolicy(), _FakeConfig())
    for name in _RESOLVED_FIELDS:
        assert getattr(resolved, name) is not None, f"{name} was not resolved"
    assert resolved.policy_class == "SmolVLAPolicy" and resolved.checkpoint == str(ckpt)
    assert resolved.input_normaliser is not None
    assert (resolved.input_normaliser.state_mode, resolved.input_normaliser.visual_mode) == (
        "MEAN_STD", "IDENTITY")
    assert resolved.rename_map == {"observation.images.top": "observation.images.image"}
    assert resolved.camera_keys == ["observation.images.image", "observation.images.image2"]
    assert (resolved.denoising_steps, resolved.control_rate_hz) == (10, 20)
    assert (resolved.temporal_ensemble_coeff, resolved.discrete_state_input) == (0.01, False)
    # The digest is the one build() derives, so the block cannot carry a hand-set identity.
    fields = {name: getattr(resolved, name) for name in DeployedPolicy.model_fields}
    del fields["digest"]
    assert DeployedPolicy.build(**fields).digest == resolved.digest
    # A requested rename map with no rename step in the pipeline is recorded as requested.
    adapter.rename_map = {"a": "b"}
    adapter._preprocess = None
    assert adapter._resolve_identity(SmolVLAPolicy(), _FakeConfig()).rename_map == {"a": "b"}


# --------------------------------------------------------------------------- #
# GATED: real load via the verified make_policy + processor path
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires PROVAEL_INTEGRATION=1 and an installed lerobot (see module docstring)",
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
    reason="requires PROVAEL_INTEGRATION=1 and an installed lerobot (downloads the checkpoint)",
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


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires PROVAEL_INTEGRATION=1 and an installed lerobot (downloads the checkpoint)",
)
def test_a_real_load_resolves_the_schema_9_identity() -> None:
    """On a real SmolVLA load every field SmolVLA has is non-null (P1.1).

    Two fields have no SmolVLA setting and stay None by design: ACT's temporal-ensembling
    coefficient and openpi's discrete state input. No rename map is passed here and the
    checkpoint's pre-processor carries no rename step, so the map is the empty one.
    """
    from lerobot.envs.factory import make_env_config

    env_cfg = make_env_config(
        "libero", task="libero_object", task_ids=[0], obs_type="pixels_agent_pos"
    )
    adapter = LeRobotAdapter(model_id=_LIBERO_CKPT, device="cpu")
    adapter.set_features(
        SuiteFeatures(action_dim=7, fps=int(env_cfg.fps), env_config=env_cfg, image_key="image")
    )
    adapter.load()
    resolved = adapter.resolved_identity
    assert resolved is not None
    for name in ("input_normaliser", "preprocessor_digest", "postprocessor_digest",
                 "weights_digest", "rename_map", "camera_keys", "denoising_steps",
                 "control_rate_hz"):
        assert getattr(resolved, name) is not None, f"{name} was not resolved on a real load"
    assert resolved.camera_keys and resolved.denoising_steps is not None
    assert resolved.temporal_ensemble_coeff is None and resolved.discrete_state_input is None
