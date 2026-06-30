"""Reproductions: registry resolution, valid attack mappings, and CLI (banner + honesty note)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from provael.attacks.registry import available_attacks, available_families, resolve_attacks
from provael.cli import app
from provael.reproductions import available_reproductions, get_reproduction

runner = CliRunner()


def test_all_reproductions_map_to_valid_attacks() -> None:
    valid = set(available_attacks()) | set(available_families())
    for name in available_reproductions():
        repro = get_reproduction(name)
        assert repro.attacks, f"{name} has no attacks"
        assert set(repro.attacks) <= valid, f"{name} maps to unknown attacks"
        # Every mapping resolves to at least one concrete attack.
        assert resolve_attacks(repro.attacks)
        assert repro.arxiv.startswith("arXiv:")
        assert repro.eai.startswith("EAI")


def test_get_reproduction_resolves_alias_and_rejects_unknown() -> None:
    assert get_reproduction("openvla_patch").name == "openvla-patch"  # alias
    with pytest.raises(KeyError):
        get_reproduction("nope")


def test_list_reproductions_cli() -> None:
    result = runner.invoke(app, ["list-reproductions"])
    assert result.exit_code == 0
    for name in available_reproductions():
        assert name in result.output


def test_reproduce_runs_on_stub_with_honesty_note() -> None:
    result = runner.invoke(app, ["reproduce", "freezevla", "--out", "/tmp/provael_test_repro"])
    assert result.exit_code == 0
    assert "arXiv:2509.19870" in result.output  # the paper is cited
    assert "paper reported (cited, NOT Provael's)" in result.output  # kept separate
    assert "properties of the deterministic test fixture" in result.output  # honesty note on stub


def test_reproduce_unknown_fails_cleanly() -> None:
    result = runner.invoke(app, ["reproduce", "nope", "--out", "/tmp/provael_test_repro2"])
    assert result.exit_code != 0
    assert "unknown reproduction" in result.output
