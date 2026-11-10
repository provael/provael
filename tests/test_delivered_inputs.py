# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Delivered-input audit (P1.8): what the policy was handed, and every declared setting was read.

A configuration that never reaches the code that reads it changes nothing while the report says
it was in force (GR00T#745), and a perturbation that was configured is not one that was delivered.
Each episode records a sha256 per distinct instruction handed to the policy, a rolling sha256 over
the camera images handed to it, and its attack's declared parameters as read; the runner fails a
run in which a declared parameter went unread. The benign arm takes the same path with an empty
spec (the proposal on IsaacLab#7451), so its record is the reference an attacked twin's is read
against.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

import provael.runner as runner_mod
from provael.attacks.base import Attack
from provael.attacks.registry import ATTACKS, make_attack
from provael.config import RunConfig
from provael.delivery import jsonable
from provael.policies.stub import StubPolicy
from provael.runner import UnreadParameterError, run, run_episode
from provael.suites.stub import BASE_INSTRUCTION, StubSuite
from provael.types import IMAGE_KEY, Observation


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stub_policy() -> StubPolicy:
    policy = StubPolicy()
    policy.load()
    return policy


# --------------------------------------------------------------------------- #
# the benign arm: the same path, an empty spec
# --------------------------------------------------------------------------- #


def test_the_benign_arm_records_the_base_instruction_and_no_parameters() -> None:
    report = run(RunConfig(attacks=["none", "benign_reword", "roleplay"], episodes=2))
    by_arm = {}
    for result in report.results:
        assert result.delivered_inputs is not None
        by_arm.setdefault(result.attack, []).append(result.delivered_inputs)
    for delivered in by_arm["none"]:
        assert delivered.instruction_sha256 == [_sha(BASE_INSTRUCTION)]
        assert delivered.parameters == {}
        assert delivered.image_sha256 is None and delivered.image_steps == 0  # no stub camera
    for delivered in by_arm["benign_reword"]:
        assert delivered.parameters == {}, "a control declares nothing; its reword is code"
        assert delivered.instruction_sha256 != [_sha(BASE_INSTRUCTION)]
    for delivered in by_arm["roleplay"]:
        assert delivered.parameters == {"target_object": "knife"}


class _CameraStub(StubSuite):
    """The stub with a camera: a deterministic frame per step, under ``observation['image']``."""

    def _observation(self) -> Observation:
        obs = super()._observation()
        frame = np.full((8, 8, 3), (self._step * 17 + self._seed) % 256, dtype=np.uint8)
        obs[IMAGE_KEY] = frame
        return obs


def _rolling(frames: list[npt.NDArray[np.uint8]]) -> str:
    digest = hashlib.sha256()
    for step, frame in enumerate(frames, start=1):
        digest.update(f"{step}\0{frame.dtype.str}\0{frame.shape}\0".encode() + frame.tobytes())
    return digest.hexdigest()


def test_the_benign_arm_hands_the_suite_s_own_frames_and_a_patch_does_not() -> None:
    horizon = 4
    policy = _stub_policy()
    benign = run_episode(policy, _CameraStub(), make_attack("none"), "reach", 3, horizon)
    reword = run_episode(policy, _CameraStub(), make_attack("benign_reword"), "reach", 3, horizon)
    patched = run_episode(policy, _CameraStub(), make_attack("patch"), "reach", 3, horizon)
    assert benign.delivered_inputs is not None
    assert reword.delivered_inputs is not None and patched.delivered_inputs is not None
    # The suite's own frames, independently: step t shows (17 t + seed) % 256 everywhere.
    frames = [
        np.full((8, 8, 3), (step * 17 + 3) % 256, dtype=np.uint8) for step in range(horizon)
    ][: benign.steps]
    assert benign.delivered_inputs.image_sha256 == _rolling(frames)
    assert benign.delivered_inputs.image_steps == benign.steps
    # An instruction-only control hands the same frames; the patch hands different ones.
    if reword.steps == benign.steps:
        assert reword.delivered_inputs.image_sha256 == benign.delivered_inputs.image_sha256
    assert patched.delivered_inputs.image_sha256 != benign.delivered_inputs.image_sha256
    assert patched.delivered_inputs.parameters == {"target_object": "knife"}


def test_the_defended_instruction_is_the_one_recorded() -> None:
    """The digest is taken after the defense, at the policy's input."""
    report = run(RunConfig(attacks=["roleplay"], episodes=1, defense="instruction_canonicalization"))
    (result,) = report.results
    assert result.delivered_inputs is not None
    assert result.delivered_inputs.instruction_sha256 == [_sha(result.adversarial_instruction)]


# --------------------------------------------------------------------------- #
# a declared parameter that was never read fails the run
# --------------------------------------------------------------------------- #


class _Configured(Attack):
    """An attack with a setting it may or may not read."""

    name = "configured"
    family = "instruction"
    parameters = ("intensity",)

    def __init__(self, *, reads: bool) -> None:
        self.intensity = 3
        self.reads = reads

    def perturb(self, instruction: str, observation: Observation) -> tuple[str, Observation]:
        if self.reads:
            return f"{instruction} x{self.intensity}", observation
        return instruction, observation


def _run_with(monkeypatch: pytest.MonkeyPatch, attack: Attack, **config: Any) -> Any:
    monkeypatch.setattr(runner_mod, "resolve_attacks", lambda _names: [attack])
    return run(RunConfig(attacks=["configured"], episodes=2, **config))


def test_an_unread_parameter_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(UnreadParameterError, match=r"\['intensity'\]"):
        _run_with(monkeypatch, _Configured(reads=False))


def test_a_read_parameter_is_recorded_as_it_was_read(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _run_with(monkeypatch, _Configured(reads=True))
    assert all(r.delivered_inputs.parameters == {"intensity": 3} for r in report.results)


def test_a_reused_search_counts_the_settings_it_was_found_under() -> None:
    """targeted_hijack searches once per (task, seed); the repeat at a seed reuses the result."""
    report = run(RunConfig(attacks=["targeted_hijack"], episodes=2, episodes_per_seed=2))
    first, repeat = (r.delivered_inputs for r in report.results)
    assert first is not None and repeat is not None
    assert first.parameters == repeat.parameters
    assert set(first.parameters) == {"target", "query_budget", "max_magnitude"}


def test_a_weight_attack_records_the_budget_its_corruption_used() -> None:
    report = run(RunConfig(attacks=["weight_bitflip_random_k1"], episodes=2))
    for result in report.results:
        assert result.applicable and result.delivered_inputs is not None
        assert result.delivered_inputs.parameters == {"flips": 1, "seed": 0}


def test_a_not_applicable_episode_records_nothing_delivered() -> None:
    result = run_episode(_stub_policy(), StubSuite(), make_attack("patch_hijack"), "reach", 0, 3)
    assert not result.applicable and result.delivered_inputs is None


# --------------------------------------------------------------------------- #
# the registry: every declaration names a real, recordable setting
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", sorted(ATTACKS))
def test_every_declared_parameter_is_a_recordable_attribute(name: str) -> None:
    attack = make_attack(name)
    for parameter in type(attack).parameters:
        assert hasattr(attack, parameter), f"{name} declares {parameter!r}, which it lacks"
        jsonable(getattr(attack, parameter))


def test_randomness_stays_local_and_seeded() -> None:
    """Two runs, interleaved with other draws on the global generators, record one thing."""
    import random

    config = RunConfig(attacks=["paraphrase", "scrambled_text", "targeted_hijack"], episodes=3)
    first = run(config)
    random.random(), np.random.random()
    second = run(config)
    assert [r.delivered_inputs for r in first.results] == [
        r.delivered_inputs for r in second.results
    ]


def test_jsonable_refuses_what_it_cannot_record_stably() -> None:
    assert jsonable((1.5, "a", None)) == [1.5, "a", None]
    assert jsonable(np.float32(0.5)) == 0.5
    assert jsonable({"b": 1, "a": (2,)}) == {"a": [2], "b": 1}
    assert set(jsonable(np.zeros((2, 2), dtype=np.uint8))) == {"sha256", "dtype", "shape"}
    with pytest.raises(TypeError, match="recordable"):
        jsonable(object())


def test_provael_attack_refuses_and_writes_no_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from typer.testing import CliRunner

    from provael.cli import app

    monkeypatch.setattr(runner_mod, "resolve_attacks", lambda _names: [_Configured(reads=False)])
    result = CliRunner().invoke(
        app, ["attack", "--attacks", "none", "--episodes", "1", "--out", str(tmp_path / "run")]
    )
    assert result.exit_code != 0
    assert "never read" in " ".join(result.output.split())
    assert not (tmp_path / "run" / "report.json").exists()
