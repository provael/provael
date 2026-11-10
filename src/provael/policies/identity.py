# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Resolve the identity of the policy that actually executed — the helpers behind issue #227.

WHY A MODULE OF PURE FUNCTIONS. The facts that make two deployments executable-inequivalent
(Tai 2026, arXiv:2606.03724) live in objects the CPU build cannot import: a Hub cache path, a
LeRobot post-processing pipeline, a torch state dict. Everything here is duck-typed over those
objects — a path string, an object with ``get_config()`` and ``state_dict()``, a sequence of
steps — so each resolution rule is unit-tested on the CPU core against fakes shaped like the real
thing, and the adapter that owns the heavy objects only wires them together.

THE RULE ON FAILURE. A helper that cannot resolve something returns ``None``; nothing here
invents a value, and nothing here swallows a typed exception it did not expect. ``None`` in a
report reads as "not resolved" — the same convention as ``resolved_device``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from provael.types import ActionUnnormaliser, InputNormaliser

#: The segment a Hugging Face Hub cache path carries between the repo directory and the files of
#: one resolved commit: ``…/models--org--name/snapshots/<commit sha>/config.json``.
_SNAPSHOT_SEGMENT = re.compile(r"/snapshots/([0-9a-f]{7,64})(?:/|$)")

#: The feature-type key the normalisation map uses for the action stream, and the prefix its
#: statistics carry in a flat state dict (``action.mean``, ``action.std``, …).
ACTION_FEATURE = "ACTION"
ACTION_STATS_PREFIX = "action."
#: The feature-type keys the normalisation map uses for the two observation streams.
STATE_FEATURE = "STATE"
VISUAL_FEATURE = "VISUAL"

#: The files lerobot 0.5.1 loads a checkpoint's processors and weights from, read in its source on
#: 10 November 2026: ``make_pre_post_processors`` loads ``policy_preprocessor.json`` and
#: ``policy_postprocessor.json`` (plus each step's ``state_file``), and
#: ``PreTrainedPolicy.from_pretrained`` loads exactly one weight file, ``model.safetensors``.
PREPROCESSOR_CONFIG = "policy_preprocessor.json"
POSTPROCESSOR_CONFIG = "policy_postprocessor.json"
WEIGHTS_FILE = "model.safetensors"


def revision_from_cache_path(path: str | None) -> str | None:
    """The commit sha embedded in a Hub cache path, or ``None`` when the path carries none.

    A file loaded from ``~/.cache/huggingface/hub`` sits under ``snapshots/<sha>/``; a file loaded
    from a local checkout does not. Reading the sha off the path is exact and needs no network,
    which matters because the run may be offline by the time identity is recorded.
    """
    if not path:
        return None
    match = _SNAPSHOT_SEGMENT.search(str(path).replace("\\", "/"))
    return match.group(1) if match else None


def resolve_hub_revision(repo_id: str, filename: str = "config.json") -> str | None:
    """The resolved commit of ``repo_id`` as cached locally, or ``None``.

    Uses ``huggingface_hub.try_to_load_from_cache``, which never touches the network: after a
    successful ``from_pretrained`` the config is in the cache, and the cache path names the commit
    the Hub resolved for whatever revision was requested. A local directory, a repo that was not
    fetched through the cache, or a missing ``huggingface_hub`` all resolve to ``None``.
    """
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return None
    try:
        cached = try_to_load_from_cache(repo_id, filename)
    except (OSError, ValueError):
        return None
    return revision_from_cache_path(cached if isinstance(cached, str) else None)


def _as_float_list(value: Any) -> list[float] | float | list[Any]:
    """A tensor / ndarray / scalar / list as plain Python floats, exactly (no rounding)."""
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        detached = getattr(value, "detach", None)
        source = detached() if callable(detached) else value
        cpu = getattr(source, "cpu", None)
        source = cpu() if callable(cpu) else source
        return source.tolist()  # type: ignore[no-any-return]
    if isinstance(value, list | tuple):
        return [_as_float_list(v) for v in value]
    return float(value)


def _digest_stats(stats: Mapping[str, Any], keep: Callable[[str], bool]) -> str | None:
    """sha256 over the canonical form of the statistics whose key ``keep`` accepts, else None."""
    kept = {key: _as_float_list(value) for key, value in stats.items() if keep(str(key))}
    if not kept:
        return None
    text = json.dumps(kept, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stats_digest(stats: Mapping[str, Any]) -> str | None:
    """sha256 over the canonical form of the statistics that apply to the ACTION stream.

    Takes a flat ``state_dict``-shaped mapping (``"action.mean" -> tensor``) and keeps only the
    ``action.`` entries. Values are serialised exactly as loaded — a digest over rounded numbers
    would call two different unnormalisers the same. ``None`` when no action statistic is present
    (an IDENTITY unnormaliser has none, and that is a fact rather than a failure).
    """
    return _digest_stats(stats, lambda key: key.startswith(ACTION_STATS_PREFIX))


def observation_stats_digest(stats: Mapping[str, Any]) -> str | None:
    """The same digest over every statistic EXCEPT the action's: what an input normaliser applies.

    A pre-processor's normaliser carries the action statistics too (lerobot normalises the action
    during training), and they do not touch an observation at inference, so they are left out:
    two checkpoints whose state statistics agree get one input digest whatever their action
    statistics say, which :func:`stats_digest` records separately.
    """
    return _digest_stats(stats, lambda key: not key.startswith(ACTION_STATS_PREFIX))


def _is_unnormaliser(step: Any) -> bool:
    return "unnormaliz" in type(step).__name__.lower()


def _is_normaliser(step: Any) -> bool:
    name = type(step).__name__.lower()
    return "normaliz" in name and "unnormaliz" not in name


def _config_of(step: Any) -> Mapping[str, Any]:
    config = step.get_config() if callable(getattr(step, "get_config", None)) else {}
    return config if isinstance(config, Mapping) else {}


def input_normaliser_from_pipeline(pipeline: Any, *, source: str) -> InputNormaliser | None:
    """Read the observation normaliser's modes and statistics off a live pre-processing pipeline.

    The input-side twin of :func:`unnormaliser_from_pipeline`, duck-typed the same way: the first
    step whose class name says "Normaliz…" (and not "Unnormaliz…") is the one; its
    ``get_config()["norm_map"]`` names the mode per feature type and its ``state_dict()`` carries
    the statistics. ``None`` when the pipeline has no such step.
    """
    steps: Iterable[Any] = getattr(pipeline, "steps", None) or ()
    for step in steps:
        if not _is_normaliser(step):
            continue
        norm_map = _config_of(step).get("norm_map", {})
        norm_map = norm_map if isinstance(norm_map, Mapping) else {}
        state_mode, visual_mode = norm_map.get(STATE_FEATURE), norm_map.get(VISUAL_FEATURE)
        state = step.state_dict() if callable(getattr(step, "state_dict", None)) else {}
        return InputNormaliser(
            state_mode=str(state_mode) if state_mode is not None else None,
            visual_mode=str(visual_mode) if visual_mode is not None else None,
            stats_digest=observation_stats_digest(state) if isinstance(state, Mapping) else None,
            source=source,
        )
    return None


def rename_map_from_pipeline(pipeline: Any) -> dict[str, str] | None:
    """The observation rename map a live pre-processor applies: ``{}`` when it has no rename step.

    lerobot's ``RenameObservationsProcessorStep`` carries the map in ``get_config()``, whether the
    checkpoint's own processor config set it or the adapter's ``--rename-map`` overrode it, so this
    is the map that ran, not the one requested. ``None`` for no pipeline, or a rename step whose map
    cannot be read.
    """
    steps = getattr(pipeline, "steps", None)
    if steps is None:
        return None
    for step in steps:
        if "rename" not in type(step).__name__.lower():
            continue
        mapping = _config_of(step).get("rename_map")
        if not isinstance(mapping, Mapping):
            return None
        return {str(key): str(value) for key, value in mapping.items()}
    return {}


def camera_keys_of(*configs: Any) -> list[str] | None:
    """The camera inputs a policy consumes, in order: the first config's ``image_features`` keys.

    lerobot's ``PreTrainedConfig.image_features`` is the VISUAL subset of ``input_features`` in
    the order the policy reads them (SmolVLA's ``prepare_images`` walks it). ``None`` when no
    config exposes it.
    """
    for config in configs:
        features = getattr(config, "image_features", None) if config is not None else None
        if isinstance(features, Mapping):
            return [str(key) for key in features]
    return None


def _int_field(config: Any, name: str) -> int | None:
    value = getattr(config, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def denoising_steps_of(config: Any) -> int | None:
    """Denoising steps per chunk: SmolVLA's ``num_steps``, else pi0 / pi0.5's
    ``num_inference_steps``.

    Read as set on the config. A diffusion config that leaves ``num_inference_steps`` at ``None``
    falls back to its training schedule inside lerobot; that fallback is not applied here, so it
    records ``None`` rather than a value this function worked out.
    """
    for name in ("num_steps", "num_inference_steps"):
        steps = _int_field(config, name)
        if steps is not None:
            return steps
    return None


def temporal_ensemble_coeff_of(config: Any) -> float | None:
    """ACT's ``temporal_ensemble_coeff`` where the config has one and sets it, else ``None``."""
    value = getattr(config, "temporal_ensemble_coeff", None)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def discrete_state_input_of(config: Any) -> bool | None:
    """``discrete_state_input`` where the config carries it (openpi's pi0.5), else ``None``."""
    value = getattr(config, "discrete_state_input", None)
    return value if isinstance(value, bool) else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate_checkpoint_file(model_id: str, filename: str, base: Path | None = None) -> Path | None:
    """Where ``filename`` of checkpoint ``model_id`` was loaded from, without the network.

    ``base`` is tried first for a step's state file, which is lerobot's own rule (its
    ``_load_step_state`` looks beside the loaded config before the Hub). A local directory is read
    directly; a Hub repo id is looked up in the local cache with
    ``huggingface_hub.try_to_load_from_cache``. ``None`` when the file is not there.
    """
    if base is not None and (base / filename).is_file():
        return base / filename
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


def processor_files_digest(model_id: str, config_filename: str) -> str | None:
    """sha256 over a processor pipeline's files as lerobot loads them, or ``None``.

    The digest is taken over the canonical JSON list of ``[filename, sha256]`` pairs: the
    pipeline's config file first, then each step's ``state_file`` in step order. Per-file hashes
    are what a reader can check independently (``sha256sum``, the Hub's LFS hashes), and the list
    is what this recomputes from them. A state file the config names and the cache does not hold
    makes the whole digest ``None``: half the files is not the pipeline that ran.
    """
    config_path = locate_checkpoint_file(model_id, config_filename)
    if config_path is None:
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pairs: list[list[str]] = [[config_filename, _file_sha256(config_path)]]
    steps = config.get("steps") if isinstance(config, dict) else None
    for step in steps if isinstance(steps, list) else []:
        state_file = step.get("state_file") if isinstance(step, dict) else None
        if not isinstance(state_file, str) or not state_file:
            continue
        path = locate_checkpoint_file(model_id, state_file, base=config_path.parent)
        if path is None:
            return None
        pairs.append([state_file, _file_sha256(path)])
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode("utf-8")).hexdigest()


def weights_file_digest(model_id: str, filename: str = WEIGHTS_FILE) -> str | None:
    """sha256 of the weight file a checkpoint loaded (what ``sha256sum`` prints), or ``None``."""
    path = locate_checkpoint_file(model_id, filename)
    return _file_sha256(path) if path is not None else None


def step_names(pipeline: Any) -> list[str]:
    """The class names of a pipeline's steps in order; ``[]`` for ``None`` or a step-less object."""
    steps = getattr(pipeline, "steps", None)
    if steps is None:
        return []
    return [type(step).__name__ for step in steps]


def unnormaliser_from_pipeline(pipeline: Any, *, source: str) -> ActionUnnormaliser | None:
    """Read the ACTION unnormalisation mode and statistics off a live post-processing pipeline.

    Duck-typed over LeRobot's ``PolicyProcessorPipeline``: the first step whose class name says
    "Unnormaliz…" is the one; its ``get_config()["norm_map"]`` names the mode per feature type and
    its ``state_dict()`` carries the statistics. ``None`` when the pipeline has no such step —
    an adapter that hands raw outputs on has no unnormaliser to record, and saying so is correct.
    """
    steps: Iterable[Any] = getattr(pipeline, "steps", None) or ()
    for step in steps:
        if not _is_unnormaliser(step):
            continue
        config = step.get_config() if callable(getattr(step, "get_config", None)) else {}
        norm_map = config.get("norm_map", {}) if isinstance(config, Mapping) else {}
        mode = norm_map.get(ACTION_FEATURE)
        state = step.state_dict() if callable(getattr(step, "state_dict", None)) else {}
        return ActionUnnormaliser(
            mode=str(mode) if mode is not None else None,
            stats_digest=stats_digest(state) if isinstance(state, Mapping) else None,
            source=source,
        )
    return None


__all__ = [
    "ACTION_FEATURE",
    "ACTION_STATS_PREFIX",
    "POSTPROCESSOR_CONFIG",
    "PREPROCESSOR_CONFIG",
    "STATE_FEATURE",
    "VISUAL_FEATURE",
    "WEIGHTS_FILE",
    "camera_keys_of",
    "denoising_steps_of",
    "discrete_state_input_of",
    "input_normaliser_from_pipeline",
    "locate_checkpoint_file",
    "observation_stats_digest",
    "processor_files_digest",
    "rename_map_from_pipeline",
    "resolve_hub_revision",
    "revision_from_cache_path",
    "stats_digest",
    "step_names",
    "temporal_ensemble_coeff_of",
    "unnormaliser_from_pipeline",
    "weights_file_digest",
]
