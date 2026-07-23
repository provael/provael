"""A first-class action schema — which action channels mean what, queried at runtime.

The optimized action attacks used to read the end-effector translation delta from a hard-coded
``MOTION_SLICE = (1, 4)`` — correct for the stub's ``0=danger, 1-3=motion`` layout, but wrong for a
real 7-DoF delta policy whose translation is channels ``0-2``. Reading the wrong channels would make
the search optimise garbage. :class:`ActionSchema` removes that magic: an adapter declares its real
layout, an attack asks the schema which channels are translation, and an **incompatible** schema
yields an explicit N/A rather than a guessed slice.

This is deliberately minimal — enough to make the action-space attacks honest — but carries the
provenance an execution manifest needs (units, frame, control mode, source, a stable digest).
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, Field, model_validator

from provael.types import Action

#: Action-schema format version (bump when the ActionSchema fields change).
ACTION_SCHEMA_VERSION = 1


class ActionSchema(BaseModel):
    """The layout of a policy/suite's action vector: which indices are translation/rotation/gripper.

    An attack that perturbs or reads a motion component **must** go through this rather than assume
    a slice. ``is_compatible`` / ``motion`` return an explicit N/A (``False`` / ``None``) when the
    runtime action does not match the declared layout, so an incompatible policy is never silently
    mis-read.
    """

    total_dim: int = Field(..., gt=0, description="Number of channels in the action vector.")
    translation_indices: tuple[int, ...] = Field(
        ..., description="Channels holding the end-effector translation delta (the 'motion')."
    )
    rotation_indices: tuple[int, ...] = Field(
        default=(), description="Channels holding the rotation delta, if any."
    )
    gripper_indices: tuple[int, ...] = Field(
        default=(), description="Gripper channel(s); NEVER treated as Cartesian motion."
    )
    component_names: tuple[str, ...] = Field(
        default=(), description="Optional per-channel names; if given, must have length total_dim."
    )
    units: str = Field("unitless", description="Units of the translation channels (e.g. 'm').")
    frame: str = Field("unspecified", description="Reference frame (e.g. 'ee', 'base', 'world').")
    control_mode: str = Field("unspecified", description="e.g. 'ee_delta', 'joint', 'absolute'.")
    source: str = Field("unspecified", description="Adapter/suite that declared this schema.")
    schema_version: int = Field(ACTION_SCHEMA_VERSION, description="ActionSchema format version.")

    @model_validator(mode="after")
    def _check_indices(self) -> ActionSchema:
        groups = {
            "translation": self.translation_indices,
            "rotation": self.rotation_indices,
            "gripper": self.gripper_indices,
        }
        seen: set[int] = set()
        for name, idxs in groups.items():
            for i in idxs:
                if not 0 <= i < self.total_dim:
                    raise ValueError(
                        f"{name} index {i} out of range for total_dim={self.total_dim}"
                    )
                if i in seen:
                    raise ValueError(f"channel {i} is claimed by more than one component group")
                seen.add(i)
        if not self.translation_indices:
            raise ValueError("an ActionSchema must declare at least one translation channel")
        if self.component_names and len(self.component_names) != self.total_dim:
            raise ValueError(
                f"component_names has {len(self.component_names)} entries, expected total_dim="
                f"{self.total_dim}"
            )
        return self

    def _flat(self, action: Action) -> npt.NDArray[np.float64]:
        return np.asarray(action, dtype=np.float64).reshape(-1)

    def _max_index(self) -> int:
        idxs = (*self.translation_indices, *self.rotation_indices, *self.gripper_indices)
        return max(idxs) if idxs else -1

    def is_compatible(self, action: Action) -> bool:
        """Whether ``action`` exposes every channel this schema declares (and they are finite).

        Checks the declared component indices are present, not the full ``total_dim`` — an attack
        only needs the channels it reads. A too-short or non-finite action is incompatible (N/A).
        """
        needed = self._max_index() + 1
        flat = self._flat(action)
        return flat.size >= needed and bool(np.all(np.isfinite(flat[:needed])))

    def motion(self, action: Action) -> tuple[float, ...] | None:
        """The translation delta of ``action`` per this schema, or ``None`` if incompatible (N/A).

        Never guesses: a too-short or non-finite action returns None rather than a padded/zeroed
        slice, so a downstream search cannot optimise a phantom motion.
        """
        if not self.is_compatible(action):
            return None
        flat = self._flat(action)
        return tuple(float(flat[i]) for i in self.translation_indices)

    def digest(self) -> str:
        """Stable SHA-256 of the canonical schema (for execution-manifest provenance)."""
        payload = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _named(n: int, names: dict[int, str]) -> tuple[str, ...]:
    return tuple(names.get(i, f"aux{i}") for i in range(n))


#: The stub suite's action convention: channel 0 is the danger axis, channels 1-3 are the
#: end-effector translation delta the suite thresholds. Matches the legacy ``MOTION_SLICE=(1, 4)``.
STUB_ACTION_SCHEMA = ActionSchema(
    total_dim=11,
    translation_indices=(1, 2, 3),
    component_names=_named(11, {0: "danger", 1: "tx", 2: "ty", 3: "tz", 4: "backdoor"}),
    units="unitless",
    frame="ee",
    control_mode="stub_danger_plus_delta",
    source="stub",
)

#: A generic real 7-DoF end-effector delta (x, y, z, roll, pitch, yaw, gripper). Translation is
#: channels 0-2 — NOT the stub's 1-3 — which is exactly the layout the hard-coded slice got wrong.
SEVEN_DOF_DELTA_SCHEMA = ActionSchema(
    total_dim=7,
    translation_indices=(0, 1, 2),
    rotation_indices=(3, 4, 5),
    gripper_indices=(6,),
    component_names=("tx", "ty", "tz", "rx", "ry", "rz", "gripper"),
    units="m",
    frame="ee",
    control_mode="ee_delta",
    source="generic-7dof-delta",
)


__all__ = [
    "ACTION_SCHEMA_VERSION",
    "ActionSchema",
    "STUB_ACTION_SCHEMA",
    "SEVEN_DOF_DELTA_SCHEMA",
]
