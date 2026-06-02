"""Shared pytest fixtures: a loaded stub policy and a stub suite."""

from __future__ import annotations

import pytest

from vla_redteam.policies.stub import StubPolicy
from vla_redteam.suites.stub import StubSuite


@pytest.fixture
def stub_policy() -> StubPolicy:
    policy = StubPolicy()
    policy.load()
    return policy


@pytest.fixture
def stub_suite() -> StubSuite:
    return StubSuite()
