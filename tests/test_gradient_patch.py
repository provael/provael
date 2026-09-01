"""The white-box gradient patch: it must be inert without gradients, and real with them.

WHY THE INERTNESS TESTS COME FIRST. This family's whole risk is reporting a white-box null it never
attempted. `patch`, `decoy_object` and `scene_text` each measured 0/50 and PRIOR_ART.md records
that those nulls "measure the absence of" an image-space attack — so an arm that silently scored 0
without ever taking a gradient would recreate exactly the defect this family exists to fix, one
level deeper. `applicable()` is therefore the load-bearing assertion, not `perturb()`.
"""

from __future__ import annotations

import numpy as np

from provael.attacks.gradient_patch import FAMILY, GradientPatch
from provael.attacks.registry import ATTACKS, FAMILIES
from provael.recipes import CONDITIONAL_FAMILIES
from provael.types import IMAGE_KEY

H, W = 16, 16


def _obs(with_image: bool = True) -> dict:
    o: dict = {"task": "t", "instruction": "pick up the block", "step": 0, "seed": 0}
    if with_image:
        rng = np.random.default_rng(0)
        o[IMAGE_KEY] = rng.integers(0, 256, (H, W, 3), dtype=np.uint8)
    return o


def _grad_oracle(scale: float = 1.0):
    """A deterministic stand-in for a policy's input gradient — no torch, no GPU."""
    def oracle(instruction, observation, image):  # noqa: ANN001, ARG001
        g = np.zeros_like(np.asarray(image, dtype=np.float32))
        g[..., 0] = scale          # push the red channel: a fixed, checkable direction
        return g
    return oracle


# ── inertness: the assertions that keep a null honest ────────────────────────
def test_not_applicable_without_a_gradient_oracle() -> None:
    """A real image is not enough. No gradients means no white-box attempt to report."""
    a = GradientPatch()
    assert a.applicable(_obs()) is False


def test_not_applicable_without_an_image() -> None:
    a = GradientPatch()
    a.attach_gradient_oracle(_grad_oracle())
    assert a.applicable(_obs(with_image=False)) is False


def test_applicable_only_with_both() -> None:
    a = GradientPatch()
    a.attach_gradient_oracle(_grad_oracle())
    assert a.applicable(_obs()) is True


def test_perturb_is_a_no_op_without_an_oracle() -> None:
    """Never substitutes noise for a gradient — that would report black-box damage as white-box."""
    a = GradientPatch()
    obs = _obs()
    instr, out = a.perturb("pick up the block", obs)
    assert instr == "pick up the block"
    assert np.array_equal(out[IMAGE_KEY], obs[IMAGE_KEY])
    assert a.last_steps_used == 0


def test_a_declining_oracle_stops_rather_than_inventing_a_direction() -> None:
    a = GradientPatch(steps=3)
    a.attach_gradient_oracle(lambda i, o, img: None)
    obs = _obs()
    _, out = a.perturb("x", obs)
    assert a.last_steps_used == 0
    assert np.array_equal(out[IMAGE_KEY], obs[IMAGE_KEY])


# ── the attack, when it does run ─────────────────────────────────────────────
def test_perturbation_respects_the_l_inf_budget() -> None:
    """The bound is the contract: no pixel may move more than eps of full scale."""
    eps = 0.10
    a = GradientPatch(eps=eps, steps=3)
    a.attach_gradient_oracle(_grad_oracle())
    obs = _obs()
    _, out = a.perturb("x", obs)
    before = np.asarray(obs[IMAGE_KEY], dtype=np.float32) / 255.0
    after = np.asarray(out[IMAGE_KEY], dtype=np.float32) / 255.0
    # +1/255 tolerance for the uint8 round-trip, which is a quantisation step, not a budget breach.
    assert np.max(np.abs(after - before)) <= eps + 1.0 / 255.0 + 1e-6
    assert a.last_steps_used == 3


def test_it_actually_changes_the_image() -> None:
    a = GradientPatch(eps=0.10, steps=3)
    a.attach_gradient_oracle(_grad_oracle())
    obs = _obs()
    _, out = a.perturb("x", obs)
    assert not np.array_equal(out[IMAGE_KEY], obs[IMAGE_KEY])


def test_it_follows_the_gradient_sign() -> None:
    """A positive gradient must move pixels up and a negative one down — otherwise the 'attack'
    is an expensive random perturbation and the white-box label is unearned."""
    obs = _obs()
    base = np.asarray(obs[IMAGE_KEY], dtype=np.float32) / 255.0
    up = GradientPatch(eps=0.1, steps=2)
    up.attach_gradient_oracle(_grad_oracle(+1.0))
    dn = GradientPatch(eps=0.1, steps=2)
    dn.attach_gradient_oracle(_grad_oracle(-1.0))
    _, o_up = up.perturb("x", obs)
    _, o_dn = dn.perturb("x", obs)
    r_up = (np.asarray(o_up[IMAGE_KEY], dtype=np.float32) / 255.0 - base)[..., 0]
    r_dn = (np.asarray(o_dn[IMAGE_KEY], dtype=np.float32) / 255.0 - base)[..., 0]
    # Away from the [0,1] clip boundaries the two must move in opposite directions.
    interior = (base[..., 0] > 0.2) & (base[..., 0] < 0.8)
    assert interior.any()
    assert (r_up[interior] > 0).all()
    assert (r_dn[interior] < 0).all()


def test_it_is_deterministic() -> None:
    outs = []
    for _ in range(2):
        a = GradientPatch(eps=0.1, steps=3)
        a.attach_gradient_oracle(_grad_oracle())
        outs.append(a.perturb("x", _obs())[1][IMAGE_KEY])
    assert np.array_equal(outs[0], outs[1])


def test_a_mismatched_gradient_shape_is_refused() -> None:
    a = GradientPatch(steps=3)
    a.attach_gradient_oracle(lambda i, o, img: np.zeros((3, 3), dtype=np.float32))
    obs = _obs()
    _, out = a.perturb("x", obs)
    assert a.last_steps_used == 0
    assert np.array_equal(out[IMAGE_KEY], obs[IMAGE_KEY])


# ── registration and threat-model metadata ───────────────────────────────────
def test_it_is_registered_as_its_own_family() -> None:
    """Separate from `optimized_patch` on purpose: same channel, different attacker access, so a
    combined family rate would average a white-box result with a black-box one."""
    assert ATTACKS["gradient_patch"] is GradientPatch
    assert FAMILIES[FAMILY] == ["gradient_patch"]
    assert FAMILY != "optimized_patch"


def test_threat_model_metadata_records_the_extra_access() -> None:
    a = GradientPatch()
    assert a.attacker_access == "white-box-gradient"
    assert ATTACKS["patch_hijack"]().attacker_access == "black-box-query"
    assert a.eai_id == "EAI02"
    assert a.action_head_class is None  # recorded from the policy, not asserted by the attack


def test_the_family_declares_why_it_skips_on_cpu() -> None:
    """A family that scores nothing must say why, or a reader cannot tell N/A from a zero."""
    assert FAMILY in CONDITIONAL_FAMILIES
    assert "gradient" in CONDITIONAL_FAMILIES[FAMILY]
