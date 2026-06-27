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

from provael.policies.base import PolicyAdapter
from provael.policies.stub import StubPolicy


def _make_stub(**_kwargs: object) -> PolicyAdapter:
    return StubPolicy()


def _make_smolvla(
    model: str | None = None,
    rename_map: dict[str, str] | None = None,
    device: str = "cuda",
    **_kwargs: object,
) -> PolicyAdapter:
    # Imported here (not at module top) so the core never hard-depends on the
    # adapter pulling optional symbols. The adapter module itself imports no
    # optional deps at module scope.
    from provael.policies.lerobot_adapter import LeRobotAdapter

    return LeRobotAdapter(
        model_id=model or "lerobot/smolvla_base",
        name="smolvla",
        device=device,
        rename_map=rename_map,
    )


#: Registry of policy factories keyed by name. Factories accept (and ignore unknown)
#: keyword overrides so the CLI can pass e.g. a fine-tuned checkpoint to `smolvla`.
POLICIES: dict[str, Callable[..., PolicyAdapter]] = {
    "stub": _make_stub,
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


def make_policy(name: str, **kwargs: object) -> PolicyAdapter:
    """Instantiate a policy by name, forwarding optional overrides to the factory.

    ``kwargs`` (e.g. ``model``, ``rename_map``, ``device``) are forwarded to the factory;
    factories ignore overrides they don't use. Does not call ``load()``.

    Raises:
        KeyError: if ``name`` is not a registered policy.
    """
    try:
        factory = POLICIES[name]
    except KeyError:
        raise KeyError(f"unknown policy {name!r}; available: {available_policies()}") from None
    return factory(**kwargs)


__all__ = [
    "POLICIES",
    "REQUIRES_LEROBOT",
    "available_policies",
    "lerobot_available",
    "make_policy",
    "policy_is_ready",
]
