"""`watch/publish-freshness.json` must agree with the constant and the rule the CLI enforces.

WHAT THIS GUARDS. The artifact publishes the second staleness window — how far the PUBLISHED
measurement has drifted from the current release — so a consumer reads the answer instead of
reimplementing it against `watch/measurements.json`. A reimplementation of a staleness rule drifts
in the reassuring direction by default: the failure mode is a window that quietly widens, and a
widened window looks exactly like a project that is keeping up.

So the binding asserted here is between the FILE and the CODE, not between the file and a literal:

1. The committed bytes equal a fresh render, so the artifact cannot lag the ledger or the version.
2. `staleAfterReleases` equals `provael.watch.STALE_AFTER_RELEASES` — the same gate this repo
   already ships for `watch/release.json` in `test_release_artifact.py`.
3. `releasesBehind` and `isStale` equal what `releases_behind()` and the comparison actually
   produce, so a hand-edit that softened either would fail rather than publish.
4. No wall-clock field. Checked against the parsed KEYS rather than the raw text, because the note
   in this artifact explains at length why there is no `generatedAt` — a substring check trips on
   the file's own prose about the thing it does not contain, which is the same way `check:versions`
   once fired on a CHANGELOG sentence quoting a version it was describing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from provael import __version__
from provael.watch import STALE_AFTER_RELEASES, published_measurement, releases_behind

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "watch" / "publish-freshness.json"
GENERATOR = REPO / "scripts" / "gen_publish_freshness_artifact.py"

#: Keys that would make the output differ on every run and break `--check` on a clean tree.
WALL_CLOCK_KEYS = {"generatedAt", "generated_at", "renderedAt", "now"}


def _generator():
    """Load the generator by path — `scripts/` is not an importable package."""
    spec = importlib.util.spec_from_file_location("gen_publish_freshness", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def artifact() -> dict:
    assert ARTIFACT.is_file(), f"{ARTIFACT} is missing. Run `make gen-publish-freshness`."
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_committed_artifact_is_current() -> None:
    """The same rule `--check` enforces, so a stale artifact fails the suite and not only CI."""
    assert _generator().main(["--check"]) == 0, (
        "watch/publish-freshness.json is stale. Run `make gen-publish-freshness` and commit it."
    )


def test_the_published_window_equals_the_constant(artifact: dict) -> None:
    """The gate this repo already ships for watch/release.json, applied to the second artifact."""
    assert artifact["staleAfterReleases"] == STALE_AFTER_RELEASES, (
        f"the artifact publishes a {artifact['staleAfterReleases']}-release window while "
        f"provael.watch enforces {STALE_AFTER_RELEASES} — a consumer would render one number and "
        "`provael doctor` another"
    )


def test_the_gap_and_the_verdict_are_what_the_code_computes(artifact: dict) -> None:
    """A hand-edit that softened either number must fail rather than publish."""
    record = published_measurement()
    assert record is not None, "no real measurement is committed; the artifact should say so"
    assert artifact["measuredWith"] == record.tool_version
    assert artifact["measuredAt"] == record.measured_at
    expected = releases_behind(record.tool_version, __version__)
    assert artifact["releasesBehind"] == expected
    assert artifact["isStale"] == (None if expected is None else expected > STALE_AFTER_RELEASES)


def test_it_names_the_version_it_was_measured_against(artifact: dict) -> None:
    """`releasesBehind` is meaningless without the version it counts back from."""
    assert artifact["currentVersion"] == __version__


def test_no_wall_clock_field(artifact: dict) -> None:
    """A wall-clock value would make `--check` fail on a clean tree, so the gate could never pass.

    Asserted against the parsed keys. The artifact's own note explains why there is no
    `generatedAt`, so a substring check over the raw text fails on the prose describing the absence
    — the same shape as a version guard firing on a sentence that quotes the version it corrects.
    """
    assert not WALL_CLOCK_KEYS & set(artifact), (
        f"{sorted(WALL_CLOCK_KEYS & set(artifact))} makes the output differ on every run"
    )


def test_render_is_byte_stable() -> None:
    """Determinism, from the generator rather than from the committed file."""
    gen = _generator()
    assert gen.render() == gen.render()


def test_a_missing_measurement_reports_null_rather_than_a_zero_gap(monkeypatch) -> None:
    """Nothing measured is not the same as measured-and-current, and zero is the reassuring answer.

    The branch matters: a consumer reading `releasesBehind: 0` renders "current". It must only ever
    see that when something real was actually measured at the current version.
    """
    gen = _generator()
    monkeypatch.setattr(gen, "published_measurement", lambda: None)
    built = gen.build()
    assert built["measuredWith"] is None
    assert built["releasesBehind"] is None
    assert built["isStale"] is None, "an unmeasured project must not publish isStale: false"
    assert built["staleAfterReleases"] == STALE_AFTER_RELEASES, (
        "the window is a property of the project, not of whether a measurement exists"
    )
