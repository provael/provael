# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The stack a run measured on: versions in the manifest, and warnings before the run (P1.1).

A LIBERO number is a measurement of the simulator and policy stack as well as the policy. These
pin three things: the copy of the ``[lerobot]`` resolution the warnings compare against equals
``uv.lock`` (a wheel ships no lock, so the copy is what a container reads); the two warnings fire
exactly when they should and say why; and ``provael attack`` and ``provael doctor`` print them.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.runtime_versions import (
    LOCKED_LEROBOT_RESOLUTION,
    TRACKED_PACKAGES,
    drift_warnings,
    installed_versions,
    lock_drift,
    release_of,
)

ROOT = Path(__file__).resolve().parents[1]
LEROBOT_EXTRA_MARKER = "extra == 'extra-7-provael-lerobot'"

runner = CliRunner()


def _locked_lerobot_resolution() -> dict[str, str]:
    """Each tracked package's version in ``uv.lock`` as the ``[lerobot]`` extra resolves it.

    A package locked at one version has no resolution markers. One locked at several (numpy: the
    ``lerobot`` and ``openpi`` extras conflict) is read at the version whose markers name the
    ``lerobot`` extra.
    """
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions: dict[str, list[dict[str, object]]] = {}
    for package in lock["package"]:
        if package["name"] in TRACKED_PACKAGES:
            versions.setdefault(package["name"], []).append(package)
    out: dict[str, str] = {}
    for name, entries in versions.items():
        if len(entries) == 1:
            out[name] = str(entries[0]["version"])
            continue
        chosen = [
            e for e in entries
            if any(LEROBOT_EXTRA_MARKER in str(m) for m in e.get("resolution-markers", []))  # type: ignore[attr-defined]
        ]
        assert len(chosen) == 1, f"{name}: cannot tell which locked version [lerobot] resolves"
        out[name] = str(chosen[0]["version"])
    return out


def test_the_copied_resolution_equals_uv_lock() -> None:
    """The copy cannot drift from the file it copies: relock, and this fails until it is updated."""
    assert _locked_lerobot_resolution() == LOCKED_LEROBOT_RESOLUTION
    assert set(LOCKED_LEROBOT_RESOLUTION) == set(TRACKED_PACKAGES)


def test_release_of_reads_the_leading_release() -> None:
    assert release_of("3.4.0") == (3, 4, 0)
    assert release_of("3.8") == (3, 8, 0)
    assert release_of("2.10.0+cu128") == (2, 10, 0)
    assert release_of("not-a-version") is None


def test_installed_versions_reads_metadata_and_marks_absence_as_none() -> None:
    versions = installed_versions(("numpy", "no-such-distribution-provael-test"))
    assert versions["numpy"] is not None
    assert versions["no-such-distribution-provael-test"] is None


def test_mujoco_from_3_4_warns_on_libero_only() -> None:
    newer = {"mujoco": "3.4.0"}
    lines = drift_warnings(newer, suite="libero", uses_lerobot=False)
    assert len(lines) == 1 and "huggingface/lerobot#2354" in lines[0]
    assert "not measured here" in lines[0], "the cause is reported upstream, not measured by us"
    assert drift_warnings({"mujoco": "3.3.2"}, suite="libero", uses_lerobot=False) == []
    assert drift_warnings(newer, suite="stub", uses_lerobot=False) == []
    assert drift_warnings({"mujoco": None}, suite="libero", uses_lerobot=False) == []


def test_lock_drift_names_each_package_and_skips_what_is_not_installed() -> None:
    installed = dict(LOCKED_LEROBOT_RESOLUTION, torch="2.9.1", robosuite=None)
    installed["mujoco"] = "3.3.2"
    assert lock_drift(installed) == {
        "mujoco": ("3.3.2", LOCKED_LEROBOT_RESOLUTION["mujoco"]),
        "torch": ("2.9.1", LOCKED_LEROBOT_RESOLUTION["torch"]),
    }
    lines = drift_warnings(installed, suite="libero", uses_lerobot=True)
    assert len(lines) == 1
    assert "torch 2.9.1 (lock 2.10.0)" in lines[0] and "robosuite" not in lines[0]
    # A run that does not use the [lerobot] stack is not compared with its lock.
    assert drift_warnings(installed, suite="stub", uses_lerobot=False) == []


def test_the_locked_stack_itself_draws_the_mujoco_warning() -> None:
    """The lock resolves mujoco 3.8.1, past the 3.4.0 line, and the warning says so."""
    lines = drift_warnings(dict(LOCKED_LEROBOT_RESOLUTION), suite="libero", uses_lerobot=True)
    assert len(lines) == 1 and "past that line as well" in lines[0]


def _flat(text: str) -> str:
    """Console output with Rich's line wrapping undone, so a sentence can be searched for."""
    return " ".join(text.split())


def test_attack_prints_the_warnings_before_it_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Printed before the run, so a LIBERO run that fails later still showed what it ran on."""
    monkeypatch.setattr(
        "provael.cli.run.installed_versions",
        lambda: dict(LOCKED_LEROBOT_RESOLUTION, torch="2.9.1"),
    )
    result = runner.invoke(
        app, ["attack", "--policy", "stub", "--suite", "libero", "--attacks", "none",
              "--episodes", "1", "--out", str(tmp_path / "run")],
    )
    output = _flat(result.output)
    assert "huggingface/lerobot#2354" in output
    assert "torch 2.9.1 (lock 2.10.0)" in output
    assert "[lerobot] resolution in uv.lock" in output, "the bracketed name must survive"


def test_a_stub_run_draws_no_warning_and_its_manifest_records_the_versions(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    result = runner.invoke(
        app, ["attack", "--policy", "stub", "--suite", "stub", "--attacks", "none",
              "--episodes", "1", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "warning:" not in result.output
    manifest = json.loads((out / "execution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_schema_version"] == 4
    assert list(manifest["package_versions"]) == sorted(TRACKED_PACKAGES)
    assert manifest["package_versions"] == installed_versions()
    assert "package_versions" not in manifest["missing_fields"]


def test_doctor_lists_the_stack_beside_the_lock() -> None:
    result = runner.invoke(app, ["doctor", "--offline"])
    assert result.exit_code == 0, result.output
    output = _flat(result.output)
    assert "simulator and policy stack" in output
    assert "[lerobot] lock" in output, "the bracketed name must survive Rich's markup"
    for name in TRACKED_PACKAGES:
        assert name in output
