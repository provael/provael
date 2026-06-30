"""Recipes: built-in resolution, YAML-file loading, errors, and CLI wiring (list + override)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.recipes import ALL_FAMILIES, RECIPES, available_recipes, load_recipe

runner = CliRunner()


def test_builtin_recipes_are_valid_runconfigs() -> None:
    # Every built-in recipe must merge into a valid RunConfig (catches typos in field names).
    for name in available_recipes():
        cfg = RunConfig.model_validate(load_recipe(name))
        assert cfg.episodes >= 1
        assert cfg.attacks


def test_known_recipe_shapes() -> None:
    assert load_recipe("quick") == {"attacks": ["instruction"], "episodes": 5}
    assert load_recipe("full-sweep") == {"attacks": ALL_FAMILIES, "episodes": 10}
    assert load_recipe("ci-gate")["seed"] == 0
    assert set(available_recipes()) == set(RECIPES)


def test_load_recipe_from_yaml_file(tmp_path: Path) -> None:
    f = tmp_path / "mine.yml"
    f.write_text("attacks: [visual]\nepisodes: 3\n")
    assert load_recipe(str(f)) == {"attacks": ["visual"], "episodes": 3}


def test_unknown_recipe_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        load_recipe("does-not-exist")


def test_non_mapping_yaml_raises_valueerror(tmp_path: Path) -> None:
    f = tmp_path / "bad.yml"
    f.write_text("- just\n- a\n- list\n")
    with pytest.raises(ValueError, match="must contain a YAML mapping"):
        load_recipe(str(f))


def test_list_recipes_cli() -> None:
    result = runner.invoke(app, ["list-recipes"])
    assert result.exit_code == 0
    for name in available_recipes():
        assert name in result.output


def test_attack_recipe_applies_preset(tmp_path: Path) -> None:
    # `--recipe quick` => instruction family (3 attacks on the stub) x 5 episodes = 15 attempts.
    out = tmp_path / "run"
    result = runner.invoke(app, ["attack", "--recipe", "quick", "--out", str(out)])
    assert result.exit_code == 0
    report = json.loads((out / "report.json").read_text())
    assert report["attempts"] == 15


def test_attack_explicit_flag_overrides_recipe(tmp_path: Path) -> None:
    # `--recipe quick --episodes 2` keeps the instruction family but uses 2 episodes => 6.
    out = tmp_path / "run"
    result = runner.invoke(
        app, ["attack", "--recipe", "quick", "--episodes", "2", "--out", str(out)]
    )
    assert result.exit_code == 0
    report = json.loads((out / "report.json").read_text())
    assert report["attempts"] == 6


def test_attack_unknown_recipe_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["attack", "--recipe", "nope", "--out", str(tmp_path / "r")])
    assert result.exit_code != 0
    assert "unknown recipe" in result.output
