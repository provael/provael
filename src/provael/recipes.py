"""Named run recipes: reusable :class:`~provael.config.RunConfig` presets for the CLI.

A *recipe* is a named preset of RunConfig overrides — the copy-paste shortcut that turns
"nine attacks across four families, ten episodes, seed 0" into one ``--recipe`` flag.

Built-in recipes are packaged *with* Provael (so ``pip install provael`` users get them with
no extra files): ``provael attack --recipe NAME`` resolves a built-in name, and
``--recipe ./path.yml`` loads a user YAML file of the same shape. The example YAMLs under
``examples/recipes/`` mirror the built-ins as editable templates.

Recipes are intentionally thin: each is a partial mapping of RunConfig fields. The CLI builds
the full RunConfig (with its own defaults) from ``{**recipe, **explicit_cli_flags}`` so any
explicitly-passed CLI option overrides the recipe.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from provael.attacks.baseline import FAMILY as BASELINE_FAMILY
from provael.attacks.registry import FAMILIES

#: **Every** adversarial family in the registry, in registry order — derived at import, never
#: hand-listed. This was a literal `["instruction", "visual", "injection", "action"]` sitting next
#: to a registry that had grown to fourteen, so `--recipe full-sweep` computed an ASR over four of
#: them and reported it as a full sweep. A hardcoded list beside a growing registry is the bug; a
#: newly-registered family now joins `full-sweep` automatically.
#:
#: Adversarial families only — the benign ``baseline`` is a CONTROL, not an attack family, and must
#: not be folded in here (``adversarial_asr`` excludes it by role, and callers reading this list as
#: "the attack families" would then over-count).
ALL_FAMILIES: list[str] = [f for f in FAMILIES if f != BASELINE_FAMILY]

#: The original four (EAI01/02/04/05) — every one applicable on the default CPU ``stub`` suite.
#: Kept as a deliberately smaller recipe, but no longer under the name ``full-sweep``.
CORE_FAMILIES: list[str] = ["instruction", "visual", "injection", "action"]

#: Families that cannot score on every suite, and the precondition each needs. Applicability is
#: ultimately decided per episode by :meth:`~provael.attacks.base.Attack.applicable`, which the
#: recipe layer cannot predict — so this records the *declared* precondition and
#: ``tests/test_recipes.py`` checks each claim against a real run on every CPU suite, so a reason
#: cannot quietly go stale.
#:
#: A family listed here is **skipped, not scored zero**. The runner marks an inapplicable episode
#: ``applicable=False``, scoring drops it from the ASR denominator, and the evidence artifacts
#: render ``N/A`` — never ``0.0%``, which would read as "we attacked it and it held".
CONDITIONAL_FAMILIES: dict[str, str] = {
    "sensor_spoof": (
        "needs a suite with spatial keep-out zones (reach / keepout_zones); no episode is "
        "applicable on the scalar-danger stub suite"
    ),
    "action_space": (
        "needs a suite with spatial keep-out zones (reach / keepout_zones); no episode is "
        "applicable on the scalar-danger stub suite"
    ),
    "misalignment": (
        "needs a suite with spatial keep-out zones (reach / keepout_zones); no episode is "
        "applicable on the scalar-danger stub suite"
    ),
    "backdoor": (
        "needs the scalar-danger stub suite; the trigger screen has no meaning on the spatial "
        "keep-out suites"
    ),
    "authorization": (
        "needs the scalar-danger stub suite; the authorization screen has no meaning on the "
        "spatial keep-out suites"
    ),
    "confidentiality": (
        "needs the scalar-danger stub suite; the memorized-canary screen has no meaning on the "
        "spatial keep-out suites"
    ),
    "action": "not applicable on the humanoid suite, which has no end-effector action channel",
    "optimized": "not applicable on the humanoid suite (same action-channel precondition)",
    "humanoid": "needs the humanoid suite (whole-body / locomotion observations)",
    "optimized_patch": (
        "needs a real image channel from a GPU policy; inert on every CPU suite, so it scores no "
        "episode in any CPU run"
    ),
    "universal_patch": (
        "needs a real image channel from a GPU policy; inert on every CPU suite, so it scores no "
        "episode in any CPU run"
    ),
}

#: The benign control attack. Every recipe includes it because an attack-success rate without a
#: false-positive control is not interpretable: you cannot tell an attack-induced unsafe state from
#: one the predicate would have flagged anyway. It is also a hard requirement of the release gate
#: (:class:`provael.verdict.ReleaseRequirements.require_benign_control`), so a run without it can
#: never reach `pass` — every shipped recipe previously produced an `incomplete` verdict by
#: construction. Adding benign episodes cannot move the adversarial ASR, which excludes them by
#: semantic role.
BENIGN_CONTROL: str = "none"


def _with_control(attacks: list[str]) -> list[str]:
    """``attacks`` with the benign control first (idempotent)."""
    return attacks if BENIGN_CONTROL in attacks else [BENIGN_CONTROL, *attacks]


@dataclass(frozen=True)
class Recipe:
    """A named preset: a human description plus a partial RunConfig override mapping."""

    name: str
    description: str
    config: dict[str, Any]


#: Built-in recipes, keyed by name. Ordered for deterministic listing.
RECIPES: dict[str, Recipe] = {
    "quick": Recipe(
        "quick",
        "Fast CPU smoke — instruction family + benign control, 5 episodes.",
        {"attacks": _with_control(["instruction"]), "episodes": 5},
    ),
    "instruction-only": Recipe(
        "instruction-only",
        "Instruction-jailbreak family only (EAI01) + benign control, 10 episodes.",
        {"attacks": _with_control(["instruction"]), "episodes": 10},
    ),
    "core-sweep": Recipe(
        "core-sweep",
        "The four core families (EAI01/02/04/05) + benign control, 10 episodes — every one "
        "applicable on the default CPU stub suite.",
        {"attacks": _with_control(CORE_FAMILIES), "episodes": 10},
    ),
    "full-sweep": Recipe(
        "full-sweep",
        f"Every one of the {len(ALL_FAMILIES)} adversarial families + benign control, 10 "
        "episodes. Families inapplicable to the chosen suite are SKIPPED (N/A), never scored 0.",
        {"attacks": _with_control(ALL_FAMILIES), "episodes": 10},
    ),
    "eai04-redirect": Recipe(
        "eai04-redirect",
        "The EAI04 targeted-redirection protocol: the optimized command-preserving instruction "
        "search + benign control, 10 episodes, horizon 280, query budget 64 — the SAME protocol "
        "as the published SmolVLA x LIBERO run, so a result is comparable to it. On a spatial "
        "suite the search scores the suite's keep-out predicate; on the CPU stub it is "
        "scaffolding and must not be reported as an EAI04 real transfer.",
        {
            "attacks": _with_control(["optimized_instruction"]),
            "episodes": 10,
            "horizon": 280,
            "seed": 0,
            "query_budget": 64,
        },
    ),
    "ci-gate": Recipe(
        "ci-gate",
        "What a CI gate runs — the core families + benign control, 10 episodes, seed 0 "
        "(kept byte-identical to the GitHub Action's default `attacks` input).",
        {"attacks": _with_control(CORE_FAMILIES), "episodes": 10, "seed": 0},
    ),
}


def available_recipes() -> list[str]:
    """Names of all built-in recipes."""
    return list(RECIPES)


def load_recipe(name_or_path: str) -> dict[str, Any]:
    """Resolve a recipe to a dict of RunConfig overrides.

    ``name_or_path`` is either a built-in recipe name (see :func:`available_recipes`) or a
    path to a YAML file holding a mapping of RunConfig fields.

    Raises:
        KeyError: an unknown built-in name that is also not an existing file.
        ValueError: a YAML file that does not parse to a mapping.
    """
    recipe = RECIPES.get(name_or_path)
    if recipe is not None:
        return dict(recipe.config)
    path = Path(name_or_path)
    if path.is_file():
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f"recipe file {name_or_path!r} must contain a YAML mapping")
        return {str(key): value for key, value in data.items()}
    raise KeyError(
        f"unknown recipe {name_or_path!r}; built-ins: {available_recipes()} "
        f"(or pass a path to a .yml file)"
    )


__all__ = [
    "ALL_FAMILIES",
    "CORE_FAMILIES",
    "CONDITIONAL_FAMILIES",
    "BENIGN_CONTROL",
    "Recipe",
    "RECIPES",
    "available_recipes",
    "load_recipe",
]
