"""GR00T-N1 humanoid adapter — a real whole-body VLA policy, routed through the LeRobot path.

NVIDIA's GR00T-N1 is an open humanoid foundation policy loadable through LeRobot's generic
``make_policy`` path (the same path SmolVLA / pi0 use), so this adapter is a thin, humanoid-aware
:class:`~provael.policies.lerobot_adapter.LeRobotAdapter` that pins the GR00T-N1 default checkpoint.
It is the first-class home for the intent documented in ``examples/adapters/groot_lerobot.md`` (a
prior stub), registered next to the LeRobot / openpi / openvla adapters.

GATED / deterministic CI: like every real adapter, construction imports nothing optional and the
heavy ``lerobot`` import happens only in :meth:`load`. In addition, a real GR00T load is **refused**
unless the real-integration path is explicitly enabled (``PROVAEL_INTEGRATION=1`` or
``PROVAEL_REQUIRE_REAL_INTEGRATION=1``, or an explicit ``allow_real=True``) — so a humanoid
whole-body policy is never loaded inadvertently in CPU CI, which red-teams the deterministic stub
only. Sim-only and defensive: this drives a *simulated* humanoid policy's action head; it ships no
real-robot control code and no real-world-harm payload (SAFETY.md).

STUB-VALIDATED elsewhere: the humanoid attack family + suite are validated on the deterministic CPU
fixture; a real humanoid transfer number (GR00T-N1 × a whole-body sim) is GPU-gated and **not run**
in this repo. See ``docs/studies/humanoid-locomotion-transfer.md``.
"""

from __future__ import annotations

import os

from provael.policies.lerobot_adapter import LeRobotAdapter

#: The default open GR00T-N1 checkpoint (the GR00T-N1 family; overridable via ``model``).
DEFAULT_GROOT_MODEL = "nvidia/GR00T-N1.5-3B"


class HumanoidIntegrationDisabledError(RuntimeError):
    """Raised when a real GR00T load is attempted without opting into the real-integration path."""


def _real_integration_enabled() -> bool:
    """True when the gated real-integration path is explicitly enabled via the environment."""
    return (
        os.environ.get("PROVAEL_INTEGRATION") == "1"
        or os.environ.get("PROVAEL_REQUIRE_REAL_INTEGRATION") == "1"
    )


class GrootAdapter(LeRobotAdapter):
    """LeRobot-routed GR00T-N1 humanoid policy adapter, gated behind the real-integration flag."""

    def __init__(
        self,
        model_id: str = DEFAULT_GROOT_MODEL,
        name: str = "groot",
        device: str = "cuda",
        rename_map: dict[str, str] | None = None,
        allow_real: bool = False,
    ) -> None:
        super().__init__(model_id=model_id, name=name, device=device, rename_map=rename_map)
        #: Explicit opt-in to load the real humanoid policy (else the env flag must be set).
        self.allow_real = allow_real

    def load(self) -> None:
        """Load GR00T-N1 via LeRobot — refused unless the real-integration path is opted into."""
        if not (self.allow_real or _real_integration_enabled()):
            raise HumanoidIntegrationDisabledError(
                "Loading the real GR00T-N1 humanoid policy is gated so CPU CI stays deterministic. "
                "Set PROVAEL_INTEGRATION=1 (or PROVAEL_REQUIRE_REAL_INTEGRATION=1), install "
                "'provael[lerobot]', and run on a GPU. On CPU, red-team the deterministic fixture "
                "with '--policy stub --suite humanoid'."
            )
        super().load()


__all__ = ["DEFAULT_GROOT_MODEL", "HumanoidIntegrationDisabledError", "GrootAdapter"]
