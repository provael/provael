# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Checkpoint supply-chain integrity — a pre-load control for the CI gate.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
This is a **supply-chain control**, not an adversarial-robustness measurement. It answers "are we
about to load the weights we think we are, in a format that is safe to load?" — a question with a
yes/no answer, checked once, before any policy is instantiated. Its second half asks the same of
the checkpoint's JSON: does loading it make lerobot fetch or run code nobody reviewed? (see
:func:`checkpoint_code_problems`).

It is **not** an attack, it produces **no attack-success rate**, and it does **not** reduce one. A
checkpoint that passes every check here can still leave its safety envelope under an adversarial
instruction at exactly the rate the ASR says. Nothing in this module may be reported as,
aggregated into, or described as moving an ASR. The two live in the same evidence pack because a
release decision needs both; they are not the same claim and must never be added together.

WHY IT EXISTS
-------------
Provael's own ``SECURITY.md`` documents **CVE-2026-25874** — LeRobot unauthenticated
pickle-deserialization RCE (CVSS 9.8), affecting ``lerobot`` through ``0.6.1`` (OSV, record
updated 11 November 2026; NVD's CPE range still ends at ``0.5.1``), in the
async-inference ``PolicyServer`` which ``pickle.loads`` untrusted payloads over an unauthenticated
gRPC endpoint (TCP/50051). Provael never starts that PolicyServer, so *that* path is not reachable
through Provael — but the same class of risk reaches any tool that loads a third-party checkpoint,
because loading a pickle executes it. The tool named the risk publicly and the reusable Action did
not check for it.

EAI MAPPING
-----------
**EAI03 — Model & pipeline poisoning, backdoors & supply chain.** The mapping is in the title:
this is checkpoint supply-chain integrity. It is deliberately NOT filed under EAI07, whose entry
declares CPS/firmware/comms/teleoperation out of scope; that scoping is about *attacks Provael
does not run*, and it would be wrong to imply this control closes any part of it. The
PolicyServer RCE that motivates this has an EAI07 flavour, but what the gate actually inspects is
the checkpoint artifact, which is EAI03.

Note EAI03 is ``attacks-implemented`` (the ``backdoor`` family screens objective-decoupled
triggers). This control sits alongside that, not inside it: the backdoor family produces a rate,
this produces a verdict.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from provael.policies.identity import revision_from_cache_path

#: The EAI risk this control belongs to. See the module docstring for why not EAI07.
INTEGRITY_EAI_ID = "EAI03"

#: Artifact filename written into the run's output directory.
INTEGRITY_JSON = "checkpoint-integrity.json"

#: Format id for the emitted artifact.
INTEGRITY_FORMAT = "provael-checkpoint-integrity/v1"

#: Weight-file suffixes that execute arbitrary code on load. `.bin`/`.pt`/`.pth`/`.ckpt` are
#: torch archives (zip-wrapped pickles); `.pkl` is a bare pickle. Loading any of them from an
#: untrusted source is equivalent to running its author's code.
PICKLE_SUFFIXES: tuple[str, ...] = (".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle")

#: The safe alternative: a length-prefixed tensor container with no code path.
SAFETENSORS_SUFFIX = ".safetensors"


class CheckpointFormat(StrEnum):
    """What kind of weights the checkpoint ships."""

    safetensors = "safetensors"
    #: Pickle-format weights present and no safetensors alternative.
    pickle = "pickle"
    #: Both present — loadable safely, so `prefer_safetensors` is satisfiable.
    mixed = "mixed"
    #: No recognised weight file (e.g. a hub id that was never fetched locally).
    unknown = "unknown"


class IntegrityVerdict(StrEnum):
    """Outcome of the pre-load check."""

    passed = "pass"
    #: A check failed. The gate must not load the policy.
    failed = "fail"
    #: Checks were deliberately skipped by an explicit opt-out. Never the default.
    skipped = "skipped"


class CheckpointIntegrity(BaseModel):
    """The emitted evidence record. Carries no rate, by construction."""

    format: str = INTEGRITY_FORMAT
    eai_id: str = INTEGRITY_EAI_ID
    checkpoint: str
    verdict: IntegrityVerdict
    digest_sha256: str | None = Field(
        None, description="SHA-256 over the checkpoint's weight files, or None when not computed."
    )
    expected_digest: str | None = Field(
        None, description="The digest the caller pinned. None means nothing was pinned."
    )
    digest_match: bool | None = Field(
        None, description="None when no digest was pinned (which is itself a failure by default)."
    )
    checkpoint_format: CheckpointFormat = CheckpointFormat.unknown
    pickle_allowed: bool = False
    findings: list[str] = Field(default_factory=list)
    note: str = Field(
        "Supply-chain control, not an adversarial-robustness result. This verdict is not an "
        "attack-success rate and does not reduce one.",
        description="Travels with the record so the distinction survives being pasted elsewhere.",
    )


def _weight_files(path: Path) -> list[Path]:
    """Every recognised weight file under ``path``, sorted for determinism."""
    suffixes = (*PICKLE_SUFFIXES, SAFETENSORS_SUFFIX)
    if path.is_file():
        return [path] if path.suffix in suffixes else []
    return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in suffixes)


def detect_format(path: Path) -> CheckpointFormat:
    """Classify the checkpoint's weight format."""
    files = _weight_files(path)
    if not files:
        return CheckpointFormat.unknown
    has_safe = any(f.suffix == SAFETENSORS_SUFFIX for f in files)
    has_pickle = any(f.suffix in PICKLE_SUFFIXES for f in files)
    if has_safe and has_pickle:
        return CheckpointFormat.mixed
    return CheckpointFormat.safetensors if has_safe else CheckpointFormat.pickle


def digest_checkpoint(path: Path) -> str | None:
    """SHA-256 over the checkpoint's weight files, order-independent and path-independent.

    Hashes each file's bytes, sorts the per-file digests, and hashes the concatenation — so the
    result does not depend on directory layout or traversal order, and a caller can pin it once
    and re-check it anywhere. Returns None when there is nothing to hash, which the caller must
    treat as a failure rather than as a match.
    """
    files = _weight_files(path)
    if not files:
        return None
    per_file = sorted(hashlib.sha256(f.read_bytes()).hexdigest() for f in files)
    return hashlib.sha256("\n".join(per_file).encode()).hexdigest()


def verify_checkpoint(
    checkpoint: str,
    path: Path | None,
    *,
    expected_digest: str | None = None,
    allow_pickle: bool = False,
    require_pinned_digest: bool = True,
    trust_checkpoint_code: bool = False,
) -> CheckpointIntegrity:
    """Check a checkpoint BEFORE the policy is loaded. Fails closed by default.

    Fail-closed is the default on every axis, matching how the rest of the gate handles defaults
    (``fail-on-regression`` defaults true):

    * **No pinned digest is a failure**, not a pass. "We did not check" and "we checked and it
      matched" must never produce the same verdict — that is the whole value of the control.
      ``require_pinned_digest=False`` is the explicit opt-out.
    * **Pickle weights are refused** unless ``allow_pickle``. Loading a pickle executes it, so an
      unpinned pickle checkpoint is arbitrary code execution with extra steps. Where both formats
      are present the checkpoint is loadable safely, so ``mixed`` passes and the finding says to
      prefer safetensors.
    * **A checkpoint whose JSON chooses code that runs on load is refused** unless
      ``trust_checkpoint_code``: every directory under ``path`` holding a lerobot ``config.json``
      or processor file goes through :func:`checkpoint_code_problems`, the check
      ``LeRobotAdapter.load`` makes. A path with none of those files is recorded as not checked.

    Args:
        checkpoint: Identity of the checkpoint (hub id or path), recorded in the evidence.
        path: Local path to the fetched checkpoint, or None when it was never fetched.
        expected_digest: The digest the caller pinned.
        allow_pickle: Explicit opt-in to loading pickle-format weights.
        require_pinned_digest: Whether an absent pin is a failure. Default True.
        trust_checkpoint_code: Explicit opt-in to code the checkpoint's JSON chooses
            (``PROVAEL_TRUST_CHECKPOINT_CODE=1`` on the command line).
    """
    findings: list[str] = []
    fmt = CheckpointFormat.unknown
    actual: str | None = None

    if path is None or not path.exists():
        findings.append(
            f"checkpoint {checkpoint!r} was not fetched locally, so nothing could be verified — "
            "pin a local path to check it before load"
        )
    else:
        fmt = detect_format(path)
        actual = digest_checkpoint(path)
        if actual is None:
            findings.append(f"no recognised weight files under {path} — nothing to digest")

    match: bool | None = None
    if expected_digest:
        match = actual is not None and actual == expected_digest
        if not match:
            findings.append(
                f"digest MISMATCH: pinned {expected_digest[:16]}… but computed "
                f"{(actual or 'nothing')[:16]}… — refusing to load"
            )
    elif require_pinned_digest:
        findings.append(
            "no checkpoint digest was pinned. Failing closed: an unverified checkpoint is the "
            "supply-chain risk this control exists for. Pass the digest, or opt out explicitly."
        )

    if fmt is CheckpointFormat.pickle and not allow_pickle:
        findings.append(
            "checkpoint ships pickle-format weights and no safetensors. Loading a pickle executes "
            "it (cf. CVE-2026-25874). Refusing without an explicit opt-in; prefer safetensors."
        )
    elif fmt is CheckpointFormat.mixed:
        findings.append(
            "both safetensors and pickle weights are present — load the safetensors and do not "
            "fall back to the pickle."
        )
    elif fmt is CheckpointFormat.pickle and allow_pickle:
        findings.append(
            "pickle-format weights loaded under an explicit opt-in. This is code execution from "
            "the checkpoint author; it is accepted here, not made safe."
        )

    blocking = [
        f for f in findings
        if "MISMATCH" in f or "Failing closed" in f or "Refusing without" in f
        or "was not fetched" in f or "nothing to digest" in f
    ]
    # Classified apart from the text match above, and after it: these findings quote strings from
    # the checkpoint's own files, which must not be able to steer the verdict by their wording.
    code_findings, code_blocking = _checkpoint_code_findings(path, trusted=trust_checkpoint_code)
    findings += code_findings
    verdict = IntegrityVerdict.failed if blocking or code_blocking else IntegrityVerdict.passed

    return CheckpointIntegrity(
        checkpoint=checkpoint,
        verdict=verdict,
        digest_sha256=actual,
        expected_digest=expected_digest,
        digest_match=match,
        checkpoint_format=fmt,
        pickle_allowed=allow_pickle,
        findings=findings,
    )


def skipped_record(checkpoint: str, reason: str) -> CheckpointIntegrity:
    """The record for an explicit opt-out — visible in the evidence, never silent."""
    return CheckpointIntegrity(
        checkpoint=checkpoint,
        verdict=IntegrityVerdict.skipped,
        findings=[f"checkpoint integrity checks were skipped by explicit opt-out: {reason}"],
    )


# --------------------------------------------------------------------------------------------- #
# What loading a LeRobot checkpoint would fetch or run
# --------------------------------------------------------------------------------------------- #
#
# The checks above ask whether these are the weights we pinned. This one asks whether the
# checkpoint chooses code that runs when it loads, and with lerobot 0.5.1 it can. Loading reads
# three JSON files first, and lerobot then:
#
# * builds the policy class config.json's `type` names. Several classes load a model their own
#   config names, and pi0_fast, sac, reward_classifier, groot and wall_x pass trust_remote_code=True
#   to that load in lerobot's own code;
# * loads SmolVLA's backbone from `vlm_model_name`, and every tokenizer step's `tokenizer_name`,
#   with from_pretrained;
# * finds each processor step by its registered name, or, with no name, imports the step's `class`
#   path and calls whatever it finds with the step's config;
# * builds `action_tokenizer_processor` with trust_remote_code defaulting to true, and
#   `reward_classifier_processor` by loading the classifier repo its config names;
# * with `use_peft`, loads a second policy that adapter_config.json names.
#
# transformers 5.3.0, which lerobot 0.5.1 pins exactly, adds PYSEC-2026-2290: LightGlueConfig hands
# a trust_remote_code read from a loaded config.json to a nested AutoConfig.from_pretrained, so a
# repo loaded with from_pretrained can turn remote code on for itself. 5.5.0 fixes it and the pin
# cannot reach it. So the check below is an allow-list, read from the JSON alone before anything
# is imported, and it runs the same whatever lerobot or transformers is installed. What it allows
# was read in lerobot 0.5.1, the pinned version: re-read it when the pin moves. What it refuses
# loads only when the operator sets PROVAEL_TRUST_CHECKPOINT_CODE=1, and may then run its
# author's code.

#: Set to ``1`` to load a checkpoint :func:`checkpoint_code_problems` objects to, accepting that its
#: author's code may run. Read from the environment so that neither ``RunConfig`` nor
#: ``report.json`` changes; the execution manifest records it (``execution.ENV_ALLOWLIST``).
TRUST_CHECKPOINT_CODE_ENV = "PROVAEL_TRUST_CHECKPOINT_CODE"

#: The files lerobot 0.5.1 reads from a checkpoint before it builds anything (its ``CONFIG_NAME``
#: and ``POLICY_PREPROCESSOR_DEFAULT_NAME`` / ``POLICY_POSTPROCESSOR_DEFAULT_NAME`` plus ``.json``).
CHECKPOINT_CONFIG = "config.json"
CHECKPOINT_PREPROCESSOR = "policy_preprocessor.json"
CHECKPOINT_POSTPROCESSOR = "policy_postprocessor.json"
CHECKPOINT_CODE_FILES: tuple[str, ...] = (
    CHECKPOINT_CONFIG,
    CHECKPOINT_PREPROCESSOR,
    CHECKPOINT_POSTPROCESSOR,
)

#: Backbone and tokenizer repos a checkpoint may name. Each was read off a known-good checkpoint's
#: files on the Hugging Face Hub on 10 November 2026, and nothing else is on the list.
KNOWN_BACKBONE_REPOS: frozenset[str] = frozenset(
    {
        # HuggingFaceVLA/smolvla_libero, the checkpoint behind the published SmolVLA runs:
        # config.json's vlm_model_name and its tokenizer_processor step's tokenizer_name.
        "HuggingFaceTB/SmolVLM2-500M-Instruct",
        # lerobot/smolvla_base, the smolvla registry default: the same two fields.
        "HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
        # lerobot/pi05_libero_finetuned_v044, the published pi0.5 leg: its tokenizer_name. pi0.5
        # has no vlm_model_name.
        "google/paligemma-3b-pt-224",
    }
)

#: The lerobot policy types this adapter loads. Read in lerobot 0.5.1 on 10 November 2026: their
#: policy classes load no repo that config.json names except SmolVLA's vlm_model_name, checked
#: against :data:`KNOWN_BACKBONE_REPOS`. Every other type is refused, pi0_fast included.
KNOWN_POLICY_TYPES: frozenset[str] = frozenset({"smolvla", "pi0", "pi05"})

#: Processor steps a checkpoint may use, by registered name, each read in lerobot 0.5.1 on
#: 10 November 2026. None loads anything beyond the tokenizer its config names, checked against
#: :data:`KNOWN_BACKBONE_REPOS`, and safetensors statistics.
KNOWN_PROCESSOR_STEPS: frozenset[str] = frozenset(
    {
        # Every step the three checkpoints behind KNOWN_BACKBONE_REPOS use.
        "rename_observations_processor",
        "to_batch_processor",
        "smolvla_new_line_processor",
        "pi05_prepare_state_tokenizer_processor_step",
        "tokenizer_processor",
        "device_processor",
        "normalizer_processor",
        "unnormalizer_processor",
        # The rest of what lerobot 0.5.1 itself writes for a pi0 or pi0.5 checkpoint.
        "pi0_new_line_processor",
        "delta_actions_processor",
        "absolute_actions_processor",
        # Listed so that its own rule decides it (see ACTION_TOKENIZER_STEP).
        "action_tokenizer_processor",
    }
)

#: lerobot 0.5.1 builds this step with ``trust_remote_code=True`` unless its config says ``false``.
ACTION_TOKENIZER_STEP = "action_tokenizer_processor"

#: Keys whose value lerobot 0.5.1 hands to ``from_pretrained``, in config.json and in a step.
_CONFIG_REPO_KEYS = frozenset({"vlm_model_name"})
_STEP_REPO_KEYS = frozenset({"tokenizer_name", "action_tokenizer_name", "paligemma_tokenizer_name"})


@dataclass(frozen=True)
class CheckpointCodeProblem:
    """One reason loading a checkpoint would make lerobot fetch or run code nobody reviewed."""

    #: Which of :data:`CHECKPOINT_CODE_FILES` it was found in.
    file: str
    #: A short, stable rule name, for tests and for searching a log.
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.file}: {self.detail}"


@dataclass(frozen=True)
class CheckpointFiles:
    """The parsed :data:`CHECKPOINT_CODE_FILES` of one checkpoint. ``None`` means absent."""

    config: object = None
    preprocessor: object = None
    postprocessor: object = None
    #: The local directory the files were read from: the checkpoint directory itself, or the Hub
    #: cache's snapshot of the one commit all three were read at. ``None`` when none was found.
    directory: Path | None = None
    #: That commit, for a Hub checkpoint; ``None`` for a local directory.
    revision: str | None = None

    def problems(self) -> list[CheckpointCodeProblem]:
        """:func:`checkpoint_code_problems` over these three files."""
        return checkpoint_code_problems(self.config, self.preprocessor, self.postprocessor)


def checkpoint_code_problems(
    config: object, preprocessor: object, postprocessor: object
) -> list[CheckpointCodeProblem]:
    """Every reason loading these files through lerobot would fetch or run unreviewed code.

    Takes the parsed ``config.json``, ``policy_preprocessor.json`` and
    ``policy_postprocessor.json``, each ``None`` when absent, and imports nothing. Empty means
    every rule passed. The rules:

    * ``trust_remote_code`` truthy anywhere in any file, and ``auto_map`` anywhere in config.json;
    * config.json's ``type`` outside :data:`KNOWN_POLICY_TYPES`, or ``use_peft`` set;
    * ``vlm_model_name``, a step's ``tokenizer_name``, or the action tokenizer's two repo names
      outside :data:`KNOWN_BACKBONE_REPOS`;
    * a step whose ``class`` import path is not lerobot's, whose registered name is outside
      :data:`KNOWN_PROCESSOR_STEPS`, or which has no registered name, so lerobot imports its class;
    * an ``action_tokenizer_processor`` step that does not set ``trust_remote_code`` to ``false``.
    """
    problems: list[CheckpointCodeProblem] = []
    documents = (
        (CHECKPOINT_CONFIG, config),
        (CHECKPOINT_PREPROCESSOR, preprocessor),
        (CHECKPOINT_POSTPROCESSOR, postprocessor),
    )
    for name, document in documents:
        if document is None:
            continue
        if not isinstance(document, dict):
            problems.append(_problem(name, "malformed", "is not a JSON object, so not checked"))
            continue
        problems += _remote_code_problems(name, document)
        if name == CHECKPOINT_CONFIG:
            problems += _config_problems(document)
        else:
            problems += _pipeline_problems(name, document)
    return problems


def _problem(file: str, rule: str, detail: str) -> CheckpointCodeProblem:
    return CheckpointCodeProblem(file=file, rule=rule, detail=detail)


def _show(value: object) -> str:
    """A parsed JSON value, re-encoded and cut short: it is a stranger's text headed for a log."""
    text = json.dumps(value)
    return text if len(text) <= 80 else f"{text[:77]}..."


def _keys(node: object, path: str = "") -> Iterator[tuple[str, str, object]]:
    """``(path, key, value)`` for every object key in a parsed JSON document, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{path}.{key}" if path else str(key)
            yield where, str(key), value
            yield from _keys(value, where)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _keys(value, f"{path}[{index}]")


def _remote_code_problems(name: str, document: dict[str, object]) -> list[CheckpointCodeProblem]:
    problems: list[CheckpointCodeProblem] = []
    for where, key, value in _keys(document):
        if key == "trust_remote_code" and value:
            problems.append(_problem(
                name, "trust-remote-code",
                f"{where} is {_show(value)}, so transformers would run code from a repo it loads",
            ))
        elif key == "auto_map" and name == CHECKPOINT_CONFIG:
            problems.append(_problem(
                name, "auto-map", f"{where} points model classes at code shipped in a repo"
            ))
    return problems


def _repo_problems(name: str, where: str, value: object) -> list[CheckpointCodeProblem]:
    if value is None or (isinstance(value, str) and value in KNOWN_BACKBONE_REPOS):
        return []
    return [_problem(
        name, "repo",
        f"{where} is {_show(value)}, not a backbone or tokenizer this project has checked; "
        "lerobot would load it with from_pretrained",
    )]


def _config_problems(config: dict[str, object]) -> list[CheckpointCodeProblem]:
    problems: list[CheckpointCodeProblem] = []
    policy_type = config.get("type")
    if not (isinstance(policy_type, str) and policy_type in KNOWN_POLICY_TYPES):
        named = f"type is {_show(policy_type)}" if "type" in config else "it names no type"
        problems.append(_problem(
            CHECKPOINT_CONFIG, "policy-type",
            f"{named}, and only {', '.join(sorted(KNOWN_POLICY_TYPES))} are loaded: other "
            "lerobot policy types load models their own config names",
        ))
    if config.get("use_peft"):
        problems.append(_problem(
            CHECKPOINT_CONFIG, "peft",
            "use_peft is set, so lerobot would also load the policy adapter_config.json names, "
            "which this check never reads",
        ))
    for where, key, value in _keys(config):
        if key in _CONFIG_REPO_KEYS:
            problems += _repo_problems(CHECKPOINT_CONFIG, where, value)
    return problems


def _pipeline_problems(name: str, pipeline: dict[str, object]) -> list[CheckpointCodeProblem]:
    steps = pipeline.get("steps", [])
    if not isinstance(steps, list):
        return [_problem(name, "malformed", "steps is not a list, so no step was checked")]
    problems: list[CheckpointCodeProblem] = []
    for index, step in enumerate(steps):
        label = f"steps[{index}]"
        if isinstance(step, dict):
            problems += _step_problems(name, label, step)
        else:
            problems.append(_problem(name, "malformed", f"{label} is not an object"))
    return problems


def _step_problems(name: str, label: str, step: dict[str, object]) -> list[CheckpointCodeProblem]:
    problems: list[CheckpointCodeProblem] = []
    class_path = step.get("class")
    lerobot_class = isinstance(class_path, str) and class_path.startswith("lerobot.")
    if "class" in step and not lerobot_class:
        problems.append(_problem(
            name, "step-class",
            f"{label} names class {_show(class_path)}, outside lerobot; lerobot imports a step's "
            "class and calls it with the step's config",
        ))
    # lerobot looks a step up by registry_name whenever the key is present, and only otherwise
    # imports its class, so the key's presence is what decides which path runs.
    if "registry_name" in step:
        registered = step["registry_name"]
        if not (isinstance(registered, str) and registered in KNOWN_PROCESSOR_STEPS):
            problems.append(_problem(
                name, "step", f"{label} is {_show(registered)}, not a step this project has read"
            ))
    elif lerobot_class:
        problems.append(_problem(
            name, "step",
            f"{label} has no registry_name, so lerobot would import {_show(class_path)} and call "
            "it with the step's config",
        ))
    step_config = step.get("config")
    for where, key, value in _keys(step_config, f"{label}.config"):
        if key in _STEP_REPO_KEYS:
            problems += _repo_problems(name, where, value)
    if step.get("registry_name") == ACTION_TOKENIZER_STEP:
        trust = step_config.get("trust_remote_code") if isinstance(step_config, dict) else None
        if trust is not False:
            problems.append(_problem(
                name, "action-tokenizer",
                f"{label} is {ACTION_TOKENIZER_STEP}, which lerobot 0.5.1 builds with "
                "trust_remote_code=true unless its config sets it to false",
            ))
    return problems


def trust_checkpoint_code(environ: Mapping[str, str] | None = None) -> bool:
    """True when the operator set ``PROVAEL_TRUST_CHECKPOINT_CODE=1``. Any other value is a no."""
    env = os.environ if environ is None else environ
    return env.get(TRUST_CHECKPOINT_CODE_ENV) == "1"


def checkpoint_code_report(
    checkpoint: str, problems: Sequence[CheckpointCodeProblem], *, refused: bool
) -> str:
    """The refusal message, or with ``refused=False`` the warning an opted-in load prints."""
    if refused:
        head = (
            f"Refusing to load {checkpoint!r}: its files would make lerobot fetch or run code "
            "this project has not reviewed."
        )
        tail = (
            f"To load it anyway, set {TRUST_CHECKPOINT_CODE_ENV}=1. That accepts code its author "
            "chose: do it only for a checkpoint you trust, on a machine with nothing to lose. "
            "See docs/checkpoint-integrity.md."
        )
    else:
        head = (
            f"Loading {checkpoint!r} under {TRUST_CHECKPOINT_CODE_ENV}=1, although its files "
            "would make lerobot fetch or run code this project has not reviewed."
        )
        tail = "Code its author chose may run in this process."
    return "\n".join([head, *(f"  - {problem}" for problem in problems), tail])


def read_checkpoint_files(checkpoint: str) -> CheckpointFiles:
    """Read :data:`CHECKPOINT_CODE_FILES` from where lerobot 0.5.1 would read them.

    A local directory when ``checkpoint`` names one, as ``PreTrainedConfig.from_pretrained``
    decides. Otherwise the Hub repo of that id, through the ``hf_hub_download`` lerobot itself
    calls: the first file found fixes the commit, and the others are read at that commit, so the
    three come from one snapshot even if the repo moves while they download. A file the repo does
    not have is absent (``None``), as it is to lerobot. Every other failure to fetch or to parse is
    raised, never swallowed: a file this could not read is a file it did not check.
    """
    local = Path(checkpoint)
    if local.is_dir():
        return read_local_checkpoint_files(local)
    documents: list[object] = []
    directory: Path | None = None
    revision: str | None = None
    for name in CHECKPOINT_CODE_FILES:
        path = _download_from_hub(checkpoint, name, revision=revision)
        if path is not None and revision is None:
            revision = revision_from_cache_path(str(path))
            if revision is None:
                raise ValueError(f"{path} is not in a Hub cache snapshot, so its commit is unknown")
            directory = path.parent
        documents.append(None if path is None else _read_json(path))
    config, preprocessor, postprocessor = documents
    return CheckpointFiles(config, preprocessor, postprocessor, directory, revision)


def read_local_checkpoint_files(directory: Path) -> CheckpointFiles:
    """:data:`CHECKPOINT_CODE_FILES` in one local directory; a missing one is ``None``."""
    config, preprocessor, postprocessor = (
        _read_json(directory / name) if (directory / name).is_file() else None
        for name in CHECKPOINT_CODE_FILES
    )
    return CheckpointFiles(config, preprocessor, postprocessor, directory)


def fetch_processor_state_files(repo_id: str, files: CheckpointFiles) -> None:
    """Download, at ``files.revision``, the statistics files the checked processor steps name.

    lerobot reads a step's ``state_file`` from the pipeline's directory first, and from the Hub
    only when the pipeline was named by repo id. A load handed :attr:`CheckpointFiles.directory`
    needs them in that directory beforehand, and this puts them there, from the same commit as
    the files that were checked. They are safetensors, which carry no code. One the repo lacks is
    left absent, as the loader treats any missing file, and lerobot then reports it.
    """
    if files.revision is None:
        return
    for pipeline in (files.preprocessor, files.postprocessor):
        steps = pipeline.get("steps") if isinstance(pipeline, dict) else None
        for step in steps if isinstance(steps, list) else []:
            state_file = step.get("state_file") if isinstance(step, dict) else None
            if isinstance(state_file, str):
                _download_from_hub(repo_id, state_file, revision=files.revision)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError are both ValueErrors
        raise ValueError(f"{path} is not UTF-8 JSON, so it could not be checked: {exc}") from exc


def _download_from_hub(repo_id: str, filename: str, *, revision: str | None) -> Path | None:
    """One file of a Hub repo as a local path; ``None`` when the Hub says there is no such file."""
    # Lazy: huggingface_hub is not in the CPU build. It arrives with lerobot, and this runs only
    # once LeRobotAdapter.load has found lerobot installed.
    from huggingface_hub import errors as hub_errors
    from huggingface_hub import hf_hub_download

    # "No such file" is the one failure that means absent. huggingface_hub 1.x raises
    # RemoteEntryNotFoundError for it, 0.x raised EntryNotFoundError. In both, the offline
    # LocalEntryNotFoundError is filed under EntryNotFoundError too, and it is a failure to fetch,
    # so it is re-raised before the broader class is caught.
    not_in_repo = getattr(hub_errors, "RemoteEntryNotFoundError", hub_errors.EntryNotFoundError)
    try:
        path = hf_hub_download(repo_id=repo_id, filename=filename, revision=revision)
    except hub_errors.LocalEntryNotFoundError:
        raise
    except not_in_repo:
        return None
    return Path(path)


def checkpoint_directories(path: Path) -> list[Path]:
    """Every directory under ``path``, itself included, that holds one of the checked files.

    A Hugging Face cache root keeps one directory per revision under ``snapshots/``. Each is
    checked, since the cache does not say which one a later load picks. Hidden directories are
    skipped: lerobot never loads a checkpoint from one, and the cache keeps empty ``.no_exist/``
    markers there for files a repo lacks.
    """
    if not path.is_dir():
        return []
    found = {
        candidate.parent
        for candidate in path.rglob("*")
        if candidate.name in CHECKPOINT_CODE_FILES
        and candidate.is_file()
        and not any(part.startswith(".") for part in candidate.relative_to(path).parts[:-1])
    }
    return sorted(found)


def _checkpoint_code_findings(path: Path | None, *, trusted: bool) -> tuple[list[str], bool]:
    """``verify_checkpoint``'s findings from :func:`checkpoint_code_problems`, and whether any
    blocks. Nothing to add when nothing was fetched: that is already a failure of its own."""
    if path is None or not path.exists():
        return [], False
    directories = checkpoint_directories(path)
    if not directories:
        return [
            f"no {CHECKPOINT_CONFIG} or policy processor file at {path}, so what loading this "
            "checkpoint would fetch or run was not checked"
        ], False
    findings: list[str] = []
    blocking = False
    for directory in directories:
        prefix = "" if directory == path else f"{directory.relative_to(path).as_posix()}/"
        try:
            problems = read_local_checkpoint_files(directory).problems()
        except ValueError as exc:
            findings.append(f"{exc}. Refusing: what loading it would run was not checked")
            blocking = True
            continue
        for problem in problems:
            if trusted:
                findings.append(
                    f"{prefix}{problem} (accepted under {TRUST_CHECKPOINT_CODE_ENV}=1: code its "
                    "author chose may run when it loads)"
                )
            else:
                findings.append(
                    f"{prefix}{problem}. Refusing: set {TRUST_CHECKPOINT_CODE_ENV}=1 to accept "
                    "code the checkpoint chooses"
                )
                blocking = True
    return findings, blocking


__all__ = [
    "INTEGRITY_EAI_ID",
    "INTEGRITY_JSON",
    "INTEGRITY_FORMAT",
    "PICKLE_SUFFIXES",
    "SAFETENSORS_SUFFIX",
    "CheckpointFormat",
    "IntegrityVerdict",
    "CheckpointIntegrity",
    "detect_format",
    "digest_checkpoint",
    "verify_checkpoint",
    "skipped_record",
    "TRUST_CHECKPOINT_CODE_ENV",
    "CHECKPOINT_CONFIG",
    "CHECKPOINT_PREPROCESSOR",
    "CHECKPOINT_POSTPROCESSOR",
    "CHECKPOINT_CODE_FILES",
    "KNOWN_BACKBONE_REPOS",
    "KNOWN_POLICY_TYPES",
    "KNOWN_PROCESSOR_STEPS",
    "ACTION_TOKENIZER_STEP",
    "CheckpointCodeProblem",
    "CheckpointFiles",
    "checkpoint_code_problems",
    "checkpoint_code_report",
    "checkpoint_directories",
    "fetch_processor_state_files",
    "read_checkpoint_files",
    "read_local_checkpoint_files",
    "trust_checkpoint_code",
]
