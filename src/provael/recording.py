# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Recording-only observation of one episode: frames, simulator snapshots and actions for a video.

WHY THIS EXISTS. :mod:`provael.video` writes the frames the policy saw, at the policy's own
resolution, and stops where the episode is scored. A demonstration video needs more: a sharper
camera than the policy's 256x256 view, a look at what the arm does after the envelope exit, and
proof that recording any of it did not change the episode. :class:`EpisodeRecorder` is the runner
argument that collects that material, and :class:`VideoSource` is the optional suite capability
that renders it.

WHAT IT MUST NOT DO. Change what the episode measures. The recorder is a runner argument, never a
:class:`~provael.config.RunConfig` field (a field would move the canonical JSON every attestation is
signed over, the reason ``audit_sink`` and the frame sink are arguments too). The runner builds the
episode's :class:`~provael.types.AttackResult` from the scored loop BEFORE any recording-only step
runs, so steps played past the verdict cannot reach a measured field: they feed the recorder and
nothing else. ``tests/test_recording.py`` holds a run with a recorder to a byte-identical report.

THE SNAPSHOT DESIGN, and why the high-resolution frames are rendered after the episode. A suite
that renders a second camera mid-episode shares a renderer with the policy's camera, and robosuite
1.4.0 resizes that shared offscreen buffer the first time a larger image is requested. So the
recorder reads the simulator's state at every step instead (a copy, no rendering) and the
:class:`VideoSource` renders those states after the episode has finished acting. During the episode
the only extra work is a read of the state and a copy of the frame the policy already received.

THE PROJECTION IS PROVEN OR NOT USED. :class:`CameraProjection` maps world points to pixels of a
rendered camera image. A drawing built on it is only as good as the camera model, so
:func:`check_projection` tests the mapping against the simulator's own segmentation render: the
projected centre of every clearly visible geom must land on that geom's pixels, and the same test
run with the image mirrored must fail. A caller draws nothing from a projection that did not pass.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np
import numpy.typing as npt

if TYPE_CHECKING:
    from provael.suites.base import SuiteAdapter
    from provael.types import Action, AttackResult, Observation

#: Why a recorded episode stopped producing frames. ``verdict``: the predicate fired and the
#: recorder did not ask for the steps after it. ``done``: the suite ended the episode (LIBERO ends
#: one on task success). ``horizon``: the step budget ran out. ``non-finite action``: the policy
#: emitted NaN/inf past the verdict, where nothing is scored, so the recording stops instead of
#: raising. ``not applicable``: the attack had no surface in this suite and nothing ran.
ENDED_BY: tuple[str, ...] = ("verdict", "done", "horizon", "non-finite action", "not applicable")


class EpisodeRecorder(Protocol):
    """Collects one episode for a video. Every method is an observation; none can steer the loop.

    The runner calls :meth:`begin` after the suite's reset, :meth:`observed` with the observation
    the policy is about to receive (after the attack and any defense, before the policy acts),
    :meth:`stepped` once the step has been executed, and :meth:`finish` with the episode's final
    result. ``scored`` is ``False`` exactly for the steps played past the verdict.
    """

    #: Keep stepping after the verdict, for frames only, until the horizon or the suite's own end
    #: of episode. The scored result is fixed before the first such step runs. On a suite that
    #: walks fixed initial states with a counter (LIBERO without ``--pin-init-states``), a
    #: recording-only step that completes the task advances that counter, which is why
    #: :func:`provael.runner.run` accepts a recorder only on a pinned or single-episode run.
    continue_past_verdict: bool

    def begin(self, suite: SuiteAdapter, *, task: str, seed: int, attack: str) -> None: ...

    def observed(self, step: int, observation: Observation) -> None: ...

    def stepped(self, step: int, action: Action, *, unsafe: bool, scored: bool) -> None: ...

    def finish(self, suite: SuiteAdapter, result: AttackResult, *, ended_by: str) -> None: ...


@dataclass
class ActionLog:
    """A recorder that keeps the executed actions and nothing else.

    The control arm of the identical-actions check: an episode recorded with frames and snapshots
    and the same episode recorded with only this must emit the same action at every step. Actions
    are kept as Python floats, which hold a float32 exactly, so a comparison is bit-for-bit.
    """

    continue_past_verdict: bool = True
    actions: list[list[float]] = field(default_factory=list)
    steps: list[int] = field(default_factory=list)
    scored: list[bool] = field(default_factory=list)
    unsafe: list[bool] = field(default_factory=list)
    ended_by: str | None = None
    verdict_step: int | None = None

    def begin(self, suite: SuiteAdapter, *, task: str, seed: int, attack: str) -> None:
        del suite, task, seed, attack

    def observed(self, step: int, observation: Observation) -> None:
        del step, observation

    def stepped(self, step: int, action: Action, *, unsafe: bool, scored: bool) -> None:
        self.steps.append(int(step))
        self.actions.append([float(x) for x in np.asarray(action).reshape(-1)])
        self.scored.append(bool(scored))
        self.unsafe.append(bool(unsafe))

    def finish(self, suite: SuiteAdapter, result: AttackResult, *, ended_by: str) -> None:
        del suite
        self.ended_by = ended_by
        self.verdict_step = result.steps_to_success

    def to_json_dict(self) -> dict[str, Any]:
        """The log as a JSON object; ``steps[i]`` executed ``actions[i]``."""
        return {
            "steps": list(self.steps),
            "actions": [list(a) for a in self.actions],
            "scored": list(self.scored),
            "unsafe": list(self.unsafe),
            "ended_by": self.ended_by,
            "verdict_step": self.verdict_step,
        }


@dataclass(frozen=True)
class ActionComparison:
    """Two action sequences compared exactly: identical, or where they first part."""

    identical: bool
    compared_steps: int
    first_differing_step: int | None
    max_abs_difference_at_first: float | None
    lengths: tuple[int, int]

    def summary(self) -> str:
        if self.identical:
            return f"identical over {self.compared_steps} steps"
        if self.first_differing_step is None:
            return (
                f"same actions over the common {self.compared_steps} steps, but different lengths "
                f"{self.lengths[0]} and {self.lengths[1]}"
            )
        return (
            f"first differing step {self.first_differing_step} (largest channel difference there "
            f"{self.max_abs_difference_at_first!r}), after {self.compared_steps} compared steps"
        )


def compare_actions(
    a: dict[str, Any], b: dict[str, Any]
) -> ActionComparison:
    """Compare two :meth:`ActionLog.to_json_dict` payloads step by step, with no tolerance.

    Exact equality is the test, not closeness: the claim being checked is that recording changed
    nothing the policy computed, and any difference at all falsifies it. Steps are matched by their
    step number, so a log that skipped a step cannot line up by accident.
    """
    steps_a, steps_b = list(a.get("steps", [])), list(b.get("steps", []))
    acts_a, acts_b = list(a.get("actions", [])), list(b.get("actions", []))
    common = min(len(steps_a), len(steps_b))
    for i in range(common):
        if steps_a[i] != steps_b[i]:
            return ActionComparison(False, i, int(steps_a[i]), None, (len(steps_a), len(steps_b)))
        va, vb = [float(x) for x in acts_a[i]], [float(x) for x in acts_b[i]]
        if va != vb:
            width = min(len(va), len(vb))
            diff = max((abs(x - y) for x, y in zip(va[:width], vb[:width], strict=True)),
                       default=float("inf"))
            if len(va) != len(vb):
                diff = float("inf")
            return ActionComparison(False, i, int(steps_a[i]), diff, (len(steps_a), len(steps_b)))
    same_length = len(steps_a) == len(steps_b)
    return ActionComparison(same_length, common, None, None, (len(steps_a), len(steps_b)))


@dataclass(frozen=True)
class CameraProjection:
    """A pinhole camera as MuJoCo renders it: world points to pixels of an upright image.

    ``rotation`` is the camera frame in world coordinates (MuJoCo's ``cam_xmat``): its columns are
    the camera's right, up and backward axes, and the camera looks along minus its third column.
    MuJoCo's ``fovy`` is the vertical field of view, so the focal length in pixels is
    ``0.5 * height / tan(fovy / 2)`` on both axes, with the principal point at the image centre.
    Pixel coordinates are continuous: ``u`` grows to the right from the left edge, ``v`` grows
    downward from the top edge of the image as a viewer sees it (row 0 at the top).
    """

    camera: str
    width: int
    height: int
    position: tuple[float, float, float]
    rotation: tuple[tuple[float, float, float], tuple[float, float, float],
                    tuple[float, float, float]]
    fovy_deg: float

    @property
    def focal_px(self) -> float:
        return 0.5 * self.height / math.tan(math.radians(self.fovy_deg) / 2.0)

    def project(
        self, points: npt.ArrayLike
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.bool_]]:
        """``(N, 3)`` world points to ``(N, 2)`` ``(u, v)`` pixels, and an in-front mask."""
        world = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        axes = np.asarray(self.rotation, dtype=np.float64)
        cam = (world - np.asarray(self.position, dtype=np.float64)) @ axes
        depth = -cam[:, 2]
        in_front = depth > 1e-9
        safe = np.where(in_front, depth, 1.0)
        f = self.focal_px
        u = self.width / 2.0 + f * cam[:, 0] / safe
        v = self.height / 2.0 - f * cam[:, 1] / safe
        return np.stack([u, v], axis=1), in_front

    def scaled(self, width: int, height: int) -> CameraProjection:
        """The same camera rendered at another resolution (``fovy`` is resolution-independent)."""
        return CameraProjection(
            self.camera, width, height, self.position, self.rotation, self.fovy_deg
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "camera": self.camera,
            "width": self.width,
            "height": self.height,
            "position": list(self.position),
            "rotation": [list(r) for r in self.rotation],
            "fovy_deg": self.fovy_deg,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> CameraProjection:
        rot = [tuple(float(v) for v in row) for row in data["rotation"]]
        if len(rot) != 3 or any(len(r) != 3 for r in rot):
            raise ValueError("a camera rotation is a 3x3 matrix")
        pos = tuple(float(v) for v in data["position"])
        if len(pos) != 3:
            raise ValueError("a camera position has three coordinates")
        return cls(
            camera=str(data["camera"]),
            width=int(data["width"]),
            height=int(data["height"]),
            position=(pos[0], pos[1], pos[2]),
            rotation=(
                (rot[0][0], rot[0][1], rot[0][2]),
                (rot[1][0], rot[1][1], rot[1][2]),
                (rot[2][0], rot[2][1], rot[2][2]),
            ),
            fovy_deg=float(data["fovy_deg"]),
        )


@dataclass(frozen=True)
class Segmentation:
    """A segmentation render of one camera, upright like :class:`CameraProjection` pixels.

    ``ids[v, u]`` is the geom drawn at that pixel, ``-1`` where none is; ``centers`` holds the world
    position of each geom that appears, as the simulator placed it for the same state.
    """

    camera: str
    ids: npt.NDArray[np.int32]
    centers: dict[int, tuple[float, float, float]]
    names: dict[int, str] = field(default_factory=dict)


#: The thresholds :func:`check_projection` uses. A geom counts only when at least
#: ``MIN_AREA_PX`` of its pixels are visible and its projected centre falls inside the image; the
#: mapping passes when at least ``MIN_GEOMS`` geoms count, at least ``MIN_HIT_RATE`` of them are
#: hit within ``TOLERANCE_PX``, and the mirrored and upside-down controls each hit at most
#: ``MAX_CONTROL_RATE`` of them. A geom's centre can sit behind another geom, which is why the hit
#: rate is not required to be 1; the controls are what show the test can tell a right mapping from
#: a wrong one.
MIN_GEOMS = 8
MIN_AREA_PX = 200
MIN_HIT_RATE = 0.8
MAX_CONTROL_RATE = 0.3
TOLERANCE_PX = 2


@dataclass(frozen=True)
class ProjectionCheck:
    """The outcome of :func:`check_projection`, with every count behind it."""

    camera: str
    width: int
    height: int
    geoms_considered: int
    hits: int
    mirrored_hits: int
    flipped_hits: int
    passed: bool
    reason: str
    thresholds: dict[str, float] = field(default_factory=dict)
    per_geom: list[dict[str, Any]] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "camera": self.camera,
            "width": self.width,
            "height": self.height,
            "geoms_considered": self.geoms_considered,
            "hits": self.hits,
            "mirrored_hits": self.mirrored_hits,
            "flipped_hits": self.flipped_hits,
            "passed": self.passed,
            "reason": self.reason,
            "thresholds": dict(self.thresholds),
            "per_geom": list(self.per_geom),
        }


def _hit(mask: npt.NDArray[np.bool_], u: float, v: float, tolerance: int) -> bool:
    height, width = mask.shape
    col, row = int(math.floor(u)), int(math.floor(v))
    if not (0 <= col < width and 0 <= row < height):
        return False
    r0, r1 = max(0, row - tolerance), min(height, row + tolerance + 1)
    c0, c1 = max(0, col - tolerance), min(width, col + tolerance + 1)
    return bool(mask[r0:r1, c0:c1].any())


def check_projection(
    projection: CameraProjection,
    segmentation: Segmentation,
    *,
    min_geoms: int = MIN_GEOMS,
    min_area_px: int = MIN_AREA_PX,
    min_hit_rate: float = MIN_HIT_RATE,
    max_control_rate: float = MAX_CONTROL_RATE,
    tolerance_px: int = TOLERANCE_PX,
) -> ProjectionCheck:
    """Test ``projection`` against the simulator's own rendering of the same state and camera.

    For every geom with at least ``min_area_px`` visible pixels, project the world position the
    simulator gives for it and ask whether the pixel lands on that geom (within ``tolerance_px``).
    The same question is asked of the image mirrored left-right and turned upside down: a mapping
    that hits nearly as often under either control is not shown to be right, whatever its own rate.
    """
    ids = np.asarray(segmentation.ids)
    height, width = ids.shape
    thresholds = {
        "min_geoms": float(min_geoms),
        "min_area_px": float(min_area_px),
        "min_hit_rate": min_hit_rate,
        "max_control_rate": max_control_rate,
        "tolerance_px": float(tolerance_px),
    }
    if (width, height) != (projection.width, projection.height):
        return ProjectionCheck(
            projection.camera, projection.width, projection.height, 0, 0, 0, 0, False,
            f"segmentation is {width}x{height} but the projection is for "
            f"{projection.width}x{projection.height}", thresholds,
        )
    considered = hits = mirrored = flipped = 0
    rows: list[dict[str, Any]] = []
    present, counts = np.unique(ids, return_counts=True)
    for gid, count in zip(present.tolist(), counts.tolist(), strict=True):
        if gid < 0 or count < min_area_px or gid not in segmentation.centers:
            continue
        uv, front = projection.project([segmentation.centers[gid]])
        u, v = float(uv[0, 0]), float(uv[0, 1])
        if not (bool(front[0]) and 0.0 <= u < width and 0.0 <= v < height):
            continue
        mask = ids == gid
        hit = _hit(mask, u, v, tolerance_px)
        hit_m = _hit(mask, width - u, v, tolerance_px)
        hit_f = _hit(mask, u, height - v, tolerance_px)
        considered += 1
        hits += int(hit)
        mirrored += int(hit_m)
        flipped += int(hit_f)
        rows.append({
            "geom": int(gid), "name": segmentation.names.get(int(gid), f"geom{gid}"),
            "area_px": int(count), "u": round(u, 2), "v": round(v, 2), "hit": hit,
            "mirrored_hit": hit_m, "flipped_hit": hit_f,
        })
    if considered < min_geoms:
        reason = f"only {considered} geom(s) qualified; at least {min_geoms} are needed"
        passed = False
    else:
        rate = hits / considered
        control = max(mirrored, flipped) / considered
        passed = rate >= min_hit_rate and control <= max_control_rate
        reason = (
            f"{hits}/{considered} projected centres on their own geom "
            f"(need {min_hit_rate:.0%}); controls mirrored {mirrored}/{considered}, "
            f"upside-down {flipped}/{considered} (must stay at or under {max_control_rate:.0%})"
        )
    return ProjectionCheck(
        projection.camera, projection.width, projection.height, considered, hits, mirrored,
        flipped, passed, reason, thresholds, rows,
    )


class VideoSource(Protocol):
    """A suite's recording-only camera rig: snapshots during the episode, renders after it.

    Optional: :meth:`provael.suites.base.SuiteAdapter.video_source` returns ``None`` on a suite
    that has none, and a recorder that needs one refuses rather than writing a video without it.
    """

    def cameras(self) -> list[str]:
        """Every camera the live scene defines, read from the simulator at the time of the call."""
        ...

    def snapshot(self) -> npt.NDArray[np.float64]:
        """A copy of the simulator state, enough to re-render this instant. Reads, never writes."""
        ...

    def upright(self, frame: npt.NDArray[Any]) -> npt.NDArray[Any]:
        """A raw frame of this suite (an observation image or a render) as the camera sees it:
        row 0 at the top, left and right as in the scene."""
        ...

    def render(
        self,
        snapshots: Sequence[npt.NDArray[np.float64]],
        cameras: Sequence[str],
        width: int,
        height: int,
    ) -> Iterator[dict[str, npt.NDArray[np.uint8]]]:
        """Render each snapshot from each camera, upright. Sets state: call after the episode."""
        ...

    def projection(self, camera: str, width: int, height: int) -> CameraProjection | None:
        """The camera's projection at this size, or ``None`` if the model is not fovy-only."""
        ...

    def segmentation(
        self, snapshot: npt.NDArray[np.float64], camera: str, width: int, height: int
    ) -> Segmentation | None:
        """A segmentation render of ``snapshot`` from ``camera``, or ``None`` if unavailable."""
        ...


__all__ = [
    "ENDED_BY",
    "MAX_CONTROL_RATE",
    "MIN_AREA_PX",
    "MIN_GEOMS",
    "MIN_HIT_RATE",
    "TOLERANCE_PX",
    "ActionComparison",
    "ActionLog",
    "CameraProjection",
    "EpisodeRecorder",
    "ProjectionCheck",
    "Segmentation",
    "VideoSource",
    "check_projection",
    "compare_actions",
]
