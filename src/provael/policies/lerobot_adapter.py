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
import numpy.typing as npt

from provael.policies.base import PolicyAdapter
from provael.policies.identity import (
    resolve_hub_revision,
    step_names,
    unnormaliser_from_pipeline,
)
from provael.types import (
    IMAGE_KEY,
    Action,
    ControllerConvention,
    DeployedPolicy,
    Observation,
    SuiteFeatures,
)

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


#: The layer whose weight matrix the weight-integrity family corrupts: the final projection from
#: the action expert's hidden state to the action chunk. Every LeRobot flow-matching policy this
#: adapter loads names it ``model.action_out_proj`` (SmolVLA, pi0, pi0.5 — read in lerobot 0.5.1).
#: pi0-FAST decodes discrete tokens and has no such layer, so on it the family is not applicable —
#: reported as such, never as a null.
WEIGHT_SURFACE_ATTR = "action_out_proj"
#: Symmetric INT8 range. ``-128`` is reachable by a bit flip and dequantizes like any other value.
INT8_MAX = 127


def symmetric_int8(weights: npt.NDArray[np.floating]) -> tuple[npt.NDArray[np.int8], float]:
    """A per-tensor symmetric INT8 view of a float weight matrix: ``(q, scale)``, ``w ~ q*scale``.

    One scale for the whole tensor, on purpose: ``provael.attacks.weight_integrity._flip_deltas``
    ranks candidate bits by their dequantized ``Δθ``, and a single scale keeps every bit in the
    tensor on one unit. The family's own ``SCALE`` differs from this one by a positive constant, so
    the ranking is identical; only the absolute step size is the adapter's.
    """
    flat = np.asarray(weights, dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(flat))) if flat.size else 0.0
    scale = peak / INT8_MAX if peak > 0.0 else 1.0
    q = np.clip(np.rint(flat / np.float32(scale)), -INT8_MAX, INT8_MAX).astype(np.int8)
    return q, scale


def dequantized_delta(
    params: npt.NDArray[np.int8], clean: npt.NDArray[np.int8], scale: float
) -> npt.NDArray[np.float32]:
    """The float change a corrupted INT8 vector implies against its clean view.

    Applied as a *delta* on the original float weights rather than by dequantizing ``params``
    outright, so that restoring the clean vector restores the original weights **exactly** —
    dequantizing would round every untouched parameter to its INT8 grid and leak a quantization
    error into every episode scored after the first weight attack.
    """
    a = np.asarray(params, dtype=np.int8).reshape(-1).astype(np.int32)
    b = np.asarray(clean, dtype=np.int8).reshape(-1).astype(np.int32)
    if a.size != b.size:
        raise ValueError(f"expected {b.size} INT8 parameters, got {a.size}")
    return ((a - b).astype(np.float32) * np.float32(scale)).astype(np.float32)


class MissingLeRobotError(RuntimeError):
    """Raised when a LeRobot-backed policy is used without the ``[lerobot]`` extra."""


class IncompatiblePolicyError(RuntimeError):
    """Raised when a checkpoint's features don't match the env (needs fine-tuning/rename)."""


def _int_or_none(value: object) -> int | None:
    """An int for a config field that is one, ``None`` for anything else (absent, None, odd)."""
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else None


def clamp_action(action: object, action_dim: int, low: float = -1.0, high: float = 1.0) -> Action:
    """Flatten a policy action to ``(action_dim,)`` float32 and clamp to ``[low, high]``.

    Pure / CPU-testable. If more than ``action_dim`` values are present (e.g. an action
    chunk leaked through), the first ``action_dim`` are taken (the first timestep).
    """
    flat = np.asarray(action, dtype=np.float32).reshape(-1)
    trimmed = flat[:action_dim] if flat.size > action_dim else flat
    result: Action = np.clip(trimmed, low, high).astype(np.float32)
    return result


_PRECISION_NAMES = {"float32": "fp32", "bfloat16": "bf16", "float16": "fp16", "float64": "fp64"}


def _precision_of(policy: Any) -> str | None:
    """``fp32`` / ``bf16`` / ``fp16`` from the loaded parameters' dtype; None when it cannot tell.

    The first parameter's dtype, which is what every mixed-precision recipe in lerobot keys on. A
    dtype outside the table (an integer-quantised checkpoint, say) is reported as None rather than
    coerced into the nearest float name.
    """
    try:
        dtype = str(next(policy.parameters()).dtype)
    except Exception:  # noqa: BLE001 - a policy with no parameters records no precision
        return None
    return _PRECISION_NAMES.get(dtype.removeprefix("torch."))


class LeRobotAdapter(PolicyAdapter):
    """Loads a LeRobot policy (default ``lerobot/smolvla_base``) and runs it on real obs.

    Construction imports nothing optional. The suite hands env metadata via
    :meth:`set_features`; :meth:`load` builds the policy + the verified pre/post and
    env pre/post processors; :meth:`act` runs one rollout step and returns a clamped
    ``(action_dim,)`` numpy action.
    """

    #: SmolVLA and the pi0 / pi0.5 checkpoints this adapter loads use flow-matching action
    #: heads. pi0-FAST is the exception (discrete FAST tokens) and should override this.
    action_head_class = "flow"


    #: Real VLA inference is model-stochastic (reports are seeded but not byte-identical).
    stochastic = True

    def __init__(
        self,
        model_id: str = "lerobot/smolvla_base",
        name: str = "smolvla",
        device: str = "cuda",
        rename_map: dict[str, str] | None = None,
        dataset_repo_id: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.name = name
        self.device = device
        self.rename_map = rename_map
        #: Shape the policy from a RECORDED DATASET instead of a live env.
        #:
        #: lerobot's make_policy needs one or the other — it reads the observation and action
        #: features from whichever it is given, and refuses with "Either one of a dataset metadata
        #: or a sim env must be provided" when handed neither. This adapter was written for the
        #: simulation path, so it only ever passed an env config, which made it unusable for any
        #: study that replays recordings and never simulates.
        #:
        #: Set this and the policy is built from LeRobotDatasetMetadata(dataset_repo_id).
        self.dataset_repo_id = dataset_repo_id
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
        # White-box surfaces (see the two sections at the end of the class). The clean float copy
        # of the weight surface, its INT8 view and scale, the reference operating point for the
        # sensitivity pass, and one-slot caches for the sensitivity vector and the clean image
        # feature. None of these exist until an attack asks for them.
        self._weight_clean: Any = None
        self._weight_q: npt.NDArray[np.int8] | None = None
        self._weight_scale: float = 1.0
        self._reference: tuple[Observation, str, int] | None = None
        self._sensitivity: npt.NDArray[np.float32] | None = None
        self._clean_feature: tuple[int, int, Any] | None = None

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
        # Record what we actually loaded onto (torch normalises e.g. "cuda" -> "cuda"), so the
        # report states the resolved device rather than the requested one.
        self.resolved_device = str(device)

        env_cfg = self._features.env_config if self._features is not None else None

        # Mirror lerobot_eval: build the policy config, then make_policy(cfg, env_cfg,
        # rename_map). make_policy requires an env (or dataset) and validates that the
        # checkpoint's visual/state features match the env's.
        policy_cfg = PreTrainedConfig.from_pretrained(self.model_id)
        policy_cfg.pretrained_path = self.model_id
        policy_cfg.device = str(device)

        # A recorded dataset can shape the policy exactly as an env does — same features, read from
        # the recording instead of the simulator. Without this branch an offline study is impossible
        # by construction, because it has no env to hand over and make_policy refuses on neither.
        ds_meta = None
        if self.dataset_repo_id is not None:
            from lerobot.datasets.dataset_metadata import LeRobotDatasetMetadata

            # revision="main" skips lerobot's get_safe_version, which demands a GIT TAG naming the
            # codebase version (e.g. "v3.0") and refuses a dataset that lacks one. Most published
            # SO-101 datasets have no such tag — of the two verified v3.0 candidates for the offline
            # study, neither carries it — so the check rejects perfectly valid data on a
            # housekeeping detail its uploader never knew about.
            #
            # Skipping it is safe HERE and only here: provael.datasets.lerobot_frames has already
            # read meta/info.json and asserted codebase_version, robot_type and dimensionality
            # before this point. We are not trusting the dataset, we are trusting our own check
            # instead of a tag.
            #
            # It also sidesteps a second failure: in lerobot 0.5.1 with huggingface_hub 1.x, the
            # raise inside get_safe_version is itself broken (HfHubHTTPError now requires
            # `response`), so the refusal surfaces as an unrelated TypeError.
            ds_meta = LeRobotDatasetMetadata(self.dataset_repo_id, revision="main")

        try:
            policy = make_policy(
                cfg=policy_cfg, ds_meta=ds_meta, env_cfg=env_cfg, rename_map=self.rename_map
            )
        except ValueError as exc:
            raise IncompatiblePolicyError(
                _CHECKPOINT_HINT.format(model=self.model_id, error=exc)
            ) from exc
        policy.eval()
        self._policy = policy
        # The precision the checkpoint actually loaded at, read off its parameters rather than
        # assumed from a flag: report.precision and the execution manifest's `precision` were None
        # on every committed real-model run, which `missing_fields` reported truthfully and which
        # the scheduled lane's provenance gate now refuses.
        self.resolved_precision = _precision_of(policy)

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
        self.resolved_identity = self._resolve_identity(policy, policy_cfg)

    def _resolve_identity(self, policy: Any, policy_cfg: Any) -> DeployedPolicy:
        """What executed, read off the live objects rather than the request (issue #227).

        Each part is resolved independently and records ``None`` where it cannot be read: the
        revision comes from the Hub cache path the config was loaded from (no network, ``None`` for
        a local checkout); the unnormaliser and its statistics from the post-processing pipeline
        that :meth:`act` really applies; the controller convention from the policy config and the
        env post-processor between the policy and the simulator. The clamp is the one this adapter
        applies itself in :meth:`act`, so it is recorded as part of the convention.
        """
        pipeline = step_names(self._postprocess) + step_names(self._env_postprocess)
        cfg = policy_cfg
        convention = ControllerConvention(
            action_dim=self._features.action_dim if self._features is not None else None,
            chunk_size=_int_or_none(getattr(cfg, "chunk_size", None)),
            n_action_steps=_int_or_none(getattr(cfg, "n_action_steps", None)),
            action_bounds=(-1.0, 1.0),
            pipeline=pipeline,
        )
        return DeployedPolicy.build(
            adapter=self.name,
            policy_class=type(policy).__name__,
            checkpoint=self.model_id,
            checkpoint_revision=resolve_hub_revision(self.model_id),
            action_unnormaliser=unnormaliser_from_pipeline(
                self._postprocess, source="lerobot-postprocessor"
            ),
            controller_convention=convention,
        )

    def reset(self) -> None:
        """Clear the policy's internal action queue between episodes (verified eval call)."""
        if self._policy is not None:
            self._policy.reset()

    def seed(self, seed: int) -> int | None:
        """Seed torch's RNGs so the flow-matching sampler is a function of the episode seed.

        WHAT THIS FIXES. The leaderboard's caveat — "SmolVLA's flow-matching sampler is not fully
        seeded, treat every number as one draw" — was true because nothing seeded it. The
        environment got ``suite.reset(task, seed)``; the policy got nothing, so the denoising
        noise came from whatever state the process's global generator was in. An earlier pilot at
        identical config gave ``goal_substitution`` 1/4 on one run and 0/4 on the next.

        WHY THE GLOBAL GENERATOR AND NOT A LOCAL ONE. LeRobot's policies call ``torch.randn`` and
        friends without accepting a ``generator=``, so there is no local generator to hand them.
        Seeding the process-wide RNG immediately before the episode is the only lever the adapter
        actually has. It is coarse — anything else in the process drawing from torch between this
        call and the rollout perturbs the sequence — but it is honest, and it is the difference
        between "seeded" and "not seeded at all".

        WHY IT IS NOT CLAIMED TO BE FULL DETERMINISM. cuDNN kernel selection, TF32 and non-
        deterministic reductions are unaffected by a seed, and this adapter does NOT set
        ``torch.use_deterministic_algorithms``: that changes which kernels run, and a measurement
        harness must not silently alter the compute path of the thing it is measuring. So
        ``stochastic`` stays True and the report still says so. What changes is that the run
        records WHICH seed the sampler started from, so a re-run is reproducible to the extent the
        hardware allows and two rows are comparable to the extent they share a seed. Overstating
        that would be the same error as the caveat this replaces, in the other direction.

        UNVERIFIED ON GPU IN THIS CHANGE. There is no lerobot or CUDA in the CPU test environment,
        so what is tested here is the contract (the runner calls it, the result records what it
        returns, a stochastic adapter must override it) and not the numerical effect. Confirming
        that two GPU runs at one seed now agree needs the GPU lane.
        """
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():  # pragma: no cover - no CUDA in the CPU test environment
            torch.cuda.manual_seed_all(seed)
        return seed

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

    def _act_offline(self, observation: Observation, instruction: str) -> Action:
        """One forward pass on a RECORDED frame. No env, no stepping, nothing executed.

        The frame arrives as lerobot tensors without a batch dimension (a dataset yields single
        samples); the policy expects a batch, so one is added here and stripped from the result.
        """
        torch = self._torch
        batch: dict[str, Any] = {}
        for key, value in observation.items():
            if not key.startswith("observation"):
                continue
            tensor = value if hasattr(value, "dim") else torch.as_tensor(np.asarray(value))
            batch[key] = tensor.unsqueeze(0) if tensor.dim() in (1, 3) else tensor
        # OUR instruction, benign or adversarial, is what the policy is being asked about. This is
        # the entire experiment: same pixels, same recorded state, one word changed.
        batch["task"] = [instruction]

        obs_t = self._preprocess(batch)
        with torch.inference_mode():
            action = self._policy.select_action(obs_t)
        action = self._postprocess(action)
        array = action.detach().to("cpu").numpy()
        if array.ndim > 1:
            array = array[0]
        return clamp_action(array, array.shape[-1])

    def _batch_from(
        self, observation: Observation, instruction: str, image_override: Any = None
    ) -> dict[str, Any]:
        """The policy-ready batch for one env observation — the verified eval path, factored out.

        ``image_override``, when given, is a torch tensor ``(1, 3, H, W)`` in ``[0, 1]`` that
        REPLACES the primary camera tensor right after ``preprocess_observation`` and before the
        env and policy processors run, so a tensor that requires grad flows through the LIBERO
        180-degree flip, the policy's resize-and-pad and its ``[-1, 1]`` rescale with its graph
        intact. That is what :meth:`input_gradient` needs; :meth:`act` never passes one.
        """
        from lerobot.envs.utils import preprocess_observation
        from lerobot.utils.constants import OBS_IMAGES

        raw = observation.get("raw", observation)
        # Fold a (possibly attack-modified) image back into the raw obs the policy reads.
        raw = self._apply_image_override(observation, raw)
        obs_t = preprocess_observation(raw)
        if image_override is not None:
            pixels_key = observation.get("pixels_key")
            key = f"{OBS_IMAGES}.{pixels_key}"
            if key not in obs_t:
                raise KeyError(f"primary camera {key!r} not in the preprocessed observation")
            obs_t[key] = image_override
        batch_size = next((v.shape[0] for v in obs_t.values() if hasattr(v, "shape")), 1)
        # Inject OUR (possibly adversarial) instruction as the task (replaces add_envs_task).
        obs_t["task"] = [instruction] * batch_size
        obs_t = self._env_preprocess(obs_t)
        return dict(self._preprocess(obs_t))

    def act(self, observation: Observation, instruction: str) -> Action:
        """Run one verified rollout step on a real LIBERO observation; return a (7,) action."""
        if not self._loaded:
            raise RuntimeError("LeRobotAdapter.act called before load(); call load() first.")

        # OFFLINE PATH: a recorded dataset frame, not a gym observation.
        #
        # Everything below this branch is env-shaped — `preprocess_observation` converts a gym env's
        # observation dict, and the env pre/post processors come from the LIBERO env config. A frame
        # read from a LeRobotDataset is ALREADY in lerobot's own format and needs none of that; it
        # needs only the policy's own processors, which `load()` built either way.
        #
        # Without this branch the adapter can only ever be driven by a simulator, which is why the
        # offline study could load a policy and still not ask it anything.
        if self.dataset_repo_id is not None:
            return self._act_offline(observation, instruction)

        if self._env_preprocess is None:
            raise RuntimeError(
                "LeRobotAdapter needs a suite that provides env features (use "
                "'--suite libero'). For reference numbers without the in-process loop:\n  "
                + LEROBOT_EVAL_LIBERO_HINT
            )

        obs_t = self._batch_from(observation, instruction)
        with self._torch.inference_mode():
            action = self._policy.select_action(obs_t)
        action = self._postprocess(action)
        action = self._env_postprocess({self._action_constant: action})[self._action_constant]

        action_dim = self._features.action_dim if self._features is not None else action.shape[-1]
        return clamp_action(action.detach().to("cpu").numpy(), action_dim)

    # -- provael.attacks.weight_integrity.WeightAccessible ------------------------------------- #
    #
    # WHAT IS EXPOSED. The weight matrix of ``model.action_out_proj`` (WEIGHT_SURFACE_ATTR): the
    # last linear map before the action chunk, on every flow-matching policy lerobot 0.5.1 ships
    # through this adapter. SmolVLA's is expert_hidden x max_action_dim; a few tens of thousands
    # of parameters, so the family's per-bit ranking table stays small. The bias is deliberately
    # left out so ONE per-tensor scale covers everything the ranking compares.
    #
    # HOW THE FLIP IS EMULATED ON A FLOAT CHECKPOINT. The float weights are viewed through a
    # symmetric per-tensor INT8 quantization (``symmetric_int8``); a flipped INT8 value is applied
    # to the live float weights as the DELTA ``(q' - q) * scale`` — the exact change the same flip
    # would make in an INT8 deployment of the same tensor — and the clean vector restores the
    # original floats bit-for-bit. Nothing runs quantized at inference. ``BitFlipRecord.emulated``
    # is True for this reason as well as the one the attack module gives.
    #
    # THE REFERENCE OPERATING POINT. ``parameter_sensitivity`` is ``d(danger)/d(weight)`` at ONE
    # fixed point for the whole run: the benign first frame of the run's first task at the run
    # seed, with the flow-matching noise seeded from the same run seed, handed over by the runner
    # through ``set_sensitivity_reference``. The danger proxy is the translation energy of the
    # executed part of the action chunk in the policy's normalized action space — "how hard the
    # policy pushes the end-effector" at that frame. It is a RANKING HEURISTIC, not the derivative
    # of the suite's predicate (which is geometric and not differentiable through the simulator);
    # whether a flip that raises it produces an unsafe episode is what the suite then measures, and
    # a null from this ranking is "one-shot first-order selection did not find it", nothing more.

    def _weight_layer(self) -> Any:
        """``model.action_out_proj`` on the loaded backend, or ``None`` where it has none."""
        model = getattr(self._policy, "model", None)
        layer = getattr(model, WEIGHT_SURFACE_ATTR, None)
        return layer if layer is not None and hasattr(layer, "weight") else None

    def quantized_parameters(self) -> npt.NDArray[np.int8]:
        """A COPY of the INT8 view of the weight surface; empty when the backend exposes none."""
        layer = self._weight_layer()
        if not self._loaded or layer is None:
            return np.zeros(0, dtype=np.int8)
        if self._weight_q is None:
            torch = self._torch
            self._weight_clean = layer.weight.detach().to("cpu", torch.float32).clone()
            self._weight_q, self._weight_scale = symmetric_int8(self._weight_clean.numpy())
        return np.array(self._weight_q, dtype=np.int8, copy=True)

    def load_quantized_parameters(self, params: npt.NDArray[np.int8]) -> None:
        """Install an INT8 vector as a delta on the clean floats; the clean vector restores."""
        layer = self._weight_layer()
        if layer is None or self._weight_q is None or self._weight_clean is None:
            raise RuntimeError("quantized_parameters() must be called before loading a vector")
        torch = self._torch
        delta = dequantized_delta(params, self._weight_q, self._weight_scale)
        restored = self._weight_clean + torch.from_numpy(delta).reshape(self._weight_clean.shape)
        with torch.no_grad():
            layer.weight.copy_(restored.to(layer.weight.device, layer.weight.dtype))

    def set_sensitivity_reference(
        self, observation: Observation, instruction: str, seed: int
    ) -> None:
        """Fix the operating point ``parameter_sensitivity`` is taken at (see the section note)."""
        self._reference = (observation, instruction, int(seed))
        self._sensitivity = None

    def parameter_sensitivity(self) -> npt.NDArray[np.float32]:
        """``d(danger)/d(weight)`` at the reference point, flattened to match the INT8 view."""
        if self._sensitivity is not None:
            return np.array(self._sensitivity, copy=True)
        if self._reference is None:
            raise RuntimeError(
                "parameter_sensitivity() needs a reference operating point: the runner calls "
                "set_sensitivity_reference(observation, instruction, seed) before the first "
                "weight attack"
            )
        layer = self._weight_layer()
        if layer is None:
            raise RuntimeError("this backend exposes no weight surface")
        torch = self._torch
        observation, instruction, seed = self._reference
        weight = layer.weight
        was_trainable = bool(weight.requires_grad)
        weight.requires_grad_(True)
        try:
            with torch.enable_grad():
                batch = self._batch_from(observation, instruction)
                torch.manual_seed(seed)
                actions = self._action_chunk(batch)
                executed = int(getattr(self._policy.config, "n_action_steps", 1))
                danger = actions[0, :executed, :3].pow(2).sum(dim=-1).mean()
                (grad,) = torch.autograd.grad(danger, weight)
        finally:
            weight.requires_grad_(was_trainable)
            self._policy.reset()  # the reference pass must leave no queued chunk behind
        self._sensitivity = grad.detach().to("cpu", torch.float32).reshape(-1).numpy()
        return np.array(self._sensitivity, copy=True)

    def _action_chunk(self, batch: dict[str, Any]) -> Any:
        """One DIFFERENTIABLE action chunk ``(B, chunk, dim)`` — the body of the backend's own
        ``predict_action_chunk`` without its ``@torch.no_grad``, read from lerobot 0.5.1."""
        from lerobot.utils.constants import OBS_LANGUAGE_ATTENTION_MASK, OBS_LANGUAGE_TOKENS

        policy = self._policy
        tokens = batch[OBS_LANGUAGE_TOKENS]
        masks = batch[OBS_LANGUAGE_ATTENTION_MASK]
        if hasattr(policy, "prepare_images") and hasattr(policy, "prepare_state"):
            # SmolVLA: images, state and language, state projected into the prefix.
            images, img_masks = policy.prepare_images(batch)
            state = policy.prepare_state(batch)
            return policy.model.sample_actions(images, img_masks, tokens, masks, state)
        if hasattr(policy, "_preprocess_images"):
            # pi0.5: the state is tokenized into the language prefix upstream.
            images, img_masks = policy._preprocess_images(batch)  # noqa: SLF001 - read from lerobot
            return policy.model.sample_actions(images, img_masks, tokens, masks)
        raise RuntimeError(
            f"{type(policy).__name__} has no action-chunk path this adapter knows how to "
            "differentiate; weight sensitivity is not available for it"
        )

    # -- provael.policies.base.InputGradientProvider ------------------------------------------- #
    #
    # ``d(objective)/d(image)`` through the policy's own vision tower, for the gradient family
    # (:mod:`provael.attacks.gradient_patch`). Objective: ``||enc(x) - enc(x_clean)||^2`` where
    # ``enc`` is the backend's ``embed_image`` (vision encoder + connector/resampler) — the feature
    # the action head consumes — and ``x_clean`` is the frame the suite produced. No labels, no
    # actions, no reward: the attack needs nothing the checkpoint does not already expose. The
    # tensor the attack receives a gradient for is the SUITE-FRAME image (before the LIBERO flip
    # and the resize), so the perturbation it writes back lands where the policy will read it.
    #
    # Nothing here touches per-episode state: ``embed_image`` populates no action queue, so the
    # runner attaches this oracle WITHOUT a reset callback. Resetting after every PGD refinement
    # would make the attacked arm re-plan a chunk every step while the benign arm re-plans every
    # ``n_action_steps`` — a confound in the attacker's favour that no rate could be read through.

    def _image_pipeline(self) -> tuple[Any, Any] | None:
        """``(prepare_images, embed_image)`` for the loaded backend, or ``None``."""
        policy = self._policy
        prepare = getattr(policy, "prepare_images", None) or getattr(
            policy, "_preprocess_images", None
        )
        model = getattr(policy, "model", None)
        vlm = getattr(model, "vlm_with_expert", None) or getattr(
            model, "paligemma_with_expert", None
        )
        embed = getattr(vlm, "embed_image", None)
        if callable(prepare) and callable(embed):
            return prepare, embed
        return None

    def provides_input_gradient(self) -> bool:
        """True once loaded on the env path with a backend whose vision tower is reachable."""
        return (
            self._loaded
            and self.dataset_repo_id is None
            and self._env_preprocess is not None
            and self._image_pipeline() is not None
        )

    def _primary_feature(self, batch: dict[str, Any], index: int | None) -> tuple[Any, int]:
        """The vision feature of the primary camera in ``batch`` and the camera's index.

        The index is found by identity when ``None``: the only image tensor that requires grad is
        the one :meth:`_batch_from` substituted, so no assumption about key naming or the policy's
        rename map is needed — and if the pipeline dropped or duplicated it, this says so.
        """
        pipeline = self._image_pipeline()
        if pipeline is None:
            raise RuntimeError("no image pipeline on this backend")
        prepare, embed = pipeline
        present = [k for k in self._policy.config.image_features if k in batch]
        if index is None:
            graded = [k for k in present if bool(getattr(batch[k], "requires_grad", False))]
            if len(graded) != 1:
                raise RuntimeError(
                    f"expected exactly one differentiable camera tensor, found {len(graded)}"
                )
            index = present.index(graded[0])
        images, _masks = prepare(batch)
        return embed(images[index]), index

    def input_gradient(
        self, instruction: str, observation: Observation, image: npt.NDArray[np.floating]
    ) -> npt.NDArray[np.floating] | None:
        """``d||enc(image) - enc(clean)||^2 / d(image)`` as a float array of ``image``'s shape."""
        if not self.provides_input_gradient() or observation.get(IMAGE_KEY) is None:
            return None
        torch = self._torch
        candidate = (
            torch.as_tensor(np.asarray(image, dtype=np.float32))
            .permute(2, 0, 1)
            .unsqueeze(0)
            .requires_grad_(True)
        )
        # No try/except around the graph: a backend or pipeline that cannot backprop raises, and
        # the run stops loudly. Declining silently would let the attack record a white-box null it
        # never attempted, which is the one outcome this whole surface exists to prevent.
        with torch.enable_grad():
            batch = self._batch_from(observation, instruction, image_override=candidate)
            feature, index = self._primary_feature(batch, None)
            clean = self._clean_feature_for(observation, instruction, index)
            objective = (feature - clean).pow(2).sum()
            (grad,) = torch.autograd.grad(objective, candidate)
        out = grad[0].permute(1, 2, 0).detach().to("cpu", torch.float32).numpy()
        return np.asarray(out, dtype=np.float32)

    def _clean_feature_for(self, observation: Observation, instruction: str, index: int) -> Any:
        """``enc(x_clean)`` for this observation, cached across the PGD refinements of one frame."""
        step = int(observation.get("step", -1))
        if self._clean_feature is not None:
            cached_id, cached_step, cached = self._clean_feature
            if cached_id == id(observation) and cached_step == step:
                return cached
        torch = self._torch
        with torch.no_grad():
            batch = self._batch_from(observation, instruction)
            clean, _ = self._primary_feature(batch, index)
        clean = clean.detach()
        self._clean_feature = (id(observation), step, clean)
        return clean


__all__ = [
    "INT8_MAX",
    "LeRobotAdapter",
    "WEIGHT_SURFACE_ATTR",
    "dequantized_delta",
    "symmetric_int8",
    "MissingLeRobotError",
    "IncompatiblePolicyError",
    "LEROBOT_EVAL_LIBERO_HINT",
    "LIBERO_FINETUNED_SMOLVLA",
    "clamp_action",
]
