"""Unit tests for the diagnostic control arms (benign_reword, nonsense_text).

These validate ``perturb`` in isolation. They deliberately do not exercise the scoring
aggregation, because the controls are not wired into the registry/role model yet (see
``provael.attacks.controls`` module docstring for the wiring decision).
"""

from __future__ import annotations

from typing import cast

from provael.attacks.controls import (
    CONTROL_FAMILY,
    BenignRewordControl,
    NonsenseTextControl,
)
from provael.types import Observation


def _obs(
    seed: int = 0,
    instruction: str = "pick up the alphabet soup and place it in the basket",
    task: str = "libero_object/0",
) -> Observation:
    return cast(Observation, {"seed": seed, "instruction": instruction, "task": task})


def test_controls_carry_the_control_role_not_baseline() -> None:
    for cls in (BenignRewordControl, NonsenseTextControl):
        atk = cls()
        assert atk.family == CONTROL_FAMILY
        assert atk.family != "baseline"


def test_benign_reword_preserves_task_and_adds_no_unsafe_target() -> None:
    original = "pick up the alphabet soup and place it in the basket"
    reworded, obs = BenignRewordControl().perturb(original, _obs(instruction=original))
    # the benign task survives verbatim
    assert "alphabet soup" in reworded and "basket" in reworded
    # unlike an instruction ATTACK, no unsafe target is smuggled in
    assert "knife" not in reworded.lower()
    # no double period from the template
    assert not reworded.endswith("..")
    # the observation is returned untouched
    assert obs["seed"] == 0


def test_benign_reword_is_deterministic_and_varies_across_seeds() -> None:
    atk = BenignRewordControl()
    a, _ = atk.perturb("pick up the cup", _obs(seed=3))
    b, _ = atk.perturb("pick up the cup", _obs(seed=3))
    assert a == b  # same seed -> same phrasing (reproducible)
    variants = {atk.perturb("pick up the cup", _obs(seed=s))[0] for s in range(4)}
    assert len(variants) > 1  # different seeds exercise the bank


def test_nonsense_text_drops_the_instruction_semantics() -> None:
    out, _ = NonsenseTextControl().perturb("pick up the alphabet soup", _obs())
    assert out == NonsenseTextControl.NONSENSE
    assert "soup" not in out
