"""Load recorded frames from a LeRobotDataset, and refuse the ones that are not what they say.

WHY THIS VALIDATES INSTEAD OF TRUSTING THE NAME. Of the five public Hugging Face datasets matching
"so101" checked on 8 August 2026, **three would have produced a wrong or meaningless study**:

    Guanli001/so101-vials-auto-dr-final100   v3.0, so101_follower, 6-DoF, 59,017 frames   OK
    wenyixu101/farpoint-so101                v3.0, so101_follower, 6-DoF, 72,433 frames   OK
    kaiserbuffle/so101_test                  v2.1  — older codebase version
    BasedLukas/so101_test_2                  v2.1  — older codebase version
    kwangchaeko/so101_test                   robot_type "koch", 4-DoF — NOT AN SO-101
    sree-aimaker/so101_pick_and_place        no meta/info.json — not a LeRobotDataset at all

The `koch` one is the dangerous case, because it fails silently: a 4-DoF dataset named `so101_test`
loads, produces numbers, and those numbers are about a different robot. Nothing downstream would
notice. So the check is on `robot_type` and dimensionality, not on the repo id, and it raises rather
than warns — a study that quietly measured the wrong arm is worse than one that did not run.

The protocol therefore names selection CRITERIA and treats specific datasets as examples. Pinning a
third-party repo that can be renamed, re-uploaded at a different version, or deleted would make the
pre-registration depend on someone else's housekeeping.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: LeRobotDataset codebase versions this loader understands. v2.1 is excluded deliberately rather
#: than by oversight: its on-disk layout differs, and silently reading it would be the same class of
#: error as reading the koch dataset. Widen this only after checking a v2.1 dataset end to end.
SUPPORTED_CODEBASE_VERSIONS = frozenset({"v3.0"})

#: Accepted `robot_type` values for an SO-101 study. Both spellings appear in the wild.
SO101_ROBOT_TYPES = frozenset({"so101", "so101_follower"})

#: The SO-101 is a 6-DoF arm. A dataset claiming otherwise is not one, whatever it is called.
SO101_DOF = 6


class DatasetRejected(ValueError):
    """The dataset is not what the study requires. Raised, never warned."""


@dataclass(frozen=True)
class DatasetInfo:
    """The subset of ``meta/info.json`` this study depends on."""

    codebase_version: str
    robot_type: str
    fps: int
    total_frames: int
    state_dim: int
    action_dim: int
    camera_keys: tuple[str, ...]


def parse_info(raw: dict[str, Any]) -> DatasetInfo:
    """Read ``meta/info.json`` into the fields the study needs, with no validation yet."""
    features = raw.get("features") or {}

    def dim(key: str) -> int:
        shape = (features.get(key) or {}).get("shape") or []
        return int(shape[0]) if shape else 0

    return DatasetInfo(
        codebase_version=str(raw.get("codebase_version", "")),
        robot_type=str(raw.get("robot_type", "")),
        fps=int(raw.get("fps", 0)),
        total_frames=int(raw.get("total_frames", 0)),
        state_dim=dim("observation.state"),
        action_dim=dim("action"),
        camera_keys=tuple(k for k in features if k.startswith("observation.images")),
    )


def validate(info: DatasetInfo, *, repo_id: str) -> None:
    """Refuse anything that would make the study measure something other than what it claims.

    Every rejection names the observed value, because "wrong dataset" without the reason sends
    someone hunting through Hugging Face rather than reading one line of their own metadata.
    """
    if info.codebase_version not in SUPPORTED_CODEBASE_VERSIONS:
        raise DatasetRejected(
            f"{repo_id}: codebase_version is {info.codebase_version!r}, this study requires one of "
            f"{sorted(SUPPORTED_CODEBASE_VERSIONS)}. Older layouts are excluded deliberately, not "
            "by oversight — read the loader's module docstring before widening this."
        )
    if info.robot_type not in SO101_ROBOT_TYPES:
        raise DatasetRejected(
            f"{repo_id}: robot_type is {info.robot_type!r}, not an SO-101. Dataset NAMES are not "
            "evidence — kwangchaeko/so101_test is named so101 and is a 4-DoF koch. Measuring it "
            "would produce numbers about a different robot and nothing downstream would notice."
        )
    if info.state_dim != SO101_DOF or info.action_dim != SO101_DOF:
        raise DatasetRejected(
            f"{repo_id}: state/action dimensions are {info.state_dim}/{info.action_dim}, expected "
            f"{SO101_DOF}/{SO101_DOF} for an SO-101."
        )
    if not info.camera_keys:
        raise DatasetRejected(
            f"{repo_id}: no observation.images.* features. A vision-language-action policy needs "
            "pixels; a state-only dataset cannot exercise the attack under study, which perturbs "
            "the instruction while the image is held fixed."
        )
    if info.total_frames <= 0:
        raise DatasetRejected(f"{repo_id}: total_frames is {info.total_frames}.")


def load_info(repo_id: str, *, local_meta: Path | None = None) -> DatasetInfo:
    """Read and validate a dataset's metadata.

    ``local_meta`` points at an already-downloaded ``info.json`` and is what the tests use — the
    validation logic must be exercised on CPU CI with no network, since its whole job is rejecting
    datasets and a check that only runs on a GPU box is a check that does not run.
    """
    if local_meta is not None:
        raw = json.loads(local_meta.read_text(encoding="utf-8"))
    else:  # pragma: no cover - requires network + huggingface_hub
        from huggingface_hub import hf_hub_download  # noqa: PLC0415 - optional, gated dependency

        path = hf_hub_download(repo_id=repo_id, filename="meta/info.json", repo_type="dataset")
        raw = json.loads(Path(path).read_text(encoding="utf-8"))

    info = parse_info(raw)
    validate(info, repo_id=repo_id)
    return info


def iter_frames(
    repo_id: str, *, limit: int | None = None
) -> Iterator[tuple[dict[str, Any], list[float], list[float]]]:  # pragma: no cover - gated
    """Yield ``(observation, recorded_action, recorded_state)`` per frame.

    Gated behind the ``[lerobot]`` extra for the same reason the policy adapters are: the default
    install stays CPU-only and six light dependencies, and this pulls a full ML stack.

    The recorded action is yielded but is NOT the study's ground truth for "correct" — it is what a
    human teleoperator did, which is a different thing from what the policy would do unattacked.
    The benign comparison arm is the POLICY's action under the benign instruction, not this. Mixing
    the two would measure "policy disagrees with human", which is not the question.
    """
    try:
        from lerobot.datasets.lerobot_dataset import LeRobotDataset  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "the [lerobot] extra is required to read frames: pip install 'provael[lerobot]'"
        ) from exc

    load_info(repo_id)  # validate before downloading gigabytes of video
    # Same reasoning as the adapter: we validated the format ourselves above, so the tag
    # lookup is redundant and rejects valid data.
    dataset = LeRobotDataset(repo_id, revision="main")
    for i, frame in enumerate(dataset):
        if limit is not None and i >= limit:
            return
        state = [float(x) for x in frame["observation.state"]]
        action = [float(x) for x in frame["action"]]
        observation = {k: v for k, v in frame.items() if k.startswith("observation")}
        yield observation, action, state


__all__ = [
    "SO101_DOF",
    "SO101_ROBOT_TYPES",
    "SUPPORTED_CODEBASE_VERSIONS",
    "DatasetInfo",
    "DatasetRejected",
    "iter_frames",
    "load_info",
    "parse_info",
    "validate",
]
