# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""The four provenance fields every scheduled-lane manifest admitted it lacked, now filled.

`repository`, `commit`, `dep_lock_digest` and `precision` sat in `missing_fields` on every run the
scheduled GPU lane ever committed. Two of them (`repository`, `dep_lock_digest`) were supplied by no
caller in any version; `precision` was declared on the adapter base class and set by one adapter
nobody has run; `commit` had a fix in `main` that the lane's pinned wheel could not see. These tests
hold each source the CLI now reads, and the end-to-end fact that a stub run from this checkout
carries none of the four gaps — which is what `scripts/check_provenance.py` refuses on.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from provael.campaign import REQUIRED_PROVENANCE, provenance_gaps
from provael.cli import app
from provael.cli._shared import (
    DEP_LOCK_ENV,
    REPOSITORY_ENV,
    _dep_lock_digest,
    _repository,
    _repository_slug,
)
from provael.policies.lerobot_adapter import _precision_of
from provael.policies.stub import StubPolicy

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()


@pytest.mark.parametrize(
    ("remote", "slug"),
    [
        ("git@github.com:provael/provael.git", "provael/provael"),
        ("https://github.com/provael/provael.git", "provael/provael"),
        ("https://github.com/provael/provael", "provael/provael"),
        ("ssh://git@github.com/provael/provael.git", "provael/provael"),
        ("https://github.com/provael/provael/", "provael/provael"),
        ("provael", None),
        ("", None),
    ],
)
def test_repository_slug_from_the_remotes_git_writes(remote: str, slug: str | None) -> None:
    assert _repository_slug(remote) == slug


def test_repository_prefers_the_explicit_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REPOSITORY_ENV, "provael/provael")
    assert _repository() == "provael/provael"
    monkeypatch.setenv(REPOSITORY_ENV, "not a slug")
    assert _repository() != "not a slug", "a malformed override must not masquerade as provenance"


def test_repository_from_this_checkouts_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(REPOSITORY_ENV, raising=False)
    monkeypatch.chdir(REPO)
    assert _repository() == "provael/provael"


def test_dep_lock_digest_is_the_checkouts_lock_file_when_there_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DEP_LOCK_ENV, raising=False)
    monkeypatch.chdir(REPO)
    expected = hashlib.sha256((REPO / "uv.lock").read_bytes()).hexdigest()
    assert _dep_lock_digest() == f"uv.lock:sha256:{expected}"


def test_dep_lock_digest_falls_back_to_the_installed_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A container that pip-installed a release has no lock file; its installed set is the fact."""
    monkeypatch.delenv(DEP_LOCK_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    digest = _dep_lock_digest()
    assert digest is not None and digest.startswith("installed:sha256:")
    assert len(digest.split(":")[-1]) == 64
    assert digest == _dep_lock_digest(), "the installed set does not change between two calls"


def test_dep_lock_digest_honours_a_well_formed_override(monkeypatch: pytest.MonkeyPatch) -> None:
    value = "uv.lock:sha256:" + "a" * 64
    monkeypatch.setenv(DEP_LOCK_ENV, value)
    assert _dep_lock_digest() == value
    monkeypatch.setenv(DEP_LOCK_ENV, "deadbeef")
    assert _dep_lock_digest() != "deadbeef", "a bare hash says nothing about what it digests"


def test_the_stub_records_the_precision_it_computes_in() -> None:
    policy = StubPolicy()
    policy.load()
    assert policy.resolved_precision == "fp32"


class _Param:
    def __init__(self, dtype: str) -> None:
        self.dtype = dtype


class _Policy:
    def __init__(self, dtype: str | None) -> None:
        self._dtype = dtype

    def parameters(self):
        if self._dtype is None:
            return iter(())
        yield _Param(self._dtype)


@pytest.mark.parametrize(
    ("dtype", "name"),
    [
        ("torch.float32", "fp32"),
        ("torch.bfloat16", "bf16"),
        ("torch.float16", "fp16"),
        ("torch.int8", None),
        (None, None),
    ],
)
def test_lerobot_precision_is_read_off_the_parameters(dtype: str | None, name: str | None) -> None:
    assert _precision_of(_Policy(dtype)) == name


def test_a_stub_run_from_this_checkout_carries_none_of_the_four_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: what the scheduled lane's gate will see once its pin carries these fields."""
    monkeypatch.delenv(REPOSITORY_ENV, raising=False)
    monkeypatch.delenv(DEP_LOCK_ENV, raising=False)
    monkeypatch.chdir(REPO)
    out = tmp_path / "run"
    result = runner.invoke(
        app,
        ["attack", "--policy", "stub", "--suite", "stub", "--attacks", "none,instruction",
         "--seeds", "1", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads((out / "execution-manifest.json").read_text(encoding="utf-8"))
    assert provenance_gaps(manifest) == []
    assert not set(REQUIRED_PROVENANCE) & set(manifest["missing_fields"])
    assert manifest["repository"] == "provael/provael"
    assert manifest["dep_lock_digest"].startswith("uv.lock:sha256:")
    assert manifest["precision"] == "fp32"
