"""Registry and config-validation coverage for the public factory API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from provael.config import RunConfig
from provael.policies.registry import (
    available_policies,
    make_policy,
    policy_is_ready,
)
from provael.suites import available_suites, make_suite, suite_is_ready


def test_suite_factory() -> None:
    assert available_suites() == ["libero", "stub"]
    suite = make_suite("stub")
    assert suite.name == "stub"
    assert suite.tasks() == ["reach"]


def test_libero_suite_registered_but_gated() -> None:
    # Constructing the libero suite is cheap and never imports lerobot; it is only
    # "ready" when the extra is installed (absent on the CPU build).
    assert "libero" in available_suites()
    assert suite_is_ready("stub") is True
    assert suite_is_ready("libero") is False
    assert make_suite("libero").name == "libero"


def test_suite_factory_rejects_unknown() -> None:
    with pytest.raises(KeyError):
        make_suite("nope")


def test_policy_factory_and_readiness() -> None:
    assert set(available_policies()) == {"stub", "smolvla"}
    assert policy_is_ready("stub") is True
    # smolvla needs the optional extra, absent on the CPU build.
    assert policy_is_ready("smolvla") is False
    assert make_policy("stub").name == "stub"


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
