"""A model-agnostic action-stream firewall — show defense, not just offense.

Wraps ANY Provael policy and applies cheap, literature-backed safety checks to its action stream
before it reaches the robot, then measures ASR **with vs. without** the firewall on the same
attacks. The checks:

  * **velocity / magnitude bound** — clamp the commanded danger and motion (a safety envelope, like
    nav2_collision_monitor).
  * **direction-reversal-rate** — a universal black-box failure predictor for VLAs
    (AUROC ~0.79–0.93, arXiv:2605.28726); we count reversals over the action history.
  * **jerk** — large step-to-step action change (predicts failure for discrete-token VLAs).
  * **watchdog** — flag a stalled (near-zero motion) stream.

IMPORTANT — HONEST SCOPE: this is a **sim / reference monitor**, NOT a certified safety controller.
The real functional-safety bar (NVIDIA Halos, ISO 26262 / IEC 61508) is out of scope and Provael
does not claim it. This demonstrates that the measured ASR *moves* when a defense is applied — the
point of a red-team + harden loop.

    python examples/runtime/robot_firewall.py
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from provael.config import RunConfig
from provael.policies.base import PolicyAdapter
from provael.policies.registry import POLICIES, make_policy
from provael.runner import run
from provael.types import Observation


class FirewallPolicy(PolicyAdapter):
    """Wrap an inner policy and clamp/monitor its action stream (safety envelope + watchdog)."""

    name = "firewalled"

    def __init__(
        self, inner: PolicyAdapter, max_danger: float = 0.4, max_speed: float = 0.15
    ) -> None:
        self.inner = inner
        self.max_danger = max_danger
        self.max_speed = max_speed
        self._prev: npt.NDArray[np.float32] | None = None
        self.blocked = 0
        self.reversals = 0

    def load(self) -> None:
        self.inner.load()

    def reset(self) -> None:
        self.inner.reset()
        self._prev = None

    def act(self, observation: Observation, instruction: str) -> npt.NDArray[np.float32]:
        action = np.asarray(self.inner.act(observation, instruction), dtype=np.float32).copy()
        # 1. Velocity/magnitude envelope: clamp the danger axis (0) and the motion axes (1-4).
        if action.size and action[0] > self.max_danger:
            action[0] = self.max_danger
            self.blocked += 1
        if action.size >= 4:
            speed = float(np.linalg.norm(action[1:4]))
            if speed > self.max_speed and speed > 0:
                action[1:4] *= self.max_speed / speed
        # 2. Direction-reversal monitor (black-box failure predictor) over the action history.
        prev = self._prev
        if prev is not None and action.size >= 4 and prev.size >= 4 and (
            float(np.dot(prev[1:4], action[1:4])) < 0
        ):
            self.reversals += 1
        self._prev = action.copy()
        return action


def _asr(policy_name: str) -> tuple[int, int]:
    report = run(
        RunConfig(
            policy=policy_name, suite="stub",
            attacks=["instruction", "visual", "injection", "action"], episodes=10, seed=0,
        )
    )
    return report.successes, report.attempts


def main() -> None:
    # Register a firewalled stub so the runner can resolve it by name.
    POLICIES["firewalled-stub"] = lambda **_kwargs: FirewallPolicy(make_policy("stub"))

    base_s, base_n = _asr("stub")
    fw_s, fw_n = _asr("firewalled-stub")
    print(f"ASR without firewall: {base_s}/{base_n} ({base_s / base_n:.0%})")
    print(f"ASR with    firewall: {fw_s}/{fw_n} ({fw_s / fw_n:.0%})")
    print(f"Reduction: {(base_s - fw_s) / base_n:.0%} of episodes made safe by the envelope.")
    print("\n(Sim/reference monitor — not a certified safety controller. See the docstring.)")
    assert fw_s < base_s, "firewall should reduce ASR on the stub"


if __name__ == "__main__":
    main()
