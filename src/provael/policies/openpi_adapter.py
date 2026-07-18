"""Adapter for openpi / π0-class flow-matching policies (Physical-Intelligence/openpi).

This is a **second non-LeRobot backend** (alongside :mod:`~provael.policies.openvla_adapter`), and
the point of it is **cross-architecture transfer**: the same instruction-family attacks that
redirect SmolVLA (a LeRobot flow-matching policy) can be pointed at a π0 policy served by Physical
Intelligence's *own* openpi stack — a different framework, same flow-matching action-head class — so
a redirection that reproduces across both is evidence the attack is about policy behaviour, not one
codebase's glue. (``lerobot/pi0`` is π0 as ported into LeRobot; this is π0 as served by openpi.)

openpi's documented cross-machine inference is a **policy server + websocket client**
(https://github.com/Physical-Intelligence/openpi ``docs/remote_inference.md``): the heavy model runs
in a server on a GPU box, and a light ``openpi-client`` (pip-installable, CPU-only) connects to it.
This adapter is that client. The verified per-step recipe is::

    from openpi_client import image_tools, websocket_client_policy
    client = websocket_client_policy.WebsocketClientPolicy(host, port)   # in load()
    observation = {
        "observation/image": image_tools.convert_to_uint8(          # resize+pad to 224
            image_tools.resize_with_pad(rgb, 224, 224)),
        "observation/state": state,          # proprioception; server normalises it
        "prompt": instruction,               # <- we inject the (adversarial) instruction here
    }
    action_chunk = client.infer(observation)["actions"]   # (action_horizon, action_dim)

DESIGN: like the other adapters, this module imports **no** optional dependency at module scope —
``openpi_client`` is imported inside :meth:`load` / :meth:`act`, which raise a clear, actionable
error when the ``[openpi]`` extra is absent. The core stays importable on a plain CPU, and
``--policy stub`` runs the whole pipeline with no model, server, or network.

SCOPE / HONESTY: this adapter is **import-guarded scaffolding validated structurally on CPU**
(construction + the missing-dependency error + the act-before-load guard + the prompt-injection
wiring are unit-tested). A real forward pass needs the ``[openpi]`` extra, ``PROVAEL_INTEGRATION=1``
**and a running openpi policy server on a GPU box** — it has **not** been run in this repo's CI, so
**no cross-model transfer number is claimed**. The observation schema (state dims, which cameras) is
checkpoint-specific and must match the served policy, exactly as OpenVLA's ``unnorm_key`` is.

**One-env constraint (honest).** The ``[openpi]`` client and the ``[lerobot]`` extra are **mutually
exclusive** — ``openpi-client`` pins ``numpy<2`` while ``lerobot`` pins ``numpy>=2`` (see pyproject
``[tool.uv] conflicts``). Provael's real image simulator (LIBERO) is lerobot-based, so a *single*
Provael env cannot both drive the LIBERO sim and query an openpi server: ``--policy openpi --suite
libero`` is not co-installable. The cross-architecture comparison (SmolVLA vs π0, same attacks) is
therefore run as **two separate-environment runs**, compared offline — the openpi run sourcing its
observations from a lerobot-free frame source (openpi's own served sim, or synthetic frames as in
the gated test). What transfers here is the **attack** (the adversarial ``prompt``), not one env.

Run the real cross-architecture transfer path on a GPU box::

    pip install 'provael[openpi]'
    # in one shell, from the openpi repo, serve a π0 checkpoint (needs the GPU):
    #   uv run scripts/serve_policy.py --env LIBERO   # exposes ws://localhost:8000
    PROVAEL_INTEGRATION=1 OPENPI_HOST=localhost OPENPI_PORT=8000 \
        pytest tests/test_openpi_adapter.py -q
    # or a full transfer-test against the same attacks that move SmolVLA:
    PROVAEL_INTEGRATION=1 provael attack --policy openpi --suite libero \
        --attacks none,instruction --seeds 10
"""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np
import numpy.typing as npt

from provael.policies.base import PolicyAdapter
from provael.policies.lerobot_adapter import clamp_action
from provael.types import Action, Observation

#: openpi's typical pre-trained input resolution (see docs/remote_inference.md).
OPENPI_RESIZE = 224

_INSTALL_HINT = (
    "The '{name}' policy requires the optional openpi client, which is not installed.\n"
    "  1. Install the extra:  pip install 'provael[openpi]'\n"
    "     (pulls the CPU-only 'openpi-client'; the model itself runs in a separate server.)\n"
    "  2. Serve a pi0 checkpoint on a GPU box from the openpi repo, e.g.\n"
    "       uv run scripts/serve_policy.py --env LIBERO   # -> ws://localhost:8000\n"
    "  3. Enable the gated integration path:  PROVAEL_INTEGRATION=1\n"
    "Run on CPU with '--policy stub' to exercise the full pipeline with no model or server."
)


class MissingOpenPiError(RuntimeError):
    """Raised when the openpi adapter is used without the ``[openpi]`` extra."""


class OpenPiAdapter(PolicyAdapter):
    """Connects to an openpi π0 policy server and runs it on real obs via the websocket client.

    Construction imports nothing optional and opens no connection. :meth:`load` imports
    ``openpi_client`` and creates the websocket client; :meth:`act` injects the (possibly
    adversarial) instruction as openpi's ``prompt``, runs one ``infer`` step, and returns the first
    action of the returned chunk, clamped to ``(action_dim,)``.
    """

    #: Real VLA inference is model-stochastic (reports are seeded but not byte-identical).
    stochastic = True

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        name: str = "openpi",
        action_dim: int = 7,
        resize: int = OPENPI_RESIZE,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.name = name
        self.action_dim = int(action_dim)
        self.resize = int(resize)
        self._client: Any = None
        self._image_tools: Any = None
        self._loaded = False

    @staticmethod
    def openpi_available() -> bool:
        """True if ``openpi_client`` is importable without importing it."""
        return importlib.util.find_spec("openpi_client") is not None

    def load(self) -> None:
        """Import the openpi client (guarded) and open the websocket to the policy server."""
        if not self.openpi_available():
            raise MissingOpenPiError(_INSTALL_HINT.format(name=self.name))

        from openpi_client import image_tools, websocket_client_policy

        self._image_tools = image_tools
        # Creating the client connects to the server; a clear error surfaces if none is running.
        self._client = websocket_client_policy.WebsocketClientPolicy(host=self.host, port=self.port)
        self._loaded = True

    def _rgb(self, observation: Observation) -> npt.NDArray[Any]:
        """Pull an (H, W, 3) uint8 RGB frame from the observation (image / rgb / pixels keys)."""
        for key in ("image", "rgb", "pixels"):
            value = observation.get(key)
            if value is not None:
                return np.asarray(value)
        raise RuntimeError(
            "OpenPiAdapter needs an RGB image in the observation (key 'image'/'rgb'/'pixels')."
        )

    def _observation(self, observation: Observation, instruction: str) -> dict[str, Any]:
        """Build openpi's observation dict, injecting the (adversarial) instruction as the prompt.

        The image is resized/pad-to-square to the model's input resolution via openpi's own
        ``image_tools`` (matching the training routine). A proprioceptive ``state`` is forwarded
        when the suite surfaces one; its dim is checkpoint-specific and validated server-side.
        """
        rgb = self._rgb(observation).astype(np.uint8)
        obs: dict[str, Any] = {
            "observation/image": self._image_tools.convert_to_uint8(
                self._image_tools.resize_with_pad(rgb, self.resize, self.resize)
            ),
            "prompt": instruction,
        }
        state = observation.get("state")
        if state is None:
            state = observation.get("ee_pos")  # LIBERO surfaces the end-effector pose
        if state is not None:
            obs["observation/state"] = np.asarray(state, dtype=np.float32)
        wrist = observation.get("wrist_image")
        if wrist is not None:
            wrist_u8 = np.asarray(wrist).astype(np.uint8)
            obs["observation/wrist_image"] = self._image_tools.convert_to_uint8(
                self._image_tools.resize_with_pad(wrist_u8, self.resize, self.resize)
            )
        return obs

    def act(self, observation: Observation, instruction: str) -> Action:
        """Run one openpi ``infer`` step; return the first action of the chunk, clamped."""
        if not self._loaded:
            raise RuntimeError("OpenPiAdapter.act called before load(); call load() first.")

        obs = self._observation(observation, instruction)
        result = self._client.infer(obs)
        actions = np.asarray(result["actions"])  # (action_horizon, action_dim) chunk
        first = actions[0] if actions.ndim == 2 else actions  # execute the first predicted step
        return clamp_action(first, self.action_dim)


__all__ = ["OpenPiAdapter", "MissingOpenPiError", "OPENPI_RESIZE"]
