# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""What a policy was actually handed in one episode (P1.8).

A configuration that never reaches the code that reads it changes nothing, while the report says
it was in force (a config key read nowhere, GR00T#745). And a perturbation that was configured is
not one that was delivered. So each episode records, at the one boundary every input crosses
(right before ``policy.act``, after the attack and any defense):

* the sha256 of each distinct instruction string the policy was handed;
* a rolling sha256 over the primary camera image it was handed on each step;
* the attack's declared parameters (:attr:`provael.attacks.base.Attack.parameters`) as they were
  read while the episode ran: the realized perturbation configuration.

The benign arm goes through the same path with an empty parameter spec, so its record is the
reference an attacked twin's is read against.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from typing import Any

import numpy as np
from pydantic import BaseModel

from provael.types import IMAGE_KEY, DeliveredInputs, Observation


def jsonable(value: Any) -> Any:
    """``value`` as a JSON value, deterministically, or ``TypeError`` for anything else.

    A declared parameter is recorded in ``report.json``, so it has to serialise the same way in
    every process: no ``repr`` (which can carry a memory address), no unordered sets.
    """
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, np.ndarray):
        return {
            "sha256": hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest(),
            "dtype": value.dtype.str,
            "shape": list(value.shape),
        }
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    raise TypeError(
        f"a declared attack parameter must be recordable as JSON; got {type(value).__name__}"
    )


class DeliveryLog:
    """One episode's delivered inputs, accumulated step by step by the runner."""

    def __init__(self) -> None:
        self._instructions: dict[str, None] = {}
        self._image = hashlib.sha256()
        self._image_steps = 0

    def handed(self, step: int, instruction: str, observation: Observation) -> None:
        """Record what the policy is about to be handed at ``step``."""
        digest = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
        self._instructions.setdefault(digest, None)
        image = observation.get(IMAGE_KEY)
        if isinstance(image, np.ndarray):
            frame = np.ascontiguousarray(image)
            header = f"{step}\0{frame.dtype.str}\0{frame.shape}\0".encode()
            self._image.update(header + frame.tobytes())
            self._image_steps += 1

    def finish(self, parameters: Mapping[str, Any]) -> DeliveredInputs:
        return DeliveredInputs(
            instruction_sha256=list(self._instructions),
            image_sha256=self._image.hexdigest() if self._image_steps else None,
            image_steps=self._image_steps,
            parameters={name: jsonable(value) for name, value in sorted(parameters.items())},
        )


__all__ = ["DeliveryLog", "jsonable"]
