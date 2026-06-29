"""Adapter for OpenVLA / OpenVLA-OFT policies loaded directly through Hugging Face ``transformers``.

This is the **model-agnostic, non-LeRobot** path: it proves Provael can red-team a VLA that
does not go through LeRobot at all. OpenVLA exposes a ``predict_action`` method on a
``transformers`` ``AutoModelForVision2Seq`` (trust-remote-code), taking a processed
(image, prompt) pair and returning a 7-DoF end-effector delta.

DESIGN: like :mod:`provael.policies.lerobot_adapter`, this module imports **no** optional
dependency at module scope — ``torch`` / ``transformers`` / ``PIL`` are imported inside
:meth:`OpenVLAAdapter.load` / :meth:`~OpenVLAAdapter.act`, which raise a clear, actionable error
when the ``[openvla]`` extra is absent. The core stays importable on a plain CPU.

The per-step path mirrors OpenVLA's documented inference recipe
(https://github.com/openvla/openvla):

    prompt = f"In: What action should the robot take to {instruction.lower()}?\\nOut:"
    inputs = processor(prompt, Image.fromarray(rgb)).to(device, dtype=bfloat16)
    action = vla.predict_action(**inputs, unnorm_key=<dataset>, do_sample=False)  # (7,) np.ndarray

SCOPE / HONESTY: this adapter is **import-guarded scaffolding validated structurally on CPU**
(construction + the missing-dependency error path are unit-tested). The real forward pass needs
a GPU, the ``[openvla]`` extra, and ``PROVAEL_INTEGRATION=1``; it has not been run in this repo's
CI. ``unnorm_key`` is checkpoint-specific (e.g. the fine-tuning dataset id) and must be supplied
for a real run — OpenVLA raises a helpful error listing valid keys if it is omitted/wrong.

Enable the real path on a GPU box::

    pip install 'provael[openvla]'
    PROVAEL_INTEGRATION=1 pytest tests/test_openvla_adapter.py -q
"""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np
import numpy.typing as npt

from provael.policies.base import PolicyAdapter
from provael.policies.lerobot_adapter import clamp_action
from provael.types import Action, Observation

_INSTALL_HINT = (
    "The '{name}' policy requires the optional OpenVLA dependency, which is not installed.\n"
    "  1. Install the extra:  pip install 'provael[openvla]'\n"
    "     (pulls transformers + torch + timm; needs a GPU machine.)\n"
    "  2. Enable the gated integration path:  PROVAEL_INTEGRATION=1\n"
    "Run on CPU with '--policy stub' to exercise the full pipeline with no model."
)

#: Surfaced when a real run omits the checkpoint-specific action-unnormalization key.
_UNNORM_HINT = (
    "OpenVLA needs an 'unnorm_key' (the action-normalization stats id, usually the fine-tuning "
    "dataset, e.g. 'libero_object' for a LIBERO checkpoint). Pass it via --unnorm-key / the "
    "policy factory. OpenVLA lists the valid keys in its error if the one given is unknown."
)


class MissingOpenVLAError(RuntimeError):
    """Raised when the OpenVLA adapter is used without the ``[openvla]`` extra."""


class OpenVLAAdapter(PolicyAdapter):
    """Loads an OpenVLA / OpenVLA-OFT model via ``transformers`` and runs it on real obs.

    Construction imports nothing optional. :meth:`load` builds the processor + model;
    :meth:`act` injects the (possibly adversarial) instruction into OpenVLA's prompt, runs one
    ``predict_action`` step, and returns a clamped ``(action_dim,)`` numpy action.
    """

    #: Real VLA inference is model-stochastic (reports are seeded but not byte-identical).
    stochastic = True

    def __init__(
        self,
        model_id: str = "openvla/openvla-7b",
        name: str = "openvla",
        device: str = "cuda",
        unnorm_key: str | None = None,
        action_dim: int = 7,
    ) -> None:
        self.model_id = model_id
        self.name = name
        self.device = device
        self.unnorm_key = unnorm_key
        self.action_dim = action_dim
        self._processor: Any = None
        self._model: Any = None
        self._torch: Any = None
        self._image_cls: Any = None
        self._loaded = False

    @staticmethod
    def openvla_available() -> bool:
        """True if ``transformers`` is importable without importing it."""
        return importlib.util.find_spec("transformers") is not None

    def load(self) -> None:
        """Import transformers (guarded) and build the processor + model."""
        if not self.openvla_available():
            raise MissingOpenVLAError(_INSTALL_HINT.format(name=self.name))

        import torch
        from PIL import Image
        from transformers import AutoModelForVision2Seq, AutoProcessor

        self._torch = torch
        self._image_cls = Image
        self._processor = AutoProcessor.from_pretrained(self.model_id, trust_remote_code=True)
        self._model = AutoModelForVision2Seq.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
        ).to(self.device)
        self._model.eval()
        self._loaded = True

    def _rgb(self, observation: Observation) -> npt.NDArray[Any]:
        """Pull an (H, W, 3) uint8 RGB frame from the observation (image / rgb / pixels keys)."""
        for key in ("image", "rgb", "pixels"):
            value = observation.get(key)
            if value is not None:
                return np.asarray(value)
        raise RuntimeError(
            "OpenVLAAdapter needs an RGB image in the observation (key 'image'/'rgb'/'pixels')."
        )

    def act(self, observation: Observation, instruction: str) -> Action:
        """Run one OpenVLA ``predict_action`` step; return a clamped (action_dim,) action."""
        if not self._loaded:
            raise RuntimeError("OpenVLAAdapter.act called before load(); call load() first.")
        if self.unnorm_key is None:
            raise RuntimeError(_UNNORM_HINT)

        image = self._image_cls.fromarray(self._rgb(observation).astype(np.uint8))
        prompt = f"In: What action should the robot take to {instruction.lower()}?\nOut:"
        inputs = self._processor(prompt, image).to(self.device, dtype=self._torch.bfloat16)
        with self._torch.inference_mode():
            action = self._model.predict_action(
                **inputs, unnorm_key=self.unnorm_key, do_sample=False
            )
        return clamp_action(np.asarray(action), self.action_dim)


__all__ = ["OpenVLAAdapter", "MissingOpenVLAError"]
