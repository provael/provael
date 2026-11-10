# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The adapter preflights refuse what they exist to refuse, and pass what they should.

Two halves, as in ``test_lerobot_adapter.py``:

* CPU tests (run anywhere): every check against fakes shaped like the objects lerobot 0.5.1 builds,
  a failing case for each, and the ``--preflight`` flag through the CLI.
* GATED tests (skipped unless ``PROVAEL_INTEGRATION=1`` and ``lerobot`` is importable): the same
  checks against the real ``HuggingFaceVLA/smolvla_libero`` checkpoint and the LIBERO simulator,
  including a doctored failing case for each. Enable on a provisioned box::

      pip install 'provael[lerobot]' 'lerobot[libero]==0.5.1'
      PROVAEL_INTEGRATION=1 pytest tests/test_preflight.py -q
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.policies import preflight
from provael.policies.lerobot_adapter import IncompatiblePolicyError, MissingLeRobotError
from provael.policies.preflight import (
    CHECK_FRAME,
    CHECK_GRIPPER,
    CHECK_IMAGE,
    CHECK_NORMALISER,
    CHECK_RENAME,
    CHECK_SOURCE,
    CHECK_WEIGHTS,
    NOT_APPLICABLE,
    PASSED,
    WEIGHT_CANARIES,
    PreflightError,
    WeightCanary,
)
from provael.policies.registry import MEASURED_POLICIES, make_policy
from provael.scoring.action_schema import SEVEN_DOF_DELTA_SCHEMA, ActionSchema
from provael.suites.libero import LIBERO_GRIPPER_RANGE, _ensure_libero_initialized
from provael.types import SuiteFeatures

_LEROBOT_AVAILABLE = importlib.util.find_spec("lerobot") is not None
_INTEGRATION_ENABLED = os.environ.get("PROVAEL_INTEGRATION") == "1"
_GATED = pytest.mark.skipif(
    not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE),
    reason="requires PROVAEL_INTEGRATION=1 and an installed lerobot (see module docstring)",
)
_LIBERO_CKPT = os.environ.get("PROVAEL_SMOLVLA_LIBERO_CKPT", "HuggingFaceVLA/smolvla_libero")
_LIBERO = SuiteFeatures(action_dim=7, task_suite="libero_object", image_key="image")
_GRIPPER = SEVEN_DOF_DELTA_SCHEMA.gripper_indices[0]


# --------------------------------------------------------------------------------------------- #
# fakes shaped like lerobot 0.5.1's objects
# --------------------------------------------------------------------------------------------- #


def _feature(kind: str, *shape: int) -> SimpleNamespace:
    return SimpleNamespace(type=kind, shape=shape)


#: The input features HuggingFaceVLA/smolvla_libero's config.json declares (read 10 Nov 2026).
_SMOLVLA_INPUTS = {
    "observation.images.image": _feature("VISUAL", 3, 4, 4),
    "observation.images.image2": _feature("VISUAL", 3, 4, 4),
    "observation.state": _feature("STATE", 8),
}
_NORM_MAP = {"VISUAL": "IDENTITY", "STATE": "MEAN_STD", "ACTION": "MEAN_STD"}


class NormalizerProcessorStep:
    """A fake with lerobot 0.5.1's public surface: ``get_config()`` and a flat ``state_dict()``."""

    def __init__(
        self,
        features: dict[str, SimpleNamespace],
        norm_map: dict[str, str],
        stats: dict[str, dict[str, Any]],
        only: set[str] | None = None,
    ) -> None:
        self.features, self.norm_map, self.stats, self.only = features, norm_map, stats, only

    def get_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "eps": 1e-8,
            "features": {k: {"type": f.type, "shape": list(f.shape)} for k, f in self.features.items()},
            "norm_map": dict(self.norm_map),
        }
        if self.only is not None:
            config["normalize_observation_keys"] = sorted(self.only)
        return config

    def state_dict(self) -> dict[str, Any]:
        return {f"{k}.{s}": np.asarray(v) for k, sub in self.stats.items() for s, v in sub.items()}


class UnnormalizerProcessorStep(NormalizerProcessorStep):
    pass


class RenameObservationsProcessorStep:
    def get_config(self) -> dict[str, Any]:
        return {"rename_map": {}}


class _Pipeline:
    """A processor pipeline: ``steps`` to read, and a call that hands the batch on unchanged."""

    def __init__(self, *steps: object) -> None:
        self.steps = list(steps)

    def __call__(self, batch: dict[str, Any]) -> dict[str, Any]:
        return dict(batch)


def _pipeline(*steps: object) -> _Pipeline:
    return _Pipeline(*steps)


#: The gripper channel's statistics in HuggingFaceVLA/smolvla_libero (revision 6721902) and
#: lerobot/pi05_libero_finetuned_v044 (7152f13), read from their unnormaliser files on 10 Nov 2026.
_GRIPPER_MEAN, _GRIPPER_STD = -0.0496407226, 0.9987671375


def _action_stats(**extra: list[float]) -> dict[str, Any]:
    mean = [0.06, 0.09, -0.09, 0.0, 0.0, 0.0, _GRIPPER_MEAN]
    std = [0.34, 0.38, 0.44, 0.04, 0.06, 0.08, _GRIPPER_STD]
    return {"mean": mean, "std": std, **extra}


def _processors(
    pre_stats: dict[str, dict[str, Any]] | None = None,
    post_stats: dict[str, dict[str, Any]] | None = None,
    pre_features: dict[str, SimpleNamespace] | None = None,
) -> tuple[_Pipeline, _Pipeline]:
    state = {"observation.state": {"mean": [0.0] * 8, "std": [1.0] * 8}}
    pre = _pipeline(
        RenameObservationsProcessorStep(),
        NormalizerProcessorStep(
            _SMOLVLA_INPUTS if pre_features is None else pre_features,
            _NORM_MAP,
            {**state, "action": _action_stats()} if pre_stats is None else pre_stats,
        ),
    )
    post = _pipeline(
        UnnormalizerProcessorStep(
            {"action": _feature("ACTION", 7)},
            _NORM_MAP,
            {"action": _action_stats()} if post_stats is None else post_stats,
        )
    )
    return pre, post


def _trained_linear(rng: np.random.Generator, out: int, fan_in: int) -> np.ndarray:
    """A weight that has left the default init's range, as the measured checkpoints' head has."""
    return rng.normal(0.0, 2.0 / np.sqrt(fan_in), size=(out, fan_in))


def _fresh_linear(rng: np.random.Generator, out: int, fan_in: int) -> np.ndarray:
    """torch's nn.Linear.reset_parameters draw: U(-1/sqrt(fan_in), 1/sqrt(fan_in))."""
    bound = 1.0 / np.sqrt(fan_in)
    return rng.uniform(-bound, bound, size=(out, fan_in))


class _FakePolicy:
    """Answers ``get_parameter`` from a dict and reads the probe's images like a VLA would."""

    def __init__(self, params: dict[str, np.ndarray], *, reads_image: bool = True) -> None:
        self.params = params
        self.reads_image = reads_image
        self.config = SimpleNamespace(input_features=_SMOLVLA_INPUTS)
        self.resets = 0
        self.batches: list[dict[str, Any]] = []

    def get_parameter(self, name: str) -> np.ndarray:
        if name not in self.params:
            raise AttributeError(f"{type(self).__name__} has no parameter {name}")
        return self.params[name]

    def reset(self) -> None:
        self.resets += 1

    def select_action(self, batch: dict[str, Any]) -> np.ndarray:
        self.batches.append(batch)
        image = float(np.mean(batch["observation.images.image"])) if self.reads_image else 0.0
        return np.array([[0.1 + 0.3 * image, -0.2, 0.0, 0.0, 0.0, 0.0, 1.0]])


class SmolVLAPolicy(_FakePolicy):
    """Named like lerobot's class, which is what WEIGHT_CANARIES is keyed by."""


class PI05Policy(_FakePolicy):
    pass


def _smolvla(rng: np.random.Generator, *, fresh: bool = False, reads_image: bool = True) -> Any:
    make = _fresh_linear if fresh else _trained_linear
    return SmolVLAPolicy(
        {
            "model.action_in_proj.weight": make(rng, 480, 32),
            "model.action_out_proj.weight": make(rng, 32, 480),
            "model.action_time_mlp_in.weight": make(rng, 480, 960),
        },
        reads_image=reads_image,
    )


class _FakeTorch:
    """The few torch calls the probe makes, on numpy, recording what it was asked."""

    float32 = np.float32

    def __init__(self) -> None:
        self.seeds: list[int] = []
        self.forks = 0
        self.random = SimpleNamespace(fork_rng=self._fork_rng)

    @contextlib.contextmanager
    def _fork_rng(self) -> Iterator[None]:
        self.forks += 1
        yield

    @contextlib.contextmanager
    def inference_mode(self) -> Iterator[None]:
        yield

    def manual_seed(self, seed: int) -> None:
        self.seeds.append(seed)

    def full(self, shape: tuple[int, ...], fill: float, dtype: Any) -> np.ndarray:
        return np.full(shape, fill, dtype=dtype)

    def zeros(self, shape: tuple[int, ...], dtype: Any) -> np.ndarray:
        return np.zeros(shape, dtype=dtype)


def _identity(batch: dict[str, Any]) -> dict[str, Any]:
    return dict(batch)


# --------------------------------------------------------------------------------------------- #
# 1. normaliser statistics
# --------------------------------------------------------------------------------------------- #


def test_normaliser_with_statistics_for_every_normalised_input_passes() -> None:
    pre, post = _processors()
    outcome = preflight.check_normaliser_statistics(pre, post, _SMOLVLA_INPUTS)
    assert outcome.status == PASSED and outcome.check == CHECK_NORMALISER


def test_normaliser_without_statistics_is_refused() -> None:
    # lerobot passes a key with no statistics on unchanged (_apply_transform), lerobot#4047.
    pre, post = _processors(pre_stats={})
    with pytest.raises(PreflightError, match=r"observation\.state \(STATE, MEAN_STD\) has no mean/std"):
        preflight.check_normaliser_statistics(pre, post, _SMOLVLA_INPUTS)


def test_a_normaliser_that_lists_no_features_is_refused_not_passed_vacuously() -> None:
    # lerobot/pi05_base's pre-processor: the normaliser lists no features and loads no stats file.
    pre, post = _processors(pre_stats={}, pre_features={})
    with pytest.raises(PreflightError, match="is not among the NormalizerProcessorStep's features"):
        preflight.check_normaliser_statistics(pre, post, _SMOLVLA_INPUTS)


def test_an_action_the_unnormaliser_has_no_statistics_for_is_refused() -> None:
    pre, post = _processors(post_stats={})
    with pytest.raises(PreflightError, match=r"action \(ACTION, MEAN_STD\) has no mean/std"):
        preflight.check_normaliser_statistics(pre, post, _SMOLVLA_INPUTS)


def test_a_missing_normaliser_step_could_not_be_verified() -> None:
    _pre, post = _processors()
    with pytest.raises(PreflightError, match="could not verify: .*no normaliser step"):
        preflight.check_normaliser_statistics(_pipeline(), post, _SMOLVLA_INPUTS)


def test_inputs_the_checkpoint_chose_not_to_normalise_are_not_refused() -> None:
    state = {"observation.state": {"mean": [0.0] * 8, "std": [1.0] * 8}}
    pre = _pipeline(NormalizerProcessorStep(_SMOLVLA_INPUTS, _NORM_MAP, {}, only=set()))
    post = _pipeline(UnnormalizerProcessorStep({}, _NORM_MAP, {"action": _action_stats(), **state}))
    assert preflight.check_normaliser_statistics(pre, post, _SMOLVLA_INPUTS).status == PASSED


def test_an_unknown_normalisation_mode_is_refused() -> None:
    pre = _pipeline(NormalizerProcessorStep(_SMOLVLA_INPUTS, {"STATE": "Z_SCORE"}, {}))
    _pre, post = _processors()
    with pytest.raises(PreflightError, match="'Z_SCORE'"):
        preflight.check_normaliser_statistics(pre, post, _SMOLVLA_INPUTS)


# --------------------------------------------------------------------------------------------- #
# 2. rename map
# --------------------------------------------------------------------------------------------- #

#: lerobot#4548's case: the stored map and the documented one swap two cameras.
_STORED = {
    "observation.images.left": "observation.images.camera1",
    "observation.images.right": "observation.images.camera2",
    "observation.images.eye_in_hand": "observation.images.camera3",
}
_SWAPPED = {
    "observation.images.left": "observation.images.camera1",
    "observation.images.eye_in_hand": "observation.images.camera2",
    "observation.images.right": "observation.images.camera3",
}


def _checkpoint_dir(tmp_path: Path, rename_map: dict[str, str] | None) -> Path:
    steps: list[dict[str, Any]] = [{"registry_name": "to_batch_processor", "config": {}}]
    if rename_map is not None:
        steps.insert(
            0, {"registry_name": "rename_observations_processor", "config": {"rename_map": rename_map}}
        )
    (tmp_path / "policy_preprocessor.json").write_text(
        json.dumps({"name": "policy_preprocessor", "steps": steps}), encoding="utf-8"
    )
    return tmp_path


def test_the_stored_rename_map_is_read_from_the_checkpoints_own_file(tmp_path: Path) -> None:
    assert preflight.embedded_rename_map(str(_checkpoint_dir(tmp_path, _STORED))) == _STORED


def test_a_checkpoint_without_a_rename_step_stores_an_empty_map(tmp_path: Path) -> None:
    assert preflight.embedded_rename_map(str(_checkpoint_dir(tmp_path, None))) == {}


def test_a_rename_map_that_swaps_two_cameras_is_refused() -> None:
    with pytest.raises(PreflightError, match="observation.images.eye_in_hand") as exc_info:
        preflight.check_rename_map(_SWAPPED, _STORED)
    assert "Drop --rename-map" in str(exc_info.value)


def test_a_rename_map_equal_to_the_stored_one_passes() -> None:
    assert preflight.check_rename_map(dict(_STORED), _STORED).status == PASSED


def test_no_rename_map_flag_needs_no_comparison() -> None:
    assert preflight.check_rename_map(None, _STORED).status == NOT_APPLICABLE


def test_a_rename_map_for_a_checkpoint_that_stores_none_passes() -> None:
    assert preflight.check_rename_map(_SWAPPED, {}).status == PASSED


def test_a_preprocessor_file_that_cannot_be_found_could_not_be_verified(tmp_path: Path) -> None:
    with pytest.raises(PreflightError, match="could not verify"):
        preflight.embedded_rename_map(str(tmp_path))


# --------------------------------------------------------------------------------------------- #
# 3. weights loaded
# --------------------------------------------------------------------------------------------- #


def test_trained_head_weights_pass() -> None:
    outcome = preflight.check_weights_loaded(_smolvla(np.random.default_rng(0)))
    assert outcome.status == PASSED and outcome.check == CHECK_WEIGHTS


def test_a_freshly_initialised_head_is_refused() -> None:
    # A swallowed load error returns the untrained model (lerobot#4577): every head weight is still
    # inside the default init's range, whatever the random draw was.
    with pytest.raises(PreflightError, match="looks freshly initialised"):
        preflight.check_weights_loaded(_smolvla(np.random.default_rng(1), fresh=True))


def test_one_untrained_canary_is_enough_to_refuse() -> None:
    policy = _smolvla(np.random.default_rng(2))
    policy.params["model.action_out_proj.weight"] = _fresh_linear(np.random.default_rng(3), 32, 480)
    with pytest.raises(PreflightError, match=r"action_out_proj\.weight: its largest \|weight\|"):
        preflight.check_weights_loaded(policy)


def test_a_zero_initialised_norm_left_at_zero_is_refused() -> None:
    rng = np.random.default_rng(4)
    params = {
        "model.action_out_proj.weight": _trained_linear(rng, 32, 1024),
        "model.paligemma_with_expert.gemma_expert.model.norm.dense.weight": np.zeros((12, 4)),
        "model.paligemma_with_expert.paligemma.model.language_model.norm.weight": rng.normal(
            0.0, 0.5, 2048
        ),
    }
    with pytest.raises(PreflightError, match=r"norm\.dense\.weight: every element is 0"):
        preflight.check_weights_loaded(PI05Policy(params))
    params["model.paligemma_with_expert.gemma_expert.model.norm.dense.weight"] = rng.normal(
        0.0, 0.01, (12, 4)
    )
    assert preflight.check_weights_loaded(PI05Policy(params)).status == PASSED


def test_a_class_with_no_declared_canaries_could_not_be_verified() -> None:
    class GrootPolicy(_FakePolicy):
        pass

    with pytest.raises(PreflightError, match="could not verify: no weights-loaded canaries"):
        preflight.check_weights_loaded(GrootPolicy({}))


def test_a_canary_the_model_does_not_have_could_not_be_verified() -> None:
    policy = _smolvla(np.random.default_rng(5))
    del policy.params["model.action_in_proj.weight"]
    with pytest.raises(PreflightError, match="could not verify: SmolVLAPolicy has no parameter"):
        preflight.check_weights_loaded(policy)


def test_the_canaries_cover_every_lerobot_class_provael_has_measured() -> None:
    # smolvla -> SmolVLAPolicy and pi05 -> PI05Policy are the measured backends; pi0 is provisioned.
    assert set(WEIGHT_CANARIES) == {"SmolVLAPolicy", "PI0Policy", "PI05Policy"}
    assert {"smolvla", "pi05"} <= set(MEASURED_POLICIES)
    for name, canaries in WEIGHT_CANARIES.items():
        assert len(canaries) == 3, name
        assert len({c.parameter for c in canaries}) == 3, name
        assert all(c.init in (preflight.CONSTANT, preflight.DEFAULT_LINEAR) for c in canaries)


def test_explicit_canaries_override_the_table() -> None:
    policy = _FakePolicy({"w": np.ones((2, 2))})
    with pytest.raises(PreflightError, match="every element is 1"):
        preflight.check_weights_loaded(policy, [WeightCanary("w", preflight.CONSTANT, 1.0)])


# --------------------------------------------------------------------------------------------- #
# 4. image sensitivity
# --------------------------------------------------------------------------------------------- #


def test_actions_that_move_with_the_image_pass() -> None:
    a = np.zeros((1, 7))
    assert preflight.check_image_sensitivity(a, a + 0.01).status == PASSED


def test_identical_actions_on_black_and_white_frames_are_refused() -> None:
    a = np.full((1, 7), 0.3)
    with pytest.raises(PreflightError, match="not reading the image"):
        preflight.check_image_sensitivity(a, a + 1e-6)


def test_a_non_finite_probe_action_is_refused() -> None:
    with pytest.raises(PreflightError, match="not reading the image"):
        preflight.check_image_sensitivity(np.zeros(7), np.full(7, np.nan))


def test_the_probe_feeds_black_then_white_frames_with_one_seed() -> None:
    torch = _FakeTorch()
    policy = _smolvla(np.random.default_rng(6))
    black, white = preflight.probe_image_sensitivity(policy, _identity, torch=torch)
    assert [float(np.max(b["observation.images.image"])) for b in policy.batches] == [0.0, 1.0]
    for batch in policy.batches:
        assert batch["observation.images.image"].shape == (1, 3, 4, 4)
        assert batch["observation.state"].shape == (1, 8) and not batch["observation.state"].any()
        assert batch["task"] == [preflight.PROBE_INSTRUCTION]
    assert torch.seeds == [preflight.PROBE_SEED] * 2 and torch.forks == 1
    assert policy.resets == 3  # before each pass, and after: no queued chunk survives the probe
    assert preflight.check_image_sensitivity(black, white).status == PASSED


def test_an_image_blind_policy_is_refused_through_the_probe() -> None:
    blind = _smolvla(np.random.default_rng(7), reads_image=False)
    black, white = preflight.probe_image_sensitivity(blind, _identity, torch=_FakeTorch())
    with pytest.raises(PreflightError, match=CHECK_IMAGE):
        preflight.check_image_sensitivity(black, white)


# --------------------------------------------------------------------------------------------- #
# 5. gripper convention
# --------------------------------------------------------------------------------------------- #


def _stats(**values: list[float]) -> dict[str, np.ndarray]:
    return {name: np.asarray(v, dtype=np.float64) for name, v in values.items()}


def _channel(value: float) -> list[float]:
    return [0.0] * _GRIPPER + [value]


def test_a_minus_one_to_one_gripper_from_min_max_passes() -> None:
    stats = _stats(min=_channel(-1.0), max=_channel(1.0))
    outcome = preflight.check_gripper_convention(stats, _GRIPPER, LIBERO_GRIPPER_RANGE)
    assert outcome.status == PASSED and outcome.check == CHECK_GRIPPER


def test_a_minus_one_to_one_gripper_from_mean_and_std_alone_passes() -> None:
    # HuggingFaceVLA/smolvla_libero stores only mean and std; a ±1 channel meets Bhatia-Davis.
    stats = _stats(mean=_channel(_GRIPPER_MEAN), std=_channel(_GRIPPER_STD))
    assert preflight.check_gripper_convention(stats, _GRIPPER, LIBERO_GRIPPER_RANGE).status == PASSED


def test_a_zero_to_one_gripper_from_min_max_is_refused() -> None:
    stats = _stats(min=_channel(0.0), max=_channel(1.0))
    with pytest.raises(PreflightError, match="runs from 0 to 1"):
        preflight.check_gripper_convention(stats, _GRIPPER, LIBERO_GRIPPER_RANGE)


def test_a_zero_to_one_gripper_from_mean_and_std_is_refused() -> None:
    stats = _stats(mean=_channel(0.5), std=_channel(0.5))
    with pytest.raises(PreflightError, match=r"fits a \[0, 1\] gripper"):
        preflight.check_gripper_convention(stats, _GRIPPER, LIBERO_GRIPPER_RANGE)


def test_a_gripper_outside_the_suites_range_is_refused() -> None:
    with pytest.raises(PreflightError, match="runs from -1 to 255"):
        preflight.check_gripper_convention(
            _stats(min=_channel(-1.0), max=_channel(255.0)), _GRIPPER, LIBERO_GRIPPER_RANGE
        )
    with pytest.raises(PreflightError, match=r"cannot lie in \[-1, 1\]"):
        preflight.check_gripper_convention(
            _stats(mean=_channel(0.0), std=_channel(2.0)), _GRIPPER, LIBERO_GRIPPER_RANGE
        )


def test_missing_gripper_statistics_could_not_be_verified() -> None:
    with pytest.raises(PreflightError, match="could not verify"):
        preflight.check_gripper_convention({}, _GRIPPER, LIBERO_GRIPPER_RANGE)
    # lerobot/smolvla_base's SO-100 action has six channels: there is no channel 6 to read.
    six = _stats(min=[-1.0] * 6, max=[1.0] * 6)
    with pytest.raises(PreflightError, match="could not verify"):
        preflight.check_gripper_convention(six, _GRIPPER, LIBERO_GRIPPER_RANGE)


def test_action_statistics_come_from_the_unnormaliser_first() -> None:
    pre, post = _processors(post_stats={"action": _action_stats(min=_channel(-1.0))})
    stats = preflight.action_statistics(post, pre)
    assert set(stats) == {"mean", "std", "min"}
    assert stats["mean"][_GRIPPER] == pytest.approx(_GRIPPER_MEAN)


# --------------------------------------------------------------------------------------------- #
# 6. frame consistency
# --------------------------------------------------------------------------------------------- #


class _FrameSuite:
    """A suite whose end-effector moves ``frame @ translation`` per step (world frame: identity)."""

    name = "fake-libero"

    def __init__(
        self,
        frame: np.ndarray | None = None,
        *,
        schema: ActionSchema | None = SEVEN_DOF_DELTA_SCHEMA,
        report_pose: bool = True,
        done_after: int | None = None,
    ) -> None:
        self.frame = np.eye(3) if frame is None else frame
        self.schema = schema
        self.report_pose = report_pose
        self.done_after = done_after
        self.pose = np.zeros(3)
        self.actions: list[np.ndarray] = []

    def action_schema(self) -> ActionSchema | None:
        return self.schema

    def reset(self, task: str, seed: int) -> dict[str, Any]:
        self.pose = np.array([0.1, -0.2, 1.0])
        return {"task": task, "ee_pos": list(self.pose) if self.report_pose else None}

    def step(self, action: np.ndarray) -> tuple[dict[str, Any], bool, dict[str, Any]]:
        self.actions.append(np.asarray(action))
        self.pose = self.pose + 0.02 * (self.frame @ np.asarray(action[:3], dtype=np.float64))
        done = self.done_after is not None and len(self.actions) >= self.done_after
        return {}, done, {"ee_pos": list(self.pose)}


def test_a_world_frame_delta_moves_the_end_effector_along_x() -> None:
    suite = _FrameSuite()
    outcome = preflight.check_frame_consistency(suite, "libero_object/0", 0)
    assert outcome.status == PASSED and outcome.check == CHECK_FRAME
    assert len(suite.actions) == preflight.FRAME_STEPS
    first = suite.actions[0]
    assert first[0] == preflight.FRAME_COMMAND and not first[1:6].any()
    assert first[_GRIPPER] == preflight.FRAME_GRIPPER_HOLD  # LIBERO's no-op keeps the gripper open


def test_a_delta_applied_in_another_frame_is_refused() -> None:
    # A +x command that the simulator turns into +y: the end-effector-frame reading of robosuite#819.
    quarter_turn = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    with pytest.raises(PreflightError, match="cosine of 0.000 to"):
        preflight.check_frame_consistency(_FrameSuite(quarter_turn), "t", 0)


def test_a_delta_that_moves_nothing_is_refused() -> None:
    with pytest.raises(PreflightError, match="under the 0.005 m it must travel"):
        preflight.check_frame_consistency(_FrameSuite(np.zeros((3, 3))), "t", 0)


def test_the_probe_stops_at_a_terminal_step() -> None:
    suite = _FrameSuite(done_after=2)
    preflight.check_frame_consistency(suite, "t", 0)
    assert len(suite.actions) == 2  # later poses would be the next episode's


def test_a_suite_without_a_pose_or_a_layout_could_not_be_verified() -> None:
    with pytest.raises(PreflightError, match="reports no end-effector position"):
        preflight.check_frame_consistency(_FrameSuite(report_pose=False), "t", 0)
    with pytest.raises(PreflightError, match="declares no translation channels"):
        preflight.check_frame_consistency(_FrameSuite(schema=None), "t", 0)


def test_the_frame_preflight_refuses_the_stub_suite_which_reports_no_pose() -> None:
    with pytest.raises(PreflightError, match="suite 'stub' reports no end-effector position"):
        preflight.run_frame_preflight("stub", None, 0)


def test_attack_preflight_flag_refuses_before_the_run(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = CliRunner().invoke(
        app, ["attack", "--suite", "stub", "--preflight", "--out", str(out)],
        env={"COLUMNS": "200"},
    )
    assert result.exit_code == 2
    assert CHECK_FRAME in " ".join(result.output.split())
    assert not (out / "report.json").exists()  # refused before anything ran


def test_attack_without_the_flag_runs_no_frame_preflight(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = CliRunner().invoke(app, ["attack", "--suite", "stub", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "report.json").exists()


# --------------------------------------------------------------------------------------------- #
# 7. the LIBERO simulator missing
# --------------------------------------------------------------------------------------------- #


def _without_libero(monkeypatch: pytest.MonkeyPatch) -> None:
    real = importlib.util.find_spec

    def find_spec(name: str, *args: Any, **kwargs: Any) -> Any:
        return None if name == "libero" else real(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)


def test_a_missing_libero_simulator_is_refused_naming_the_platform_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _without_libero(monkeypatch)
    # A config left behind by an earlier install must not hide the missing package.
    monkeypatch.setenv("LIBERO_CONFIG_PATH", str(tmp_path))
    (tmp_path / "config.yaml").write_text("benchmark_root: x\n", encoding="utf-8")
    with pytest.raises(MissingLeRobotError) as exc_info:
        _ensure_libero_initialized()
    message = str(exc_info.value)
    assert "sys_platform == 'linux'" in message
    assert "https://github.com/huggingface/LIBERO" in message


def test_an_installed_libero_with_a_config_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: object() if name == "libero" else real(name, *a, **k),
    )
    monkeypatch.setenv("LIBERO_CONFIG_PATH", str(tmp_path))
    (tmp_path / "config.yaml").write_text("benchmark_root: x\n", encoding="utf-8")
    assert _ensure_libero_initialized() is None


# --------------------------------------------------------------------------------------------- #
# 8. an untuned base checkpoint on LIBERO
# --------------------------------------------------------------------------------------------- #


def test_the_pi05_base_checkpoint_is_refused_on_libero_naming_the_fine_tune() -> None:
    with pytest.raises(PreflightError, match="lerobot/pi05_libero_finetuned_v044"):
        preflight.refuse_untuned_base_checkpoint("lerobot/pi05_base", _LIBERO)


def test_the_registry_default_for_pi05_is_the_refused_base() -> None:
    adapter = make_policy("pi05")
    assert getattr(adapter, "model_id", None) == "lerobot/pi05_base"
    assert adapter.model_id in preflight.LIBERO_UNTUNED_BASE_CHECKPOINTS  # type: ignore[attr-defined]


def test_the_base_checkpoint_is_not_refused_off_libero_or_when_tuned() -> None:
    other = SuiteFeatures(action_dim=7, task_suite="not_libero")
    preflight.refuse_untuned_base_checkpoint("lerobot/pi05_base", other)
    preflight.refuse_untuned_base_checkpoint("lerobot/pi05_base", None)
    preflight.refuse_untuned_base_checkpoint("lerobot/pi05_libero_finetuned_v044", _LIBERO)


def test_a_preflight_refusal_is_an_incompatible_policy_error() -> None:
    # Every command that reports an unloadable checkpoint as one clean line reports this one too.
    assert issubclass(PreflightError, IncompatiblePolicyError)


# --------------------------------------------------------------------------------------------- #
# 9. loaded_checkpoint_source
# --------------------------------------------------------------------------------------------- #


def test_no_loaded_checkpoint_source_is_not_applicable() -> None:
    outcome = preflight.check_loaded_checkpoint_source(_FakePolicy({}), "org/ckpt")
    assert outcome.status == NOT_APPLICABLE and outcome.check == CHECK_SOURCE


def test_a_source_naming_the_requested_checkpoint_passes() -> None:
    policy = _FakePolicy({})
    # The shape lerobot PR 4712 sets on GrootPolicy.
    policy.loaded_checkpoint_source = {  # type: ignore[attr-defined]
        "is_finetuned_checkpoint": True, "repo_id": "org/ckpt", "revision": None,
    }
    outcome = preflight.check_loaded_checkpoint_source(policy, "org/ckpt")
    assert outcome.status == PASSED and "is_finetuned_checkpoint=True" in outcome.detail


def test_a_source_naming_another_checkpoint_is_refused() -> None:
    policy = _FakePolicy({})
    policy.loaded_checkpoint_source = {"repo_id": "org/base", "is_finetuned_checkpoint": False}  # type: ignore[attr-defined]
    with pytest.raises(PreflightError, match="loaded 'org/base', not the requested 'org/ckpt'"):
        preflight.check_loaded_checkpoint_source(policy, "org/ckpt")


def test_a_source_of_an_unknown_shape_could_not_be_verified() -> None:
    policy = _FakePolicy({})
    for odd in ("org/ckpt", {"revision": "abc"}):
        policy.loaded_checkpoint_source = odd  # type: ignore[attr-defined]
        with pytest.raises(PreflightError, match="could not verify"):
            preflight.check_loaded_checkpoint_source(policy, "org/ckpt")


# --------------------------------------------------------------------------------------------- #
# the load-time sequence
# --------------------------------------------------------------------------------------------- #


def test_the_load_preflight_runs_every_policy_check_in_order() -> None:
    pre, post = _processors()
    outcomes = preflight.check_lerobot_policy(
        _smolvla(np.random.default_rng(8)), pre, post,
        model_id="HuggingFaceVLA/smolvla_libero", rename_map=None, features=_LIBERO,
        torch=_FakeTorch(),
    )
    assert [o.check for o in outcomes] == [
        CHECK_SOURCE, CHECK_NORMALISER, CHECK_RENAME, CHECK_WEIGHTS, CHECK_GRIPPER, CHECK_IMAGE,
    ]
    assert [o.status for o in outcomes] == [
        NOT_APPLICABLE, PASSED, NOT_APPLICABLE, PASSED, PASSED, PASSED,
    ]


def test_the_gripper_check_only_runs_on_libero() -> None:
    pre, post = _processors(post_stats={"action": _action_stats(min=_channel(0.0), max=_channel(1.0))})
    outcomes = preflight.check_lerobot_policy(
        _smolvla(np.random.default_rng(9)), pre, post,
        model_id="x/y", rename_map=None, features=None, torch=_FakeTorch(),
    )
    gripper = next(o for o in outcomes if o.check == CHECK_GRIPPER)
    assert gripper.status == NOT_APPLICABLE
    with pytest.raises(PreflightError, match=CHECK_GRIPPER):
        preflight.check_lerobot_policy(
            _smolvla(np.random.default_rng(9)), pre, post,
            model_id="x/y", rename_map=None, features=_LIBERO, torch=_FakeTorch(),
        )


def test_the_load_preflight_refuses_a_swapped_rename_map_from_the_checkpoint_dir(
    tmp_path: Path,
) -> None:
    pre, post = _processors()
    with pytest.raises(PreflightError, match=CHECK_RENAME):
        preflight.check_lerobot_policy(
            _smolvla(np.random.default_rng(10)), pre, post,
            model_id=str(_checkpoint_dir(tmp_path, _STORED)), rename_map=_SWAPPED,
            features=_LIBERO, torch=_FakeTorch(),
        )


def test_a_probe_that_cannot_run_could_not_be_verified() -> None:
    def select_action(self: Any, batch: dict[str, Any]) -> np.ndarray:
        raise KeyError("observation.language.tokens")

    # Same class name, so the weights check (which runs first) reads its canaries and passes.
    broken_cls = type("SmolVLAPolicy", (SmolVLAPolicy,), {"select_action": select_action})
    pre, post = _processors()
    broken = broken_cls(_smolvla(np.random.default_rng(11)).params)
    with pytest.raises(PreflightError, match="could not verify: the probe's forward pass failed"):
        preflight.check_lerobot_policy(
            broken, pre, post, model_id="x/y", rename_map=None, features=None, torch=_FakeTorch()
        )


# --------------------------------------------------------------------------------------------- #
# GATED: the real checkpoint and simulator (PROVAEL_INTEGRATION=1)
# --------------------------------------------------------------------------------------------- #


def _loaded_smolvla() -> Any:
    from lerobot.envs.factory import make_env_config

    from provael.policies.lerobot_adapter import LeRobotAdapter

    cfg = make_env_config("libero", task="libero_object", task_ids=[0], obs_type="pixels_agent_pos")
    adapter = LeRobotAdapter(model_id=_LIBERO_CKPT, device=os.environ.get("PROVAEL_DEVICE", "cpu"))
    adapter.set_features(
        SuiteFeatures(action_dim=7, env_config=cfg, image_key="image", task_suite="libero_object")
    )
    adapter.load()
    return adapter


@_GATED
def test_real_smolvla_libero_passes_every_load_preflight() -> None:
    adapter = _loaded_smolvla()
    statuses = {o.check: o.status for o in adapter.preflight_outcomes}
    assert statuses == {
        CHECK_SOURCE: NOT_APPLICABLE,  # lerobot 0.5.1 sets loaded_checkpoint_source on no policy
        CHECK_NORMALISER: PASSED,
        CHECK_RENAME: NOT_APPLICABLE,
        CHECK_WEIGHTS: PASSED,
        CHECK_GRIPPER: PASSED,
        CHECK_IMAGE: PASSED,
    }


@_GATED
def test_real_doctored_policies_are_refused() -> None:
    import torch
    from lerobot.processor.normalize_processor import hotswap_stats

    adapter = _loaded_smolvla()
    policy, pre, post = adapter._policy, adapter._preprocess, adapter._postprocess
    features = policy.config.input_features
    # 1: the same pre-processor with its statistics removed (hotswap_stats copies the pipeline)
    with pytest.raises(PreflightError, match=CHECK_NORMALISER):
        preflight.check_normaliser_statistics(hotswap_stats(pre, {}), post, features)
    # 5: the same unnormaliser with a [0, 1] gripper's statistics
    zero_one = {"action": {"min": np.zeros(7), "max": np.ones(7)}}
    with pytest.raises(PreflightError, match=CHECK_GRIPPER):
        preflight.check_gripper_convention(
            preflight.action_statistics(hotswap_stats(post, zero_one)), _GRIPPER, LIBERO_GRIPPER_RANGE
        )

    # 4: a pre-processor that blacks out every camera, so both probe passes see the same frame
    def blind(batch: dict[str, Any]) -> Any:
        return pre({k: (v * 0 if k.startswith("observation.images") else v) for k, v in batch.items()})

    black, white = preflight.probe_image_sensitivity(policy, blind, torch=torch)
    with pytest.raises(PreflightError, match=CHECK_IMAGE):
        preflight.check_image_sensitivity(black, white)
    # 3: the head re-initialised as a swallowed load error would leave it (last: it is destructive)
    for name in ("action_in_proj", "action_out_proj", "action_time_mlp_in"):
        getattr(policy.model, name).reset_parameters()
    with pytest.raises(PreflightError, match=CHECK_WEIGHTS):
        preflight.check_weights_loaded(policy)


@_GATED
def test_real_rename_map_is_read_from_the_cached_preprocessor() -> None:
    _loaded_smolvla()  # puts the checkpoint's policy_preprocessor.json in the cache
    assert preflight.embedded_rename_map(_LIBERO_CKPT) == {}  # this checkpoint stores no map


@_GATED
def test_real_pi05_base_is_refused_on_libero() -> None:
    from provael.policies.lerobot_adapter import LeRobotAdapter

    adapter = LeRobotAdapter(model_id="lerobot/pi05_base", name="pi05", device="cpu")
    adapter.set_features(_LIBERO)
    with pytest.raises(IncompatiblePolicyError) as exc_info:
        adapter.load()
    if isinstance(exc_info.value, PreflightError):
        assert "lerobot/pi05_libero_finetuned_v044" in str(exc_info.value)


def _libero_suite() -> Any:
    from provael.suites.libero import LiberoSuiteAdapter

    suite = LiberoSuiteAdapter(task_suite="libero_object", task_ids=(0,))
    try:
        suite.reset("libero_object/0", seed=0)
    except (MissingLeRobotError, ModuleNotFoundError, ImportError) as exc:
        pytest.skip(f"LIBERO simulator not installed: {exc}")
    return suite


@_GATED
def test_real_libero_installed_initialises_without_raising() -> None:
    _libero_suite()
    assert _ensure_libero_initialized() is None


@_GATED
def test_real_libero_moves_the_end_effector_along_a_commanded_x() -> None:
    outcome = preflight.check_frame_consistency(_libero_suite(), "libero_object/0", 0)
    assert outcome.status == PASSED


@_GATED
def test_real_libero_with_swapped_translation_channels_is_refused() -> None:
    suite = _libero_suite()
    real_step = suite.step

    def swapped(action: Any) -> Any:  # a +x command delivered as +y: another frame
        arr = np.asarray(action, dtype=np.float32).copy()
        arr[[0, 1]] = arr[[1, 0]]
        return real_step(arr)

    suite.step = swapped
    with pytest.raises(PreflightError, match=CHECK_FRAME):
        preflight.check_frame_consistency(suite, "libero_object/0", 0)
