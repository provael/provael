"""Policy registry: resolve a policy name to a :class:`PolicyAdapter`.

``stub`` is always available (pure CPU, no deps). The real VLA policies map to adapters that
are cheap to *construct* and never import their heavy dependency at module scope — the optional
import happens only in :meth:`PolicyAdapter.load`, which raises a clear, actionable error if the
extra is missing. This keeps the core CPU build importable and lets the CLI surface a friendly
message instead of a traceback.

Two adapter backends are reused across many models:

* **LeRobot-native** (``smolvla``, ``pi0``, ``pi05``, ``pi0fast``) — all load through LeRobot's
  generic ``PreTrainedConfig.from_pretrained`` + ``make_policy`` path, so adding one is a
  config-level change (a different default checkpoint). Needs ``provael[lerobot]``.
* **LeRobot-native but NOT provisioned** (``groot``) — LeRobot does register a ``groot`` policy
  type, but its dependencies live in LeRobot's own ``[groot]`` extra (peft, dm-tree, timm,
  flash-attn) and ``provael[lerobot]`` pins ``lerobot[smolvla,libero]`` only. Installing the
  advertised extra therefore does **not** make ``groot`` runnable, and no GR00T checkpoint has
  been loaded in this repo. It is registered **scaffolding** — the same honesty scope ``openvla``
  and ``openpi`` state in their module docstrings — and :data:`SCAFFOLDING_POLICIES` records that
  so ``list-policies`` cannot advertise a capability the install cannot deliver.
* **Hugging Face ``transformers``** (``openvla``) — loads OpenVLA / OpenVLA-OFT directly via
  ``AutoModelForVision2Seq``. Needs ``provael[openvla]``. This is the model-agnostic path that
  does not go through LeRobot.
* **openpi websocket client** (``openpi``) — connects to a Physical-Intelligence/openpi π0 policy
  *server* (the model runs there, on a GPU). Needs the CPU-only ``provael[openpi]`` client. This is
  the cross-architecture-transfer backend: the same attacks that move SmolVLA, aimed at π0 as served
  by openpi's own stack (a different framework, same flow-matching action head).

Each real policy accepts a ``model`` override so a fine-tuned (e.g. LIBERO) checkpoint can be
passed from the CLI.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable

from provael.policies.base import PolicyAdapter
from provael.policies.stub import StubPolicy


def _make_stub(**_kwargs: object) -> PolicyAdapter:
    return StubPolicy()


def _lerobot_native(
    default_model: str, policy_name: str, action_head_class: str | None = None
) -> Callable[..., PolicyAdapter]:
    """Build a factory for a LeRobot-native policy (reuses the generic LeRobotAdapter).

    ``smolvla`` / ``pi0`` / ``pi05`` / ``pi0fast`` differ only by their default checkpoint —
    LeRobot's ``make_policy`` selects the right policy class from the checkpoint config. The
    optional ``lerobot`` import stays inside the adapter's ``load``.
    """

    def factory(
        model: str | None = None,
        rename_map: dict[str, str] | None = None,
        device: str = "cuda",
        **_kwargs: object,
    ) -> PolicyAdapter:
        from provael.policies.lerobot_adapter import LeRobotAdapter

        adapter = LeRobotAdapter(
            model_id=model or default_model,
            name=policy_name,
            device=device,
            rename_map=rename_map,
        )
        # LeRobotAdapter declares "flow" because SmolVLA and the pi0/pi0.5 checkpoints it loads use
        # flow-matching heads, and its own comment names pi0-FAST as the exception that "should
        # override this". Nothing did: pi0fast was registered through this same factory, so every
        # pi0fast result would have stamped action_head_class="flow" when the head is discrete FAST
        # tokens. The runner prefers the policy's value over the attack's, so nothing downstream
        # would have caught it — a self-describing result, wrong by construction.
        if action_head_class is not None:
            adapter.action_head_class = action_head_class
        return adapter

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


def _make_openpi(
    host: str | None = None,
    port: int | None = None,
    **_kwargs: object,
) -> PolicyAdapter:
    """Build the openpi websocket-client adapter, defaulting the server address from the env.

    openpi runs the model in a separate GPU server; this client connects to it. The address comes
    from ``host``/``port`` kwargs, else ``OPENPI_HOST``/``OPENPI_PORT``, else ``localhost:8000``.
    """
    from provael.policies.openpi_adapter import OpenPiAdapter

    return OpenPiAdapter(
        host=host or os.environ.get("OPENPI_HOST") or "localhost",
        port=int(port or os.environ.get("OPENPI_PORT") or 8000),
    )


def _make_groot(
    model: str | None = None,
    rename_map: dict[str, str] | None = None,
    device: str = "cuda",
    **_kwargs: object,
) -> PolicyAdapter:
    """Build the dedicated, gated GR00T-N1 humanoid adapter (routed through the LeRobot path)."""
    from provael.policies.groot_adapter import DEFAULT_GROOT_MODEL, GrootAdapter

    return GrootAdapter(model_id=model or DEFAULT_GROOT_MODEL, device=device, rename_map=rename_map)


#: Registry of policy factories keyed by name. Factories accept (and ignore unknown) keyword
#: overrides so the CLI can pass e.g. a fine-tuned checkpoint via ``--model``.
POLICIES: dict[str, Callable[..., PolicyAdapter]] = {
    "stub": _make_stub,
    "smolvla": _lerobot_native("lerobot/smolvla_base", "smolvla"),
    "pi0": _lerobot_native("lerobot/pi0", "pi0"),
    "pi05": _lerobot_native("lerobot/pi05_base", "pi05"),
    "pi0fast": _lerobot_native("lerobot/pi0fast_base", "pi0fast", action_head_class="token"),
    "groot": _make_groot,
    "openvla": _make_openvla,
    "openpi": _make_openpi,
}

#: policy name -> (extra name, importable module that makes it runnable here).
_REQUIRES_EXTRA: dict[str, tuple[str, str]] = {
    "smolvla": ("lerobot", "lerobot"),
    "pi0": ("lerobot", "lerobot"),
    "pi05": ("lerobot", "lerobot"),
    "pi0fast": ("lerobot", "lerobot"),
    "groot": ("lerobot", "lerobot"),
    "openvla": ("openvla", "transformers"),
    "openpi": ("openpi", "openpi_client"),
}

#: Policies that require the optional ``[lerobot]`` extra (kept for back-compat).
REQUIRES_LEROBOT: frozenset[str] = frozenset(
    name for name, (extra, _module) in _REQUIRES_EXTRA.items() if extra == "lerobot"
)

#: policy name -> why it is scaffolding rather than a runnable backend. A policy listed here is
#: registered and structurally unit-tested, but no checkpoint has ever been driven through it in
#: this repo, so nothing may present it as ready. ``groot`` additionally has no extra that
#: provisions it: LeRobot's ``groot`` policy type needs ``lerobot[groot]``, which
#: ``provael[lerobot]`` does not pull in, so the extra the CLI names leaves it unrunnable.
SCAFFOLDING_POLICIES: dict[str, str] = {
    "groot": (
        "scaffolding: needs lerobot[groot], which provael[lerobot] does not install; "
        "no GR00T checkpoint has been loaded here"
    ),
    "openvla": "scaffolding: structurally tested on CPU; no real forward pass has been run here",
    "openpi": "scaffolding: also needs a running openpi policy server; not exercised here",
}

#: policy name -> the committed evidence that a real checkpoint has actually been driven through
#: it. **Declared here, never inferred from the filesystem.** `list-defenses` learned this the hard
#: way in 0.26.0: it probed for ``docs/studies/<name>.md`` to decide "measured", which worked in a
#: git checkout and silently reported the opposite in an installed wheel, because ``docs/`` is not
#: packaged. ``results/`` is not packaged either, so a probe for a committed run report would fail
#: the same way — and failing *toward* "measured" is the direction that ships a false claim.
MEASURED_POLICIES: dict[str, str] = {
    "smolvla": "real SmolVLA x LIBERO run committed in results/smolvla_libero_object",
}

#: Status labels rendered by ``list-policies``. Kept as constants so the CLI, the tests and any
#: future emitter all say the same words about the same backend.
STATUS_MEASURED = "measured"
STATUS_FIXTURE = "CPU fixture"
STATUS_SCAFFOLDING = "scaffolding — no checkpoint ever run"
STATUS_UNRUN = "no run committed here"


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


def policy_scaffolding_note(name: str) -> str | None:
    """Why ``name`` is scaffolding rather than a runnable backend, or ``None`` if it is real.

    :func:`policy_is_ready` answers "is the declared dependency importable here", which is a
    strictly weaker claim than "this backend has been run". Both are surfaced by ``list-policies``
    so a reader is never told a policy is ready when all that was verified is an import.
    """
    return SCAFFOLDING_POLICIES.get(name)


def policy_status(name: str) -> str:
    """How much is actually known about ``name``: measured, fixture, scaffolding, or never run.

    This answers a strictly different question from :func:`policy_is_ready`, and conflating the two
    is the failure this exists to prevent. "Ready" means *the declared dependency imports in this
    environment* — a statement about the machine. "Status" means *has a real checkpoint ever been
    driven through this adapter and the result committed* — a statement about the evidence. A
    backend can be ready and never run; ``list-policies`` showed only readiness, so all seven
    non-stub backends rendered identically to anyone skimming for something to point `--policy` at.

    The distinction is the whole product: someone who runs against a backend that has never loaded
    a checkpoint and reports the resulting ASR as a measurement has produced a number about
    scaffolding. Three of the eight registered backends are in exactly that state.
    """
    if name in SCAFFOLDING_POLICIES:
        return STATUS_SCAFFOLDING
    if name in MEASURED_POLICIES:
        return STATUS_MEASURED
    if policy_extra(name) is None:
        return STATUS_FIXTURE  # `stub`: deterministic CPU arithmetic, embodies nothing
    return STATUS_UNRUN


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
    "MEASURED_POLICIES",
    "POLICIES",
    "REQUIRES_LEROBOT",
    "SCAFFOLDING_POLICIES",
    "STATUS_FIXTURE",
    "STATUS_MEASURED",
    "STATUS_SCAFFOLDING",
    "STATUS_UNRUN",
    "available_policies",
    "lerobot_available",
    "make_policy",
    "policy_extra",
    "policy_is_ready",
    "policy_scaffolding_note",
    "policy_status",
]
