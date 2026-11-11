# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Opt-in run sidecars: the action chunks a policy predicted, and per-step timing (P1.5).

Neither belongs in ``report.json``. A chunk record is large (a policy that re-plans every step
predicts a whole chunk per step, most of it never executed), and timing is wall-clock, which the
determinism contract keeps out of the report and out of everything digested from it. Each is
written beside ``report.json`` only when asked for (``provael attack --record-chunks`` /
``--record-timing``), and the execution manifest records each file's sha256, so a sidecar cannot
be paired with the wrong run.

The runner touches no file. It fills a caller-owned :class:`ChunkLog` or :class:`TimingLog`, the way
it fills the defense audit trail, and the CLI writes them. Episodes are keyed by their position in
``report.results``, so a sidecar joins its report without guessing; an episode replayed from a
``--resume`` ledger ran in an earlier process and has no entry.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

#: Sidecar file names, written beside ``report.json``.
CHUNKS_NPZ = "chunks.npz"
TIMING_JSON = "timing.json"

#: Format labels, so a future layout is a new label rather than a silent reinterpretation.
CHUNKS_FORMAT = "provael-chunks/v1"
TIMING_FORMAT = "provael-timing/v1"

#: A fixed zip timestamp: the same chunks always write the same bytes, so the sha256 the
#: execution manifest records depends on the chunks alone.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


@dataclass
class _EpisodeChunks:
    index: int
    task: str
    attack: str
    seed: int
    chunks: list[npt.NDArray[np.float32]] = field(default_factory=list)
    predicted_at: list[int] = field(default_factory=list)
    executed: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class ChunkLog:
    """Every chunk the policy predicted on a live step, and which row of it each step executed.

    A policy adapter hands each chunk it predicts to :meth:`sink`
    (:meth:`provael.policies.base.PolicyAdapter.record_chunks`). An attack's search can query the
    policy before the live step, and those chunks were never executed, so the runner calls
    :meth:`before_act` right before the live ``act`` and keeps only what that call predicted.
    ``space`` is the adapter's own statement of the units the chunks are in.
    """

    space: str | None = None
    pending: list[npt.NDArray[np.float32]] = field(default_factory=list)
    episodes: list[_EpisodeChunks] = field(default_factory=list)

    def sink(self, chunk: Any) -> None:
        """Receive one predicted chunk, ``(rows, action_dim)`` (a single action is one row)."""
        arr = np.array(chunk, dtype=np.float32, copy=True)
        self.pending.append(arr.reshape(1, -1) if arr.ndim < 2 else arr.reshape(-1, arr.shape[-1]))

    def start(self, index: int, task: str, attack: str, seed: int) -> None:
        """Open the record of the episode at ``report.results[index]``."""
        self.episodes.append(_EpisodeChunks(index, task, attack, seed))

    def before_act(self) -> None:
        self.pending.clear()

    def after_act(self, step: int) -> None:
        """File what the live ``act`` at ``step`` predicted, or advance a row in the current chunk.

        A step whose ``act`` predicted nothing executed the next row of the last chunk (an action
        queue); a step before any chunk was seen is recorded as ``(-1, -1)``.
        """
        if not self.episodes:
            return
        episode = self.episodes[-1]
        if self.pending:
            episode.chunks.append(self.pending[-1])
            episode.predicted_at.append(step)
            episode.executed.append((len(episode.chunks) - 1, 0))
        elif episode.executed and episode.executed[-1][0] >= 0:
            chunk, row = episode.executed[-1]
            episode.executed.append((chunk, row + 1))
        else:
            episode.executed.append((-1, -1))
        self.pending.clear()

    def arrays(self) -> dict[str, npt.NDArray[Any]]:
        """The npz members: per episode its chunks, their rows, when each was predicted, and
        ``(chunk, row)`` for every executed step; plus ``meta``, a JSON index of the episodes."""
        out: dict[str, npt.NDArray[Any]] = {}
        index: list[dict[str, Any]] = []
        for episode in self.episodes:
            if not episode.executed:
                continue
            prefix = f"r{episode.index:05d}"
            rows = max((c.shape[0] for c in episode.chunks), default=0)
            dim = max((c.shape[1] for c in episode.chunks), default=0)
            stacked = np.full((len(episode.chunks), rows, dim), np.nan, dtype=np.float32)
            for i, chunk in enumerate(episode.chunks):
                stacked[i, : chunk.shape[0], : chunk.shape[1]] = chunk
            out[f"{prefix}_chunks"] = stacked
            out[f"{prefix}_rows"] = np.array([c.shape[0] for c in episode.chunks], dtype=np.int32)
            out[f"{prefix}_predicted_at"] = np.array(episode.predicted_at, dtype=np.int32)
            out[f"{prefix}_executed"] = np.array(episode.executed, dtype=np.int32).reshape(-1, 2)
            index.append({
                "result_index": episode.index, "task": episode.task, "attack": episode.attack,
                "seed": episode.seed, "chunks": len(episode.chunks), "steps": len(episode.executed),
            })
        meta = {"format": CHUNKS_FORMAT, "space": self.space, "episodes": index}
        out["meta"] = np.array(json.dumps(meta, sort_keys=True))
        return out


def npz_bytes(arrays: dict[str, npt.NDArray[Any]]) -> bytes:
    """A deterministic ``.npz``: members in name order, each with a fixed timestamp.

    ``numpy.savez`` stamps every member with the current time, so the same arrays written twice
    would hash differently. ``numpy.load`` reads this exactly as it reads ``savez`` output.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(arrays):
            member = io.BytesIO()
            np.save(member, np.asarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, member.getvalue())
    return buffer.getvalue()


@dataclass
class _EpisodeTiming:
    index: int
    task: str
    attack: str
    seed: int
    observed_ns: list[int] = field(default_factory=list)
    dispatched_ns: list[int] = field(default_factory=list)


@dataclass
class TimingLog:
    """Per step, when its observation was in hand and when its action went to the simulator.

    Nanoseconds since the log was created, from a monotonic clock (``time.perf_counter_ns``). Wall
    clock, so it lives here and never in ``report.json``: the runner reads the clock only when a
    log was passed in, and only into the log.
    """

    clock: Callable[[], int] = time.perf_counter_ns
    origin: int = -1
    episodes: list[_EpisodeTiming] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.origin < 0:
            self.origin = self.clock()

    def start(self, index: int, task: str, attack: str, seed: int) -> None:
        """Open the record of the episode at ``report.results[index]``."""
        self.episodes.append(_EpisodeTiming(index, task, attack, seed))

    def now(self) -> int:
        """Nanoseconds since the log was created."""
        return self.clock() - self.origin

    def step(self, observed_ns: int, dispatched_ns: int) -> None:
        """One step: when its observation came back from the simulator (or the reset), and when
        its action was handed to the simulator."""
        if self.episodes:
            self.episodes[-1].observed_ns.append(observed_ns)
            self.episodes[-1].dispatched_ns.append(dispatched_ns)

    def to_json(self) -> str:
        body = {
            "format": TIMING_FORMAT,
            "clock": "time.perf_counter_ns(), nanoseconds since the run started (monotonic)",
            "episodes": [
                {
                    "result_index": e.index, "task": e.task, "attack": e.attack, "seed": e.seed,
                    "observed_ns": e.observed_ns, "dispatched_ns": e.dispatched_ns,
                }
                for e in self.episodes
                if e.observed_ns
            ],
        }
        return json.dumps(body, indent=2, sort_keys=True) + "\n"


def write_chunks(log: ChunkLog, out_dir: Path) -> tuple[Path, str]:
    """Write ``chunks.npz`` into ``out_dir``; return its path and sha256."""
    data = npz_bytes(log.arrays())
    path = out_dir / CHUNKS_NPZ
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def write_timing(log: TimingLog, out_dir: Path) -> tuple[Path, str]:
    """Write ``timing.json`` into ``out_dir``; return its path and sha256."""
    data = log.to_json().encode("utf-8")
    path = out_dir / TIMING_JSON
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


__all__ = [
    "CHUNKS_FORMAT",
    "CHUNKS_NPZ",
    "TIMING_FORMAT",
    "TIMING_JSON",
    "ChunkLog",
    "TimingLog",
    "npz_bytes",
    "write_chunks",
    "write_timing",
]
