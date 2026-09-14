"""The LeRobot adapter's white-box surfaces: INT8-emulated weight access and input gradients.

Three layers, gated by what the environment can run:

* pure numpy (always): the INT8 view and the delta arithmetic, and the runner's wiring with fake
  policies — including that the deterministic stub path is untouched;
* ``torch`` + ``lerobot`` importable (the ``[lerobot]`` extra; CI's CPU lane skips): the adapter's
  methods against a tiny SmolVLA-shaped fake, so the graph, the exact restore and the by-identity
  camera lookup are exercised without a checkpoint;
* ``PROVAEL_INTEGRATION=1`` (GPU lane, or a patient CPU): the real LIBERO-fine-tuned SmolVLA
  checkpoint, no simulator — one synthetic observation with the env's feature shapes.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

import numpy as np
import pytest

from provael.attacks.gradient_patch import GradientOracleAttack, GradientPatch
from provael.attacks.instruction import RolePlayAttack
from provael.attacks.weight_integrity import (
    GradientBitFlip,
    RandomBitFlip,
    SensitivityReferencePolicy,
    WeightAccessible,
)
from provael.policies.base import InputGradientProvider, PolicyAdapter
from provael.policies.lerobot_adapter import (
    INT8_MAX,
    LeRobotAdapter,
    dequantized_delta,
    symmetric_int8,
)
from provael.policies.stub import StubPolicy
from provael.runner import _configure_optimized, _configure_weight_reference
from provael.suites.stub import StubSuite
from provael.types import IMAGE_KEY, Action, Observation

_HAS_TORCH = importlib.util.find_spec("torch") is not None
_HAS_LEROBOT = importlib.util.find_spec("lerobot") is not None
_INTEGRATION = os.environ.get("PROVAEL_INTEGRATION") == "1"


# ── the INT8 view (pure numpy) ───────────────────────────────────────────────
def test_symmetric_int8_is_a_faithful_view() -> None:
    rng = np.random.default_rng(0)
    w = rng.standard_normal((6, 5)).astype(np.float32) * 0.01
    q, scale = symmetric_int8(w)
    assert q.dtype == np.int8 and q.shape == (30,)
    assert scale == pytest.approx(float(np.abs(w).max()) / INT8_MAX)
    assert int(np.abs(q.astype(int)).max()) == INT8_MAX  # the peak maps to the edge of the range
    assert np.abs(q.astype(np.float32) * scale - w.reshape(-1)).max() <= scale / 2 + 1e-7


def test_symmetric_int8_of_nothing_is_empty_and_of_zeros_is_zeros() -> None:
    q, scale = symmetric_int8(np.zeros(0, dtype=np.float32))
    assert q.size == 0 and scale == 1.0
    q, scale = symmetric_int8(np.zeros(4, dtype=np.float32))
    assert list(q) == [0, 0, 0, 0] and scale == 1.0


def test_dequantized_delta_is_zero_where_untouched_and_exact_where_flipped() -> None:
    clean = np.array([3, -7, 100, 0], dtype=np.int8)
    corrupt = clean.copy()
    corrupt.view(np.uint8)[1] ^= np.uint8(1 << 7)  # the sign bit of parameter 1: -7 -> 121
    delta = dequantized_delta(corrupt, clean, scale=0.5)
    assert delta.dtype == np.float32
    assert delta[0] == 0.0 and delta[2] == 0.0 and delta[3] == 0.0
    assert delta[1] == pytest.approx((int(corrupt[1]) - (-7)) * 0.5)
    assert np.all(dequantized_delta(clean, clean, 0.5) == 0.0)  # restore == no change
    with pytest.raises(ValueError):
        dequantized_delta(clean[:2], clean, 0.5)


# ── an unloaded adapter is not attackable, and says so as "not applicable" ───
def test_unloaded_adapter_exposes_no_weights_so_the_family_is_not_applicable() -> None:
    adapter = LeRobotAdapter()
    assert isinstance(adapter, WeightAccessible)
    assert isinstance(adapter, SensitivityReferencePolicy)
    assert isinstance(adapter, InputGradientProvider)
    assert adapter.quantized_parameters().size == 0
    assert adapter.provides_input_gradient() is False
    arm = GradientBitFlip(flips=4)
    assert arm.corrupt(adapter, episode_seed=0) is None
    assert arm.applicable({}) is False


# ── runner wiring, with fakes ────────────────────────────────────────────────
class _GradPolicy(PolicyAdapter):
    name = "gradpolicy"

    def __init__(self, ready: bool) -> None:
        self.ready = ready
        self.calls = 0

    def load(self) -> None: ...

    def act(self, observation: Observation, instruction: str) -> Action:
        return np.zeros(5, dtype=np.float32)

    def provides_input_gradient(self) -> bool:
        return self.ready

    def input_gradient(self, instruction: str, observation: Observation, image: Any) -> Any:
        self.calls += 1
        return np.ones_like(np.asarray(image, dtype=np.float32))


def test_runner_attaches_the_input_gradient_only_when_the_policy_provides_one() -> None:
    for ready in (True, False):
        attack = GradientPatch(steps=1)
        assert isinstance(attack, GradientOracleAttack)
        policy = _GradPolicy(ready)
        _configure_optimized([attack, RolePlayAttack()], policy, StubSuite(), None)
        obs = {"seed": 0, "step": 0, IMAGE_KEY: np.zeros((4, 4, 3), dtype=np.uint8)}
        assert attack.applicable(obs) is ready
        if ready:
            attack.perturb("x", obs)
            assert policy.calls == 1 and attack.last_steps_used == 1


def test_runner_attaches_no_reset_callback_to_the_gradient_oracle() -> None:
    """A reset after every refinement would make the attacked arm re-plan every step."""
    attack = GradientPatch(steps=1)
    _configure_optimized([attack], _GradPolicy(True), StubSuite(), None)
    assert attack._reset is None


class _ReferencePolicy(StubPolicy):
    """The stub, plus the reference hook a real adapter needs — to see what the runner hands over."""

    def __init__(self) -> None:
        super().__init__()
        self.reference: tuple[Observation, str, int] | None = None

    def set_sensitivity_reference(
        self, observation: Observation, instruction: str, seed: int
    ) -> None:
        self.reference = (observation, instruction, seed)


def test_runner_hands_over_the_first_task_at_the_run_seed_only_for_weight_arms() -> None:
    suite = StubSuite()
    policy = _ReferencePolicy()
    policy.load()
    _configure_weight_reference([RolePlayAttack()], policy, suite, "reach", 3)
    assert policy.reference is None  # no weight arm: nothing to reference, no extra reset
    _configure_weight_reference([RolePlayAttack(), RandomBitFlip(flips=1)], policy, suite, "reach", 3)
    assert policy.reference is not None
    observation, instruction, seed = policy.reference
    assert seed == 3 and observation["task"] == "reach"
    assert instruction == str(observation.get("instruction", ""))


def test_the_stub_never_enters_the_reference_path() -> None:
    """The deterministic fixture has a closed-form derivative; the goldens must not move."""
    stub = StubPolicy()
    assert not isinstance(stub, SensitivityReferencePolicy)
    assert not isinstance(stub, InputGradientProvider)


# ── the adapter's methods against a SmolVLA-shaped fake (torch + lerobot) ────
@pytest.fixture
def fake_adapter() -> LeRobotAdapter:
    torch = pytest.importorskip("torch")
    pytest.importorskip("lerobot")
    nn = torch.nn

    class _Config:
        n_action_steps = 2
        image_features = {"observation.images.image": None, "observation.images.image2": None}

    class _VLM(nn.Module):
        def embed_image(self, image: Any) -> Any:
            # A feature that depends on the pixels: spatial mean per channel, then a fixed map.
            return image.mean(dim=(2, 3)) @ self.mix

        def __init__(self) -> None:
            super().__init__()
            self.mix = nn.Parameter(torch.eye(3), requires_grad=False)

    class _Model(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.vlm_with_expert = _VLM()
            self.action_out_proj = nn.Linear(4, 32, bias=True)
            with torch.no_grad():
                self.action_out_proj.weight.copy_(
                    torch.linspace(-0.05, 0.05, 128).reshape(32, 4)
                )

        def sample_actions(self, images, img_masks, tokens, masks, state):  # noqa: ANN001
            # (B, chunk, dim): the expert's hidden is the padded state, straight into the head.
            hidden = torch.nn.functional.pad(state, (0, 4 - state.shape[-1]))
            out = self.action_out_proj(hidden)  # (B, 32)
            return out.unsqueeze(1).repeat(1, 3, 1)

    class _Policy(nn.Module):
        config = _Config()

        def __init__(self) -> None:
            super().__init__()
            self.model = _Model()
            self.resets = 0

        def reset(self) -> None:
            self.resets += 1

        def prepare_images(self, batch: dict[str, Any]) -> tuple[list[Any], list[Any]]:
            keys = [k for k in self.config.image_features if k in batch]
            return [batch[k] * 2.0 - 1.0 for k in keys], [torch.ones(1, dtype=torch.bool)] * len(keys)

        def prepare_state(self, batch: dict[str, Any]) -> Any:
            return batch["observation.state"]

    adapter = LeRobotAdapter(model_id="fake", device="cpu")
    adapter._torch = torch
    adapter._policy = _Policy()
    adapter._loaded = True
    adapter._env_preprocess = lambda b: {**b, "flipped": True}  # stands in for LiberoProcessorStep
    adapter._preprocess = lambda b: {
        **b,
        "observation.language.tokens": torch.zeros(1, 4, dtype=torch.long),
        "observation.language.attention_mask": torch.ones(1, 4, dtype=torch.bool),
    }
    return adapter


def _fake_observation(seed: int = 0) -> Observation:
    rng = np.random.default_rng(seed)
    pixels = {
        "image": rng.integers(0, 256, (1, 8, 8, 3), dtype=np.uint8),
        "image2": rng.integers(0, 256, (1, 8, 8, 3), dtype=np.uint8),
    }
    raw = {"pixels": pixels, "agent_pos": np.array([[0.1, 0.2, 0.3]], dtype=np.float32)}
    return {
        "task": "libero_object/0", "instruction": "pick up the bowl", "seed": seed, "step": 0,
        "raw": raw, IMAGE_KEY: pixels["image"][0], "pixels_key": "image",
    }


def test_fake_weight_surface_round_trips_exactly(fake_adapter: LeRobotAdapter) -> None:
    torch = pytest.importorskip("torch")
    layer = fake_adapter._weight_layer()
    before = layer.weight.detach().clone()
    q = fake_adapter.quantized_parameters()
    assert q.shape == (128,) and q.dtype == np.int8
    corrupt = q.copy()
    corrupt[5] = np.int8(int(q[5]) ^ 0x40)
    fake_adapter.load_quantized_parameters(corrupt)
    after = layer.weight.detach()
    changed = (after != before).sum().item()
    assert changed == 1
    expected = (int(corrupt[5]) - int(q[5])) * fake_adapter._weight_scale
    assert (after - before).reshape(-1)[5].item() == pytest.approx(expected, rel=1e-5)
    fake_adapter.load_quantized_parameters(q)
    assert torch.equal(layer.weight.detach(), before)  # bit-for-bit, not approximately
    with pytest.raises(ValueError):
        fake_adapter.load_quantized_parameters(q[:10])


def test_fake_sensitivity_is_the_autograd_gradient_at_the_reference(
    fake_adapter: LeRobotAdapter,
) -> None:
    with pytest.raises(RuntimeError, match="reference"):
        fake_adapter.parameter_sensitivity()
    obs = _fake_observation()
    fake_adapter.set_sensitivity_reference(obs, obs["instruction"], seed=0)
    fake_adapter.quantized_parameters()
    sens = fake_adapter.parameter_sensitivity()
    assert sens.shape == (128,) and sens.dtype == np.float32 and np.isfinite(sens).all()
    # danger = mean over executed steps of ||a[:3]||^2 with a = W h + b, h = pad(state):
    # d/dW[i, j] = 2 a_i h_j for i < 3, else 0 — so rows 3.. of the gradient are zero.
    grid = sens.reshape(32, 4)
    assert np.abs(grid[3:]).max() == 0.0
    assert np.abs(grid[:3]).max() > 0.0
    assert fake_adapter._policy.resets == 1  # the reference pass leaves no queued chunk behind
    # the weight arm then runs end to end and restores exactly
    layer = fake_adapter._weight_layer()
    before = layer.weight.detach().clone()
    arm = GradientBitFlip(flips=2)
    record = arm.corrupt(fake_adapter, episode_seed=0)
    assert record is not None and record.flips == 2 and record.emulated is True
    assert not fake_adapter._torch.equal(layer.weight.detach(), before)
    arm.restore(fake_adapter)
    assert fake_adapter._torch.equal(layer.weight.detach(), before)


def test_fake_input_gradient_flows_to_the_suite_frame(fake_adapter: LeRobotAdapter) -> None:
    obs = _fake_observation()
    assert fake_adapter.provides_input_gradient()
    x = np.asarray(obs[IMAGE_KEY], dtype=np.float32) / 255.0
    at_clean = fake_adapter.input_gradient(obs["instruction"], obs, x)
    # zero up to the rounding between uint8/255 in the candidate and in the clean pass
    assert at_clean is not None and at_clean.shape == x.shape and np.abs(at_clean).max() < 1e-6
    shifted = np.clip(x + 0.1, 0.0, 1.0)
    grad = fake_adapter.input_gradient(obs["instruction"], obs, shifted)
    assert grad is not None and grad.shape == x.shape and grad.dtype == np.float32
    assert np.isfinite(grad).all() and np.abs(grad).max() > 0.0
    # the feature is the spatial mean, so the gradient is uniform over pixels and non-negative
    # where the shift moved the mean up: the direction points back along the objective
    assert (grad >= 0).all()
    # and the attack lands a perturbation through it
    attack = GradientPatch(eps=0.1, steps=2)
    attack.attach_gradient_oracle(fake_adapter.input_gradient, None)
    _, adv = attack.perturb(obs["instruction"], obs)
    assert attack.last_steps_used == 2
    assert np.abs(adv[IMAGE_KEY].astype(int) - obs[IMAGE_KEY].astype(int)).max() > 0


# ── the real checkpoint, no simulator (PROVAEL_INTEGRATION=1) ────────────────
@pytest.mark.skipif(
    not (_INTEGRATION and _HAS_TORCH and _HAS_LEROBOT),
    reason="requires PROVAEL_INTEGRATION=1 and the [lerobot] extra (downloads the checkpoint)",
)
def test_real_smolvla_exposes_both_surfaces() -> None:
    from lerobot.envs.factory import make_env_config

    from provael.policies.lerobot_adapter import LIBERO_FINETUNED_SMOLVLA
    from provael.types import SuiteFeatures

    cfg = make_env_config("libero", task="libero_object", task_ids=[0], obs_type="pixels_agent_pos")
    features = SuiteFeatures(
        action_dim=7, fps=int(getattr(cfg, "fps", 30)),
        camera_keys=tuple(k for k in cfg.features if str(k).startswith("pixels")),
        image_key=IMAGE_KEY, task_suite="libero_object", env_config=cfg,
    )
    adapter = LeRobotAdapter(model_id=LIBERO_FINETUNED_SMOLVLA, name="smolvla", device="cpu")
    adapter.set_features(features)
    adapter.load()
    rng = np.random.default_rng(0)
    pixels = {
        "image": rng.integers(0, 256, (1, 256, 256, 3), dtype=np.uint8),
        "image2": rng.integers(0, 256, (1, 256, 256, 3), dtype=np.uint8),
    }
    raw = {
        "pixels": pixels,
        "robot_state": {
            "eef": {"pos": np.array([[0.0, 0.0, 1.0]], dtype=np.float32),
                    "quat": np.array([[0.0, 0.0, 0.0, 1.0]], dtype=np.float32)},
            "gripper": {"qpos": np.array([[0.02, -0.02]], dtype=np.float32)},
        },
    }
    obs: Observation = {
        "task": "libero_object/0", "instruction": "pick up the alphabet soup and place it in the basket",
        "seed": 0, "step": 0, "raw": raw, IMAGE_KEY: pixels["image"][0], "pixels_key": "image",
    }
    q = adapter.quantized_parameters()
    assert q.size > 0
    adapter.set_sensitivity_reference(obs, str(obs["instruction"]), 0)
    sens = adapter.parameter_sensitivity()
    assert sens.shape == q.shape and np.isfinite(sens).all()
    layer = adapter._weight_layer()
    before = layer.weight.detach().clone()
    arm = RandomBitFlip(flips=4)
    assert arm.corrupt(adapter, episode_seed=0) is not None
    arm.restore(adapter)
    assert adapter._torch.equal(layer.weight.detach(), before)
    x = np.asarray(obs[IMAGE_KEY], dtype=np.float32) / 255.0
    grad = adapter.input_gradient(str(obs["instruction"]), obs, np.clip(x + 0.05, 0, 1))
    assert grad is not None and grad.shape == x.shape and np.isfinite(grad).all()
    assert np.abs(grad).max() > 0.0
