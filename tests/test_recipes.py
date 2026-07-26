"""Recipes: built-in resolution, YAML-file loading, errors, and CLI wiring (list + override)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.recipes import (
    ALL_FAMILIES,
    BENIGN_CONTROL,
    RECIPES,
    available_recipes,
    load_recipe,
)

runner = CliRunner()


def test_builtin_recipes_are_valid_runconfigs() -> None:
    # Every built-in recipe must merge into a valid RunConfig (catches typos in field names).
    for name in available_recipes():
        cfg = RunConfig.model_validate(load_recipe(name))
        assert cfg.episodes >= 1
        assert cfg.attacks


def test_known_recipe_shapes() -> None:
    assert load_recipe("quick") == {"attacks": ["none", "instruction"], "episodes": 5}
    assert load_recipe("full-sweep") == {"attacks": ["none", *ALL_FAMILIES], "episodes": 10}
    assert load_recipe("ci-gate")["seed"] == 0
    assert set(available_recipes()) == set(RECIPES)


def test_every_recipe_ships_the_benign_control() -> None:
    """An ASR with no false-positive control is not interpretable, and the release gate requires one.

    `ReleaseRequirements.require_benign_control` defaults to True, so a recipe without the `none`
    arm can never reach a `pass` verdict — every shipped recipe used to be `incomplete` by
    construction. Adding benign episodes cannot move the adversarial ASR (it excludes them by
    semantic role), so there is no downside to always carrying it.
    """
    for name in available_recipes():
        attacks = load_recipe(name)["attacks"]
        assert BENIGN_CONTROL in attacks, f"recipe {name!r} omits the benign control"
        assert attacks[0] == BENIGN_CONTROL, f"recipe {name!r} should list the control first"
    # The control is not an attack family: it must stay out of ALL_FAMILIES.
    assert BENIGN_CONTROL not in ALL_FAMILIES


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
    # `--recipe quick` => benign control + instruction family (3 attacks on the stub) = 4 arms
    # x 5 episodes = 20 applicable episodes; the 5 benign ones stay out of the adversarial ASR.
    out = tmp_path / "run"
    result = runner.invoke(app, ["attack", "--recipe", "quick", "--out", str(out)])
    assert result.exit_code == 0
    report = json.loads((out / "report.json").read_text())
    assert report["attempts"] == 20
    assert report["adversarial_attempts"] == 15
    assert report["benign_fpr"] is not None  # the control the release gate requires


def test_attack_explicit_flag_overrides_recipe(tmp_path: Path) -> None:
    # `--recipe quick --episodes 2` keeps the arms (control + instruction) but 2 episodes => 8.
    out = tmp_path / "run"
    result = runner.invoke(
        app, ["attack", "--recipe", "quick", "--episodes", "2", "--out", str(out)]
    )
    assert result.exit_code == 0
    report = json.loads((out / "report.json").read_text())
    assert report["attempts"] == 8


def test_attack_unknown_recipe_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["attack", "--recipe", "nope", "--out", str(tmp_path / "r")])
    assert result.exit_code != 0
    assert "unknown recipe" in result.output
