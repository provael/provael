"""Policy registry: resolve a policy name to a :class:`PolicyAdapter`.

``stub`` is always available (pure CPU, no deps). ``smolvla`` maps to the LeRobot
adapter; constructing it is cheap and never imports lerobot — the optional
dependency is only touched in :meth:`PolicyAdapter.load`, which raises a clear,
actionable error if the ``[lerobot]`` extra is not installed. This keeps the core
CPU build importable and lets the CLI surface a friendly message instead of a
traceback.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable

from vla_redteam.policies.base import PolicyAdapter
from vla_redteam.policies.stub import StubPolicy


def _make_smolvla() -> PolicyAdapter:
    # Imported here (not at module top) so the core never hard-depends on the
    # adapter pulling optional symbols. The adapter module itself imports no
    # optional deps at module scope.
    from vla_redteam.policies.lerobot_adapter import LeRobotAdapter

    return LeRobotAdapter(model_id="lerobot/smolvla_base", name="smolvla")


#: Registry of policy factories keyed by name.
POLICIES: dict[str, Callable[[], PolicyAdapter]] = {
    "stub": StubPolicy,
    "smolvla": _make_smolvla,
}

#: Policies that require the optional ``[lerobot]`` extra (and typically a GPU).
REQUIRES_LEROBOT: frozenset[str] = frozenset({"smolvla"})


def lerobot_available() -> bool:
    """True if the ``lerobot`` package is importable in the current environment."""
    return importlib.util.find_spec("lerobot") is not None


def available_policies() -> list[str]:
    """Names of all registered policies."""
    return list(POLICIES)


def policy_is_ready(name: str) -> bool:
    """Whether ``name`` can run in the current environment right now."""
    if name in REQUIRES_LEROBOT:
        return lerobot_available()
    return name in POLICIES


def make_policy(name: str) -> PolicyAdapter:
    """Instantiate a policy by name (does not call ``load()``).

    Raises:
        KeyError: if ``name`` is not a registered policy.
    """
    try:
        factory = POLICIES[name]
    except KeyError:
        raise KeyError(f"unknown policy {name!r}; available: {available_policies()}") from None
    return factory()


__all__ = [
    "POLICIES",
    "REQUIRES_LEROBOT",
    "available_policies",
    "lerobot_available",
    "make_policy",
    "policy_is_ready",
]
