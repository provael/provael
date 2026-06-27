"""Adapter for real VLA policies loaded through LeRobot (e.g. SmolVLA).

DESIGN: this module imports **no** optional dependency at module scope, so the core
package stays importable on a plain CPU with the ``[lerobot]`` extra absent. All
contact with ``lerobot`` / ``torch`` happens inside :meth:`LeRobotAdapter.load` /
:meth:`~LeRobotAdapter.act`, which raise a clear, actionable error when the extra is
missing.

VERIFICATION (milestone M2): :meth:`act` replicates LeRobot's own evaluator rollout
(``lerobot/scripts/lerobot_eval.py``) for ``lerobot==0.5.1`` — read, not guessed. The
verified per-step path is::

    obs = preprocess_observation(raw_obs)        # lerobot.envs.utils
    obs["task"] = [instruction] * n_envs         # (we inject the *attacked* instruction
                                                 #  here, replacing add_envs_task)
    obs = env_preprocessor(obs)                  # LiberoProcessorStep (robot_state -> state)
    obs = preprocessor(obs)                      # policy preprocessor (normalize + device)
    action = policy.select_action(obs)           # one action; chunk queue is internal
    action = postprocessor(action)               # unnormalize
    action = env_postprocessor({ACTION: action})[ACTION]   # identity for LIBERO
    action = action.cpu().numpy()                # (n_envs, action_dim) -> clamp to [-1, 1]

Setup mirrors eval: ``make_policy(cfg=policy_cfg, env_cfg=env_cfg)`` +
``make_pre_post_processors(policy_cfg, pretrained_path, …)`` +
``make_env_pre_post_processors(env_cfg, policy_cfg)``. The env config is supplied by the
suite via :class:`~provael.types.SuiteFeatures` (``set_features``).

NOTE: real-policy inference is **model-stochastic**; reports for it are seeded but NOT
byte-deterministic (only the stub is). See SAFETY.md / README.

Enable the real path on a GPU box::

    pip install 'provael[lerobot]' 'lerobot[libero]==0.5.1'
    PROVAEL_INTEGRATION=1 pytest tests/test_lerobot_adapter.py tests/test_libero_adapter.py -q
"""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np

from provael.policies.base import PolicyAdapter
from provael.types import Action, Observation, SuiteFeatures

_INSTALL_HINT = (
    "The '{name}' policy requires the optional LeRobot dependency, which is not "
    "installed.\n"
    "  1. Install the extra:  pip install 'provael[lerobot]'\n"
    "     (pulls lerobot[smolvla]==0.5.1; needs Python >=3.12 and a GPU machine.)\n"
    "  2. For the LIBERO simulator, also install LeRobot's LIBERO extra:\n"
    "       pip install 'lerobot[libero]==0.5.1'\n"
    "  3. Enable the gated integration path:  PROVAEL_INTEGRATION=1\n"
    "Run on CPU with '--policy stub' to exercise the full pipeline with no model."
)

#: LeRobot's own evaluator — the documented reference for SmolVLA-on-LIBERO.
LEROBOT_EVAL_LIBERO_HINT = (
    "lerobot-eval --policy.path=<your-libero-finetuned-smolvla> --env.type=libero "
    "--env.task=libero_object   # or libero_10 / libero_spatial / libero_goal"
)

#: A ready LIBERO-fine-tuned SmolVLA checkpoint, verified to load through the glue.
LIBERO_FINETUNED_SMOLVLA = "HuggingFaceVLA/smolvla_libero"

#: Surfaced when ``make_policy`` rejects the checkpoint for the env's features. VERIFIED
#: by running it: ``lerobot/smolvla_base`` expects ``observation.images.camera1/2/3`` but
#: LIBERO provides ``image``/``image2`` (+ 8-dim state) — the base model is NOT directly
#: evaluable on LIBERO; it must be fine-tuned on LIBERO first (per the official docs). The
#: message names the ready fix so a forgetful user doesn't have to rediscover it.
_CHECKPOINT_HINT = (
    "The policy checkpoint '{model}' is not compatible with the LIBERO observation "
    "features.\nlerobot's make_policy reported:\n  {error}\n"
    "LIBERO provides 2 cameras (observation.images.image, image2) + 8-dim state; "
    "lerobot/smolvla_base expects camera1/2/3 and is untrained on LIBERO.\n"
    "Fix: pass a LIBERO-fine-tuned checkpoint, e.g.\n"
    f"  --model {LIBERO_FINETUNED_SMOLVLA}   (a ready LIBERO-fine-tuned SmolVLA)\n"
    "Or train your own: lerobot-train --policy.type=smolvla --policy.load_vlm_weights=true "
    "--dataset.repo_id=HuggingFaceVLA/libero --env.type=libero --env.task=libero_10\n"
    "If your checkpoint uses different obs keys, also pass --rename-map (LeRobot LIBERO docs)."
)


class MissingLeRobotError(RuntimeError):
    """Raised when a LeRobot-backed policy is used without the ``[lerobot]`` extra."""


class IncompatiblePolicyError(RuntimeError):
    """Raised when a checkpoint's features don't match the env (needs fine-tuning/rename)."""


def clamp_action(action: object, action_dim: int, low: float = -1.0, high: float = 1.0) -> Action:
    """Flatten a policy action to ``(action_dim,)`` float32 and clamp to ``[low, high]``.

    Pure / CPU-testable. If more than ``action_dim`` values are present (e.g. an action
    chunk leaked through), the first ``action_dim`` are taken (the first timestep).
    """
    flat = np.asarray(action, dtype=np.float32).reshape(-1)
    trimmed = flat[:action_dim] if flat.size > action_dim else flat
    result: Action = np.clip(trimmed, low, high).astype(np.float32)
    return result


class LeRobotAdapter(PolicyAdapter):
    """Loads a LeRobot policy (default ``lerobot/smolvla_base``) and runs it on real obs.

    Construction imports nothing optional. The suite hands env metadata via
    :meth:`set_features`; :meth:`load` builds the policy + the verified pre/post and
    env pre/post processors; :meth:`act` runs one rollout step and returns a clamped
    ``(action_dim,)`` numpy action.
    """

    #: Real VLA inference is model-stochastic (reports are seeded but not byte-identical).
    stochastic = True

    def __init__(
        self,
        model_id: str = "lerobot/smolvla_base",
        name: str = "smolvla",
        device: str = "cuda",
        rename_map: dict[str, str] | None = None,
    ) -> None:
        self.model_id = model_id
        self.name = name
        self.device = device
        self.rename_map = rename_map
        self._features: SuiteFeatures | None = None
        self._policy: Any = None
        self._preprocess: Any = None
        self._postprocess: Any = None
        self._env_preprocess: Any = None
        self._env_postprocess: Any = None
        self._torch: Any = None
        self._device: Any = None
        self._action_constant: str = "action"
        self._loaded = False

    # -- availability / features -------------------------------------------

    @staticmethod
    def lerobot_available() -> bool:
        """True if ``lerobot`` is importable without importing it."""
        return importlib.util.find_spec("lerobot") is not None

    def set_features(self, features: SuiteFeatures) -> None:
        self._features = features

    # -- lifecycle ----------------------------------------------------------

    def load(self) -> None:
        """Import lerobot (guarded) and build the policy + processors (verified eval path)."""
        if not self.lerobot_available():
            raise MissingLeRobotError(_INSTALL_HINT.format(name=self.name))

        import torch
        from lerobot.configs.policies import PreTrainedConfig
        from lerobot.envs.factory import make_env_pre_post_processors
        from lerobot.policies.factory import make_policy, make_pre_post_processors
        from lerobot.utils.constants import ACTION

        self._torch = torch
        self._action_constant = ACTION
        device = torch.device(self.device)
        self._device = device

        env_cfg = self._features.env_config if self._features is not None else None

        # Mirror lerobot_eval: build the policy config, then make_policy(cfg, env_cfg,
        # rename_map). make_policy requires an env (or dataset) and validates that the
        # checkpoint's visual/state features match the env's.
        policy_cfg = PreTrainedConfig.from_pretrained(self.model_id)
        policy_cfg.pretrained_path = self.model_id
        policy_cfg.device = str(device)

        try:
            policy = make_policy(cfg=policy_cfg, env_cfg=env_cfg, rename_map=self.rename_map)
        except ValueError as exc:
            raise IncompatiblePolicyError(
                _CHECKPOINT_HINT.format(model=self.model_id, error=exc)
            ) from exc
        policy.eval()
        self._policy = policy

        preprocessor_overrides: dict[str, Any] = {"device_processor": {"device": str(device)}}
        if self.rename_map is not None:
            preprocessor_overrides["rename_observations_processor"] = {
                "rename_map": self.rename_map
            }
        self._preprocess, self._postprocess = make_pre_post_processors(
            policy_cfg=policy_cfg,
            pretrained_path=policy_cfg.pretrained_path,
            preprocessor_overrides=preprocessor_overrides,
        )
        if env_cfg is not None:
            self._env_preprocess, self._env_postprocess = make_env_pre_post_processors(
                env_cfg=env_cfg, policy_cfg=policy_cfg
            )
        self._loaded = True

    def reset(self) -> None:
        """Clear the policy's internal action queue between episodes (verified eval call)."""
        if self._policy is not None:
            self._policy.reset()

    def _apply_image_override(self, observation: Observation, raw: Any) -> Any:
        """Fold ``observation[image_key]`` (an attack may have edited it) back into ``raw``.

        Returns a shallow copy of ``raw`` with the primary camera image replaced (re-adding
        the env's batch dim). No-op if no image / pixels key is present.
        """
        image_key = self._features.image_key if self._features is not None else None
        image = observation.get(image_key) if image_key else None
        pixels_key = observation.get("pixels_key")
        if image is None or pixels_key is None:
            return raw
        if not (isinstance(raw, dict) and isinstance(raw.get("pixels"), dict)):
            return raw
        batched = np.asarray(image)[None, ...]  # (H, W, 3) -> (1, H, W, 3)
        return {**raw, "pixels": {**raw["pixels"], pixels_key: batched}}

    def act(self, observation: Observation, instruction: str) -> Action:
        """Run one verified rollout step on a real LIBERO observation; return a (7,) action."""
        if not self._loaded:
            raise RuntimeError("LeRobotAdapter.act called before load(); call load() first.")
        if self._env_preprocess is None:
            raise RuntimeError(
                "LeRobotAdapter needs a suite that provides env features (use "
                "'--suite libero'). For reference numbers without the in-process loop:\n  "
                + LEROBOT_EVAL_LIBERO_HINT
            )

        from lerobot.envs.utils import preprocess_observation

        raw = observation.get("raw", observation)
        # Fold a (possibly attack-modified) image back into the raw obs the policy reads.
        raw = self._apply_image_override(observation, raw)
        obs_t = preprocess_observation(raw)
        batch_size = next((v.shape[0] for v in obs_t.values() if hasattr(v, "shape")), 1)
        # Inject OUR (possibly adversarial) instruction as the task (replaces add_envs_task).
        obs_t["task"] = [instruction] * batch_size
        obs_t = self._env_preprocess(obs_t)
        obs_t = self._preprocess(obs_t)
        with self._torch.inference_mode():
            action = self._policy.select_action(obs_t)
        action = self._postprocess(action)
        action = self._env_postprocess({self._action_constant: action})[self._action_constant]

        action_dim = self._features.action_dim if self._features is not None else action.shape[-1]
        return clamp_action(action.detach().to("cpu").numpy(), action_dim)


__all__ = [
    "LeRobotAdapter",
    "MissingLeRobotError",
    "IncompatiblePolicyError",
    "LEROBOT_EVAL_LIBERO_HINT",
    "LIBERO_FINETUNED_SMOLVLA",
    "clamp_action",
]
