"""Registry and config-validation coverage for the public factory API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from provael.config import RunConfig
from provael.policies.registry import (
    available_policies,
    make_policy,
    policy_extra,
    policy_is_ready,
)
from provael.suites import available_suites, make_suite, suite_is_ready


def test_suite_factory() -> None:
    assert available_suites() == ["libero", "metaworld", "reach", "stub"]
    suite = make_suite("stub")
    assert suite.name == "stub"
    assert suite.tasks() == ["reach"]


def test_cpu_suites_ready_real_suites_gated() -> None:
    # stub (scalar) and reach (spatial) are pure CPU; libero + metaworld wrap real sims and are
    # only "ready" when the [lerobot] extra is installed (absent on the CPU build).
    assert suite_is_ready("stub") is True
    assert suite_is_ready("reach") is True
    assert suite_is_ready("libero") is False
    assert suite_is_ready("metaworld") is False
    # Constructing the gated suites is cheap and never imports the simulator.
    assert make_suite("libero").name == "libero"
    assert make_suite("metaworld").name == "metaworld"
    assert make_suite("reach").calibration_kind == "spatial"


def test_suite_factory_rejects_unknown() -> None:
    with pytest.raises(KeyError):
        make_suite("nope")


def test_policy_factory_and_readiness() -> None:
    assert set(available_policies()) == {
        "stub", "smolvla", "pi0", "pi05", "pi0fast", "groot", "openvla"
    }
    assert policy_is_ready("stub") is True
    # The LeRobot-native policies need the [lerobot] extra, absent on the CPU build.
    for name in ("smolvla", "pi0", "pi05", "pi0fast", "groot"):
        assert policy_is_ready(name) is False
        assert policy_extra(name) == "lerobot"
    # OpenVLA needs the [openvla] extra (transformers), also absent on the CPU build.
    assert policy_is_ready("openvla") is False
    assert policy_extra("openvla") == "openvla"
    assert policy_extra("stub") is None
    assert make_policy("stub").name == "stub"


def test_real_policy_construction_is_cheap_and_imports_nothing() -> None:
    # Constructing any real policy must not import its heavy extra (only load() does).
    assert make_policy("pi0", model="lerobot/pi0_libero_finetuned").name == "pi0"
    assert make_policy("groot").name == "groot"
    assert make_policy("openvla", unnorm_key="libero_object").name == "openvla"


def test_policy_factory_rejects_unknown() -> None:
    with pytest.raises(KeyError):
        make_policy("nope")


def test_config_rejects_empty_attacks() -> None:
    with pytest.raises(ValidationError):
        RunConfig(attacks=[])


def test_config_defaults() -> None:
    config = RunConfig()
    assert config.policy == "stub"
    assert config.suite == "stub"
    assert config.attacks == ["instruction"]
    assert config.episodes == 10
    assert config.seed == 0
    assert config.horizon == 8
