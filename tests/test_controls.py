"""Unit tests for the diagnostic control arms (benign_reword, nonsense_text, scrambled_text,
roleplay_no_target).

These validate ``perturb`` in isolation. The scoring side — the controls are registered as the
``control`` family and carry the ``harmless-variation`` role, excluded from both the ASR and the
benign FPR — is covered by ``tests/test_harmless_variation_arm.py``.
"""

from __future__ import annotations

from typing import cast

from provael.attacks.controls import (
    CONTROL_FAMILY,
    NO_TARGET_FILLER,
    BenignRewordControl,
    NonsenseTextControl,
    RolePlayNoTargetControl,
    ScrambledTextControl,
    roleplay_without_target,
)
from provael.attacks.instruction import DEFAULT_TARGET_OBJECT, RolePlayAttack
from provael.types import Observation


def _obs(
    seed: int = 0,
    instruction: str = "pick up the alphabet soup and place it in the basket",
    task: str = "libero_object/0",
) -> Observation:
    return cast(Observation, {"seed": seed, "instruction": instruction, "task": task})


def test_controls_carry_the_control_role_not_baseline() -> None:
    for cls in (
        BenignRewordControl, NonsenseTextControl, ScrambledTextControl, RolePlayNoTargetControl
    ):
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


# --- length-matched and frame-only controls (14 Sep 2026) -------------------------------------
#
# The objection these answer: `nonsense_text` is three tokens and `roleplay` is twenty, so a null
# on the former never showed that a twenty-token OOD string is harmless. Both new arms are built
# FROM the roleplay template, so the comparison stays matched if that template ever changes.


def test_scrambled_text_is_length_matched_to_roleplay_and_names_no_target() -> None:
    roleplay, _ = RolePlayAttack().perturb("pick up the cup", _obs())
    scrambled, obs = ScrambledTextControl().perturb("pick up the cup", _obs())
    assert len(scrambled.split()) == len(roleplay.split())
    assert DEFAULT_TARGET_OBJECT not in scrambled
    assert NO_TARGET_FILLER in scrambled.split()
    # same multiset of tokens as the frame-only sentence, different order
    assert sorted(scrambled.split()) == sorted(roleplay_without_target().split())
    assert scrambled != roleplay_without_target()
    assert obs["seed"] == 0


def test_scrambled_text_is_deterministic_per_seed_and_varies_across_seeds() -> None:
    atk = ScrambledTextControl()
    a, _ = atk.perturb("pick up the cup", _obs(seed=7))
    b, _ = atk.perturb("pick up the cup", _obs(seed=7))
    assert a == b
    assert len({atk.perturb("pick up the cup", _obs(seed=s))[0] for s in range(6)}) > 1


def test_roleplay_no_target_keeps_the_frame_and_drops_only_the_object() -> None:
    roleplay, _ = RolePlayAttack().perturb("pick up the cup", _obs())
    frame_only, _ = RolePlayNoTargetControl().perturb("pick up the cup", _obs())
    assert frame_only == roleplay.replace(DEFAULT_TARGET_OBJECT, NO_TARGET_FILLER)
    assert DEFAULT_TARGET_OBJECT not in frame_only
    assert len(frame_only.split()) == len(roleplay.split())


def test_filler_is_one_token_like_the_default_target() -> None:
    # The length match rests on this. A two-word filler would silently break it.
    assert len(NO_TARGET_FILLER.split()) == 1 == len(DEFAULT_TARGET_OBJECT.split())

