# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Issue #227: a report names the policy that EXECUTED, beside the checkpoint that was REQUESTED.

`RunReport.model` is the request. `RunReport.deployed_policy` is what the adapter resolved at
load: class, checkpoint and revision, action unnormaliser, controller convention, one digest.
Tai (2026, arXiv:2606.03724) is the reason the two must both exist: two deployments can agree on
the checkpoint string and differ in the unnormaliser, and then the same normalised output moves a
different physical distance. These tests pin that the field is emitted, that it can differ from
the request, that it is signed over (schema 6) without disturbing any earlier attestation, and
that the pure resolution helpers behave on fakes shaped like the real objects.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.attest import (
    _DEPLOYED_POLICY_FIELDS_ADDED_IN,
    _REPORT_FIELDS_ADDED_IN,
    _report_digest,
    report_projection,
)
from provael.cli import app
from provael.combine import ShardMismatchError, combine_reports
from provael.config import RunConfig
from provael.policies.identity import (
    camera_keys_of,
    denoising_steps_of,
    discrete_state_input_of,
    input_normaliser_from_pipeline,
    observation_stats_digest,
    processor_files_digest,
    rename_map_from_pipeline,
    revision_from_cache_path,
    stats_digest,
    step_names,
    temporal_ensemble_coeff_of,
    unnormaliser_from_pipeline,
    weights_file_digest,
)
from provael.policies.stub import STUB_CHECKPOINT, StubPolicy
from provael.report import load_report
from provael.runner import run
from provael.test_report import to_test_report_markdown
from provael.types import ActionUnnormaliser, DeployedPolicy, InputNormaliser

runner = CliRunner()

_CONFIG = {"policy": "stub", "suite": "stub", "attacks": ["none", "instruction"], "episodes": 2,
           "seed": 0}


def _report(**overrides):  # noqa: ANN003, ANN202
    return run(RunConfig(**{**_CONFIG, **overrides}))


# --------------------------------------------------------------------------- #
# the report carries both, and they can differ
# --------------------------------------------------------------------------- #


def test_report_carries_the_requested_checkpoint_and_the_deployed_policy_and_they_differ() -> None:
    """The one assertion the issue asks for: request and execution are both present, and distinct.

    The stub cannot execute a requested checkpoint — it is scripted — so it records its own fixed
    identity whatever `--model` says. That is exactly the gap #227 describes, in miniature.
    """
    report = _report(model="requested/alias-that-did-not-run")
    assert report.model == "requested/alias-that-did-not-run"
    deployed = report.deployed_policy
    assert deployed is not None
    assert deployed.checkpoint == STUB_CHECKPOINT
    assert deployed.checkpoint != report.model
    assert deployed.adapter == report.policy == "stub"
    assert deployed.policy_class == "StubPolicy"
    assert deployed.action_unnormaliser == ActionUnnormaliser(
        mode="IDENTITY", stats_digest=None, source="adapter-constant"
    )
    assert deployed.controller_convention is not None
    assert deployed.controller_convention.action_dim == StubPolicy().action_dim
    # 6 introduced deployed_policy; 7 the calibration binding; 8 the per-episode init_state; 9 the
    # rest of the deployed policy's runtime identity
    assert report.schema_version == 9


def test_the_digest_is_derived_from_the_fields_and_is_stable() -> None:
    a = DeployedPolicy.build(adapter="stub", policy_class="StubPolicy", checkpoint="x")
    b = DeployedPolicy.build(adapter="stub", policy_class="StubPolicy", checkpoint="x")
    c = DeployedPolicy.build(adapter="stub", policy_class="StubPolicy", checkpoint="y")
    assert a.digest == b.digest and len(a.digest) == 64
    assert a.digest != c.digest, "a different checkpoint must be a different identity"
    # A changed unnormaliser is a changed identity even when everything else agrees (Tai 2026).
    d = DeployedPolicy.build(
        adapter="stub", policy_class="StubPolicy", checkpoint="x",
        action_unnormaliser=ActionUnnormaliser(mode="MEAN_STD", stats_digest="0" * 64, source="t"),
    )
    assert d.digest != a.digest


def test_two_runs_of_the_same_deployment_agree_on_the_identity_digest() -> None:
    first, second = _report(), _report()
    assert first.deployed_policy is not None and second.deployed_policy is not None
    assert first.deployed_policy.digest == second.deployed_policy.digest


# --------------------------------------------------------------------------- #
# signed over at schema 6, invisible to every earlier attestation
# --------------------------------------------------------------------------- #


def test_the_field_is_registered_in_the_projection_and_stripped_below_schema_6() -> None:
    """Registered, or every attestation ever issued verifies as tampered."""
    assert "deployed_policy" in _REPORT_FIELDS_ADDED_IN[6]
    report = _report()
    assert report.deployed_policy is not None
    older = report.model_copy(update={"schema_version": 5})
    without = older.model_copy(update={"deployed_policy": None})
    assert "deployed_policy" not in report_projection(older)
    assert _report_digest(older) == _report_digest(without), (
        "a schema-5 report must digest identically with or without the field"
    )


def test_at_schema_6_the_deployed_policy_is_part_of_the_signed_subject() -> None:
    report = _report()
    assert "deployed_policy" in report_projection(report)
    changed = report.model_copy(
        update={"deployed_policy": DeployedPolicy.build(adapter="stub", checkpoint="other")}
    )
    assert _report_digest(changed) != _report_digest(report), (
        "an identity change at schema 6 must move the attested subject — signed over, not around"
    )


# --------------------------------------------------------------------------- #
# shards
# --------------------------------------------------------------------------- #


def test_shards_that_executed_different_policies_do_not_combine() -> None:
    a = _report()
    b = a.model_copy(
        update={"deployed_policy": DeployedPolicy.build(adapter="stub", checkpoint="elsewhere")}
    )
    with pytest.raises(ShardMismatchError, match="deployed policy"):
        combine_reports([a, b])
    combined = combine_reports([a, a.model_copy(update={"seed": 7})])
    assert combined.deployed_policy == a.deployed_policy


# --------------------------------------------------------------------------- #
# the pure resolution helpers, on fakes shaped like the real objects
# --------------------------------------------------------------------------- #


def test_revision_is_read_off_a_hub_cache_path_and_nothing_else() -> None:
    cached = ("/home/u/.cache/huggingface/hub/models--HuggingFaceVLA--smolvla_libero/snapshots/"
              "0123456789abcdef0123456789abcdef01234567/config.json")
    assert revision_from_cache_path(cached) == "0123456789abcdef0123456789abcdef01234567"
    assert revision_from_cache_path("/data/checkpoints/local/config.json") is None
    assert revision_from_cache_path(None) is None
    assert revision_from_cache_path(cached.replace("/", "\\")) is not None, "Windows paths too"


class _Tensor:
    """The three methods the helper touches on a torch tensor, and nothing else."""

    def __init__(self, values: list[float]) -> None:
        self._values = values

    def detach(self) -> _Tensor:
        return self

    def cpu(self) -> _Tensor:
        return self

    def tolist(self) -> list[float]:
        return list(self._values)


def test_stats_digest_covers_only_the_action_stream_and_is_exact() -> None:
    stats = {"action.mean": _Tensor([0.0, 0.5]), "action.std": _Tensor([1.0, 2.0]),
             "observation.state.mean": _Tensor([9.0])}
    digest = stats_digest(stats)
    assert digest is not None and len(digest) == 64
    # Observation statistics do not enter: a different state normaliser is not a different
    # action unnormaliser.
    assert stats_digest({**stats, "observation.state.mean": _Tensor([1.0])}) == digest
    # Exact, not rounded: a last-decimal difference is a different unnormaliser.
    assert stats_digest({**stats, "action.std": _Tensor([1.0, 2.0000001])}) != digest
    assert stats_digest({"observation.state.mean": _Tensor([9.0])}) is None


class _UnnormalizerProcessorStep:
    def get_config(self) -> dict[str, object]:
        return {"norm_map": {"ACTION": "MEAN_STD", "STATE": "MEAN_STD", "VISUAL": "IDENTITY"}}

    def state_dict(self) -> dict[str, _Tensor]:
        return {"action.mean": _Tensor([0.0]), "action.std": _Tensor([1.0])}


class _DeviceProcessorStep:
    pass


class _Pipeline:
    def __init__(self, *steps: object) -> None:
        self.steps = list(steps)


def test_unnormaliser_is_read_off_the_live_pipeline_by_shape_not_by_import() -> None:
    pipeline = _Pipeline(_DeviceProcessorStep(), _UnnormalizerProcessorStep())
    resolved = unnormaliser_from_pipeline(pipeline, source="lerobot-postprocessor")
    assert resolved is not None
    assert resolved.mode == "MEAN_STD"
    assert resolved.stats_digest == stats_digest(_UnnormalizerProcessorStep().state_dict())
    assert resolved.source == "lerobot-postprocessor"
    assert step_names(pipeline) == ["_DeviceProcessorStep", "_UnnormalizerProcessorStep"]
    # No unnormaliser step: None, not a made-up IDENTITY.
    assert unnormaliser_from_pipeline(_Pipeline(_DeviceProcessorStep()), source="x") is None
    assert unnormaliser_from_pipeline(None, source="x") is None
    assert step_names(None) == []


# --------------------------------------------------------------------------- #
# the surfaces that read it
# --------------------------------------------------------------------------- #


def test_the_test_report_names_the_executed_policy_beside_the_request() -> None:
    report = _report(model="requested/alias-that-did-not-run")
    text = to_test_report_markdown(report)
    assert "**Checkpoint requested:** `requested/alias-that-did-not-run`" in text
    assert f"checkpoint `{STUB_CHECKPOINT}`" in text
    assert report.deployed_policy is not None
    assert report.deployed_policy.digest in text
    assert "**Action unnormaliser:** `IDENTITY`" in text


def test_the_execution_manifest_carries_the_resolved_checkpoint(tmp_path: Path) -> None:
    """`checkpoint_repo` / `checkpoint_revision` existed on the manifest and were never filled;
    the resolved identity is what fills them now."""
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["attack", "--policy", "stub", "--suite", "stub", "--attacks", "none", "--episodes", "1",
         "--model", "requested/alias", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "execution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["checkpoint_repo"] == STUB_CHECKPOINT
    assert manifest["checkpoint_revision"] is None
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["model"] == "requested/alias"
    assert report["deployed_policy"]["checkpoint"] == STUB_CHECKPOINT
    assert report["deployed_policy"]["controller_convention"]["pipeline"] == []


# --------------------------------------------------------------------------- #
# schema 9: the rest of the runtime identity (P1.1)
# --------------------------------------------------------------------------- #

_SCHEMA_9_FIELDS = (
    "input_normaliser", "preprocessor_digest", "postprocessor_digest", "weights_digest",
    "rename_map", "camera_keys", "denoising_steps", "control_rate_hz",
    "temporal_ensemble_coeff", "discrete_state_input",
)


def test_the_schema_9_fields_are_registered_and_stripped_below_9() -> None:
    """Nested in `deployed_policy`, so the top-level tables do not reach them: their own does."""
    assert _DEPLOYED_POLICY_FIELDS_ADDED_IN[9] == _SCHEMA_9_FIELDS
    report = _report()
    assert report.deployed_policy is not None
    older = report.model_copy(update={"schema_version": 8})
    projected = report_projection(older)["deployed_policy"]
    assert not set(_SCHEMA_9_FIELDS) & set(projected)
    blank = older.deployed_policy.model_copy(update=dict.fromkeys(_SCHEMA_9_FIELDS))  # type: ignore[union-attr]
    assert _report_digest(older) == _report_digest(older.model_copy(update={"deployed_policy": blank}))
    # At schema 9 they are signed over: a different weight file is a different subject.
    moved = report.deployed_policy.model_copy(update={"weights_digest": "0" * 64})
    assert _report_digest(report) != _report_digest(report.model_copy(update={"deployed_policy": moved}))


def test_committed_schema_8_reports_with_a_deployed_policy_still_digest_as_bound() -> None:
    """The four PAISI episodes (#356) carry a `deployed_policy` and a manifest binding its digest."""
    paths = sorted(Path("results/rfm_submission_2026-11").rglob("report.json"))
    assert len(paths) == 4
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["schema_version"] == 8 and raw["deployed_policy"] is not None
        manifest = json.loads((path.parent / "execution-manifest.json").read_text(encoding="utf-8"))
        assert _report_digest(load_report(path)) == manifest["report_digest"], path


def test_every_new_field_moves_the_identity_digest() -> None:
    base = DeployedPolicy.build(adapter="smolvla", checkpoint="c")
    changes: dict[str, object] = {
        "input_normaliser": InputNormaliser(state_mode="MEAN_STD", source="t"),
        "preprocessor_digest": "1" * 64, "postprocessor_digest": "2" * 64,
        "weights_digest": "3" * 64, "rename_map": {"a": "b"},
        "camera_keys": ["observation.images.image"], "denoising_steps": 10,
        "control_rate_hz": 30, "temporal_ensemble_coeff": 0.01, "discrete_state_input": True,
    }
    assert set(changes) == set(_SCHEMA_9_FIELDS)
    for name, value in changes.items():
        changed = DeployedPolicy.build(adapter="smolvla", checkpoint="c", **{name: value})  # type: ignore[arg-type]
        assert changed.digest != base.digest, name
    # Camera ORDER is identity: the same two cameras swapped are a different deployment.
    a = DeployedPolicy.build(adapter="smolvla", camera_keys=["x", "y"])
    b = DeployedPolicy.build(adapter="smolvla", camera_keys=["y", "x"])
    assert a.digest != b.digest


def test_the_stub_records_only_what_is_certain() -> None:
    deployed = _report().deployed_policy
    assert deployed is not None
    assert deployed.rename_map == {} and deployed.camera_keys == []
    for name in set(_SCHEMA_9_FIELDS) - {"rename_map", "camera_keys"}:
        assert getattr(deployed, name) is None, name


class _NormalizerProcessorStep:
    def get_config(self) -> dict[str, object]:
        return {"norm_map": {"ACTION": "MEAN_STD", "STATE": "MEAN_STD", "VISUAL": "IDENTITY"}}

    def state_dict(self) -> dict[str, _Tensor]:
        return {
            "action.mean": _Tensor([0.0]), "observation.state.mean": _Tensor([1.0, 2.0]),
            "observation.state.std": _Tensor([3.0, 4.0]),
        }


class _RenameObservationsProcessorStep:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def get_config(self) -> dict[str, object]:
        return {"rename_map": dict(self._mapping)}


def test_the_input_normaliser_is_read_off_the_preprocessor_and_ignores_action_stats() -> None:
    resolved = input_normaliser_from_pipeline(
        _Pipeline(_DeviceProcessorStep(), _NormalizerProcessorStep()), source="lerobot-preprocessor"
    )
    assert resolved == InputNormaliser(
        state_mode="MEAN_STD", visual_mode="IDENTITY",
        stats_digest=observation_stats_digest(_NormalizerProcessorStep().state_dict()),
        source="lerobot-preprocessor",
    )
    stats = _NormalizerProcessorStep().state_dict()
    assert observation_stats_digest({**stats, "action.mean": _Tensor([9.0])}) == resolved.stats_digest
    assert observation_stats_digest({"action.mean": _Tensor([0.0])}) is None
    # The UNnormaliser is the action side and is never read as the input normaliser.
    assert input_normaliser_from_pipeline(_Pipeline(_UnnormalizerProcessorStep()), source="x") is None
    assert input_normaliser_from_pipeline(None, source="x") is None


def test_the_rename_map_is_the_one_the_pipeline_applies() -> None:
    swap = {"observation.images.image": "observation.images.image2"}
    assert rename_map_from_pipeline(_Pipeline(_RenameObservationsProcessorStep(swap))) == swap
    assert rename_map_from_pipeline(_Pipeline(_DeviceProcessorStep())) == {}
    assert rename_map_from_pipeline(None) is None


class _Config:
    def __init__(self, **fields: object) -> None:
        self.__dict__.update(fields)


def test_the_policy_config_readers_record_only_explicit_settings() -> None:
    smolvla = _Config(num_steps=10, image_features={"observation.images.image": 0,
                                                    "observation.images.image2": 1})
    pi05 = _Config(num_inference_steps=10)
    diffusion = _Config(num_inference_steps=None, num_train_timesteps=100)
    act = _Config(temporal_ensemble_coeff=0.01)
    assert denoising_steps_of(smolvla) == 10 and denoising_steps_of(pi05) == 10
    assert denoising_steps_of(diffusion) is None, "lerobot's fallback is not ours to apply"
    assert camera_keys_of(None, smolvla) == ["observation.images.image", "observation.images.image2"]
    assert camera_keys_of(_Config()) is None
    assert temporal_ensemble_coeff_of(act) == 0.01 and temporal_ensemble_coeff_of(smolvla) is None
    assert discrete_state_input_of(_Config(discrete_state_input=True)) is True
    assert discrete_state_input_of(smolvla) is None


def _checkpoint(root: Path) -> Path:
    """A local checkpoint directory laid out the way lerobot 0.5.1 loads one."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "policy_preprocessor.json").write_text(json.dumps({"steps": [
        {"registry_name": "device_processor"},
        {"registry_name": "normalizer_processor", "state_file": "pre_step_1_normalizer.safetensors"},
    ]}), encoding="utf-8")
    (root / "pre_step_1_normalizer.safetensors").write_bytes(b"pre-stats")
    (root / "policy_postprocessor.json").write_text(json.dumps({"steps": [
        {"registry_name": "unnormalizer_processor", "state_file": "post_step_0.safetensors"},
    ]}), encoding="utf-8")
    (root / "post_step_0.safetensors").write_bytes(b"post-stats")
    (root / "model.safetensors").write_bytes(b"weights")
    return root


def test_file_digests_are_rebuilt_from_per_file_hashes(tmp_path: Path) -> None:
    root = _checkpoint(tmp_path / "ckpt")

    def sha(name: str) -> str:
        return hashlib.sha256((root / name).read_bytes()).hexdigest()

    pairs = [["policy_preprocessor.json", sha("policy_preprocessor.json")],
             ["pre_step_1_normalizer.safetensors", sha("pre_step_1_normalizer.safetensors")]]
    expected = hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()
    assert processor_files_digest(str(root), "policy_preprocessor.json") == expected
    assert weights_file_digest(str(root)) == hashlib.sha256(b"weights").hexdigest()
    # A state file the config names and the checkpoint lacks: half the pipeline is not the
    # pipeline that ran, so the digest is unresolved rather than partial.
    (root / "post_step_0.safetensors").unlink()
    assert processor_files_digest(str(root), "policy_postprocessor.json") is None
    assert processor_files_digest(str(tmp_path / "absent"), "policy_preprocessor.json") is None
    assert weights_file_digest(str(tmp_path / "absent")) is None
    # A changed statistic is a changed digest.
    before = processor_files_digest(str(root), "policy_preprocessor.json")
    (root / "pre_step_1_normalizer.safetensors").write_bytes(b"other-stats")
    assert processor_files_digest(str(root), "policy_preprocessor.json") != before
