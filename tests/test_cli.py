# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""CLI smoke tests via typer's CliRunner."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from provael import __version__
from provael.attacks.registry import FAMILIES
from provael.cli import app
from provael.report import load_report

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_list_policies() -> None:
    result = runner.invoke(app, ["list-policies"])
    assert result.exit_code == 0
    assert "stub" in result.output
    assert "smolvla" in result.output


def test_list_attacks() -> None:
    result = runner.invoke(app, ["list-attacks"])
    assert result.exit_code == 0
    assert "roleplay" in result.output
    assert "instruction" in result.output


def test_attack_runs_and_writes_report(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "attack",
            "--policy", "stub",
            "--suite", "stub",
            "--attacks", "instruction",
            "--episodes", "5",
            "--seed", "0",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0
    assert (out / "report.json").exists()
    assert (out / "report.md").exists()

    report = load_report(out)
    # 1 task x 3 instruction attacks x 5 episodes on the adversarial side; the benign floor and
    # the control family ride along by default (P2.1) and stay out of that denominator.
    assert report.adversarial_attempts == 15
    assert report.attempts == 5 * (3 + 1 + len(FAMILIES["control"]))
    assert 0.0 <= report.asr <= 1.0
    assert "ASR" in result.output  # headline printed


def test_attack_runs_all_three_families(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        [
            "attack",
            "--policy", "stub",
            "--suite", "stub",
            "--attacks", "instruction,visual,injection",
            "--episodes", "5",
            "--seed", "0",
            "--out", str(out),
        ],
    )
    assert result.exit_code == 0
    report = load_report(out)
    # 1 task x 7 attacks (3 instruction + 2 visual + 2 injection) x 5 episodes, adversarial; the
    # floor and the controls the instruction family brings with it are counted apart (P2.1).
    assert report.adversarial_attempts == 35
    assert set(report.attacks) == {
        "roleplay", "goal_substitution", "paraphrase",
        "patch", "decoy_object", "scene_text", "mcp_tool_desc",
        "none", *FAMILIES["control"],
    }


def test_list_attacks_shows_new_families() -> None:
    result = runner.invoke(app, ["list-attacks"])
    assert result.exit_code == 0
    for token in ("patch", "scene_text", "visual", "injection"):
        assert token in result.output


def test_report_command_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert runner.invoke(app, ["attack", "--episodes", "5", "--out", str(out)]).exit_code == 0
    result = runner.invoke(app, ["report", "--in", str(out)])
    assert result.exit_code == 0
    assert "ASR" in result.output


def test_smolvla_without_extra_exits_cleanly() -> None:
    result = runner.invoke(app, ["attack", "--policy", "smolvla", "--episodes", "2"])
    # Clean, actionable failure — not a crash (exit 1 from an uncaught exception).
    assert result.exit_code == 2
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_unknown_attack_exits_cleanly() -> None:
    result = runner.invoke(app, ["attack", "--attacks", "bogus", "--episodes", "2"])
    assert result.exit_code == 2


def test_libero_suite_without_extra_exits_cleanly() -> None:
    # Symmetry with the smolvla test: --suite libero on a CPU box (no extra) is clean.
    result = runner.invoke(app, ["attack", "--policy", "stub", "--suite", "libero", "--episodes", "2"])
    assert result.exit_code == 2


def test_seeds_alias_and_bad_rename_map(tmp_path: Path) -> None:
    out = tmp_path / "run"
    # --seeds is an alias for --episodes (1 task x 3 attacks x 2 seeds = 6 attempts).
    ok = runner.invoke(app, ["attack", "--seeds", "2", "--no-controls", "--out", str(out)])
    assert ok.exit_code == 0
    assert load_report(out).attempts == 6
    # Invalid JSON rename-map -> clean error.
    bad = runner.invoke(app, ["attack", "--rename-map", "not-json", "--episodes", "1"])
    assert bad.exit_code == 2


def test_version_flag_matches_the_version_subcommand() -> None:
    """`--version` is what everyone reaches for; the subcommand is what scripts pin to."""
    flag = runner.invoke(app, ["--version"])
    sub = runner.invoke(app, ["version"])
    assert flag.exit_code == 0 and sub.exit_code == 0
    assert flag.stdout.strip() == sub.stdout.strip()
    assert __version__ in flag.stdout


def test_no_args_still_prints_help_not_the_version() -> None:
    """Adding an app callback must not turn a bare `provael` into a no-op.

    Rich wraps the usage line to the terminal width and interleaves ANSI styling, and CI's width
    differs from a developer's, so the raw substring matched locally and not in CI. Strip the
    escapes and collapse whitespace before asserting on rendered text.
    """
    result = runner.invoke(app, [])
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    plain = " ".join(plain.split())
    assert "Usage: provael" in plain
    assert "COMMAND" in plain  # the command list, not just a version string


def _flat(text: str) -> str:
    """Console output with Rich's line wrapping undone, so a sentence can be searched for."""
    return " ".join(text.split())


def _init_states_file(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "init-states.json"
    path.write_text(body, encoding="utf-8")
    return path


def test_init_states_with_an_adversarial_arm_must_pin_one_state_per_seed(tmp_path: Path) -> None:
    """Repeats at one seed on different scenes would break the pairing, so it is refused."""
    states = _init_states_file(tmp_path, '{"reach": [3, 4, 5, 6]}')
    result = runner.invoke(
        app,
        ["attack", "--attacks", "none,roleplay", "--episodes", "4", "--episodes-per-seed", "2",
         "--init-states", str(states), "--out", str(tmp_path / "run")],
    )
    assert result.exit_code != 0
    assert "must pin one state per seed" in _flat(result.output)
    assert not (tmp_path / "run" / "report.json").exists()


def test_init_states_and_a_pin_are_refused_together(tmp_path: Path) -> None:
    states = _init_states_file(tmp_path, '{"reach": [3]}')
    result = runner.invoke(
        app,
        ["attack", "--attacks", "none", "--episodes", "1", "--pin-init-states", "2",
         "--init-states", str(states), "--out", str(tmp_path / "run")],
    )
    assert result.exit_code != 0
    assert "pass one of them" in _flat(result.output)


def test_init_states_that_are_not_a_json_object_of_indices_are_refused(tmp_path: Path) -> None:
    for body, message in (("{not json", "--init-states"), ('{"reach": [-1]}', "invalid "),
                          ('{"reach": []}', "invalid ")):
        states = _init_states_file(tmp_path, body)
        result = runner.invoke(
            app,
            ["attack", "--attacks", "none", "--episodes", "1", "--init-states", str(states),
             "--out", str(tmp_path / "run")],
        )
        assert result.exit_code != 0, body
        assert message in _flat(result.output), body


def test_init_states_on_a_suite_without_fixed_init_states_are_refused(tmp_path: Path) -> None:
    states = _init_states_file(tmp_path, '{"reach": [3]}')
    result = runner.invoke(
        app,
        ["attack", "--attacks", "none", "--episodes", "1", "--init-states", str(states),
         "--out", str(tmp_path / "run")],
    )
    assert result.exit_code != 0
    assert "keeps no fixed initial states" in _flat(result.output)


def test_termination_fixed_horizon_runs_to_the_horizon_and_says_so(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["attack", "--attacks", "none,roleplay", "--episodes", "2", "--horizon", "6",
         "--termination", "fixed-horizon", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    report = load_report(out / "report.json")
    assert report.termination_mode == "fixed-horizon"
    assert all(r.steps == 6 for r in report.results if r.applicable)
    assert "episode termination | fixed horizon" in (out / "report.md").read_text(encoding="utf-8")


def test_termination_is_refused_where_the_suite_cannot_honour_it(tmp_path: Path) -> None:
    refused = runner.invoke(
        app,
        ["attack", "--suite", "reach", "--attacks", "none", "--episodes", "1",
         "--termination", "fixed-horizon", "--out", str(tmp_path / "reach")],
    )
    assert refused.exit_code != 0
    assert "refusing to label first-event episodes as fixed-horizon" in _flat(refused.output)
    assert not (tmp_path / "reach" / "report.json").exists()
    bogus = runner.invoke(
        app,
        ["attack", "--attacks", "none", "--episodes", "1", "--termination", "whenever",
         "--out", str(tmp_path / "bogus")],
    )
    assert bogus.exit_code != 0
    assert "invalid configuration" in _flat(bogus.output)


# --- Controls by default (P2.1) -----------------------------------------------------------------


def _run_attack(tmp_path: Path, *args: str) -> tuple[str, list[str]]:
    """Run ``provael attack`` on the stub with ``args``; return its output and the arms it ran."""
    out = tmp_path / "run"
    result = runner.invoke(
        app, ["attack", "--policy", "stub", "--suite", "stub", "--episodes", "2", "--out", str(out),
              *args],
    )
    assert result.exit_code == 0, result.output
    return result.output, load_report(out).attacks


def test_an_instruction_run_gets_the_benign_floor_and_the_controls_by_default(
    tmp_path: Path,
) -> None:
    """The default `--attacks instruction` now runs `none` first and the control family last."""
    output, arms = _run_attack(tmp_path)
    assert arms == ["none", *FAMILIES["instruction"], *FAMILIES["control"]]
    assert "--no-controls" in output  # the note names the opt-out
    for control in FAMILIES["control"]:
        assert control in output


def test_no_controls_runs_only_the_arms_named(tmp_path: Path) -> None:
    _output, arms = _run_attack(tmp_path, "--attacks", "instruction", "--no-controls")
    assert arms == FAMILIES["instruction"]


def test_a_run_without_an_instruction_channel_arm_is_unchanged(tmp_path: Path) -> None:
    output, arms = _run_attack(tmp_path, "--attacks", "visual")
    assert arms == FAMILIES["visual"]
    assert "--no-controls" not in output


def test_controls_already_named_are_not_added_twice(tmp_path: Path) -> None:
    _output, arms = _run_attack(tmp_path, "--attacks", "roleplay,none,benign_reword")
    rest = [c for c in FAMILIES["control"] if c != "benign_reword"]
    assert arms == ["roleplay", "none", "benign_reword", *rest]
    assert len(arms) == len(set(arms))


def test_a_recipe_with_an_instruction_family_gets_the_controls_too(tmp_path: Path) -> None:
    """`quick` names `none` and the instruction family; the default adds the control family."""
    _output, arms = _run_attack(tmp_path, "--recipe", "quick")
    assert arms == ["none", *FAMILIES["instruction"], *FAMILIES["control"]]


def test_the_adversarial_headline_does_not_move_with_the_controls(tmp_path: Path) -> None:
    """The canary: controls and the floor are excluded from the adversarial ASR by role."""
    with_controls = tmp_path / "with"
    without = tmp_path / "without"
    for out, extra in ((with_controls, []), (without, ["--no-controls"])):
        result = runner.invoke(
            app,
            ["attack", "--policy", "stub", "--suite", "stub", "--attacks",
             "instruction,visual,injection", "--episodes", "10", "--seed", "0", "--out", str(out),
             *extra],
        )
        assert result.exit_code == 0, result.output
    a, b = load_report(with_controls), load_report(without)
    assert a.adversarial_headline() == b.adversarial_headline()
    assert (a.adversarial_successes, a.adversarial_attempts) == (47, 70)
