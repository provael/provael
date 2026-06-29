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

#: The four shipped attack families (EAI01/02/04/05), in canonical order.
ALL_FAMILIES: list[str] = ["instruction", "visual", "injection", "action"]


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
        "Fast CPU smoke — instruction family, 5 episodes.",
        {"attacks": ["instruction"], "episodes": 5},
    ),
    "instruction-only": Recipe(
        "instruction-only",
        "Instruction-jailbreak family only (EAI01), 10 episodes.",
        {"attacks": ["instruction"], "episodes": 10},
    ),
    "full-sweep": Recipe(
        "full-sweep",
        "All four families (EAI01/02/04/05), 10 episodes.",
        {"attacks": ALL_FAMILIES, "episodes": 10},
    ),
    "ci-gate": Recipe(
        "ci-gate",
        "What a CI gate runs — all families, 10 episodes, seed 0 (matches the GitHub Action).",
        {"attacks": ALL_FAMILIES, "episodes": 10, "seed": 0},
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


__all__ = ["ALL_FAMILIES", "Recipe", "RECIPES", "available_recipes", "load_recipe"]
