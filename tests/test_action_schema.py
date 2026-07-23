"""ActionSchema: which action channels are motion, queried at runtime, N/A when incompatible.

Pins the schema by running it: validation (in-range, disjoint, named), motion extraction for
4D/7D/8D/custom layouts, the explicit N/A on a too-short or non-finite action (never a guessed
slice), gripper never read as motion, the stub schema reproducing the legacy ``MOTION_SLICE`` slice,
and the runner wiring the SUITE's schema onto the optimized action attacks.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from provael.attacks.optimized import TargetedTrajectoryHijack, _motion_of
from provael.attacks.optimized_patch import OptimizedPatchHijack
from provael.policies.stub import StubPolicy
from provael.runner import _configure_optimized
from provael.scoring.action_schema import (
    SEVEN_DOF_DELTA_SCHEMA,
    STUB_ACTION_SCHEMA,
    ActionSchema,
)
from provael.suites.stub import StubSuite


def _seven_dof() -> ActionSchema:
    return SEVEN_DOF_DELTA_SCHEMA


# --------------------------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------------------------

def test_index_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError, match="out of range"):
        ActionSchema(total_dim=4, translation_indices=(1, 2, 9))


def test_overlapping_component_groups_are_rejected() -> None:
    with pytest.raises(ValidationError, match="more than one component"):
        ActionSchema(total_dim=7, translation_indices=(0, 1, 2), gripper_indices=(2,))


def test_a_schema_must_declare_a_translation_channel() -> None:
    with pytest.raises(ValidationError, match="at least one translation"):
        ActionSchema(total_dim=4, translation_indices=())


def test_component_names_length_must_match_total_dim() -> None:
    with pytest.raises(ValidationError, match="component_names"):
        ActionSchema(total_dim=7, translation_indices=(0, 1, 2), component_names=("a", "b"))


# --------------------------------------------------------------------------------------------
# motion extraction across layouts — the whole point
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("schema", "action", "expected"),
    [
        # 7-DoF ee-delta: translation is channels 0-2 (NOT 1-3)
        (SEVEN_DOF_DELTA_SCHEMA, [1.0, 2.0, 3.0, 0, 0, 0, 9.0], (1.0, 2.0, 3.0)),
        # stub: channel 0 danger, translation 1-3
        (STUB_ACTION_SCHEMA, [0.9, 1.0, 2.0, 3.0] + [0.0] * 7, (1.0, 2.0, 3.0)),
        # a 4-DoF planar+gripper layout: translation 0-1, gripper 3
        (ActionSchema(total_dim=4, translation_indices=(0, 1), gripper_indices=(3,)),
         [5.0, 6.0, 0.0, 9.0], (5.0, 6.0)),
        # an 8-DoF dual-arm-ish custom layout: translation at 2-4
        (ActionSchema(total_dim=8, translation_indices=(2, 3, 4)),
         [0, 0, 7.0, 8.0, 9.0, 0, 0, 0], (7.0, 8.0, 9.0)),
    ],
)
def test_motion_reads_declared_channels(
    schema: ActionSchema, action: list[float], expected: tuple[float, ...]
) -> None:
    assert schema.motion(np.asarray(action, dtype=np.float32)) == expected


def test_gripper_is_never_read_as_motion() -> None:
    # channel 6 (gripper=9.0) must not appear in the motion vector
    motion = SEVEN_DOF_DELTA_SCHEMA.motion(np.asarray([1, 2, 3, 0, 0, 0, 9.0], dtype=np.float32))
    assert motion == (1.0, 2.0, 3.0) and 9.0 not in motion


# --------------------------------------------------------------------------------------------
# N/A: incompatible actions are never guessed
# --------------------------------------------------------------------------------------------

def test_too_short_action_is_na_not_a_guessed_slice() -> None:
    # a 3-DoF action cannot satisfy a schema whose max channel is 6
    action = np.asarray([1.0, 2.0, 3.0], dtype=np.float32)
    assert SEVEN_DOF_DELTA_SCHEMA.is_compatible(action) is False
    assert SEVEN_DOF_DELTA_SCHEMA.motion(action) is None


def test_non_finite_action_is_incompatible() -> None:
    action = np.asarray([1.0, np.nan, 3.0, 0, 0, 0, 0], dtype=np.float32)
    assert SEVEN_DOF_DELTA_SCHEMA.is_compatible(action) is False
    assert SEVEN_DOF_DELTA_SCHEMA.motion(action) is None


def test_digest_is_stable_and_layout_sensitive() -> None:
    assert SEVEN_DOF_DELTA_SCHEMA.digest() == SEVEN_DOF_DELTA_SCHEMA.digest()
    other = SEVEN_DOF_DELTA_SCHEMA.model_copy(update={"translation_indices": (1, 2, 3)})
    assert other.digest() != SEVEN_DOF_DELTA_SCHEMA.digest()


# --------------------------------------------------------------------------------------------
# the optimized attacks use the schema, not a hard-coded slice
# --------------------------------------------------------------------------------------------

def test_motion_of_falls_back_to_stub_slice_without_a_schema() -> None:
    # backward compatibility: the legacy MOTION_SLICE=(1,4) path is preserved when schema is None
    action = np.asarray([0.9, 1.0, 2.0, 3.0, 0.0, 0.0, 0.0], dtype=np.float32)
    assert _motion_of(action) == [1.0, 2.0, 3.0]
    assert _motion_of(action, STUB_ACTION_SCHEMA) == [1.0, 2.0, 3.0]  # schema agrees


def test_optimized_attacks_default_to_the_stub_schema() -> None:
    assert TargetedTrajectoryHijack().action_schema is STUB_ACTION_SCHEMA
    assert OptimizedPatchHijack().action_schema is STUB_ACTION_SCHEMA


def test_runner_wires_the_suite_schema_onto_optimized_attacks() -> None:
    attack = TargetedTrajectoryHijack(action_schema=_seven_dof())  # start with a different schema
    assert attack.action_schema is SEVEN_DOF_DELTA_SCHEMA
    _configure_optimized([attack], StubPolicy(), StubSuite(), query_budget=None)
    # the runner overrode it with the SUITE's declared schema (the stub's)
    assert attack.action_schema == STUB_ACTION_SCHEMA


def test_stub_suite_declares_its_action_schema() -> None:
    assert StubSuite().action_schema() == STUB_ACTION_SCHEMA
