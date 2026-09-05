"""provael (Provael) — red-team open Vision-Language-Action robot policies.

A model-agnostic harness that perturbs the instructions/observations fed to a VLA
policy inside a simulator and measures how often those perturbations drive the
policy into an *unsafe* state. The headline metric is the Attack Success Rate (ASR).

The core (abstractions, attacks, scoring, runner, report, CLI) runs on a plain CPU
with no GPU and no model/dataset download, using a deterministic StubPolicy and
StubSuite. Real VLA policies (e.g. SmolVLA via LeRobot) live behind the optional
``provael[lerobot]`` extra and are gated behind ``PROVAEL_INTEGRATION=1``.
"""

__version__ = "0.39.3"

# ── The documented public surface ────────────────────────────────────────────
#
# `docs/python-api.md` has always been the published API, and nothing enforced it: a rename
# could land, the gate stays green, and the docs go on describing an import that no longer
# resolves. `__all__` is that list, and `tests/test_public_api.py` fails if the two disagree
# in either direction.
#
# WHY THESE ARE LAZY. Every documented name lives in a submodule, and importing all eight
# eagerly here costs ~1.14 s and pulls numpy in, against ~1.1 ms for the bare package today.
# That is a ~1000x regression paid by every `import provael` and by CLI startup, to make an
# import shorter. PEP 562 gives the short import without the cost: nothing is loaded until
# the name is actually touched. The test asserts the laziness holds, because the cheap way
# to break it is a convenience import added at the top of this file.
#
# The submodule paths in the docs keep working exactly as before; this only adds the
# top-level spelling.

_EXPORTS: dict[str, str] = {
    "RunConfig": "provael.config",
    "run": "provael.runner",
    "PolicyAdapter": "provael.policies.base",
    "POLICIES": "provael.policies.registry",
    "SuiteAdapter": "provael.suites.base",
    "to_scorecard_markdown": "provael.scorecard",
    "to_oscal_json": "provael.oscal",
    "to_avid_json": "provael.avid",
}

__all__ = ["__version__", *sorted(_EXPORTS)]


def __getattr__(name: str) -> object:
    """Resolve a documented export on first access (PEP 562)."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module_name), name)
    globals()[name] = value  # cache, so the import cost is paid at most once
    return value


def __dir__() -> list[str]:
    """Make the lazy names discoverable to `dir()` and tab-completion."""
    return sorted(__all__)
