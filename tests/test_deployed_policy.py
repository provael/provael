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

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.attest import _REPORT_FIELDS_ADDED_IN, _report_digest, report_projection
from provael.cli import app
from provael.combine import ShardMismatchError, combine_reports
from provael.config import RunConfig
from provael.policies.identity import (
    revision_from_cache_path,
    stats_digest,
    step_names,
    unnormaliser_from_pipeline,
)
from provael.policies.stub import STUB_CHECKPOINT, StubPolicy
from provael.runner import run
from provael.test_report import to_test_report_markdown
from provael.types import ActionUnnormaliser, DeployedPolicy

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
    assert report.schema_version == 6


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
