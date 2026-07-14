"""P0.2 — the LIBERO real-path predicate is not theater.

Two halves, mirroring ``test_libero_adapter.py``:

* A **CPU predicate test** (runs anywhere, no sim): the *real* combined
  :meth:`~provael.suites.base.SuiteAdapter.evaluate_unsafe` path — the same one the runner calls —
  flags an end-effector position inside the keep-out zone and clears one outside it, driven only by
  the verified ``ee_pos`` signal. This proves the predicate has teeth without a simulator.
* **Gated integration tests** (skipped unless ``PROVAEL_INTEGRATION=1`` AND ``lerobot`` is importable)
  that exercise the same predicate against a REAL LIBERO rollout: a benign rollout stays out of the
  keep-out zone, and a deliberately in-zone end-effector (built from a real observation) is flagged.
  Enable on a provisioned box::

      pip install 'provael[lerobot]' 'lerobot[libero]==0.5.1'
      PROVAEL_INTEGRATION=1 pytest tests/test_libero_realpath.py -q
"""

from __future__ import annotations

import importlib.util
import os

import pytest

from provael.policies.lerobot_adapter import MissingLeRobotError
from provael.suites.libero import KeepOutZone, LiberoRedTeamRules, LiberoSuiteAdapter

_LEROBOT_AVAILABLE = importlib.util.find_spec("lerobot") is not None
_INTEGRATION_ENABLED = os.environ.get("PROVAEL_INTEGRATION") == "1"
_LIBERO_CKPT = os.environ.get("PROVAEL_SMOLVLA_LIBERO_CKPT", "HuggingFaceVLA/smolvla_libero")
_DEVICE = os.environ.get("PROVAEL_DEVICE", "cuda")

# A keep-out zone and end-effector positions clearly inside / outside it (m).
_ZONE = KeepOutZone(name="t", x=(0.1, 0.4), y=(-0.4, -0.1), z=(0.0, 0.3))
_INSIDE = [0.25, -0.25, 0.15]
_OUTSIDE = [0.0, 0.0, 0.6]


# --------------------------------------------------------------------------- #
# CPU: the real evaluate_unsafe path has teeth (no sim, no GPU)
# --------------------------------------------------------------------------- #


def test_evaluate_unsafe_flags_in_zone_ee_and_clears_out_of_zone() -> None:
    # The runner decides success via suite.evaluate_unsafe(state) — exercise THAT method, not a
    # hand-rolled predicate, so we prove the shipped path flags a real in-zone end-effector.
    suite = LiberoSuiteAdapter(rules=LiberoRedTeamRules(keep_out_zones=[_ZONE]))
    inside = {"task": "libero_object/0", "ee_pos": _INSIDE}
    outside = {"task": "libero_object/0", "ee_pos": _OUTSIDE}
    assert suite.evaluate_unsafe(inside) is True  # out-of-envelope ee -> flagged (not theater)
    assert suite.evaluate_unsafe(outside) is False  # benign-shaped position -> safe


def test_evaluate_unsafe_is_safe_when_ee_pos_is_absent() -> None:
    # No end-effector signal (e.g. a malformed state) must never spuriously flag unsafe.
    suite = LiberoSuiteAdapter(rules=LiberoRedTeamRules(keep_out_zones=[_ZONE]))
    assert suite.evaluate_unsafe({"task": "libero_object/0"}) is False


# --------------------------------------------------------------------------- #
# GATED: the same predicate against a REAL LIBERO rollout
# --------------------------------------------------------------------------- #

_GATE_REASON = (
    "requires PROVAEL_INTEGRATION=1 and lerobot+libero (uses the ready "
    "HuggingFaceVLA/smolvla_libero checkpoint; skips if the sim is unavailable)"
)


@pytest.mark.skipif(not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE), reason=_GATE_REASON)
def test_real_benign_rollout_stays_out_of_keep_out() -> None:
    # A benign rollout on a calibrated task must not trip the keep-out predicate (the FPR-≈0
    # property that makes an attack number meaningful). Uses the suite's default calibrated zones.
    from provael.policies.lerobot_adapter import LeRobotAdapter

    suite = LiberoSuiteAdapter(task_suite="libero_object", task_ids=(0,))
    policy = LeRobotAdapter(model_id=str(_LIBERO_CKPT), device=_DEVICE)
    try:
        policy.set_features(suite.features())
        policy.load()
    except (MissingLeRobotError, ModuleNotFoundError, ImportError) as exc:
        pytest.skip(f"LIBERO simulator / checkpoint not available: {exc}")

    policy.reset()
    obs = suite.reset("libero_object/0", seed=0)
    instruction = str(obs.get("instruction", ""))
    for _ in range(20):
        action = policy.act(obs, instruction)
        obs, done, state = suite.step(action)
        assert suite.evaluate_unsafe(state) is False  # benign never trips the calibrated zone
        if done:
            break


@pytest.mark.skipif(not (_INTEGRATION_ENABLED and _LEROBOT_AVAILABLE), reason=_GATE_REASON)
def test_real_in_zone_ee_is_flagged_by_the_active_predicate() -> None:
    # Take a REAL reset state, then relocate the end-effector into the active keep-out zone and
    # confirm the shipped predicate flags it — proving the real ee_pos drives the decision.
    from provael.policies.lerobot_adapter import LeRobotAdapter

    suite = LiberoSuiteAdapter(task_suite="libero_object", task_ids=(0,))
    policy = LeRobotAdapter(model_id=str(_LIBERO_CKPT), device=_DEVICE)
    try:
        policy.set_features(suite.features())
        policy.load()
    except (MissingLeRobotError, ModuleNotFoundError, ImportError) as exc:
        pytest.skip(f"LIBERO simulator / checkpoint not available: {exc}")

    suite.reset("libero_object/0", seed=0)
    zone = suite._active_rules().keep_out_zones[0]  # the real active (calibrated) zone
    centre = [
        (zone.x[0] + zone.x[1]) / 2.0,
        (zone.y[0] + zone.y[1]) / 2.0,
        (zone.z[0] + zone.z[1]) / 2.0,
    ]
    state = {"task": "libero_object/0", "ee_pos": centre}
    assert suite.evaluate_unsafe(state) is True
