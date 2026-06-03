"""Adapter for real VLA policies loaded through LeRobot (e.g. SmolVLA).

DESIGN: this module imports **no** optional dependency at module scope, so the core
package stays importable on a plain CPU with the ``[lerobot]`` extra absent. All
contact with ``lerobot`` / ``torch`` happens inside :meth:`LeRobotAdapter.load`,
which raises a clear, actionable error when the extra is missing.

VERIFICATION (milestone M5): the calls below were written **after** introspecting
the installed ``lerobot==0.5.1`` package — symbols and signatures were confirmed,
not guessed. The verified facts:

  * ``lerobot.policies.smolvla.modeling_smolvla.SmolVLAPolicy.from_pretrained(id)``
    loads the policy. SmolVLA additionally needs the ``[smolvla]`` extra
    (transformers) — base ``lerobot`` alone raises ``No module named 'transformers'``.
  * ``lerobot.policies.factory.make_pre_post_processors(policy_cfg, pretrained_path=None,
    **kwargs) -> (preprocess_pipeline, postprocess_pipeline)``.
  * ``lerobot.policies.utils.build_inference_frame(observation, device, ds_features,
    task=None, robot_type=None) -> dict`` builds a model-ready frame from a raw obs.
  * ``PreTrainedPolicy.select_action(batch: dict[str, torch.Tensor]) -> torch.Tensor``.

This mirrors the official single-observation example shipped at
``examples/tutorial/smolvla/using_smolvla_example.py`` (v0.5.1):
``build_inference_frame -> preprocess -> select_action -> postprocess``.

The raw-observation -> ``ds_features`` wiring for a full simulator (LIBERO) belongs
to the LIBERO ``SuiteAdapter`` (Part 2); ``lerobot-eval`` already does it end to end.
See :data:`LEROBOT_EVAL_LIBERO_HINT`.

Enable the real path on a GPU box::

    pip install 'vla-redteam[lerobot]'         # pulls lerobot[smolvla]==0.5.1
    ROBOPWN_INTEGRATION=1 pytest tests/test_lerobot_adapter.py -q
"""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np

from vla_redteam.policies.base import PolicyAdapter
from vla_redteam.types import Action, Observation

_INSTALL_HINT = (
    "The '{name}' policy requires the optional LeRobot dependency, which is not "
    "installed.\n"
    "  1. Install the extra:  pip install 'vla-redteam[lerobot]'\n"
    "     (pulls lerobot[smolvla]==0.5.1; needs Python >=3.12 and a GPU machine.)\n"
    "  2. For the LIBERO simulator, also install LeRobot's LIBERO extra:\n"
    "       pip install 'lerobot[libero]==0.5.1'\n"
    "  3. Enable the gated integration path:  ROBOPWN_INTEGRATION=1\n"
    "Run on CPU with '--policy stub' to exercise the full pipeline with no model."
)

#: The verified, documented way to evaluate SmolVLA on LIBERO with LeRobot today.
#: The full LIBERO SuiteAdapter is Part 2; until then this is the supported path.
LEROBOT_EVAL_LIBERO_HINT = (
    "lerobot-eval --policy.path=lerobot/smolvla_base --env.type=libero "
    "--env.task=libero_object   # or libero_10 / libero_spatial / libero_goal"
)


class MissingLeRobotError(RuntimeError):
    """Raised when a LeRobot-backed policy is used without the ``[lerobot]`` extra."""


class LeRobotAdapter(PolicyAdapter):
    """Loads a LeRobot policy (default: ``lerobot/smolvla_base``) and runs it.

    Construction is cheap and imports nothing optional. :meth:`load` performs the
    guarded import and builds the policy + pre/post processors. :meth:`act` runs the
    verified single-observation inference pipeline and returns a 1-D ``numpy`` action.

    ``dataset_features`` / ``robot_type`` describe the observation schema for
    :func:`build_inference_frame`; they are supplied by the environment adapter
    (e.g. a LIBERO ``SuiteAdapter`` in Part 2). Without them :meth:`act` raises a
    clear error pointing at :data:`LEROBOT_EVAL_LIBERO_HINT`.
    """

    def __init__(
        self,
        model_id: str = "lerobot/smolvla_base",
        name: str = "smolvla",
        device: str = "cuda",
        dataset_features: dict[str, dict[str, Any]] | None = None,
        robot_type: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.name = name
        self.device = device
        self.dataset_features = dataset_features
        self.robot_type = robot_type
        self._policy: Any = None
        self._preprocess: Any = None
        self._postprocess: Any = None
        self._torch: Any = None
        self._device: Any = None
        self._loaded = False

    # -- availability -------------------------------------------------------

    @staticmethod
    def lerobot_available() -> bool:
        """True if ``lerobot`` is importable without importing it."""
        return importlib.util.find_spec("lerobot") is not None

    # -- lifecycle ----------------------------------------------------------

    def load(self) -> None:
        """Import lerobot (guarded) and build the policy + processors.

        Raises:
            MissingLeRobotError: if the ``[lerobot]`` extra is not installed.
        """
        if not self.lerobot_available():
            raise MissingLeRobotError(_INSTALL_HINT.format(name=self.name))

        # Imports are deferred to here (verified against lerobot==0.5.1).
        import torch
        from lerobot.policies.factory import make_pre_post_processors
        from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

        self._torch = torch
        self._device = torch.device(self.device)

        policy = SmolVLAPolicy.from_pretrained(self.model_id)
        policy.to(self._device)
        policy.eval()
        policy.reset()  # clear the action queue between episodes

        # make_pre_post_processors(policy_cfg, pretrained_path, **kwargs) -> (pre, post)
        preprocess, postprocess = make_pre_post_processors(
            policy.config,
            self.model_id,
            preprocessor_overrides={"device_processor": {"device": str(self._device)}},
        )

        self._policy = policy
        self._preprocess = preprocess
        self._postprocess = postprocess
        self._loaded = True

    def act(self, observation: Observation, instruction: str) -> Action:
        """Run verified inference: build frame -> preprocess -> select_action -> postprocess.

        Returns a 1-D float32 ``numpy`` action vector.
        """
        if not self._loaded:
            raise RuntimeError("LeRobotAdapter.act called before load(); call load() first.")
        if self.dataset_features is None:
            raise RuntimeError(
                "LeRobotAdapter.act needs `dataset_features` describing the observation "
                "schema (built by the environment/suite adapter). The full LIBERO wiring "
                "is Part 2; today use lerobot-eval directly:\n  " + LEROBOT_EVAL_LIBERO_HINT
            )

        from lerobot.policies.utils import build_inference_frame

        frame = build_inference_frame(
            observation=observation,
            device=self._device,
            ds_features=self.dataset_features,
            task=instruction,
            robot_type=self.robot_type,
        )
        batch = self._preprocess(frame)
        with self._torch.inference_mode():
            action_tensor = self._policy.select_action(batch)
        action_tensor = self._postprocess(action_tensor)

        result: Action = np.asarray(
            action_tensor.detach().to("cpu").numpy(), dtype=np.float32
        ).reshape(-1)
        return result


__all__ = ["LeRobotAdapter", "MissingLeRobotError", "LEROBOT_EVAL_LIBERO_HINT"]
