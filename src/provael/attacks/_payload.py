"""Shared, deterministic helpers for attack payloads.

Every attack must be a pure, reproducible function of its inputs. These helpers
centralise the two things the families share:

  * :func:`episode_index` — pick a per-episode variant deterministically from the
    observation's ``"seed"`` (with a stable SHA-256 fallback), so seed-varying
    attacks stay reproducible across processes, platforms, and numpy versions.
  * :func:`append_channel` / :func:`set_channel` — inject into an observation
    *without mutating the input* (return a shallow copy), so the runner can reuse
    the suite's observation between steps safely.
"""

from __future__ import annotations

import hashlib

from provael.types import Observation


def episode_index(observation: Observation, modulus: int) -> int:
    """Pick a deterministic index in ``[0, modulus)`` from the observation.

    Prefers the episode ``seed`` (present in our suites); otherwise falls back to a
    stable SHA-256 hash of the instruction/task context so ``perturb`` stays a pure,
    reproducible function even on suites that don't expose a seed.
    """
    seed = observation.get("seed")
    if isinstance(seed, int):
        return seed % modulus
    key = str(observation.get("instruction", "")) + str(observation.get("task", ""))
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:4], "big") % modulus


def append_channel(observation: Observation, key: str, *items: str) -> Observation:
    """Return a shallow copy of ``observation`` with ``items`` appended to list ``key``.

    The input observation is never mutated. Missing channels are created.
    """
    existing = list(observation.get(key, []))
    existing.extend(items)
    return {**observation, key: existing}


def set_channel(observation: Observation, key: str, value: str) -> Observation:
    """Return a shallow copy of ``observation`` with text channel ``key`` set to ``value``."""
    return {**observation, key: value}


__all__ = ["episode_index", "append_channel", "set_channel"]
