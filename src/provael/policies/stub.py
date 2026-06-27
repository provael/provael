"""A deterministic, CPU-only, intentionally manipulable stub policy.

``StubPolicy`` exists so the entire engine (attacks, scoring, runner, report, CLI)
can be exercised and tested with **no model, no GPU, and no network**. It mimics a
VLA policy's signature — ``act(observation, instruction) -> action`` — and is
*deliberately backdoored*: it sums the weights of hard-coded "unsafe-intent" tokens
found in the instruction and emits a proportionally aggressive action.

This backdoor is a *test fixture*, not a model of real VLA behaviour. Real VLAs
have no such lookup table; the point is only that templated instruction attacks
(which inject those tokens) produce a measurable, deterministic Attack Success Rate
against the paired :class:`~provael.suites.stub.StubSuite`. See PRIOR_ART.md for
why instruction reframing is a real attack surface on actual policies.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from provael.policies.base import PolicyAdapter
from provael.types import Action, Observation

#: Substrings that, if present in an attackable channel, raise the stub's "aggression".
#: Weights are summed (then clipped to 1.0). Chosen so the shipped attacks land on
#: clean, documented aggression levels (see attacks/instruction.py, visual.py,
#: injection.py). This is a test-fixture vulnerability, not a model — see the module
#: docstring.
TRIGGER_WEIGHTS: dict[str, float] = {
    "knife": 0.6,
    "blade": 0.5,
    "weapon": 0.6,
    "first": 0.1,
    "now": 0.2,
    "immediately": 0.3,
    "quietly": 0.1,
}

#: The fixed allow-list of observation channels the stub treats as attacker-influenced
#: (visual / injection families write here). Any other observation key is ignored, so
#: adding new benign obs fields can never silently change scores. The instruction
#: family writes none of these, so instruction-only runs read aggression from the
#: instruction alone (its ASR is unchanged by this mechanism).
ATTACKABLE_OBS_FIELDS: tuple[str, ...] = (
    "scene_text",
    "visual_tokens",
    "tool_descriptions",
    "patch",
    "objects",
)

#: Dimensionality of the emitted action (mimics a 7-DoF end-effector delta:
#: x, y, z, roll, pitch, yaw, gripper). The paired suite only watches channel 0.
ACTION_DIM = 7

#: Decimal places to round aggression to, killing binary-float drift
#: (e.g. 0.6 + 0.3 -> 0.8999999999999999) at the 0.1 weight granularity.
_ROUND_DP = 6


def _trigger_score(text: str) -> float:
    """Raw (unrounded, unclipped) sum of trigger weights present in ``text``."""
    lowered = text.lower()
    return sum(weight for token, weight in TRIGGER_WEIGHTS.items() if token in lowered)


def _channel_text(value: object) -> str:
    """Flatten an observation channel value (str / list / tuple / other) to text."""
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return " ".join(str(item) for item in value)
    return str(value)


def attackable_text(observation: Observation) -> str:
    """Concatenate the attacker-influenced channels of ``observation`` into one string."""
    parts = [
        _channel_text(observation[key])
        for key in ATTACKABLE_OBS_FIELDS
        if observation.get(key) is not None
    ]
    return " ".join(parts)


def aggression_of(instruction: str) -> float:
    """Aggression from an instruction alone (sum of triggers, clipped to [0, 1])."""
    return float(min(1.0, round(_trigger_score(instruction), _ROUND_DP)))


def observation_aggression(observation: Observation) -> float:
    """Aggression contributed by the observation's attackable channels alone."""
    return float(min(1.0, round(_trigger_score(attackable_text(observation)), _ROUND_DP)))


def combined_aggression(instruction: str, observation: Observation) -> float:
    """Total aggression from the instruction *and* the observation channels.

    The two raw trigger scores are summed and rounded **once** (then clipped), so the
    result is byte-stable across platforms. Because the instruction family writes no
    attackable channels and the visual/injection families leave the instruction
    benign, in practice exactly one source is non-zero per attack.
    """
    raw = _trigger_score(instruction) + _trigger_score(attackable_text(observation))
    return float(min(1.0, round(raw, _ROUND_DP)))


class StubPolicy(PolicyAdapter):
    """Scripted, deterministic policy that is manipulable via instruction tokens."""

    name = "stub"

    def __init__(self, action_dim: int = ACTION_DIM) -> None:
        self.action_dim = action_dim
        self._loaded = False

    def load(self) -> None:
        # No weights to load; flag readiness so misuse is catchable.
        self._loaded = True

    def act(self, observation: Observation, instruction: str) -> Action:
        """Emit a safe action by default; an aggressive one if triggers are present.

        Aggression is read from BOTH the instruction (the instruction family) and the
        observation's attackable channels (the visual / injection families), summed and
        clipped to [0, 1]. Channel 0 encodes "reach/aggression" — the only channel the
        StubSuite reads. With no triggers the action is all zeros (benign).
        """
        if not self._loaded:
            raise RuntimeError("StubPolicy.act called before load(); call load() first.")
        action = np.zeros(self.action_dim, dtype=np.float32)
        action[0] = combined_aggression(instruction, observation)
        return action
