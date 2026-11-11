# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Preflight checks that refuse a real-policy run before it measures the wrong thing.

Each check guards a failure that raises nothing. The run completes, the episodes roll out and the
report carries well-formed rates, and the rates describe a policy fed un-normalised state, an
untrained model, two swapped cameras, an image it never reads, a gripper command on the wrong
scale, or a simulator that moves the arm in another frame. Most have been reported upstream:

1. **Normaliser statistics** (https://github.com/huggingface/lerobot/issues/4047). lerobot 0.5.1's
   ``NormalizerProcessorStep`` normalises only the features it lists and returns a feature
   unchanged when no statistics are loaded for its key; ``lerobot/pi05_base`` ships a
   pre-processor whose normaliser lists no features and loads no statistics file.
2. **Rename map** (https://github.com/huggingface/lerobot/issues/4548). ``--rename-map`` replaces
   the map the checkpoint's pre-processor stores (lerobot 0.5.1 merges a step override as
   ``{**saved, **override}``), and ``make_policy`` skips its camera check whenever a rename map is
   given, so a map that swaps two cameras loads without a word.
3. **Weights loaded** (https://github.com/huggingface/lerobot/issues/4577). pi0 / pi0.5's
   ``from_pretrained`` print a warning and return the freshly initialised model when the weights
   cannot be applied, and the base class loads with ``strict=False``.
4. **Image sensitivity** (https://github.com/openvla/openvla/issues/346; the all-black /
   all-white test is the one suggested on https://github.com/openvla/openvla/issues/303). The
   first reports OpenVLA returning the same action for every image on transformers >= 4.50.
5. **Gripper convention**. LIBERO reads its gripper channel as -1 open, +1 closed; a checkpoint
   trained on a [0, 1] gripper is commanded half-closed when it means open.
6. **Frame consistency** (https://github.com/ARISE-Initiative/robosuite/issues/819): whether an
   end-effector delta lands in the frame the observation reports. Behind
   ``provael attack --preflight``, because it steps a simulator of its own.
7. A missing LIBERO simulator is refused in
   :func:`provael.suites.libero._ensure_libero_initialized`.
8. **An untuned base checkpoint on LIBERO** (https://github.com/huggingface/lerobot/issues/2533):
   ``lerobot/pi05_base``, the default the ``pi05`` entry loads, is refused there by name.
9. **loaded_checkpoint_source**, when a policy exposes it. No policy in lerobot 0.5.1 does; it is
   proposed for ``GrootPolicy`` in https://github.com/huggingface/lerobot/pull/4712.

FAIL CLOSED. A check that finds its failure raises :class:`PreflightError`. A check that cannot read
what it needs (a statistic, a file, a parameter, a declared canary) raises too, saying it could not
verify, rather than passing what it never looked at.

WHERE THEY RUN. :meth:`provael.policies.lerobot_adapter.LeRobotAdapter.load` calls
:func:`refuse_untuned_base_checkpoint` before the weights download and
:func:`check_lerobot_policy` once lerobot has built the policy and its processors, reading the live
objects. The CLI runs :func:`run_frame_preflight` on a suite of its own before the run, so the
run's environment, and the scene order of an unpinned LIBERO run, are untouched.

DUCK-TYPED, like :mod:`provael.policies.identity`: nothing here imports lerobot or torch at module
scope, so every rule is unit-tested on the CPU core against fakes shaped like the objects lerobot
0.5.1 builds, and the gated tests run the same functions against the real ones.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import numpy as np
import numpy.typing as npt

from provael.policies.lerobot_adapter import IncompatiblePolicyError
from provael.types import SuiteFeatures

if TYPE_CHECKING:
    from provael.suites.base import SuiteAdapter


class PreflightError(IncompatiblePolicyError):
    """A preflight check refused the run, or could not verify what it exists to check.

    A subclass of :class:`IncompatiblePolicyError`, so every command that already reports an
    unloadable checkpoint as one clean line reports a refused preflight the same way.
    """


#: Outcome statuses. A failure is never an outcome: it raises.
PASSED = "passed"
NOT_APPLICABLE = "not-applicable"

CHECK_SOURCE = "loaded-checkpoint-source"
CHECK_NORMALISER = "normaliser-statistics"
CHECK_RENAME = "rename-map"
CHECK_WEIGHTS = "weights-loaded"
CHECK_GRIPPER = "gripper-convention"
CHECK_IMAGE = "image-sensitivity"
CHECK_FRAME = "frame-consistency"
CHECK_BASE = "libero-checkpoint"


@dataclass(frozen=True)
class PreflightOutcome:
    """What one check that did not refuse found: ``passed``, or ``not-applicable`` and why."""

    check: str
    status: str
    detail: str


def _refuse(check: str, message: str) -> NoReturn:
    raise PreflightError(f"preflight [{check}] refused this run: {message}")


def _unverified(check: str, message: str) -> NoReturn:
    raise PreflightError(
        f"preflight [{check}] could not verify: {message}. Refusing rather than running a check "
        "that never looked."
    )


def _name(value: object) -> str:
    """A lerobot enum member (``FeatureType.STATE``) or a plain string, as its string value."""
    return str(getattr(value, "value", value))


def _to_numpy(value: Any) -> npt.NDArray[np.float64]:
    """A torch tensor (any dtype or device) or an array-like, as a float64 numpy array."""
    detach = getattr(value, "detach", None)
    if callable(detach):
        tensor = detach()
        tensor = tensor.float() if callable(getattr(tensor, "float", None)) else tensor
        tensor = tensor.cpu() if callable(getattr(tensor, "cpu", None)) else tensor
        value = tensor.numpy()
    return np.asarray(value, dtype=np.float64)


def _steps(pipeline: Any) -> list[Any]:
    steps = getattr(pipeline, "steps", None)
    return list(steps) if steps is not None else []


def _is_unnormaliser(step: Any) -> bool:
    return "unnormaliz" in type(step).__name__.lower()


def _is_normaliser(step: Any) -> bool:
    name = type(step).__name__.lower()
    return "normaliz" in name and "unnormaliz" not in name


def _config_of(step: Any) -> Mapping[str, Any]:
    get = getattr(step, "get_config", None)
    config = get() if callable(get) else None
    return config if isinstance(config, Mapping) else {}


def _stats_of(step: Any) -> dict[str, dict[str, Any]]:
    """``{feature key: {statistic: value}}`` from a step's flat ``state_dict`` (``key.stat``).

    lerobot 0.5.1's ``_NormalizationMixin.state_dict`` flattens ``_tensor_stats`` to
    ``"<feature>.<stat>"`` and its ``load_state_dict`` splits on the last dot; this does the same.
    """
    get = getattr(step, "state_dict", None)
    flat = get() if callable(get) else None
    stats: dict[str, dict[str, Any]] = {}
    if isinstance(flat, Mapping):
        for flat_key, value in flat.items():
            key, _, stat = str(flat_key).rpartition(".")
            if key:
                stats.setdefault(key, {})[stat] = value
    return stats


def _feature_types(features: Mapping[str, Any] | None) -> dict[str, str]:
    """``{key: "STATE" | "VISUAL" | ...}`` from lerobot ``PolicyFeature`` objects or plain dicts."""
    types: dict[str, str] = {}
    for key, feature in (features or {}).items():
        if isinstance(feature, Mapping):
            types[str(key)] = _name(feature.get("type"))
        else:
            types[str(key)] = _name(getattr(feature, "type", None))
    return types


# --------------------------------------------------------------------------------------------- #
# 9. loaded_checkpoint_source
# --------------------------------------------------------------------------------------------- #


def check_loaded_checkpoint_source(policy: Any, model_id: str) -> PreflightOutcome:
    """Hold a policy's own ``loaded_checkpoint_source`` record to the checkpoint that was asked for.

    The shape read is the one https://github.com/huggingface/lerobot/pull/4712 sets on
    ``GrootPolicy`` (``{"is_finetuned_checkpoint", "repo_id", "revision"}``), unmerged when this
    was written; no policy in lerobot 0.5.1 sets the attribute, so on 0.5.1 this reports
    not-applicable. A record whose ``repo_id`` is not the requested checkpoint is refused; one that
    is not a mapping, or carries no ``repo_id``, could not be verified and is refused too.
    """
    source = getattr(policy, "loaded_checkpoint_source", None)
    if source is None:
        return PreflightOutcome(
            CHECK_SOURCE,
            NOT_APPLICABLE,
            f"{type(policy).__name__} exposes no loaded_checkpoint_source (lerobot 0.5.1 sets "
            "it on no policy)",
        )
    if not isinstance(source, Mapping) or "repo_id" not in source:
        _unverified(
            CHECK_SOURCE,
            f"{type(policy).__name__}.loaded_checkpoint_source is {source!r}, not a mapping with a "
            "'repo_id'",
        )
    if str(source["repo_id"]) != str(model_id):
        _refuse(
            CHECK_SOURCE,
            f"the policy reports it loaded {source['repo_id']!r}, not the requested {model_id!r}",
        )
    record = ", ".join(f"{key}={source[key]!r}" for key in sorted(source))
    return PreflightOutcome(CHECK_SOURCE, PASSED, f"loaded_checkpoint_source: {record}")


# --------------------------------------------------------------------------------------------- #
# 1. normaliser statistics
# --------------------------------------------------------------------------------------------- #

#: The statistics each normalisation mode reads, as lerobot 0.5.1's
#: ``_NormalizationMixin._apply_transform`` reads them. A key with none of them loaded is returned
#: unchanged, which is the silent no-op this check exists for.
REQUIRED_STATS: dict[str, tuple[str, ...]] = {
    "MEAN_STD": ("mean", "std"),
    "MIN_MAX": ("min", "max"),
    "QUANTILES": ("q01", "q99"),
    "QUANTILE10": ("q10", "q90"),
}
IDENTITY = "IDENTITY"
#: lerobot 0.5.1 ``utils/constants.py``: the action key the (un)normaliser reads statistics under.
ACTION_KEY = "action"
ACTION_TYPE = "ACTION"


def _missing_statistics(step: Any, features: Mapping[str, str], *, observation: bool) -> list[str]:
    """Why each normalised feature in ``features`` would pass ``step`` unchanged; ``[]`` if none.

    An observation is normalised only when the step lists it (``_normalize_observation`` walks the
    step's own ``features``) and, where ``normalize_observation_keys`` is set, names it there; the
    action is looked up by key alone (``_normalize_action``). Either way the statistics the mode
    reads must be loaded.
    """
    config = _config_of(step)
    norm_map = {str(kind): _name(mode) for kind, mode in dict(config.get("norm_map") or {}).items()}
    listed = config.get("features")
    listed_keys = set(listed) if isinstance(listed, Mapping) else set()
    only = config.get("normalize_observation_keys")
    stats = _stats_of(step)
    step_name = type(step).__name__
    problems: list[str] = []
    for key, kind in sorted(features.items()):
        if observation and kind == ACTION_TYPE:
            continue
        mode = norm_map.get(kind, IDENTITY)
        if mode == IDENTITY:
            continue
        if observation and only is not None and key not in set(only):
            continue  # the checkpoint chose not to normalise it: a decision, not a missing file
        needed = REQUIRED_STATS.get(mode)
        if needed is None:
            problems.append(f"{key} uses normalisation mode {mode!r}, which lerobot 0.5.1 lacks")
            continue
        if observation and key not in listed_keys:
            problems.append(
                f"{key} ({kind}, {mode}) is not among the {step_name}'s features, so it reaches "
                "the model un-normalised"
            )
            continue
        missing = [stat for stat in needed if stat not in stats.get(key, {})]
        if missing:
            problems.append(
                f"{key} ({kind}, {mode}) has no {'/'.join(missing)} statistics loaded in the "
                f"{step_name}, so lerobot passes it on unchanged"
            )
    return problems


def check_normaliser_statistics(
    preprocessor: Any, postprocessor: Any, input_features: Mapping[str, Any] | None
) -> PreflightOutcome:
    """Refuse a policy whose normaliser would pass a normalised input, or its action, unchanged.

    ``input_features`` are the POLICY's (``policy.config.input_features``), not the normaliser's own
    list: a normaliser that lists nothing, as ``lerobot/pi05_base``'s does, would otherwise pass by
    having nothing to check. Read from the live pipelines' ``get_config()`` and ``state_dict()``.
    """
    types = _feature_types(input_features)
    if not types:
        _unverified(CHECK_NORMALISER, "the policy declares no input features")
    normalisers = [step for step in _steps(preprocessor) if _is_normaliser(step)]
    if not normalisers:
        _unverified(CHECK_NORMALISER, "the policy's pre-processor has no normaliser step")
    unnormalisers = [step for step in _steps(postprocessor) if _is_unnormaliser(step)]
    if not unnormalisers:
        _unverified(CHECK_NORMALISER, "the policy's post-processor has no unnormaliser step")
    problems = _missing_statistics(normalisers[0], types, observation=True)
    problems += _missing_statistics(unnormalisers[0], {ACTION_KEY: ACTION_TYPE}, observation=False)
    if problems:
        _refuse(
            CHECK_NORMALISER,
            "; ".join(problems)
            + ". The checkpoint needs its processor statistics (lerobot's "
            "migrate_policy_normalization script writes them for an older checkpoint): "
            "https://github.com/huggingface/lerobot/issues/4047",
        )
    return PreflightOutcome(
        CHECK_NORMALISER,
        PASSED,
        f"every input of {sorted(types)} that is normalised, and the action, has the statistics "
        "its mode reads loaded",
    )


# --------------------------------------------------------------------------------------------- #
# 2. rename map
# --------------------------------------------------------------------------------------------- #

#: lerobot 0.5.1 ``POLICY_PREPROCESSOR_DEFAULT_NAME`` + ".json", and its rename step's registry
#: name and class name in that file.
PREPROCESSOR_CONFIG = "policy_preprocessor.json"
RENAME_STEP_NAMES = ("rename_observations_processor", "RenameObservationsProcessorStep")


def locate_checkpoint_file(model_id: str, filename: str) -> Path | None:
    """``filename`` of ``model_id`` as it sits on this machine, never fetched: ``None`` if absent.

    A local directory is read in place; a Hub id is looked up in the Hugging Face cache with
    ``huggingface_hub.try_to_load_from_cache``, which makes no network call (the same lookup
    :func:`provael.policies.identity.resolve_hub_revision` uses). After a load, the cache holds the
    file lerobot just read.
    """
    local = Path(model_id)
    if local.is_dir():
        candidate = local / filename
        return candidate if candidate.is_file() else None
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    try:
        cached = try_to_load_from_cache(model_id, filename)
    except (OSError, ValueError):
        return None
    return Path(cached) if isinstance(cached, str) and Path(cached).is_file() else None


def embedded_rename_map(model_id: str) -> dict[str, str]:
    """The rename map ``model_id``'s own ``policy_preprocessor.json`` stores; ``{}`` if it has none.

    Read from the file and not from the live pipeline, because the live rename step holds the
    override: lerobot 0.5.1's ``DataProcessorPipeline._instantiate_step`` builds it from
    ``{**saved_cfg, **override}``, so once ``--rename-map`` is passed the stored map exists nowhere
    else. The file is the copy lerobot read (local directory or Hugging Face cache); nothing is
    fetched. Raises :class:`PreflightError` when the file is absent or unreadable.
    """
    path = locate_checkpoint_file(model_id, PREPROCESSOR_CONFIG)
    if path is None:
        _unverified(
            CHECK_RENAME,
            f"{PREPROCESSOR_CONFIG} of {model_id!r} is in neither a local directory nor the "
            "Hugging Face cache, so the rename map it stores cannot be compared with --rename-map",
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _unverified(CHECK_RENAME, f"{path} could not be read as JSON ({exc})")
    steps = config.get("steps") if isinstance(config, dict) else None
    if not isinstance(steps, list):
        _unverified(CHECK_RENAME, f"{path} has no list of steps")
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = step.get("registry_name") or str(step.get("class", "")).rsplit(".", 1)[-1]
        if name not in RENAME_STEP_NAMES:
            continue
        step_config = step.get("config") or {}
        mapping = step_config.get("rename_map", {}) if isinstance(step_config, dict) else None
        if not isinstance(mapping, dict):
            _unverified(CHECK_RENAME, f"the rename step in {path} carries no readable rename_map")
        return {str(key): str(value) for key, value in mapping.items()}
    return {}


def check_rename_map(
    requested: Mapping[str, str] | None, embedded: Mapping[str, str]
) -> PreflightOutcome:
    """Refuse a ``--rename-map`` that differs from the non-empty map the checkpoint stores.

    The override replaces the stored map wholesale, so any difference (a changed target, an added
    key, a dropped one) changes which camera feeds which input. A checkpoint that stores no map
    states no renaming, and the flag is then the only map there is: that passes, recorded.
    """
    if requested is None:
        return PreflightOutcome(
            CHECK_RENAME, NOT_APPLICABLE, "no --rename-map given; the checkpoint's own map applies"
        )
    wanted = {str(key): str(value) for key, value in requested.items()}
    stored = dict(embedded)
    if not stored:
        return PreflightOutcome(
            CHECK_RENAME,
            PASSED,
            f"the checkpoint stores no rename map; --rename-map {wanted} is the only one",
        )
    if wanted == stored:
        return PreflightOutcome(
            CHECK_RENAME, PASSED, f"--rename-map equals the stored map {stored}"
        )
    differences = [
        f"{key}: --rename-map -> {wanted.get(key)!r}, checkpoint -> {stored.get(key)!r}"
        for key in sorted(set(wanted) | set(stored))
        if wanted.get(key) != stored.get(key)
    ]
    _refuse(
        CHECK_RENAME,
        "--rename-map differs from the rename map the checkpoint's pre-processor stores, and "
        "lerobot would apply the flag in its place (" + "; ".join(differences) + "). Drop "
        "--rename-map to use the checkpoint's own map, or pass exactly that map: "
        "https://github.com/huggingface/lerobot/issues/4548",
    )


# --------------------------------------------------------------------------------------------- #
# 3. weights loaded
# --------------------------------------------------------------------------------------------- #

CONSTANT = "constant"
DEFAULT_LINEAR = "default-linear"
#: An untrained default-initialised weight's largest |value| is at most 1/sqrt(fan_in). Rounding a
#: draw just under the bound to bfloat16 can lift it by at most 2**-8 of itself (bfloat16 keeps
#: eight significant bits), so a trained weight must clear the bound by more than this fraction.
DEFAULT_LINEAR_MARGIN = 0.05


@dataclass(frozen=True)
class WeightCanary:
    """One named parameter whose freshly initialised values are known from its class's init code.

    ``init`` is :data:`CONSTANT` (every element is ``constant`` in a fresh instance) or
    :data:`DEFAULT_LINEAR` (a plain ``torch.nn.Linear`` weight, drawn from
    ``U(-1/sqrt(fan_in), 1/sqrt(fan_in))`` by ``reset_parameters``).
    """

    parameter: str
    init: str
    constant: float = 0.0


#: Three canaries per policy class, each read in lerobot 0.5.1 / transformers 5.3.0 / torch 2.10
#: (the versions the lock resolves for ``provael[lerobot]``) and checked against a trained
#: checkpoint's own file on 10 November 2026: ``HuggingFaceVLA/smolvla_libero`` (6721902),
#: ``lerobot/pi0`` (e4ed526) and ``lerobot/pi05_libero_finetuned_v044`` (7152f13). In each, every
#: canary is outside what a fresh initialisation can produce.
#:
#: SmolVLA's are all in the action head, deliberately. The action expert's RMSNorm weights are 1.0
#: in ``HuggingFaceVLA/smolvla_libero``, their initial value, so they cannot tell trained from
#: untrained; and its VLM is loaded from SmolVLM2 at construction (``load_vlm_weights`` is true),
#: so VLM tensors differ from their init whether or not the policy's own weights load. The head
#: linears (``VLAFlowMatching.__init__``) are plain ``nn.Linear`` and are touched by nothing else.
#:
#: pi0 / pi0.5 add one zero-initialised normalisation weight in the action expert and one in the
#: language model: ``PiGemmaRMSNorm`` sets ``weight`` (or, adaptive, ``dense.weight``) to zeros,
#: and ``PiGemmaModel`` installs its norms after ``GemmaModel.__init__`` has run ``post_init``, so
#: no transformers init overwrites them. A partial load that misses either component is caught.
WEIGHT_CANARIES: dict[str, tuple[WeightCanary, ...]] = {
    "SmolVLAPolicy": (
        WeightCanary("model.action_in_proj.weight", DEFAULT_LINEAR),
        WeightCanary("model.action_out_proj.weight", DEFAULT_LINEAR),
        WeightCanary("model.action_time_mlp_in.weight", DEFAULT_LINEAR),
    ),
    "PI0Policy": (
        WeightCanary("model.action_out_proj.weight", DEFAULT_LINEAR),
        WeightCanary("model.paligemma_with_expert.gemma_expert.model.norm.weight", CONSTANT, 0.0),
        WeightCanary(
            "model.paligemma_with_expert.paligemma.model.language_model.norm.weight", CONSTANT, 0.0
        ),
    ),
    "PI05Policy": (
        WeightCanary("model.action_out_proj.weight", DEFAULT_LINEAR),
        WeightCanary(
            "model.paligemma_with_expert.gemma_expert.model.norm.dense.weight", CONSTANT, 0.0
        ),
        WeightCanary(
            "model.paligemma_with_expert.paligemma.model.language_model.norm.weight", CONSTANT, 0.0
        ),
    ),
}


def _looks_untrained(canary: WeightCanary, values: npt.NDArray[np.float64]) -> str | None:
    """Why ``values`` is what a fresh initialisation of ``canary`` could hold, or ``None``."""
    if canary.init == CONSTANT:
        if values.size and bool(np.all(values == canary.constant)):
            return f"every element is {canary.constant:g}, its initial value"
        return None
    if canary.init == DEFAULT_LINEAR:
        if values.ndim != 2 or values.shape[1] == 0:
            _unverified(CHECK_WEIGHTS, f"{canary.parameter} is not a 2-D linear weight")
        bound = 1.0 / math.sqrt(values.shape[1])
        peak = float(np.max(np.abs(values))) if values.size else 0.0
        if not peak > bound * (1.0 + DEFAULT_LINEAR_MARGIN):
            return (
                f"its largest |weight| {peak:.4g} is inside the default init's range "
                f"±{bound:.4g} (1/sqrt(fan_in={values.shape[1]}))"
            )
        return None
    _unverified(CHECK_WEIGHTS, f"{canary.parameter} declares an unknown init {canary.init!r}")


def check_weights_loaded(
    policy: Any, canaries: Sequence[WeightCanary] | None = None
) -> PreflightOutcome:
    """Refuse a policy whose named canary tensors still hold what a fresh initialisation holds.

    METHOD CHOSEN, AND WHY. Each canary is compared with the set of values a fresh initialisation
    of its submodule can produce, read from the class's own init code; no second model and no
    re-initialised copy is built, and the cost is one pass over three tensors. A constant init is
    compared element by element; a default ``nn.Linear`` init has support
    ``[-1/sqrt(fan_in), 1/sqrt(fan_in)]``, and an untrained weight never leaves it. A deepcopy of
    each submodule re-initialised with its own init was considered and rejected: for a randomly
    initialised layer the copy is a new random draw, so "differs from the copy" holds for an
    untrained tensor too and the check would pass every untrained head; transformers 5.3.0's init
    helpers (``transformers.initialization``) skip any tensor flagged ``_is_hf_initialized``, so a
    copied submodule's init can return it unchanged; and lerobot's RMSNorm classes expose no
    ``reset_parameters``.

    A policy class with no canaries declared in :data:`WEIGHT_CANARIES` could not be verified and
    is refused: canaries are added after reading the class's init and a trained checkpoint.
    """
    cls = type(policy).__name__
    declared = tuple(canaries) if canaries is not None else WEIGHT_CANARIES.get(cls, ())
    if not declared:
        _unverified(
            CHECK_WEIGHTS,
            f"no weights-loaded canaries are declared for {cls}; add three to WEIGHT_CANARIES in "
            "provael.policies.preflight after reading its init code and a trained checkpoint",
        )
    get = getattr(policy, "get_parameter", None)
    if not callable(get):
        _unverified(CHECK_WEIGHTS, f"{cls} has no get_parameter to read its weights by name")
    untrained: list[str] = []
    for canary in declared:
        try:
            tensor = get(canary.parameter)
        except AttributeError as exc:
            _unverified(CHECK_WEIGHTS, f"{cls} has no parameter {canary.parameter!r} ({exc})")
        reason = _looks_untrained(canary, _to_numpy(tensor))
        if reason is not None:
            untrained.append(f"{canary.parameter}: {reason}")
    if untrained:
        _refuse(
            CHECK_WEIGHTS,
            f"{cls} looks freshly initialised, not loaded: " + "; ".join(untrained) + ". A load "
            "error swallowed inside from_pretrained returns the untrained model: "
            "https://github.com/huggingface/lerobot/issues/4577",
        )
    return PreflightOutcome(
        CHECK_WEIGHTS,
        PASSED,
        f"{', '.join(canary.parameter for canary in declared)} are outside what a fresh "
        f"initialisation of {cls} holds",
    )


# --------------------------------------------------------------------------------------------- #
# 4. image sensitivity
# --------------------------------------------------------------------------------------------- #

#: Two forward passes that differ only in the frame (every camera all black, then all white; the
#: same state, instruction and sampler seed) must move the action by more than this: the largest
#: |difference| over the action vector, in the policy's normalised action space. A stated design
#: threshold, far above float round-off between two runs of one input; it has not been calibrated
#: against a real policy's response.
IMAGE_SENSITIVITY_EPSILON = 1e-3
PROBE_SEED = 0
PROBE_INSTRUCTION = "pick up the object"
#: Feature types filled with zeros in the probe batch; VISUAL features get the probe's fill.
_ZERO_FILLED = ("STATE", "ENV")


def probe_batch(input_features: Mapping[str, Any], fill: float, *, torch: Any) -> dict[str, Any]:
    """A one-sample batch: every camera filled with ``fill``, state zero, a fixed instruction.

    Keys and shapes are the policy's own (``config.input_features``), the batch ``_act_offline``
    builds from a recorded frame: keys starting ``observation`` and a ``task`` list, which lerobot
    0.5.1's ``batch_to_transition`` maps to the observation and the complementary data.
    """
    batch: dict[str, Any] = {}
    for key, feature in input_features.items():
        shape = (1, *(int(size) for size in getattr(feature, "shape", ())))
        kind = _name(getattr(feature, "type", None))
        if kind == "VISUAL":
            batch[key] = torch.full(shape, float(fill), dtype=torch.float32)
        elif kind in _ZERO_FILLED:
            batch[key] = torch.zeros(shape, dtype=torch.float32)
    batch["task"] = [PROBE_INSTRUCTION]
    return batch


def probe_image_sensitivity(policy: Any, preprocess: Any, *, torch: Any) -> tuple[Any, Any]:
    """The policy's first action on an all-black and on an all-white frame, sampler seeded alike.

    Runs the policy's own pre-processor and ``select_action`` after a ``reset``, the path
    :meth:`~provael.policies.lerobot_adapter.LeRobotAdapter.act` takes, inside
    ``torch.random.fork_rng`` so the process RNG is left where it was, and resets the policy after,
    so no queued chunk survives into the run.
    """
    features = getattr(getattr(policy, "config", None), "input_features", None) or {}
    if not any(_name(getattr(f, "type", None)) == "VISUAL" for f in features.values()):
        _unverified(CHECK_IMAGE, f"{type(policy).__name__} declares no image input")

    def first_action(fill: float) -> Any:
        batch = dict(preprocess(probe_batch(features, fill, torch=torch)))
        policy.reset()
        torch.manual_seed(PROBE_SEED)
        with torch.inference_mode():
            return policy.select_action(batch)

    try:
        with torch.random.fork_rng():
            black = first_action(0.0)
            white = first_action(1.0)
    finally:
        policy.reset()
    return black, white


def check_image_sensitivity(
    black: Any, white: Any, epsilon: float = IMAGE_SENSITIVITY_EPSILON
) -> PreflightOutcome:
    """Refuse a policy whose action does not move between an all-black and an all-white frame."""
    a, b = _to_numpy(black).reshape(-1), _to_numpy(white).reshape(-1)
    if a.size == 0 or a.shape != b.shape:
        _unverified(CHECK_IMAGE, f"the probe returned actions of shapes {a.shape} and {b.shape}")
    moved = float(np.max(np.abs(b - a)))
    if not moved > epsilon:
        _refuse(
            CHECK_IMAGE,
            f"the action moved by {moved:.3g} between an all-black and an all-white frame (it must "
            f"move by more than {epsilon:g}), so the policy is not reading the image: "
            "https://github.com/openvla/openvla/issues/346",
        )
    return PreflightOutcome(
        CHECK_IMAGE,
        PASSED,
        f"the action moved by {moved:.3g} (> {epsilon:g}) between an all-black and an all-white "
        "frame",
    )


# --------------------------------------------------------------------------------------------- #
# 5. gripper convention
# --------------------------------------------------------------------------------------------- #

#: Slack for float32 statistics when testing a range or the Bhatia-Davis variance bound.
GRIPPER_TOLERANCE = 1e-4


def action_statistics(*pipelines: Any) -> dict[str, npt.NDArray[np.float64]]:
    """``{statistic: per-channel values}`` for the action, from the first step that carries them.

    The post-processor's unnormaliser first: its statistics are the ones that turn the policy's
    output into the command the simulator receives.
    """
    for pipeline in pipelines:
        for step in _steps(pipeline):
            if "normaliz" not in type(step).__name__.lower():
                continue
            stats = _stats_of(step).get(ACTION_KEY)
            if stats:
                return {name: _to_numpy(value).reshape(-1) for name, value in stats.items()}
    return {}


def check_gripper_convention(
    stats: Mapping[str, npt.NDArray[np.float64]],
    index: int,
    expected: tuple[float, float],
) -> PreflightOutcome:
    """Refuse a checkpoint whose training data used another gripper range than the suite reads.

    The checkpoint's own action statistics say which range its gripper channel was trained in.
    With ``min``/``max``, the channel must lie inside ``expected`` and reach both sides of zero.
    With only ``mean``/``std`` (``HuggingFaceVLA/smolvla_libero`` stores no others), it must be
    feasible inside ``expected`` and infeasible for a [0, 1] channel, by the Bhatia-Davis bound:
    a value confined to ``[lo, hi]`` has a variance of at most ``(hi - mean) * (mean - lo)``. A ±1
    channel meets that bound with equality; a [0, 1] channel has a mean in [0, 1] and a variance of
    at most ``mean * (1 - mean)``. Which end opens the gripper is not visible in the statistics and
    is not checked.
    """
    lo, hi = expected
    tol = GRIPPER_TOLERANCE

    def at(name: str) -> float | None:
        values = stats.get(name)
        return float(values[index]) if values is not None and values.size > index else None

    low, high = at("min"), at("max")
    mean, std = at("mean"), at("std")
    if low is not None and high is not None:
        found = f"the training data's gripper channel {index} runs from {low:g} to {high:g}"
        if not (lo - tol <= low < 0.0 < high <= hi + tol):
            _refuse(
                CHECK_GRIPPER,
                f"{found}, and this suite reads it in [{lo:g}, {hi:g}] with -1 open and +1 closed",
            )
        return PreflightOutcome(CHECK_GRIPPER, PASSED, found)
    if mean is not None and std is not None:
        variance = std * std
        found = f"the training data's gripper channel {index} has mean {mean:.4g} and std {std:.4g}"
        fits_expected = lo - tol <= mean <= hi + tol and variance <= (hi - mean) * (mean - lo) + tol
        fits_unit = -tol <= mean <= 1.0 + tol and variance <= mean * (1.0 - mean) + tol
        if not fits_expected or fits_unit:
            _refuse(
                CHECK_GRIPPER,
                f"{found}, which "
                + ("fits a [0, 1] gripper" if fits_unit else f"cannot lie in [{lo:g}, {hi:g}]")
                + f"; this suite reads the channel in [{lo:g}, {hi:g}] with -1 open and +1 closed",
            )
        return PreflightOutcome(
            CHECK_GRIPPER, PASSED, f"{found}: feasible in [{lo:g}, {hi:g}], not in [0, 1]"
        )
    _unverified(
        CHECK_GRIPPER,
        f"the checkpoint's action statistics give neither min/max nor mean/std for channel "
        f"{index} (statistics found: {sorted(stats)})",
    )


# --------------------------------------------------------------------------------------------- #
# 8. an untuned base checkpoint on LIBERO
# --------------------------------------------------------------------------------------------- #

#: Base checkpoints never fine-tuned on LIBERO, and the LIBERO fine-tune to pass instead.
#: ``lerobot/pi05_libero_finetuned_v044`` is the checkpoint the committed pi0.5 run used
#: (``results/pi05_libero_object_2026-09-18``, ``report.json`` ``model``).
LIBERO_UNTUNED_BASE_CHECKPOINTS: dict[str, str] = {
    "lerobot/pi05_base": "lerobot/pi05_libero_finetuned_v044",
}


def _names_libero(features: SuiteFeatures | None) -> bool:
    from provael.suites.libero import LIBERO_TASK_SUITES

    return features is not None and features.task_suite in LIBERO_TASK_SUITES


def refuse_untuned_base_checkpoint(model_id: str, features: SuiteFeatures | None) -> None:
    """Refuse, before its weights download, a base checkpoint on LIBERO that was never tuned for it.

    The same answer ``make_policy`` already gives ``lerobot/smolvla_base`` on LIBERO (an
    :class:`IncompatiblePolicyError` naming the fine-tuned checkpoint), given here by name because
    the pi0.5 base would otherwise reach the simulator with a misleading message or a traceback.
    """
    tuned = LIBERO_UNTUNED_BASE_CHECKPOINTS.get(model_id)
    if tuned is None or not _names_libero(features):
        return
    _refuse(
        CHECK_BASE,
        f"{model_id} is a pre-trained base checkpoint that was not fine-tuned on LIBERO; LeRobot "
        "fine-tuned the pi0.5 weights for LIBERO rather than evaluating them out of the box "
        "(https://github.com/huggingface/lerobot/issues/2533). Pass a LIBERO-fine-tuned "
        f"checkpoint, e.g. --model {tuned} (the checkpoint the committed pi05 LIBERO run used)",
    )


# --------------------------------------------------------------------------------------------- #
# the adapter's load-time preflight
# --------------------------------------------------------------------------------------------- #


def check_lerobot_policy(
    policy: Any,
    preprocessor: Any,
    postprocessor: Any,
    *,
    model_id: str,
    rename_map: Mapping[str, str] | None,
    features: SuiteFeatures | None,
    torch: Any = None,
) -> tuple[PreflightOutcome, ...]:
    """Run checks 9, 1, 2, 3, 5 and 4, in that order, on what lerobot built; raise on the first.

    Cheap reads first and the two forward passes last. The gripper check runs on a LIBERO suite
    only, where the expected range is known. ``torch`` is injectable so the CPU tests can drive the
    probe with a fake; a real load imports it.
    """
    from provael.scoring.action_schema import SEVEN_DOF_DELTA_SCHEMA
    from provael.suites.libero import LIBERO_GRIPPER_RANGE

    config = getattr(policy, "config", None)
    outcomes = [
        check_loaded_checkpoint_source(policy, model_id),
        check_normaliser_statistics(
            preprocessor, postprocessor, getattr(config, "input_features", None)
        ),
        check_rename_map(
            rename_map, embedded_rename_map(model_id) if rename_map is not None else {}
        ),
        check_weights_loaded(policy),
    ]
    if _names_libero(features):
        outcomes.append(
            check_gripper_convention(
                action_statistics(postprocessor, preprocessor),
                SEVEN_DOF_DELTA_SCHEMA.gripper_indices[0],
                LIBERO_GRIPPER_RANGE,
            )
        )
    else:
        outcomes.append(
            PreflightOutcome(CHECK_GRIPPER, NOT_APPLICABLE, "not a LIBERO suite; no range to hold")
        )
    if torch is None:
        import torch as torch_module

        torch = torch_module
    try:
        black, white = probe_image_sensitivity(policy, preprocessor, torch=torch)
    except PreflightError:
        raise
    except Exception as exc:  # noqa: BLE001 - a probe that cannot run has verified nothing
        _unverified(CHECK_IMAGE, f"the probe's forward pass failed ({type(exc).__name__}: {exc})")
    outcomes.append(check_image_sensitivity(black, white))
    return tuple(outcomes)


# --------------------------------------------------------------------------------------------- #
# 6. frame consistency (provael attack --preflight)
# --------------------------------------------------------------------------------------------- #

#: The probe: ``FRAME_COMMAND`` on the first translation channel for ``FRAME_STEPS`` steps must move
#: the end-effector at least ``FRAME_MIN_TRAVEL_M`` with a cosine of at least
#: ``FRAME_MIN_COSINE`` to that axis in the observation's frame. Stated design thresholds; none has
#: been calibrated on a live simulator.
FRAME_STEPS = 5
FRAME_COMMAND = 0.5
FRAME_MIN_TRAVEL_M = 0.005
FRAME_MIN_COSINE = 0.9
#: The gripper value held during the probe: LIBERO's no-op action keeps it at -1, open (lerobot
#: 0.5.1 ``get_libero_dummy_action``), so the probe grasps nothing on its way.
FRAME_GRIPPER_HOLD = -1.0


def check_frame_consistency(
    suite: SuiteAdapter,
    task: str,
    seed: int,
    *,
    steps: int = FRAME_STEPS,
    command: float = FRAME_COMMAND,
) -> PreflightOutcome:
    """Command a +x end-effector delta for a few steps and refuse unless the pose moved along +x.

    An invariant rather than a unit test: if the simulator applies the delta in another frame than
    the one its observation reports the pose in, the arm still moves and every rate still comes
    out, and nothing else notices (https://github.com/ARISE-Initiative/robosuite/issues/819). Uses
    only the suite's public surface (``action_schema``, ``reset``, ``step`` and ``ee_pos``). One
    axis is probed, so a frame that agrees with the world on x alone passes.
    """
    schema = suite.action_schema()
    if schema is None or not schema.translation_indices:
        _unverified(CHECK_FRAME, f"suite {suite.name!r} declares no translation channels")
    start = suite.reset(task, seed).get("ee_pos")
    if start is None:
        _unverified(CHECK_FRAME, f"suite {suite.name!r} reports no end-effector position")
    action = np.zeros(schema.total_dim, dtype=np.float32)
    action[schema.translation_indices[0]] = command
    for gripper in schema.gripper_indices:
        action[gripper] = FRAME_GRIPPER_HOLD
    end: Iterable[float] = start
    taken = 0
    for _ in range(steps):
        _obs, done, state = suite.step(action)
        position = state.get("ee_pos")
        if position is None:
            _unverified(CHECK_FRAME, f"suite {suite.name!r} stopped reporting ee_pos at a step")
        end = position
        taken += 1
        if done:  # LIBERO resets itself after a terminal step; later poses are another episode's
            break
    delta = np.asarray(list(end), dtype=np.float64) - np.asarray(list(start), dtype=np.float64)
    travel = float(np.linalg.norm(delta))
    moved = ", ".join(f"{v:+.4f}" for v in delta)
    summary = f"a +x command of {command:g} for {taken} step(s) moved the end-effector ({moved}) m"
    if not travel >= FRAME_MIN_TRAVEL_M:
        _refuse(CHECK_FRAME, f"{summary}, under the {FRAME_MIN_TRAVEL_M:g} m it must travel")
    cosine = float(delta[0] / travel)
    if not cosine >= FRAME_MIN_COSINE:
        _refuse(
            CHECK_FRAME,
            f"{summary}, at a cosine of {cosine:.3f} to +x (it must be at least "
            f"{FRAME_MIN_COSINE:g}): the simulator applies the delta in another frame than it "
            "reports the pose in (https://github.com/ARISE-Initiative/robosuite/issues/819)",
        )
    return PreflightOutcome(CHECK_FRAME, PASSED, f"{summary}; cosine to +x {cosine:.3f}")


def run_frame_preflight(
    suite_name: str, tasks: Sequence[str] | None, seed: int
) -> PreflightOutcome:
    """:func:`check_frame_consistency` on a suite of its own, built for the run's first task.

    Its own suite, so its own environment: the run builds another, so the frame check's reset and
    steps do not move the reset counter the run's unpinned LIBERO scenes are walked by.
    """
    from provael.suites import make_suite

    suite = make_suite(suite_name, tasks=list(tasks) if tasks else None)
    chosen = list(tasks) if tasks else suite.tasks()
    if not chosen:
        _unverified(CHECK_FRAME, f"suite {suite_name!r} exposes no task to probe")
    return check_frame_consistency(suite, chosen[0], seed)


__all__ = [
    "CHECK_BASE",
    "CHECK_FRAME",
    "CHECK_GRIPPER",
    "CHECK_IMAGE",
    "CHECK_NORMALISER",
    "CHECK_RENAME",
    "CHECK_SOURCE",
    "CHECK_WEIGHTS",
    "CONSTANT",
    "DEFAULT_LINEAR",
    "IMAGE_SENSITIVITY_EPSILON",
    "LIBERO_UNTUNED_BASE_CHECKPOINTS",
    "NOT_APPLICABLE",
    "PASSED",
    "WEIGHT_CANARIES",
    "PreflightError",
    "PreflightOutcome",
    "WeightCanary",
    "action_statistics",
    "check_frame_consistency",
    "check_gripper_convention",
    "check_image_sensitivity",
    "check_lerobot_policy",
    "check_loaded_checkpoint_source",
    "check_normaliser_statistics",
    "check_rename_map",
    "check_weights_loaded",
    "embedded_rename_map",
    "locate_checkpoint_file",
    "probe_batch",
    "probe_image_sensitivity",
    "refuse_untuned_base_checkpoint",
    "run_frame_preflight",
]
