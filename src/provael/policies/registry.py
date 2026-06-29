"""Policy registry: resolve a policy name to a :class:`PolicyAdapter`.

``stub`` is always available (pure CPU, no deps). The real VLA policies map to adapters that
are cheap to *construct* and never import their heavy dependency at module scope — the optional
import happens only in :meth:`PolicyAdapter.load`, which raises a clear, actionable error if the
extra is missing. This keeps the core CPU build importable and lets the CLI surface a friendly
message instead of a traceback.

Two adapter backends are reused across many models:

* **LeRobot-native** (``smolvla``, ``pi0``, ``pi05``, ``pi0fast``, ``groot``) — all load through
  LeRobot's generic ``PreTrainedConfig.from_pretrained`` + ``make_policy`` path, so adding one is
  a config-level change (a different default checkpoint). Needs ``provael[lerobot]``.
* **Hugging Face ``transformers``** (``openvla``) — loads OpenVLA / OpenVLA-OFT directly via
  ``AutoModelForVision2Seq``. Needs ``provael[openvla]``. This is the model-agnostic path that
  does not go through LeRobot.

Each real policy accepts a ``model`` override so a fine-tuned (e.g. LIBERO) checkpoint can be
passed from the CLI.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable

from provael.policies.base import PolicyAdapter
from provael.policies.stub import StubPolicy


def _make_stub(**_kwargs: object) -> PolicyAdapter:
    return StubPolicy()


def _lerobot_native(default_model: str, policy_name: str) -> Callable[..., PolicyAdapter]:
    """Build a factory for a LeRobot-native policy (reuses the generic LeRobotAdapter).

    ``smolvla`` / ``pi0`` / ``pi05`` / ``pi0fast`` / ``groot`` differ only by their default
    checkpoint — LeRobot's ``make_policy`` selects the right policy class from the checkpoint
    config. The optional ``lerobot`` import stays inside the adapter's ``load``.
    """

    def factory(
        model: str | None = None,
        rename_map: dict[str, str] | None = None,
        device: str = "cuda",
        **_kwargs: object,
    ) -> PolicyAdapter:
        from provael.policies.lerobot_adapter import LeRobotAdapter

        return LeRobotAdapter(
            model_id=model or default_model,
            name=policy_name,
            device=device,
            rename_map=rename_map,
        )

    return factory


def _make_openvla(
    model: str | None = None,
    device: str = "cuda",
    unnorm_key: str | None = None,
    **_kwargs: object,
) -> PolicyAdapter:
    from provael.policies.openvla_adapter import OpenVLAAdapter

    return OpenVLAAdapter(
        model_id=model or "openvla/openvla-7b", device=device, unnorm_key=unnorm_key
    )


#: Registry of policy factories keyed by name. Factories accept (and ignore unknown) keyword
#: overrides so the CLI can pass e.g. a fine-tuned checkpoint via ``--model``.
POLICIES: dict[str, Callable[..., PolicyAdapter]] = {
    "stub": _make_stub,
    "smolvla": _lerobot_native("lerobot/smolvla_base", "smolvla"),
    "pi0": _lerobot_native("lerobot/pi0", "pi0"),
    "pi05": _lerobot_native("lerobot/pi05_base", "pi05"),
    "pi0fast": _lerobot_native("lerobot/pi0fast_base", "pi0fast"),
    "groot": _lerobot_native("nvidia/GR00T-N1.5-3B", "groot"),
    "openvla": _make_openvla,
}

#: policy name -> (extra name, importable module that makes it runnable here).
_REQUIRES_EXTRA: dict[str, tuple[str, str]] = {
    "smolvla": ("lerobot", "lerobot"),
    "pi0": ("lerobot", "lerobot"),
    "pi05": ("lerobot", "lerobot"),
    "pi0fast": ("lerobot", "lerobot"),
    "groot": ("lerobot", "lerobot"),
    "openvla": ("openvla", "transformers"),
}

#: Policies that require the optional ``[lerobot]`` extra (kept for back-compat).
REQUIRES_LEROBOT: frozenset[str] = frozenset(
    name for name, (extra, _module) in _REQUIRES_EXTRA.items() if extra == "lerobot"
)


def lerobot_available() -> bool:
    """True if the ``lerobot`` package is importable in the current environment."""
    return importlib.util.find_spec("lerobot") is not None


def available_policies() -> list[str]:
    """Names of all registered policies."""
    return list(POLICIES)


def policy_extra(name: str) -> str | None:
    """The optional extra a policy needs (e.g. ``"lerobot"`` / ``"openvla"``), or None for CPU."""
    req = _REQUIRES_EXTRA.get(name)
    return req[0] if req is not None else None


def policy_is_ready(name: str) -> bool:
    """Whether ``name`` can run in the current environment right now."""
    req = _REQUIRES_EXTRA.get(name)
    if req is not None:
        return importlib.util.find_spec(req[1]) is not None
    return name in POLICIES


def make_policy(name: str, **kwargs: object) -> PolicyAdapter:
    """Instantiate a policy by name, forwarding optional overrides to the factory.

    ``kwargs`` (e.g. ``model``, ``rename_map``, ``device``, ``unnorm_key``) are forwarded to the
    factory; factories ignore overrides they don't use. Does not call ``load()``.

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
    "policy_extra",
    "policy_is_ready",
]
