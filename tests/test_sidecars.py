# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The opt-in chunk and timing sidecars (P1.5): beside the report, never in it.

A chunked policy predicts several steps and executes some, so ``report.json``'s actions are only
the rows that ran (openvla#303: "for the steps that ran, predicted and executed are the same").
``--record-chunks`` writes every predicted chunk and which row each step executed; ``--record-timing``
writes when each step's observation arrived and its action left. Both are absent by default, both
are bound to the run by sha256 in the execution manifest, and neither moves a byte of the report.
The lerobot and openpi chunk hooks are checked against fakes; lerobot is not installed here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from typer.testing import CliRunner

from provael.attacks.registry import make_attack
from provael.cli import app
from provael.config import RunConfig
from provael.policies.lerobot_adapter import LeRobotAdapter
from provael.policies.openpi_adapter import OpenPiAdapter
from provael.policies.stub import StubPolicy
from provael.report import to_json
from provael.runner import run, run_episode
from provael.sidecars import CHUNKS_NPZ, TIMING_JSON, ChunkLog, TimingLog, npz_bytes
from provael.suites.stub import StubSuite
from provael.types import Action, Observation

runner = CliRunner()


def _attack(out: Path, *flags: str) -> Path:
    result = runner.invoke(
        app,
        ["attack", "--attacks", "none,roleplay,targeted_hijack", "--episodes", "2",
         "--horizon", "4", *flags, "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    return out


def test_the_sidecars_are_absent_by_default(tmp_path: Path) -> None:
    out = _attack(tmp_path / "plain")
    assert not (out / CHUNKS_NPZ).exists() and not (out / TIMING_JSON).exists()
    manifest = json.loads((out / "execution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["sidecars"] is None


def test_the_sidecars_are_bound_by_digest_and_leave_the_report_alone(tmp_path: Path) -> None:
    plain = _attack(tmp_path / "plain")
    both = _attack(tmp_path / "both", "--record-chunks", "--record-timing")
    report = (both / "report.json").read_bytes()
    assert report == (plain / "report.json").read_bytes(), "a sidecar moved the report"
    manifest = json.loads((both / "execution-manifest.json").read_text(encoding="utf-8"))
    for name in (CHUNKS_NPZ, TIMING_JSON):
        digest = hashlib.sha256((both / name).read_bytes()).hexdigest()
        assert manifest["sidecars"][name] == digest
    assert manifest["report_digest"] == json.loads(
        (plain / "execution-manifest.json").read_text(encoding="utf-8")
    )["report_digest"]


def test_chunks_npz_reads_back_and_is_the_same_bytes_every_run(tmp_path: Path) -> None:
    first = _attack(tmp_path / "a", "--record-chunks")
    second = _attack(tmp_path / "b", "--record-chunks")
    assert (first / CHUNKS_NPZ).read_bytes() == (second / CHUNKS_NPZ).read_bytes()
    report = json.loads((first / "report.json").read_text(encoding="utf-8"))
    with np.load(first / CHUNKS_NPZ, allow_pickle=False) as npz:
        meta = json.loads(str(npz["meta"]))
        assert meta["format"] == "provael-chunks/v1"
        assert meta["space"].startswith("controller units")
        for entry in meta["episodes"]:
            row = report["results"][entry["result_index"]]
            assert (row["task"], row["attack"], row["seed"]) == (
                entry["task"], entry["attack"], entry["seed"]
            )
            prefix = f"r{entry['result_index']:05d}"
            chunks, executed = npz[f"{prefix}_chunks"], npz[f"{prefix}_executed"]
            # The stub predicts one row per step: every executed action IS its chunk.
            assert executed.tolist() == [[i, 0] for i in range(row["steps"])]
            actions = [d["action"] for d in row["decisions"]]
            assert chunks[:, 0, :] == pytest.approx(np.asarray(actions, dtype=np.float32))


def test_a_search_s_queries_are_not_recorded_as_executed_chunks() -> None:
    """targeted_hijack queries the policy through its oracle before the live step.

    Fixed horizon, so the episode runs all three steps past the hijack's first exit.
    """
    log = ChunkLog()
    report = run(
        RunConfig(attacks=["targeted_hijack"], episodes=1, horizon=3, termination="fixed-horizon"),
        chunk_log=log,
    )
    assert report.results[0].applicable
    (episode,) = log.episodes
    assert len(episode.chunks) == 3 and episode.predicted_at == [1, 2, 3]


class _ChunkedStub(StubPolicy):
    """The stub, predicting a three-row chunk every second step and executing two rows of it.

    The rows repeat the stub's own action, so nothing about the episode changes but the chunking.
    """

    def __init__(self) -> None:
        super().__init__()
        self._queue: list[Action] = []
        self._sink: Any = None

    def record_chunks(self, sink: Any) -> str | None:
        self._sink = sink
        return "fake chunked units"

    def act(self, observation: Observation, instruction: str) -> Action:
        if not self._queue:
            base = super().act(observation, instruction)
            chunk = np.stack([base, base, base])
            if self._sink is not None:
                self._sink(chunk)
            self._queue = [chunk[0], chunk[1]]
        return self._queue.pop(0)


def test_each_step_points_at_the_chunk_and_row_it_executed() -> None:
    policy = _ChunkedStub()
    policy.load()
    log = ChunkLog()
    log.space = policy.record_chunks(log.sink)
    log.start(0, "reach", "none", 0)
    run_episode(policy, StubSuite(), make_attack("none"), "reach", 0, 5, chunk_log=log)
    (episode,) = log.episodes
    assert episode.predicted_at == [1, 3, 5]
    assert episode.executed == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
    arrays = log.arrays()
    assert arrays["r00000_chunks"].shape == (3, 3, 11), "the row that never ran is kept"
    assert arrays["r00000_rows"].tolist() == [3, 3, 3]


def test_a_policy_that_hands_over_no_chunks_says_so() -> None:
    from provael.policies.base import PolicyAdapter

    class _Silent(StubPolicy):
        def record_chunks(self, sink: Any) -> str | None:
            return PolicyAdapter.record_chunks(self, sink)

    log = ChunkLog()
    policy = _Silent()
    policy.load()
    log.space = policy.record_chunks(log.sink)
    log.start(0, "reach", "none", 0)
    run_episode(policy, StubSuite(), make_attack("none"), "reach", 0, 2, chunk_log=log)
    assert log.space is None
    assert log.episodes[0].executed == [(-1, -1), (-1, -1)]


def test_npz_bytes_are_deterministic_and_numpy_reads_them(tmp_path: Path) -> None:
    arrays: dict[str, npt.NDArray[Any]] = {
        "b": np.arange(6, dtype=np.int32).reshape(3, 2),
        "a": np.array("{\"k\": 1}"),
    }
    data = npz_bytes(arrays)
    assert data == npz_bytes(dict(reversed(list(arrays.items()))))
    path = tmp_path / "x.npz"
    path.write_bytes(data)
    with np.load(path, allow_pickle=False) as npz:
        assert npz["b"].tolist() == [[0, 1], [2, 3], [4, 5]] and str(npz["a"]) == '{"k": 1}'


def test_timing_records_arrival_before_dispatch_for_every_step() -> None:
    ticks = iter(range(0, 10_000, 10))
    log = TimingLog(clock=lambda: next(ticks))
    run(RunConfig(attacks=["none"], episodes=2, horizon=3), timing_log=log)
    body = json.loads(log.to_json())
    assert body["format"] == "provael-timing/v1" and len(body["episodes"]) == 2
    for episode in body["episodes"]:
        observed, dispatched = episode["observed_ns"], episode["dispatched_ns"]
        assert len(observed) == len(dispatched) == 3
        assert all(o < d for o, d in zip(observed, dispatched, strict=True))
        assert observed == sorted(observed)


def test_timing_never_reaches_the_report() -> None:
    config = RunConfig(attacks=["none", "instruction"], episodes=2)
    assert to_json(run(config, timing_log=TimingLog(), chunk_log=ChunkLog())) == to_json(
        run(config)
    )


# --------------------------------------------------------------------------- #
# the adapters' hooks, against fakes of the libraries they wrap
# --------------------------------------------------------------------------- #


class _Tensor:
    """Just enough of a torch tensor for the hook: detach().float().cpu().numpy()."""

    def __init__(self, array: npt.NDArray[Any]) -> None:
        self.array = array

    def detach(self) -> _Tensor:
        return self

    def float(self) -> _Tensor:
        return self

    def cpu(self) -> _Tensor:
        return self

    def numpy(self) -> npt.NDArray[Any]:
        return self.array


class _SmolVLALike:
    """lerobot 0.5.1's SmolVLA select_action shape: fill the queue from _get_action_chunk."""

    def __init__(self, n_action_steps: int = 2) -> None:
        self.n_action_steps = n_action_steps
        self.queue: list[Any] = []
        self.calls = 0

    def _get_action_chunk(self, batch: dict[str, Any], noise: Any = None) -> _Tensor:
        self.calls += 1
        return _Tensor(np.full((1, 5, 7), float(self.calls), dtype=np.float32))

    def select_action(self, batch: dict[str, Any]) -> Any:
        if not self.queue:
            chunk = self._get_action_chunk(batch, None)
            self.queue.extend(chunk.array[0][: self.n_action_steps])
        return self.queue.pop(0)


class _Pi0Like:
    """lerobot 0.5.1's PI0 / PI0.5 shape: the queue is filled from predict_action_chunk."""

    def predict_action_chunk(self, batch: dict[str, Any]) -> _Tensor:
        return _Tensor(np.zeros((1, 4, 7), dtype=np.float32))


def test_the_lerobot_hook_records_the_whole_chunk_and_returns_it_untouched() -> None:
    adapter = LeRobotAdapter()
    assert adapter.record_chunks(lambda chunk: None) is None, "nothing loaded yet"
    policy = _SmolVLALike()
    adapter._policy = policy
    seen: list[npt.NDArray[Any]] = []
    space = adapter.record_chunks(seen.append)
    assert space is not None and "before its post-processor" in space
    actions = [policy.select_action({}) for _ in range(3)]
    assert len(seen) == 2 and all(chunk.shape == (5, 7) for chunk in seen)
    assert [float(a[0]) for a in actions] == [1.0, 1.0, 2.0], "the queue is unchanged"
    # Wrapping again never stacks, and None stops it.
    adapter.record_chunks(seen.append)
    policy.select_action({})
    assert len(seen) == 2  # the queue still held a row: no new chunk
    adapter.record_chunks(None)
    assert "_get_action_chunk" not in vars(policy)
    policy.queue.clear()
    policy.select_action({})
    assert len(seen) == 2


def test_the_lerobot_hook_takes_predict_action_chunk_where_select_action_uses_it() -> None:
    adapter = LeRobotAdapter()
    adapter._policy = _Pi0Like()
    seen: list[npt.NDArray[Any]] = []
    assert adapter.record_chunks(seen.append) is not None
    adapter._policy.predict_action_chunk({})
    assert len(seen) == 1 and seen[0].shape == (4, 7)
    adapter._policy = object()
    assert adapter.record_chunks(seen.append) is None, "a policy with no chunk path hands none"


def test_the_openpi_hook_records_the_chunk_the_server_returned() -> None:
    class _Client:
        def infer(self, obs: dict[str, Any]) -> dict[str, Any]:
            return {"actions": np.ones((10, 7), dtype=np.float32)}

    adapter = OpenPiAdapter()
    assert adapter.record_chunks(lambda chunk: None) is None, "no client before load"
    adapter._client = _Client()
    seen: list[npt.NDArray[Any]] = []
    assert adapter.record_chunks(seen.append) == "as the openpi policy server returned them"
    result = adapter._client.infer({})
    assert result["actions"].shape == (10, 7) and len(seen) == 1 and seen[0].shape == (10, 7)
    adapter.record_chunks(None)
    adapter._client.infer({})
    assert len(seen) == 1
