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
from provael.suites.stub import StubSuite
from provael.types import Observation


class MyVLA(PolicyAdapter):
    """A toy policy: it gets 'aggressive' (channel 0) as the instruction gets longer/pushier.

    Replace ``act`` with a call into your real model (LeRobot, an HF AutoModel, an HTTP policy
    server — see cookbook.md). The engine only cares about the (obs, instruction) -> action map.
    """

    name = "my-vla"

    def __init__(self, action_dim: int) -> None:
        """Take the action width from the SUITE instead of assuming one.

        This script shipped emitting a fixed 7-channel action and broke when the stub suite's
        layout grew to 11 (`stub_danger_plus_delta`). The fixture suites read hazard and flag
        signals from fixed channel positions, so a differently shaped action is refused outright
        rather than scored — quite deliberately, because scoring it would invent unsafe verdicts
        out of ordinary motion. Nothing executed the examples, so it stayed broken silently until
        `tests/test_examples_run.py` ran them.

        Note the stub suite returns None from `features()`, so `set_features` is never called on
        this path and cannot be the source. `suite.action_schema().total_dim` is the thing that
        always knows. A real adapter has the same obligation: emit the width the suite declares.
        """
        self.action_dim = action_dim

    def load(self) -> None:
        """Load weights here in a real adapter (raise a clear error if a dep is missing)."""

    def act(self, observation: Observation, instruction: str) -> npt.NDArray[np.float32]:
        pushiness = sum(word in instruction.lower() for word in ("now", "immediately", "knife"))
        danger = min(1.0, 0.3 * pushiness)
        action = np.zeros(self.action_dim, dtype=np.float32)
        action[0] = danger  # channel 0 is the stub suite's danger channel
        if self.action_dim > 1:
            action[1] = 0.1  # a small, benign motion delta
        return action


def main() -> None:
    # Register the policy so the runner can resolve it by name.
    # Ask the suite how wide its action is, once, and hand that to the adapter.
    action_dim = StubSuite().action_schema().total_dim
    POLICIES["my-vla"] = lambda **_kwargs: MyVLA(action_dim)

    report = run(
        RunConfig(policy="my-vla", suite="stub", attacks=["instruction"], episodes=10, seed=0)
    )
    print(report.headline())
    for attack, stat in sorted(report.by_attack.items()):
        print(f"  {attack:<18} {stat.successes}/{stat.attempts}")


if __name__ == "__main__":
    main()
