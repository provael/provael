# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Recipes: built-in resolution, YAML-file loading, errors, and CLI wiring (list + override)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from provael.attacks.controls import CONTROL_FAMILY
from provael.attacks.registry import FAMILIES
from provael.cli import app
from provael.config import RunConfig
from provael.coverage import NON_ADVERSARIAL_FAMILIES
from provael.recipes import (
    ALL_FAMILIES,
    BENIGN_CONTROL,
    CONDITIONAL_FAMILIES,
    CORE_FAMILIES,
    RECIPES,
    available_recipes,
    load_recipe,
)
from provael.runner import run
from provael.scoring.asr import by_family

runner = CliRunner()
REPO = Path(__file__).resolve().parent.parent


def test_builtin_recipes_are_valid_runconfigs() -> None:
    # Every built-in recipe must merge into a valid RunConfig (catches typos in field names).
    for name in available_recipes():
        cfg = RunConfig.model_validate(load_recipe(name))
        assert cfg.episodes >= 1
        assert cfg.attacks


def test_known_recipe_shapes() -> None:
    assert load_recipe("quick") == {"attacks": ["none", "instruction"], "episodes": 5}
    # BOTH controls bracket the attack families: the benign-FPR baseline leads, the
    # harmless-variation reword trails. full-sweep is the one recipe that carries the reword arm,
    # because a complete sweep without it cannot separate attacker choice from brittleness to
    # rephrasing.
    assert load_recipe("full-sweep") == {
        "attacks": ["none", *ALL_FAMILIES, CONTROL_FAMILY],
        "episodes": 10,
    }
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


# --------------------------------------------------------------------------- #
# full-sweep must mean what it says
# --------------------------------------------------------------------------- #


def test_full_sweep_covers_every_registry_family() -> None:
    """The bug: ALL_FAMILIES was a hardcoded list of four beside a registry that held fourteen.

    `--recipe full-sweep` therefore computed an ASR over 4/14 families and printed it as a full
    sweep, with nothing in the output saying so. That number can end up in a conformity file.
    Deriving the list from the registry is the fix; this asserts the derivation, so registering a
    new family without it appearing in full-sweep is a test failure rather than a silent gap.
    """
    registry_adversarial = set(FAMILIES) - NON_ADVERSARIAL_FAMILIES
    swept_all = set(load_recipe("full-sweep")["attacks"])
    swept = swept_all - NON_ADVERSARIAL_FAMILIES - {BENIGN_CONTROL}
    assert swept == registry_adversarial

    # full-sweep must also carry BOTH controls. A sweep of every attack with no reword control
    # cannot separate attacker choice from brittleness to rephrasing, which is the strongest
    # objection to this project's own headline result.
    assert BENIGN_CONTROL in swept_all, "full-sweep lost the benign-FPR control"
    assert CONTROL_FAMILY in swept_all, "full-sweep lost the harmless-variation control"
    assert len(swept) == 17  # adversarial families only; the two control families are not attacks


def test_every_family_is_swept_or_declared_conditional_with_a_reason() -> None:
    """Every registry family is either in full-sweep or explicitly declared skippable, with why."""
    for family in FAMILIES:
        # Both control families are exempt: ALL_FAMILIES is "the ATTACK families", and neither the
        # benign-FPR baseline nor the harmless-variation reword is an attack. full-sweep runs both
        # of them via _with_both_controls, which test_known_recipe_shapes asserts separately.
        if family in NON_ADVERSARIAL_FAMILIES:
            continue
        assert family in ALL_FAMILIES, f"{family} is in no sweep and is not declared conditional"
    for family, reason in CONDITIONAL_FAMILIES.items():
        assert family in ALL_FAMILIES, f"{family} is declared conditional but is not a family"
        assert len(reason) > 20, f"{family}'s skip reason is too thin to act on: {reason!r}"


def test_core_sweep_keeps_the_old_four_under_an_honest_name() -> None:
    assert load_recipe("core-sweep")["attacks"] == [BENIGN_CONTROL, *CORE_FAMILIES]
    assert set(CORE_FAMILIES) < set(ALL_FAMILIES)  # strict subset
    # "full" must be the bigger one, or the rename achieved nothing.
    assert len(load_recipe("full-sweep")["attacks"]) > len(load_recipe("core-sweep")["attacks"])


@pytest.mark.parametrize("suite", ["stub", "reach", "humanoid"])
def test_full_sweep_never_crashes_and_never_scores_a_skip_as_zero(suite: str) -> None:
    """A skipped family is N/A, never 0% — the distinction the ASR denominator depends on."""
    cfg = RunConfig.model_validate({**load_recipe("full-sweep"), "policy": "stub", "suite": suite,
                                    "episodes": 4, "seed": 0})
    report = run(cfg)  # must not raise on families the suite cannot support

    stats = by_family(report.results)
    for family in ALL_FAMILIES:
        stat = stats.get(family)
        if stat is None or stat.attempts == 0:
            # Skipped: it contributed NOTHING to the denominator. `measured_rate` is the honest
            # N/A accessor; `asr` is 0.0 at zero attempts only as a serialisation sentinel, and
            # reading that as a result is exactly the "0% looks like a pass" failure.
            assert stat is None or stat.measured_rate is None
            assert family in CONDITIONAL_FAMILIES, (
                f"{family} scored nothing on {suite} but declares no precondition — either it is "
                f"broken or CONDITIONAL_FAMILIES is missing an entry"
            )

    # The sweep still produced a real adversarial measurement on every CPU suite.
    assert report.adversarial_attempts > 0


def test_declared_preconditions_match_reality_on_the_cpu_suites() -> None:
    """A family declared conditional must actually be skipped somewhere, or the reason is fiction.

    Without this, CONDITIONAL_FAMILIES rots into a list of excuses for families that in fact run
    fine — which would let a genuinely-broken family hide behind a stale precondition.
    """
    skipped_somewhere: set[str] = set()
    for suite in ("stub", "reach", "humanoid"):
        cfg = RunConfig.model_validate({**load_recipe("full-sweep"), "policy": "stub",
                                        "suite": suite, "episodes": 4, "seed": 0})
        stats = by_family(run(cfg).results)
        for family in ALL_FAMILIES:
            stat = stats.get(family)
            if stat is None or stat.attempts == 0:
                skipped_somewhere.add(family)

    assert skipped_somewhere == set(CONDITIONAL_FAMILIES), (
        f"declared-but-never-skipped={sorted(set(CONDITIONAL_FAMILIES) - skipped_somewhere)}, "
        f"skipped-but-undeclared={sorted(skipped_somewhere - set(CONDITIONAL_FAMILIES))}"
    )


def test_the_action_default_carries_the_benign_control_and_matches_ci_gate() -> None:
    """action.yml's default omitted `none`, producing an ASR with no control arm.

    The release gate requires a benign control, so that default could only ever reach
    `incomplete` — and the rate it printed had no false-positive baseline to be read against.
    Bound to the `ci-gate` recipe here so the Action and the recipe claiming to match it cannot
    drift apart again.
    """
    action = yaml.safe_load((REPO / "action.yml").read_text(encoding="utf-8"))
    default = action["inputs"]["attacks"]["default"]
    tokens = [t.strip() for t in default.split(",")]

    assert BENIGN_CONTROL in tokens, f"action.yml default {default!r} has no benign control"
    assert tokens == load_recipe("ci-gate")["attacks"], (
        f"action.yml default {tokens} has drifted from the ci-gate recipe "
        f"{load_recipe('ci-gate')['attacks']}"
    )


def test_the_reference_workflow_default_also_carries_the_control() -> None:
    gate = yaml.safe_load(
        (REPO / ".github" / "workflows" / "checkpoint-security-gate.yml").read_text("utf-8")
    )
    # `on:` parses as the YAML boolean True — the workflow key, not a string.
    default = gate[True]["workflow_dispatch"]["inputs"]["attacks"]["default"]
    assert BENIGN_CONTROL in [t.strip() for t in default.split(",")]


@pytest.mark.parametrize("name", sorted(RECIPES))
def test_example_yaml_mirrors_the_builtin_it_documents(name: str) -> None:
    """The `.yml` templates are copy-paste starting points; a stale one ships a stale scan.

    All five drifted at once: every example omitted the `none` control, so anyone starting from
    one got an ASR with no false-positive baseline and a gate that could never reach `pass`.
    """
    path = REPO / "examples" / "recipes" / f"{name}.yml"
    assert path.is_file(), f"built-in recipe {name!r} has no examples/recipes/{name}.yml twin"
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == RECIPES[name].config


def test_every_example_recipe_carries_the_benign_control() -> None:
    """Including regression-gate.yml, which has no built-in twin to inherit it from."""
    for path in sorted((REPO / "examples" / "recipes").glob("*.yml")):
        attacks = yaml.safe_load(path.read_text(encoding="utf-8"))["attacks"]
        assert BENIGN_CONTROL in attacks, f"{path.name} has no benign control"


# --------------------------------------------------------------------------- #
# full-sweep on a REAL policy runs what has met a real policy (20 September 2026)
# --------------------------------------------------------------------------- #


def test_full_sweep_on_the_fixture_runs_every_family() -> None:
    """The fixture exists to exercise the whole pipeline; nothing is narrowed there."""
    from provael.recipes import full_sweep_attacks

    assert full_sweep_attacks(real_policy=False) == load_recipe("full-sweep")["attacks"]


def test_full_sweep_on_a_real_policy_defaults_to_the_measured_families() -> None:
    """On a real policy the default is the families with a committed real-policy measurement.

    The fixture-only families are implemented and runnable, but every rate they have produced is a
    property of a fixture written to be attackable — `full-sweep` on the CPU prints an ASR in the
    eighties for them. A buyer pointing the sweep at their own checkpoint gets the families whose
    real-policy behaviour is on record; the rest are one flag away, and the flag says what they are.
    """
    from provael.attacks.registry import (
        FAMILY_STATUS_FIXTURE_ONLY,
        FAMILY_STATUS_MEASURED,
        MEASURED_FAMILIES,
        family_status,
    )
    from provael.recipes import fixture_only_families, full_sweep_attacks

    narrowed = full_sweep_attacks(real_policy=True)
    assert BENIGN_CONTROL in narrowed and CONTROL_FAMILY in narrowed, "both controls stay"
    swept = [f for f in narrowed if f not in NON_ADVERSARIAL_FAMILIES and f != BENIGN_CONTROL]
    assert set(swept) == set(MEASURED_FAMILIES)
    assert all(family_status(f) == FAMILY_STATUS_MEASURED for f in swept)
    assert set(fixture_only_families()) == set(ALL_FAMILIES) - set(MEASURED_FAMILIES)
    assert all(family_status(f) == FAMILY_STATUS_FIXTURE_ONLY for f in fixture_only_families())
    # opting in restores the whole registry, in the same order as the fixture sweep
    assert full_sweep_attacks(real_policy=True, include_fixture_families=True) == full_sweep_attacks(
        real_policy=False
    )


def test_the_packaged_measured_families_match_the_derived_partition() -> None:
    """`MEASURED_FAMILIES` is declared (a wheel has no results/); coverage() derives the same set.

    Same contract as `MEASURED_POLICIES`: in a checkout the two must agree in both directions, so
    a family cannot be declared measured without a committed applicable adversarial episode, and a
    committed one cannot stay `fixture-only`. Each entry must also name a results directory that
    exists.
    """
    from provael.attacks.registry import MEASURED_FAMILIES
    from provael.coverage import coverage

    cov = coverage()
    if not cov.evidence_scanned:  # a wheel: nothing to compare against
        return
    assert set(MEASURED_FAMILIES) == set(cov.real_policy_families)
    root = Path(__file__).resolve().parents[1]
    for family, evidence in MEASURED_FAMILIES.items():
        dirs = [tok.rstrip("(),;") for tok in evidence.replace("_\n", "_").split() if tok.startswith("results/")]
        assert dirs, f"{family}: the evidence string names no results/ directory"
        for d in dirs:
            assert (root / d).is_dir(), f"{family}: {d} does not exist"


def test_cli_full_sweep_narrows_on_a_real_policy_and_says_so(tmp_path: Path) -> None:
    """The CLI prints the narrowing before it tries to load the policy, and names the flag."""
    from provael.recipes import fixture_only_families

    result = runner.invoke(
        app,
        ["attack", "--recipe", "full-sweep", "--policy", "smolvla", "--suite", "libero",
         "--out", str(tmp_path)],
    )
    # smolvla needs the [lerobot] extra, so the run itself fails on this CPU lane; the
    # resolution happens before the load, which is the point of the assertion.
    combined = result.stdout + (result.stderr or "")
    assert "full-sweep on a real policy runs the" in combined
    assert "--include-fixture-families" in combined
    for family in fixture_only_families():
        assert family in combined
    stub = runner.invoke(
        app, ["attack", "--recipe", "full-sweep", "--policy", "stub", "--out", str(tmp_path / "s")]
    )
    assert stub.exit_code == 0, stub.stdout
    assert "fixture-only families are not run" not in stub.stdout + (stub.stderr or "")
