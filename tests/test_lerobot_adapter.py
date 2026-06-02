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
def test_adapter_loads_and_returns_action_of_expected_shape() -> None:
    # NOTE: the dummy observation keys are confirmed against the installed lerobot
    # API in milestone M5's verified _build/act implementation. Shape/range checks
    # here are intentionally loose so they survive minor API revisions.
    adapter = LeRobotAdapter(model_id="lerobot/smolvla_base", device="cpu")
    adapter.load()

    dummy_obs = {
        "rgb": np.zeros((256, 256, 3), dtype=np.uint8),
        "proprio": np.zeros(7, dtype=np.float32),
        "instruction": "pick up the cup",
    }
    action = adapter.act(dummy_obs, "pick up the cup")

    assert isinstance(action, np.ndarray)
    assert action.ndim == 1
    assert action.size >= 1
