"""OpenVLA adapter: CPU-testable construction + error paths; gated real-forward integration test.

The real forward pass needs a GPU, the ``[openvla]`` extra, and ``PROVAEL_INTEGRATION=1``; it is
skipped otherwise (mirrors ``tests/test_lerobot_adapter.py``). Everything that does NOT require
``transformers`` (construction, the missing-dependency error, the unnorm-key guard) is exercised
on the CPU build.
"""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

from provael.policies.openvla_adapter import (
    MissingOpenVLAError,
    OpenVLAAdapter,
    UnpinnedRemoteCodeError,
)

_HAS_TRANSFORMERS = importlib.util.find_spec("transformers") is not None
_INTEGRATION = os.environ.get("PROVAEL_INTEGRATION") == "1"


def test_construction_imports_nothing_optional() -> None:
    adapter = OpenVLAAdapter(model_id="openvla/openvla-7b", unnorm_key="libero_object")
    assert adapter.name == "openvla"
    assert adapter.stochastic is True
    assert adapter.action_dim == 7


@pytest.mark.skipif(_HAS_TRANSFORMERS, reason="transformers installed; missing-dep path not testable")
def test_load_without_extra_raises_actionable_error() -> None:
    with pytest.raises(MissingOpenVLAError, match=r"provael\[openvla\]"):
        OpenVLAAdapter().load()


def test_act_before_load_raises() -> None:
    adapter = OpenVLAAdapter(unnorm_key="libero_object")
    with pytest.raises(RuntimeError, match="before load"):
        adapter.act({"image": np.zeros((8, 8, 3), dtype=np.uint8)}, "pick up the cup")


# --------------------------------------------------------------------------------------------
# trust_remote_code revision pinning (Phase 6) — CPU-testable, no transformers needed
# --------------------------------------------------------------------------------------------

def test_release_mode_refuses_unpinned_remote_code(monkeypatch: pytest.MonkeyPatch) -> None:
    # trust_remote_code=True executes repo code; an unpinned load in release mode is refused.
    monkeypatch.setenv("PROVAEL_REQUIRE_REAL_INTEGRATION", "1")
    with pytest.raises(UnpinnedRemoteCodeError, match="commit SHA"):
        OpenVLAAdapter()._resolve_revision()


def test_pinned_revision_is_honoured_in_release_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVAEL_REQUIRE_REAL_INTEGRATION", "1")
    adapter = OpenVLAAdapter(revision="0123abcd")
    assert adapter._resolve_revision() == "0123abcd"


def test_discovery_mode_warns_but_allows_unpinned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROVAEL_REQUIRE_REAL_INTEGRATION", raising=False)
    adapter = OpenVLAAdapter()
    with pytest.warns(UserWarning, match="UNPINNED"):
        assert adapter._resolve_revision() is None


@pytest.mark.skipif(
    not (_HAS_TRANSFORMERS and _INTEGRATION),
    reason="requires PROVAEL_INTEGRATION=1 and the [openvla] extra (GPU; downloads the model)",
)
def test_real_openvla_forward() -> None:  # pragma: no cover - integration only
    adapter = OpenVLAAdapter(unnorm_key="bridge_orig")
    adapter.load()
    action = adapter.act({"image": np.zeros((224, 224, 3), dtype=np.uint8)}, "pick up the cup")
    assert action.shape == (7,)
