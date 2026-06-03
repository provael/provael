"""LeRobot adapter tests.

Two halves:

* The **missing-dependency** test runs on a plain CPU box (where ``lerobot`` is not
  installed) and asserts the adapter fails with a clear, actionable error.
* The **integration** test is GATED: it is skipped unless BOTH
  ``ROBOPWN_INTEGRATION=1`` is set AND ``lerobot`` is importable. Enable it on a
  provisioned (GPU) machine with::

      pip install 'vla-redteam[lerobot]'
      ROBOPWN_INTEGRATION=1 pytest tests/test_lerobot_adapter.py -q
"""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

from vla_redteam.policies.lerobot_adapter import LeRobotAdapter, MissingLeRobotError

_LEROBOT_AVAILABLE = importlib.util.find_spec("lerobot") is not None
_INTEGRATION_ENABLED = os.environ.get("ROBOPWN_INTEGRATION") == "1"


@pytest.mark.skipif(_LEROBOT_AVAILABLE, reason="this test asserts the lerobot-absent path")
def test_missing_lerobot_raises_actionable_error() -> None:
    adapter = LeRobotAdapter()
    assert adapter.lerobot_available() is False
    with pytest.raises(MissingLeRobotError) as exc_info:
        adapter.load()
    message = str(exc_info.value)
    assert "lerobot" in message.lower()
    assert "vla-redteam[lerobot]" in message
    assert "ROBOPWN_INTEGRATION" in message


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires ROBOPWN_INTEGRATION=1 and an installed lerobot (see module docstring)",
)
def test_adapter_loads_against_real_api() -> None:
    # Highest-value, drift-sensitive check: the adapter actually loads SmolVLA
    # (SmolVLAPolicy.from_pretrained) and builds the verified pre/post processors
    # (make_pre_post_processors). Runs on a provisioned box without the simulator.
    adapter = LeRobotAdapter(model_id="lerobot/smolvla_base", device="cpu")
    adapter.load()
    assert adapter._loaded is True
    assert adapter._policy is not None
    assert adapter._preprocess is not None and adapter._postprocess is not None
    assert hasattr(adapter._policy, "select_action")


@pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires ROBOPWN_INTEGRATION=1 and an installed lerobot (see module docstring)",
)
def test_adapter_returns_action_for_dummy_libero_obs() -> None:
    # Build ds_features and a dummy observation from lerobot's OWN LiberoEnv config
    # (verified: action dim 7) — no fabricated schema. LiberoEnv is instantiable
    # without launching MuJoCo.
    from lerobot.datasets.feature_utils import combine_feature_dicts, hw_to_dataset_features
    from lerobot.envs.configs import LiberoEnv
    from lerobot.utils.constants import ACTION, OBS_STR

    env_cfg = LiberoEnv(task="libero_object")
    shapes = {key: feat.shape for key, feat in env_cfg.features.items()}
    obs_shapes = {k: v for k, v in shapes.items() if k != ACTION}
    ds_features = combine_feature_dicts(
        hw_to_dataset_features(obs_shapes, OBS_STR),
        hw_to_dataset_features({ACTION: shapes[ACTION]}, ACTION),
    )
    dummy_obs = {key: np.zeros(shape, dtype=np.float32) for key, shape in obs_shapes.items()}

    adapter = LeRobotAdapter(
        model_id="lerobot/smolvla_base",
        device="cpu",
        dataset_features=ds_features,
        robot_type="libero",
    )
    adapter.load()
    action = adapter.act(dummy_obs, "pick up the black bowl")

    assert isinstance(action, np.ndarray)
    assert action.ndim == 1
    assert action.size == 7  # verified LIBERO action dimension


@pytest.mark.skipif(
    _LEROBOT_AVAILABLE,
    reason="this test asserts act()'s clear error when dataset_features is absent",
)
def test_act_requires_dataset_features_message() -> None:
    # Even without lerobot we can assert the guard message names the eval path.
    from vla_redteam.policies.lerobot_adapter import LEROBOT_EVAL_LIBERO_HINT

    assert "lerobot-eval" in LEROBOT_EVAL_LIBERO_HINT
    assert "--env.type=libero" in LEROBOT_EVAL_LIBERO_HINT
