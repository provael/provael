"""Episode video: frames reach the sink, the report does not move, and the writer is optional.

The sink is a runner ARGUMENT, not a config field, for the same reason ``audit_sink`` is: a
config field would move ``RunReport``'s canonical JSON and therefore every attestation digest
issued before it. The first test below is the guard on that promise — a run with a sink and a run
without one must be byte-identical.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from provael.attacks.instruction import RolePlayAttack
from provael.config import RunConfig
from provael.policies.stub import StubPolicy
from provael.report import to_json
from provael.runner import run, run_episode
from provael.suites.stub import StubSuite
from provael.types import IMAGE_KEY, Action, Observation, State
from provael.video import (
    BORDER_PX,
    FrameList,
    Mp4Writer,
    clip_name,
    image_from,
    mark_unsafe,
)


class _ImageSuite(StubSuite):
    """The stub suite with a deterministic 16x16 RGB frame attached to every observation."""

    def _with_image(self, obs: Observation) -> Observation:
        step = int(obs.get("step", 0))
        frame = np.full((16, 16, 3), fill_value=(step * 7) % 256, dtype=np.uint8)
        return {**obs, IMAGE_KEY: frame}

    def reset(self, task: str, seed: int) -> Observation:
        return self._with_image(super().reset(task, seed))

    def step(self, action: Action) -> tuple[Observation, bool, State]:
        obs, done, state = super().step(action)
        return self._with_image(obs), done, state


def test_frames_reach_the_sink_and_the_unsafe_step_is_flagged(stub_policy: StubPolicy) -> None:
    sink = FrameList()
    result = run_episode(
        stub_policy, _ImageSuite(), RolePlayAttack(), task="reach", seed=0, horizon=8,
        frame_sink=sink,
    )
    # one frame per executed step, in order, and the last one carries the verdict
    assert [s for s, _, _ in sink.frames] == list(range(1, result.steps + 1))
    assert sink.frames[-1][2] is result.success
    assert all(img.shape == (16, 16, 3) and img.dtype == np.uint8 for _, img, _ in sink.frames)


def test_recording_does_not_move_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One writer per episode, closed after it, and the report byte-identical either way."""
    import provael.runner as runner_module

    opened: list[Path] = []
    closed: list[Path] = []

    class _FakeWriter(FrameList):
        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path
            opened.append(path)

        def close(self) -> None:
            super().close()
            closed.append(self.path)

    # No ffmpeg on the CPU build: swap the MP4 writer for an in-memory one with the same shape.
    monkeypatch.setattr(runner_module, "Mp4Writer", _FakeWriter)
    config = RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=4, seed=0)
    plain = to_json(run(config))
    recorded = to_json(run(config, video_dir=tmp_path / "clips"))
    assert recorded == plain
    # 3 instruction arms x 4 episodes: a clip was opened and closed for every episode
    assert len(opened) == 12 and closed == opened
    assert opened[0].parent == tmp_path / "clips"
    assert opened[0].name == clip_name("reach", 0, "roleplay")


def test_a_suite_without_images_yields_no_frames(stub_policy: StubPolicy) -> None:
    sink = FrameList()
    run_episode(
        stub_policy, StubSuite(), RolePlayAttack(), task="reach", seed=0, horizon=4,
        frame_sink=sink,
    )
    assert sink.frames == []


@pytest.mark.parametrize(
    ("raw", "expected_shape"),
    [
        (np.zeros((8, 8, 3), dtype=np.uint8), (8, 8, 3)),
        (np.zeros((3, 8, 8), dtype=np.float32), (8, 8, 3)),  # CHW float -> HWC uint8
        (np.zeros((1, 8, 8, 3), dtype=np.uint8), (8, 8, 3)),  # batched by a VectorEnv
        (np.zeros((8, 8, 1), dtype=np.uint8), (8, 8, 3)),  # grey -> RGB
    ],
)
def test_image_from_accepts_the_shapes_adapters_emit(raw: Any, expected_shape: Any) -> None:
    out = image_from({IMAGE_KEY: raw})
    assert out is not None and out.shape == expected_shape and out.dtype == np.uint8


def test_image_from_refuses_what_it_cannot_read() -> None:
    assert image_from({}) is None
    assert image_from({IMAGE_KEY: np.zeros((8, 8), dtype=np.uint8)}) is None
    assert image_from({IMAGE_KEY: np.zeros((8, 8, 4), dtype=np.uint8)}) is None


def test_float_frames_are_scaled_not_truncated() -> None:
    out = image_from({IMAGE_KEY: np.full((4, 4, 3), 0.5, dtype=np.float32)})
    assert out is not None and int(out[0, 0, 0]) == 127


def test_mark_unsafe_draws_a_border_and_leaves_the_middle() -> None:
    img = np.zeros((32, 32, 3), dtype=np.uint8)
    marked = mark_unsafe(img)
    assert tuple(marked[0, 0]) == (220, 30, 30)
    assert tuple(marked[BORDER_PX, BORDER_PX]) == (0, 0, 0)
    assert img.sum() == 0  # the input is not mutated


def test_clip_name_is_filesystem_safe() -> None:
    assert clip_name("libero_object/3", 2, "roleplay") == "libero_object-3__seed2__roleplay.mp4"


@pytest.mark.skipif(
    importlib.util.find_spec("imageio") is None or importlib.util.find_spec("imageio_ffmpeg") is None,
    reason="imageio + imageio-ffmpeg ship with the [lerobot] extra, not the CPU core",
)
def test_mp4_writer_writes_a_playable_file(tmp_path: Path) -> None:
    writer = Mp4Writer(tmp_path / "clip.mp4")
    for step in range(1, 6):
        writer.frame(step, np.full((16, 16, 3), step * 40, dtype=np.uint8), unsafe=step >= 4)
    writer.close()
    assert writer.frames_written == 5
    assert (tmp_path / "clip.mp4").stat().st_size > 0


@pytest.mark.skipif(
    importlib.util.find_spec("imageio") is None or importlib.util.find_spec("imageio_ffmpeg") is None,
    reason="imageio + imageio-ffmpeg ship with the [lerobot] extra, not the CPU core",
)
def test_compose_side_by_side_aligns_steps_and_holds_the_shorter_clip(tmp_path: Path) -> None:
    from provael.video import GAP_PX, compose_side_by_side

    def _clip(path: Path, frames: int, level: int) -> None:
        w = Mp4Writer(path)
        for step in range(1, frames + 1):
            w.frame(step, np.full((16, 24, 3), level, dtype=np.uint8), unsafe=False)
        w.close()

    _clip(tmp_path / "benign.mp4", 6, 40)
    _clip(tmp_path / "attacked.mp4", 3, 200)  # stopped early: the predicate fired
    n = compose_side_by_side(tmp_path / "benign.mp4", tmp_path / "attacked.mp4", tmp_path / "ab.mp4")
    assert n == 6  # the longer clip's length; the shorter holds its last frame

    import imageio.v2 as imageio

    # a for-loop, not list(): imageio's ffmpeg reader reports an infinite __len__
    frames = [np.asarray(f) for f in imageio.get_reader(str(tmp_path / "ab.mp4"))]
    assert len(frames) == 6
    assert frames[0].shape == (16, 24 + GAP_PX + 24, 3)
    # left half dark, right half bright, in the last frame too (the held frame is still there)
    assert int(frames[-1][8, 4].mean()) < 90 and int(frames[-1][8, -4].mean()) > 150


def test_compose_refuses_an_empty_clip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import provael.video as video

    monkeypatch.setattr(video, "_read_frames", lambda p: [])
    with pytest.raises(ValueError, match="nothing to compose"):
        video.compose_side_by_side(tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "o.mp4")
