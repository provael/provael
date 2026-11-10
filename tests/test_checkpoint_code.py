# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""What a checkpoint's own files would make lerobot fetch or run, checked before anything loads.

lerobot 0.5.1 loads whatever backbone, tokenizer, step class or policy type a checkpoint's JSON
names, and transformers 5.3.0, which it pins, lets a repo loaded with ``from_pretrained`` turn
remote code on for itself (PYSEC-2026-2290). ``provael.integrity.checkpoint_code_problems`` is the
allow-list between ``provael attack --model <repo>`` and that.

The three known-good checkpoints below mirror the files read off the Hub on 10 November 2026 and
must pass. Every rule fails on a fixture of its own, with no other rule firing. Nothing here needs
lerobot, torch or the network, except the one test gated on ``PROVAEL_INTEGRATION=1``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.execution import ENV_ALLOWLIST
from provael.integrity import (
    CHECKPOINT_CODE_FILES,
    INTEGRITY_JSON,
    KNOWN_BACKBONE_REPOS,
    TRUST_CHECKPOINT_CODE_ENV,
    CheckpointFiles,
    IntegrityVerdict,
    checkpoint_code_problems,
    checkpoint_code_report,
    checkpoint_directories,
    digest_checkpoint,
    fetch_processor_state_files,
    read_checkpoint_files,
    trust_checkpoint_code,
    verify_checkpoint,
)
from provael.policies.groot_adapter import GrootAdapter
from provael.policies.lerobot_adapter import (
    LIBERO_FINETUNED_SMOLVLA,
    IncompatiblePolicyError,
    LeRobotAdapter,
    UntrustedCheckpointCodeWarning,
    UntrustedCheckpointError,
)

runner = CliRunner()

_INTEGRATION = os.environ.get("PROVAEL_INTEGRATION") == "1"
_HUB_INSTALLED = importlib.util.find_spec("huggingface_hub") is not None

# --------------------------------------------------------------------------------------------- #
# The three known-good checkpoints, mirroring their files on the Hub (10 November 2026)
# --------------------------------------------------------------------------------------------- #

_IMAGE = {"type": "VISUAL", "shape": [3, 256, 256]}
_ACTION = {"type": "ACTION", "shape": [7]}
_FEATURES = {
    "observation.images.image": _IMAGE,
    "observation.images.image2": _IMAGE,
    "observation.state": {"type": "STATE", "shape": [8]},
    "action": _ACTION,
}
_NORM_MAP = {"VISUAL": "IDENTITY", "STATE": "MEAN_STD", "ACTION": "MEAN_STD"}


def _step(name: str, **config: Any) -> dict[str, Any]:
    return {"registry_name": name, "config": config}


def _tokenizer(repo: str, max_length: int, padding: str) -> dict[str, Any]:
    return _step(
        "tokenizer_processor", max_length=max_length, task_key="task", padding_side="right",
        padding=padding, truncation=True, tokenizer_name=repo,
    )


def _device(device: str) -> dict[str, Any]:
    return _step("device_processor", device=device, float_dtype=None)


def _normalizer(index: int) -> dict[str, Any]:
    step = _step("normalizer_processor", eps=1e-08, features=_FEATURES, norm_map=_NORM_MAP)
    return {**step, "state_file": f"policy_preprocessor_step_{index}_normalizer_processor.safetensors"}


def _unnormalizer(index: int) -> dict[str, Any]:
    step = _step("unnormalizer_processor", eps=1e-08, features={"action": _ACTION}, norm_map=_NORM_MAP)
    return {**step, "state_file": f"policy_postprocessor_step_{index}_unnormalizer_processor.safetensors"}


def _pipeline(name: str, *steps: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "steps": list(steps)}


def _smolvla(backbone: str, *, padding: str, repo_id: str | None, unnormalize_first: bool) -> CheckpointFiles:
    config = {
        "type": "smolvla", "n_obs_steps": 1,
        "input_features": {k: v for k, v in _FEATURES.items() if k != "action"},
        "output_features": {"action": _ACTION}, "device": "cuda", "use_amp": False,
        "push_to_hub": True, "repo_id": repo_id, "chunk_size": 50, "n_action_steps": 1,
        "normalization_mapping": _NORM_MAP, "tokenizer_max_length": 48,
        "vlm_model_name": backbone, "load_vlm_weights": True, "attention_mode": "cross_attn",
    }
    preprocessor = _pipeline(
        "policy_preprocessor",
        _step("rename_observations_processor", rename_map={}),
        _step("to_batch_processor"),
        _step("smolvla_new_line_processor"),
        _tokenizer(backbone, 48, padding),
        _device("cuda"),
        _normalizer(5),
    )
    postprocessor = (
        _pipeline("policy_postprocessor", _unnormalizer(0), _device("cpu"))
        if unnormalize_first
        else _pipeline("policy_postprocessor", _device("cpu"), _unnormalizer(1))
    )
    return CheckpointFiles(config, preprocessor, postprocessor)


def _pi05_libero() -> CheckpointFiles:
    config = {
        "type": "pi05", "n_obs_steps": 1,
        "input_features": {k: v for k, v in _FEATURES.items() if k != "action"},
        "output_features": {"action": _ACTION}, "device": "cuda", "use_amp": False,
        "push_to_hub": True, "chunk_size": 50, "n_action_steps": 50,
        "paligemma_variant": "gemma_2b", "action_expert_variant": "gemma_300m",
        "tokenizer_max_length": 200,
        # Training lineage, and loaded as nothing: the adapter overwrites pretrained_path with the
        # checkpoint it was given, and repo_id is where training pushed to.
        "pretrained_path": "lerobot/pi05_libero", "repo_id": "pepijn223/pi05_libero_31_9_non_q",
    }
    preprocessor = _pipeline(
        "policy_preprocessor",
        _step("rename_observations_processor", rename_map={}),
        _step("to_batch_processor"),
        _normalizer(2),
        _step("pi05_prepare_state_tokenizer_processor_step"),
        _tokenizer("google/paligemma-3b-pt-224", 200, "max_length"),
        _device("cuda"),
    )
    postprocessor = _pipeline("policy_postprocessor", _unnormalizer(0), _device("cpu"))
    return CheckpointFiles(config, preprocessor, postprocessor)


KNOWN_GOOD: dict[str, Callable[[], CheckpointFiles]] = {
    "HuggingFaceVLA/smolvla_libero": lambda: _smolvla(
        "HuggingFaceTB/SmolVLM2-500M-Instruct", padding="longest", repo_id="None",
        unnormalize_first=False,
    ),
    "lerobot/smolvla_base": lambda: _smolvla(
        "HuggingFaceTB/SmolVLM2-500M-Video-Instruct", padding="max_length", repo_id=None,
        unnormalize_first=True,
    ),
    "lerobot/pi05_libero_finetuned_v044": _pi05_libero,
}


def _bad(mutate: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], None]) -> CheckpointFiles:
    """smolvla_libero's files with one change, so exactly one rule has something to say."""
    good = KNOWN_GOOD["HuggingFaceVLA/smolvla_libero"]()
    config, pre, post = (copy.deepcopy(d) for d in (good.config, good.preprocessor, good.postprocessor))
    assert isinstance(config, dict) and isinstance(pre, dict) and isinstance(post, dict)
    mutate(config, pre, post)
    return CheckpointFiles(config, pre, post)


def _rules(files: CheckpointFiles) -> set[str]:
    return {problem.rule for problem in files.problems()}


def _write(directory: Path, files: CheckpointFiles) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, document in zip(
        CHECKPOINT_CODE_FILES, (files.config, files.preprocessor, files.postprocessor), strict=True
    ):
        if document is not None:
            (directory / name).write_text(json.dumps(document), encoding="utf-8")
    (directory / "model.safetensors").write_bytes(b"weights")
    return directory


# --------------------------------------------------------------------------------------------- #
# The known-good set passes, and the allow-list is exactly what it names
# --------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("checkpoint", sorted(KNOWN_GOOD))
def test_a_known_good_checkpoint_passes(checkpoint: str) -> None:
    assert KNOWN_GOOD[checkpoint]().problems() == []


def test_the_repo_allow_list_is_exactly_what_the_known_good_checkpoints_name() -> None:
    named: set[str] = set()
    for build in KNOWN_GOOD.values():
        files = build()
        assert isinstance(files.config, dict) and isinstance(files.preprocessor, dict)
        if "vlm_model_name" in files.config:
            named.add(files.config["vlm_model_name"])
        named |= {
            step["config"]["tokenizer_name"]
            for step in files.preprocessor["steps"]
            if "tokenizer_name" in step["config"]
        }
    assert named == KNOWN_BACKBONE_REPOS


def test_absent_files_are_not_problems() -> None:
    assert checkpoint_code_problems(None, None, None) == []
    good = KNOWN_GOOD["lerobot/smolvla_base"]()
    assert checkpoint_code_problems(good.config, None, None) == []
    assert checkpoint_code_problems(None, good.preprocessor, None) == []


# --------------------------------------------------------------------------------------------- #
# Each rule, on a fixture of its own
# --------------------------------------------------------------------------------------------- #


def test_trust_remote_code_anywhere_is_refused() -> None:
    def in_config(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["trust_remote_code"] = True

    def deep_in_a_step(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"][3]["config"]["extra"] = [{"trust_remote_code": True}]

    def as_a_truthy_string(_config: dict[str, Any], _pre: dict[str, Any], post: dict[str, Any]) -> None:
        post["steps"][0]["config"]["trust_remote_code"] = "false"  # a non-empty string is true

    for mutate in (in_config, deep_in_a_step, as_a_truthy_string):
        assert _rules(_bad(mutate)) == {"trust-remote-code"}, mutate.__name__


def test_trust_remote_code_false_is_not_a_problem() -> None:
    def explicit_false(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["trust_remote_code"] = False

    assert _bad(explicit_false).problems() == []


def test_auto_map_in_config_is_refused() -> None:
    def auto_map(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["auto_map"] = {"AutoConfig": "configuration_x.XConfig"}

    assert _rules(_bad(auto_map)) == {"auto-map"}


@pytest.mark.parametrize("repo", ["someone/lightglue-config", "./backbone", "HuggingFaceTB/SmolVLM2-500M-Instruct-x", 7])
def test_a_backbone_outside_the_list_is_refused(repo: object) -> None:
    def backbone(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["vlm_model_name"] = repo

    problems = _bad(backbone).problems()
    assert {p.rule for p in problems} == {"repo"}
    assert problems[0].file == "config.json" and "vlm_model_name" in problems[0].detail


def test_a_tokenizer_outside_the_list_is_refused() -> None:
    def tokenizer(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"][3]["config"]["tokenizer_name"] = "someone/tokenizer"

    problems = _bad(tokenizer).problems()
    assert {p.rule for p in problems} == {"repo"}
    assert problems[0].file == "policy_preprocessor.json"
    assert "steps[3].config.tokenizer_name" in problems[0].detail


def test_a_step_class_outside_lerobot_is_refused() -> None:
    def outside(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"].append({"class": "evil.module.Step", "config": {}})

    assert _rules(_bad(outside)) == {"step-class"}


def test_a_step_class_outside_lerobot_is_refused_even_beside_a_registered_name() -> None:
    def beside(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"][0]["class"] = "evil.module.Step"

    assert _rules(_bad(beside)) == {"step-class"}


def test_a_lerobot_class_with_no_registered_name_is_refused() -> None:
    """lerobot imports the path and calls what it finds with the step's config: not only steps."""

    def unregistered(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"].append({
            "class": "lerobot.policies.groot.utils.copytree",
            "config": {"src": "a", "dst": "b"},
        })

    assert _rules(_bad(unregistered)) == {"step"}


@pytest.mark.parametrize("name", ["reward_classifier_processor", "groot_pack_inputs_v3", None, 3])
def test_a_step_this_project_has_not_read_is_refused(name: object) -> None:
    def unknown(_config: dict[str, Any], _pre: dict[str, Any], post: dict[str, Any]) -> None:
        post["steps"].append({"registry_name": name, "config": {"pretrained_path": None}})

    assert _rules(_bad(unknown)) == {"step"}


def test_an_action_tokenizer_must_turn_remote_code_off() -> None:
    def default_trust(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"].append(_step("action_tokenizer_processor", action_tokenizer_name="google/paligemma-3b-pt-224"))

    def explicit_false(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"].append(_step(
            "action_tokenizer_processor", action_tokenizer_name="google/paligemma-3b-pt-224",
            trust_remote_code=False,
        ))

    def false_but_a_foreign_tokenizer(_config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        pre["steps"].append(_step(
            "action_tokenizer_processor", action_tokenizer_name="physical-intelligence/fast",
            trust_remote_code=False,
        ))

    assert _rules(_bad(default_trust)) == {"action-tokenizer"}
    assert _bad(explicit_false).problems() == []
    assert _rules(_bad(false_but_a_foreign_tokenizer)) == {"repo"}


@pytest.mark.parametrize("policy_type", ["pi0_fast", "sac", "reward_classifier", "groot", None])
def test_a_policy_type_this_adapter_does_not_load_is_refused(policy_type: str | None) -> None:
    def other_type(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        if policy_type is None:
            del config["type"]
        else:
            config["type"] = policy_type

    assert _rules(_bad(other_type)) == {"policy-type"}


def test_peft_is_refused_because_it_loads_a_second_policy() -> None:
    def peft(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["use_peft"] = True

    def peft_off(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["use_peft"] = False

    assert _rules(_bad(peft)) == {"peft"}
    assert _bad(peft_off).problems() == []


def test_a_shape_this_cannot_read_is_refused_rather_than_skipped() -> None:
    good = KNOWN_GOOD["HuggingFaceVLA/smolvla_libero"]()
    assert {p.rule for p in checkpoint_code_problems(["not", "an", "object"], None, None)} == {"malformed"}
    assert {p.rule for p in checkpoint_code_problems(good.config, {"steps": {"a": 1}}, None)} == {"malformed"}
    assert {p.rule for p in checkpoint_code_problems(good.config, {"steps": ["x"]}, None)} == {"malformed"}


def test_the_refusal_names_every_problem_and_the_way_in() -> None:
    def two(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["vlm_model_name"] = "someone/backbone"
        config["use_peft"] = True

    problems = _bad(two).problems()
    refusal = checkpoint_code_report("someone/ckpt", problems, refused=True)
    warning = checkpoint_code_report("someone/ckpt", problems, refused=False)
    for text in (refusal, warning):
        assert "'someone/ckpt'" in text and TRUST_CHECKPOINT_CODE_ENV in text
        assert all(str(problem) in text for problem in problems)
    assert refusal.startswith("Refusing") and warning.startswith("Loading")


def test_a_strangers_text_is_quoted_on_one_line_and_cut_short() -> None:
    def line_break(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["vlm_model_name"] = "some/one\nERROR: forged log line"

    def long_name(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["vlm_model_name"] = "x" * 5000

    (broken,) = _bad(line_break).problems()
    assert "\n" not in broken.detail and r"some/one\nERROR" in broken.detail
    (long,) = _bad(long_name).problems()
    assert '"' + "x" * 76 + "..." in long.detail and "x" * 77 not in long.detail


# --------------------------------------------------------------------------------------------- #
# The opt-in
# --------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize(("value", "trusted"), [("1", True), ("0", False), ("true", False), ("", False)])
def test_only_the_value_one_opts_in(value: str, trusted: bool) -> None:
    assert trust_checkpoint_code({TRUST_CHECKPOINT_CODE_ENV: value}) is trusted
    assert trust_checkpoint_code({}) is False


def test_the_opt_in_is_recorded_in_the_execution_manifest() -> None:
    """A run that passed the check and one that overrode it are different claims."""
    assert TRUST_CHECKPOINT_CODE_ENV in ENV_ALLOWLIST


# --------------------------------------------------------------------------------------------- #
# Reading the files: a local directory, or the Hub
# --------------------------------------------------------------------------------------------- #


def test_a_local_directory_is_read_as_lerobot_reads_it(tmp_path: Path) -> None:
    good = KNOWN_GOOD["lerobot/pi05_libero_finetuned_v044"]()
    directory = _write(tmp_path / "ckpt", good)
    files = read_checkpoint_files(str(directory))
    assert _documents(files) == _documents(good)
    assert files.directory == directory and files.revision is None
    (directory / "policy_postprocessor.json").unlink()
    assert read_checkpoint_files(str(directory)).postprocessor is None


def test_a_file_that_is_not_json_is_raised_not_skipped(tmp_path: Path) -> None:
    directory = _write(tmp_path / "ckpt", KNOWN_GOOD["lerobot/smolvla_base"]())
    (directory / "config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="config.json is not UTF-8 JSON"):
        read_checkpoint_files(str(directory))


def _documents(files: CheckpointFiles) -> tuple[object, object, object]:
    return files.config, files.preprocessor, files.postprocessor


class _HubErrors(types.ModuleType):
    """huggingface_hub.errors as 1.x arranges it."""

    def __init__(self) -> None:
        super().__init__("huggingface_hub.errors")

        class HfHubHTTPError(OSError):
            pass

        class EntryNotFoundError(Exception):
            pass

        class RemoteEntryNotFoundError(HfHubHTTPError, EntryNotFoundError):
            pass

        class LocalEntryNotFoundError(FileNotFoundError, EntryNotFoundError):
            pass

        class RepositoryNotFoundError(HfHubHTTPError):
            pass

        self.HfHubHTTPError = HfHubHTTPError
        self.EntryNotFoundError = EntryNotFoundError
        self.RemoteEntryNotFoundError = RemoteEntryNotFoundError
        self.LocalEntryNotFoundError = LocalEntryNotFoundError
        self.RepositoryNotFoundError = RepositoryNotFoundError


_COMMIT_A = "a" * 40
_COMMIT_B = "b" * 40


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    """A fake huggingface_hub that lays files out as its cache does.

    ``answers[commit][filename]`` is a document to serve or an exception to raise, ``main`` is the
    commit an unpinned download resolves to, and ``after`` runs after every download, so a test
    can move ``main`` the way a repo owner could while a load is under way.
    """
    errors = _HubErrors()
    state: dict[str, Any] = {
        "errors": errors, "answers": {_COMMIT_A: {}, _COMMIT_B: {}}, "main": _COMMIT_A,
        "calls": [], "after": lambda: None, "root": tmp_path / "hub" / "models--someone--ckpt",
    }

    def hf_hub_download(*, repo_id: str, filename: str, revision: str | None = None) -> str:
        commit = revision or state["main"]
        state["calls"].append((repo_id, filename, revision))
        answer = state["answers"][commit][filename]
        if isinstance(answer, BaseException):
            raise answer
        path = state["root"] / "snapshots" / commit / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(answer, bytes):
            path.write_bytes(answer)
        else:
            path.write_text(json.dumps(answer), encoding="utf-8")
        state["after"]()
        return str(path)

    module = types.ModuleType("huggingface_hub")
    module.hf_hub_download = hf_hub_download  # type: ignore[attr-defined]
    module.errors = errors  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", errors)
    return state


def _serve(hub: dict[str, Any], files: CheckpointFiles, commit: str = _COMMIT_A) -> None:
    hub["answers"][commit].update(zip(CHECKPOINT_CODE_FILES, _documents(files), strict=True))


def test_the_hub_is_asked_for_the_three_files_lerobot_reads(hub: dict[str, Any]) -> None:
    good = KNOWN_GOOD["HuggingFaceVLA/smolvla_libero"]()
    _serve(hub, good)
    files = read_checkpoint_files("HuggingFaceVLA/smolvla_libero")
    assert _documents(files) == _documents(good)
    assert files.revision == _COMMIT_A
    assert files.directory == hub["root"] / "snapshots" / _COMMIT_A
    assert [(repo, name) for repo, name, _ in hub["calls"]] == [
        ("HuggingFaceVLA/smolvla_libero", name) for name in CHECKPOINT_CODE_FILES
    ]


def test_the_three_files_come_from_one_commit_even_if_the_repo_moves(hub: dict[str, Any]) -> None:
    """The owner swaps the repo after config.json is read; the processors still come from it."""
    _serve(hub, KNOWN_GOOD["lerobot/smolvla_base"](), _COMMIT_A)
    _serve(hub, _bad(lambda _c, pre, _p: pre["steps"].append(_step("reward_classifier_processor"))), _COMMIT_B)

    def move_main() -> None:
        hub["main"] = _COMMIT_B

    hub["after"] = move_main
    files = read_checkpoint_files("lerobot/smolvla_base")
    assert files.revision == _COMMIT_A and files.problems() == []
    assert [revision for _, _, revision in hub["calls"]] == [None, _COMMIT_A, _COMMIT_A]


def test_a_file_the_repo_does_not_have_is_absent(hub: dict[str, Any]) -> None:
    good = KNOWN_GOOD["lerobot/smolvla_base"]()
    _serve(hub, good)
    hub["answers"][_COMMIT_A]["policy_postprocessor.json"] = hub["errors"].RemoteEntryNotFoundError("404")
    files = read_checkpoint_files("lerobot/smolvla_base")
    assert files.postprocessor is None and files.config == good.config
    assert files.problems() == []


def test_an_older_hub_404_is_absent_too(hub: dict[str, Any]) -> None:
    """huggingface_hub 0.x had no RemoteEntryNotFoundError; its EntryNotFoundError was the 404."""
    errors = hub["errors"]
    del errors.RemoteEntryNotFoundError
    _serve(hub, KNOWN_GOOD["lerobot/smolvla_base"]())
    hub["answers"][_COMMIT_A]["config.json"] = errors.EntryNotFoundError("404")
    files = read_checkpoint_files("lerobot/smolvla_base")
    assert files.config is None and files.revision == _COMMIT_A  # pinned by the next file found


@pytest.mark.parametrize(
    "error",
    [
        lambda e: e.LocalEntryNotFoundError("offline, and not in the cache"),
        lambda e: e.RepositoryNotFoundError("no such repo, or no access"),
        lambda e: e.HfHubHTTPError("503"),
        lambda e: ConnectionError("network unreachable"),
    ],
    ids=["offline", "no-repo", "server-error", "network"],
)
def test_every_other_fetch_error_is_raised(hub: dict[str, Any], error: Callable[[Any], BaseException]) -> None:
    _serve(hub, KNOWN_GOOD["lerobot/smolvla_base"]())
    raised = error(hub["errors"])
    hub["answers"][_COMMIT_A]["policy_preprocessor.json"] = raised
    with pytest.raises(type(raised)):
        read_checkpoint_files("lerobot/smolvla_base")


def test_the_statistics_the_steps_name_are_fetched_at_the_checked_commit(hub: dict[str, Any]) -> None:
    good = KNOWN_GOOD["lerobot/smolvla_base"]()
    _serve(hub, good)
    for name in ("policy_preprocessor_step_5_normalizer_processor.safetensors",
                 "policy_postprocessor_step_0_unnormalizer_processor.safetensors"):
        hub["answers"][_COMMIT_A][name] = b"stats"
    files = read_checkpoint_files("lerobot/smolvla_base")
    hub["main"] = _COMMIT_B  # the repo moves after the check: the statistics must not follow it
    fetch_processor_state_files("lerobot/smolvla_base", files)
    fetched = [(name, revision) for _, name, revision in hub["calls"][3:]]
    assert fetched == [
        ("policy_preprocessor_step_5_normalizer_processor.safetensors", _COMMIT_A),
        ("policy_postprocessor_step_0_unnormalizer_processor.safetensors", _COMMIT_A),
    ]
    assert files.directory is not None
    assert (files.directory / "policy_preprocessor_step_5_normalizer_processor.safetensors").is_file()


@pytest.mark.skipif(
    not (_INTEGRATION and _HUB_INSTALLED),
    reason="requires PROVAEL_INTEGRATION=1 and huggingface_hub (reads three files from the Hub)",
)
def test_the_published_smolvla_checkpoint_passes_on_the_hub() -> None:
    files = read_checkpoint_files(LIBERO_FINETUNED_SMOLVLA)
    assert None not in (files.config, files.preprocessor, files.postprocessor)
    assert files.revision is not None
    assert files.problems() == []


# --------------------------------------------------------------------------------------------- #
# LeRobotAdapter.load: refused before anything is imported from lerobot or torch
# --------------------------------------------------------------------------------------------- #


@pytest.fixture
def lerobot_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend lerobot is installed, and make torch, the first import past the check, fail loudly.

    A load that reaches the ImportError got past the check; a refusal never reaches it.
    """
    monkeypatch.setattr(LeRobotAdapter, "lerobot_available", staticmethod(lambda: True))
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.delenv(TRUST_CHECKPOINT_CODE_ENV, raising=False)


def _foreign_backbone(tmp_path: Path) -> Path:
    def backbone(config: dict[str, Any], pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["vlm_model_name"] = "someone/lightglue-config"
        pre["steps"][3]["config"]["tokenizer_name"] = "someone/lightglue-config"

    return _write(tmp_path / "foreign", _bad(backbone))


@pytest.mark.usefixtures("lerobot_present")
def test_a_known_good_checkpoint_loads_past_the_check(tmp_path: Path) -> None:
    directory = _write(tmp_path / "good", KNOWN_GOOD["HuggingFaceVLA/smolvla_libero"]())
    with pytest.raises(ImportError, match="torch"):
        LeRobotAdapter(model_id=str(directory), device="cpu").load()


@pytest.mark.usefixtures("lerobot_present")
def test_a_foreign_backbone_is_refused_before_any_import(tmp_path: Path) -> None:
    directory = _foreign_backbone(tmp_path)
    with pytest.raises(UntrustedCheckpointError) as caught:
        LeRobotAdapter(model_id=str(directory), device="cpu").load()
    message = str(caught.value)
    assert "someone/lightglue-config" in message and "vlm_model_name" in message
    assert f"{TRUST_CHECKPOINT_CODE_ENV}=1" in message
    # Every command that already turns an unloadable checkpoint into one clean line catches this.
    assert isinstance(caught.value, IncompatiblePolicyError)


@pytest.mark.usefixtures("lerobot_present")
def test_the_opt_in_loads_it_with_a_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TRUST_CHECKPOINT_CODE_ENV, "1")
    directory = _foreign_backbone(tmp_path)
    with (
        pytest.warns(UntrustedCheckpointCodeWarning, match="someone/lightglue-config"),
        pytest.raises(ImportError, match="torch"),
    ):
        LeRobotAdapter(model_id=str(directory), device="cpu").load()


@pytest.mark.usefixtures("lerobot_present")
def test_the_groot_adapter_inherits_the_check(tmp_path: Path) -> None:
    with pytest.raises(UntrustedCheckpointError):
        GrootAdapter(model_id=str(_foreign_backbone(tmp_path)), device="cpu", allow_real=True).load()


@pytest.mark.usefixtures("lerobot_present")
def test_a_hub_repo_with_no_config_is_not_loaded(hub: dict[str, Any]) -> None:
    """Nothing to load, and nothing checked that a later fetch could be held to."""
    _serve(hub, KNOWN_GOOD["lerobot/smolvla_base"]())
    hub["answers"][_COMMIT_A]["config.json"] = hub["errors"].RemoteEntryNotFoundError("404")
    with pytest.raises(IncompatiblePolicyError, match="no config.json") as caught:
        LeRobotAdapter(model_id="someone/ckpt", device="cpu").load()
    assert not isinstance(caught.value, UntrustedCheckpointError)


@pytest.fixture
def fake_lerobot(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Just enough of torch and lerobot 0.5.1 for ``load()`` to finish, recording what lerobot
    is handed: where it reads config.json, the weights and the processors from."""
    seen: dict[str, Any] = {}

    class PreTrainedConfig:
        @classmethod
        def from_pretrained(cls, path: str) -> Any:
            seen["config"] = path
            return types.SimpleNamespace(pretrained_path=None, device=None)

    def make_policy(*, cfg: Any, ds_meta: Any, env_cfg: Any, rename_map: Any) -> Any:
        seen["weights"] = cfg.pretrained_path
        return types.SimpleNamespace(eval=lambda: None, parameters=lambda: iter(()))

    def make_pre_post_processors(*, policy_cfg: Any, pretrained_path: str, preprocessor_overrides: Any) -> Any:
        seen["processors"] = pretrained_path
        local = Path(pretrained_path)
        seen["processor_files"] = sorted(p.name for p in local.iterdir()) if local.is_dir() else []
        return types.SimpleNamespace(steps=[]), types.SimpleNamespace(steps=[])

    attributes: dict[str, dict[str, Any]] = {
        "torch": {"device": lambda name: name},
        "lerobot": {}, "lerobot.configs": {}, "lerobot.envs": {}, "lerobot.policies": {},
        "lerobot.utils": {},
        "lerobot.configs.policies": {"PreTrainedConfig": PreTrainedConfig},
        "lerobot.envs.factory": {"make_env_pre_post_processors": lambda **_: (None, None)},
        "lerobot.policies.factory": {
            "make_policy": make_policy, "make_pre_post_processors": make_pre_post_processors,
        },
        "lerobot.utils.constants": {"ACTION": "action"},
    }
    for name, attrs in attributes.items():
        module = types.ModuleType(name)
        for attr, value in attrs.items():
            setattr(module, attr, value)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(LeRobotAdapter, "lerobot_available", staticmethod(lambda: True))
    monkeypatch.delenv(TRUST_CHECKPOINT_CODE_ENV, raising=False)
    return seen


def test_a_hub_checkpoint_is_loaded_from_the_snapshot_that_was_checked(
    hub: dict[str, Any], fake_lerobot: dict[str, Any]
) -> None:
    """Handed the repo id, lerobot would fetch config.json and the processors again later, and
    the owner could have swapped them by then. It is handed the checked snapshot instead."""
    _serve(hub, KNOWN_GOOD["lerobot/smolvla_base"](), _COMMIT_A)
    _serve(hub, _bad(lambda config, _pre, _post: config.update(vlm_model_name="someone/x")), _COMMIT_B)
    for name in ("policy_preprocessor_step_5_normalizer_processor.safetensors",
                 "policy_postprocessor_step_0_unnormalizer_processor.safetensors"):
        hub["answers"][_COMMIT_A][name] = b"stats"

    def move_main() -> None:
        hub["main"] = _COMMIT_B

    hub["after"] = move_main
    adapter = LeRobotAdapter(model_id="someone/ckpt", device="cpu")
    adapter.load()
    snapshot = str(hub["root"] / "snapshots" / _COMMIT_A)
    assert fake_lerobot["config"] == snapshot
    assert fake_lerobot["processors"] == snapshot
    assert "policy_preprocessor_step_5_normalizer_processor.safetensors" in fake_lerobot["processor_files"]
    # The weights still load by the id given: safetensors, which carry no code.
    assert fake_lerobot["weights"] == "someone/ckpt"
    assert adapter.resolved_identity.checkpoint == "someone/ckpt"


def test_a_local_checkpoint_is_handed_over_as_given(tmp_path: Path, fake_lerobot: dict[str, Any]) -> None:
    directory = str(_write(tmp_path / "good", KNOWN_GOOD["HuggingFaceVLA/smolvla_libero"]()))
    LeRobotAdapter(model_id=directory, device="cpu").load()
    assert fake_lerobot["config"] == fake_lerobot["processors"] == fake_lerobot["weights"] == directory


@pytest.mark.usefixtures("lerobot_present")
def test_provael_attack_refuses_in_one_clean_line(tmp_path: Path) -> None:
    result = runner.invoke(app, [
        "attack", "--policy", "smolvla", "--suite", "stub", "--model", str(_foreign_backbone(tmp_path)),
        "--attacks", "none", "--episodes", "1", "--out", str(tmp_path / "run"),
    ])
    assert result.exit_code != 0
    assert "Refusing to load" in result.output and "Traceback" not in result.output
    assert not (tmp_path / "run" / "report.json").exists()


# --------------------------------------------------------------------------------------------- #
# verify-checkpoint makes the same check on a local checkpoint
# --------------------------------------------------------------------------------------------- #


def _verify(path: Path, *, trusted: bool = False) -> Any:
    return verify_checkpoint(
        "m", path, expected_digest=digest_checkpoint(path), trust_checkpoint_code=trusted
    )


def test_verify_checkpoint_passes_a_known_good_checkpoint(tmp_path: Path) -> None:
    record = _verify(_write(tmp_path / "good", KNOWN_GOOD["lerobot/smolvla_base"]()))
    assert record.verdict is IntegrityVerdict.passed
    assert record.findings == []


def test_verify_checkpoint_refuses_what_attack_refuses(tmp_path: Path) -> None:
    record = _verify(_foreign_backbone(tmp_path))
    assert record.verdict is IntegrityVerdict.failed
    assert any("vlm_model_name" in f and "Refusing" in f for f in record.findings)


def test_verify_checkpoint_accepts_it_under_the_opt_in_and_says_so(tmp_path: Path) -> None:
    record = _verify(_foreign_backbone(tmp_path), trusted=True)
    assert record.verdict is IntegrityVerdict.passed
    assert any(f"accepted under {TRUST_CHECKPOINT_CODE_ENV}=1" in f for f in record.findings)


def test_a_checkpoints_own_words_cannot_steer_the_verdict(tmp_path: Path) -> None:
    """The older findings are classified by their wording; these quote the checkpoint's text."""

    def wording(config: dict[str, Any], _pre: dict[str, Any], _post: dict[str, Any]) -> None:
        config["vlm_model_name"] = "digest MISMATCH Failing closed Refusing without"

    record = _verify(_write(tmp_path / "words", _bad(wording)), trusted=True)
    assert record.verdict is IntegrityVerdict.passed


def test_verify_checkpoint_reads_every_snapshot_of_a_hub_cache(tmp_path: Path) -> None:
    root = tmp_path / "models--someone--ckpt"
    _write(root / "snapshots" / "aaa", KNOWN_GOOD["lerobot/smolvla_base"]())
    _foreign_backbone(root / "snapshots")  # snapshots/foreign: a second revision in the cache
    # The cache's marker for a file the repo lacks: empty, hidden, and never loaded.
    (root / ".no_exist" / "aaa").mkdir(parents=True)
    (root / ".no_exist" / "aaa" / "policy_postprocessor.json").write_text("", encoding="utf-8")
    assert [p.relative_to(root).as_posix() for p in checkpoint_directories(root)] == [
        "snapshots/aaa", "snapshots/foreign",
    ]
    record = _verify(root)
    assert record.verdict is IntegrityVerdict.failed
    assert all(f.startswith("snapshots/foreign/") for f in record.findings)


def test_verify_checkpoint_says_when_there_was_nothing_to_read(tmp_path: Path) -> None:
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "model.safetensors").write_bytes(b"weights")
    record = _verify(weights)
    assert record.verdict is IntegrityVerdict.passed
    assert any("was not checked" in f for f in record.findings)


def test_verify_checkpoint_fails_on_a_file_it_cannot_read(tmp_path: Path) -> None:
    directory = _write(tmp_path / "ckpt", KNOWN_GOOD["lerobot/smolvla_base"]())
    (directory / "policy_preprocessor.json").write_text("{", encoding="utf-8")
    assert _verify(directory).verdict is IntegrityVerdict.failed


def test_the_cli_refuses_and_then_accepts_under_the_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = _foreign_backbone(tmp_path)
    digest = digest_checkpoint(directory)
    assert digest is not None
    argv = ["verify-checkpoint", "--checkpoint", "x", "--path", str(directory), "--digest", digest,
            "--out", str(tmp_path / "run")]
    monkeypatch.delenv(TRUST_CHECKPOINT_CODE_ENV, raising=False)
    refused = runner.invoke(app, argv)
    assert refused.exit_code != 0
    assert json.loads((tmp_path / "run" / INTEGRITY_JSON).read_text())["verdict"] == "fail"
    monkeypatch.setenv(TRUST_CHECKPOINT_CODE_ENV, "1")
    accepted = runner.invoke(app, argv)
    assert accepted.exit_code == 0, accepted.output
    assert json.loads((tmp_path / "run" / INTEGRITY_JSON).read_text())["verdict"] == "pass"
