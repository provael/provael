"""Bring your own VLA in ~30 lines — a runnable, CPU-only custom PolicyAdapter.

A Provael *policy* is anything that maps ``(observation, instruction) -> action`` (the tiny
:class:`provael.policies.base.PolicyAdapter` ABC). This script defines a toy policy, registers it,
and red-teams it through the real engine — no GPU, no model, no network. Run it:

    python examples/python-api/custom_policy_adapter.py
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from provael.config import RunConfig
from provael.policies.base import PolicyAdapter
from provael.policies.registry import POLICIES
from provael.runner import run
from provael.types import Observation


class MyVLA(PolicyAdapter):
    """A toy policy: it gets 'aggressive' (channel 0) as the instruction gets longer/pushier.

    Replace ``act`` with a call into your real model (LeRobot, an HF AutoModel, an HTTP policy
    server — see cookbook.md). The engine only cares about the (obs, instruction) -> action map.
    """

    name = "my-vla"

    def load(self) -> None:
        """Load weights here in a real adapter (raise a clear error if a dep is missing)."""

    def act(self, observation: Observation, instruction: str) -> npt.NDArray[np.float32]:
        pushiness = sum(word in instruction.lower() for word in ("now", "immediately", "knife"))
        danger = min(1.0, 0.3 * pushiness)
        return np.array([danger, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)


def main() -> None:
    # Register the policy so the runner can resolve it by name.
    POLICIES["my-vla"] = lambda **_kwargs: MyVLA()

    report = run(
        RunConfig(policy="my-vla", suite="stub", attacks=["instruction"], episodes=10, seed=0)
    )
    print(report.headline())
    for attack, stat in sorted(report.by_attack.items()):
        print(f"  {attack:<18} {stat.successes}/{stat.attempts}")


if __name__ == "__main__":
    main()
