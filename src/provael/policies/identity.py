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
from collections.abc import Iterable, Mapping
from typing import Any

from provael.types import ActionUnnormaliser

#: The segment a Hugging Face Hub cache path carries between the repo directory and the files of
#: one resolved commit: ``…/models--org--name/snapshots/<commit sha>/config.json``.
_SNAPSHOT_SEGMENT = re.compile(r"/snapshots/([0-9a-f]{7,64})(?:/|$)")

#: The feature-type key the normalisation map uses for the action stream, and the prefix its
#: statistics carry in a flat state dict (``action.mean``, ``action.std``, …).
ACTION_FEATURE = "ACTION"
ACTION_STATS_PREFIX = "action."


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


def stats_digest(stats: Mapping[str, Any]) -> str | None:
    """sha256 over the canonical form of the statistics that apply to the ACTION stream.

    Takes a flat ``state_dict``-shaped mapping (``"action.mean" -> tensor``) and keeps only the
    ``action.`` entries. Values are serialised exactly as loaded — a digest over rounded numbers
    would call two different unnormalisers the same. ``None`` when no action statistic is present
    (an IDENTITY unnormaliser has none, and that is a fact rather than a failure).
    """
    action_stats = {
        key: _as_float_list(value)
        for key, value in stats.items()
        if str(key).startswith(ACTION_STATS_PREFIX)
    }
    if not action_stats:
        return None
    text = json.dumps(action_stats, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_unnormaliser(step: Any) -> bool:
    return "unnormaliz" in type(step).__name__.lower()


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
    "resolve_hub_revision",
    "revision_from_cache_path",
    "stats_digest",
    "step_names",
    "unnormaliser_from_pipeline",
]
