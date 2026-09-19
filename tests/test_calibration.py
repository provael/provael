# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Calibration core: Wilson CI, seed split, scalar/spatial fitting, model, artifact IO."""

from __future__ import annotations

from pathlib import Path

import pytest

from provael import __version__
from provael.calibration import (
    Calibration,
    DuplicateCalibrationError,
    ToolVersionMismatchError,
    artifact_name,
    calibrate_one,
    calibrate_suite,
    collect_benign_signals,
    fit_scalar_threshold,
    fit_spatial_zone,
    load_calibrations,
    save_calibration,
    split_seeds,
    to_json,
    wilson_ci,
)
from provael.policies.stub import StubPolicy
from provael.suites.keepout_zones import KeepOutZone
from provael.suites.stub import StubSuite


def test_wilson_ci_brackets_point_estimate() -> None:
    low, high = wilson_ci(8, 10)
    assert low < 0.8 < high
    assert round(low, 2) == 0.49
    assert round(high, 2) == 0.94


def test_wilson_ci_edges() -> None:
    assert wilson_ci(0, 0) == (0.0, 0.0)
    low, high = wilson_ci(0, 10)
    assert low == 0.0 and 0.25 < high < 0.31
    low, high = wilson_ci(10, 10)
    assert high == pytest.approx(1.0) and 0.69 < low < 0.73


def test_split_seeds_is_deterministic_and_requires_two() -> None:
    fit, holdout = split_seeds(list(range(10)))
    assert fit == [0, 1, 2, 3, 4, 5, 6] and holdout == [7, 8, 9]
    assert fit + holdout == list(range(10))  # no overlap, full cover
    with pytest.raises(ValueError):
        split_seeds([0])


def test_fit_scalar_threshold_hits_target_on_spread() -> None:
    scores = [i / 10 for i in range(10)]  # 0.0 .. 0.9
    threshold, fpr = fit_scalar_threshold(scores, scores, target_fpr=0.2)
    # Tightest t with <=20% of holdout strictly above it: 0.7 leaves {0.8, 0.9} = 20%.
    assert threshold == pytest.approx(0.7)
    assert fpr <= 0.2


def test_fit_scalar_threshold_degenerate_benign_is_clean() -> None:
    # The stub's benign danger is constant 0 -> threshold 0, FPR 0, and any positive
    # attack danger is flagged (strict >).
    threshold, fpr = fit_scalar_threshold([0.0] * 7, [0.0] * 3, target_fpr=0.05)
    assert threshold == 0.0 and fpr == 0.0
    assert Calibration(
        policy="stub", suite="stub", task="reach", kind="scalar",
        threshold=threshold, target_fpr=0.05, benign_fpr=fpr, n_benign=10,
    ).is_unsafe({"danger": 0.6})
    assert not Calibration(
        policy="stub", suite="stub", task="reach", kind="scalar",
        threshold=threshold, target_fpr=0.05, benign_fpr=fpr, n_benign=10,
    ).is_unsafe({"danger": 0.0})


def test_fit_spatial_zone_keeps_benign_out() -> None:
    # Benign EE clustered in a small box; the hazard zone is placed disjoint from it.
    benign = [[[0.0, 0.0, 0.0], [0.01, 0.0, 0.0]] for _ in range(6)]
    envelope, zones, fpr, detail = fit_spatial_zone(benign[:4], benign[4:], target_fpr=0.05)
    assert len(envelope) == 3 and len(zones) == 1
    assert detail.face_selected_from_data is False, (
        "a benign-only fit cannot choose a face and must not claim it did"
    )
    assert detail.detection_rate is None, "no adversarial arm ran; None is not 0.0"
    assert fpr <= 0.05
    # A benign point is NOT in the hazard zone; a point inside the zone IS.
    zone = zones[0]
    assert not zone.contains([0.0, 0.0, 0.0])
    inside = [(zone.x[0] + zone.x[1]) / 2, (zone.y[0] + zone.y[1]) / 2, (zone.z[0] + zone.z[1]) / 2]
    assert zone.contains(inside)


def test_calibration_spatial_is_unsafe() -> None:
    zone = KeepOutZone(name="hz", x=(1.0, 2.0), y=(1.0, 2.0), z=(1.0, 2.0))
    cal = Calibration(
        policy="smolvla", suite="libero", task="libero_object/0", kind="spatial",
        keep_out_zones=[zone], target_fpr=0.05, benign_fpr=0.0, n_benign=10,
    )
    assert cal.is_unsafe({"ee_pos": [1.5, 1.5, 1.5]})
    assert not cal.is_unsafe({"ee_pos": [0.0, 0.0, 0.0]})
    assert not cal.is_unsafe({"ee_pos": None})


def test_artifact_round_trip_and_determinism(tmp_path: Path) -> None:
    cal = Calibration(
        policy="stub", suite="stub", task="reach", kind="scalar",
        threshold=0.0, target_fpr=0.05, benign_fpr=0.0, n_benign=10,
        fit_seeds=[0, 1, 2], holdout_seeds=[3, 4],
    )
    path = save_calibration(cal, tmp_path)
    assert path.name == artifact_name("stub", "stub", "reach") == "stub__stub__reach.json"
    # Byte-deterministic.
    assert to_json(cal) == to_json(cal)
    # Round-trips and is discoverable by (policy, suite).
    loaded = load_calibrations(tmp_path, "stub", "stub")
    assert set(loaded) == {"reach"}
    assert loaded["reach"].threshold == 0.0
    assert load_calibrations(tmp_path, "other", "stub") == {}


def test_artifact_name_sanitizes_task() -> None:
    assert artifact_name("smolvla", "libero", "libero_object/0") == "smolvla__libero__libero_object_0.json"


# ---------------------------------------------------------------------------------------------
# Seeding the calibration rollouts, and saying so honestly.
#
# WHY THESE EXIST. `PolicyAdapter.seed` was called from exactly one place in the codebase —
# `runner.run_episode`, the attack path. `collect_benign_signals` seeded the ENVIRONMENT and not
# the policy, so a flow-matching sampler like SmolVLA's drew its noise from ambient torch state.
# The ten `libero_object` zones committed on 6 September 2026 were fitted that way: the envelopes
# that every later measurement is scored against came from rollouts nobody can reproduce.
#
# The fix is two claims, and each is a way this can go wrong on its own, so each gets a test:
# the policy is seeded at all, and the artifact records what the adapter APPLIED rather than what
# the caller asked for. The second is the one that rots quietly — recording the requested seed
# would make every calibration claim a determinism no adapter delivered.
# ---------------------------------------------------------------------------------------------


class _RecordingPolicy(StubPolicy):
    """A stub that records the seeds it is handed and reports applying every one of them."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[int] = []

    def seed(self, seed: int) -> int | None:
        self.seen.append(seed)
        return seed


class _UnseedablePolicy(StubPolicy):
    """A stub that is handed seeds and applies none — the base-class default, made explicit."""

    def __init__(self) -> None:
        super().__init__()
        self.seen: list[int] = []

    def seed(self, seed: int) -> int | None:
        self.seen.append(seed)
        return None


def test_benign_rollouts_seed_the_policy_not_only_the_environment() -> None:
    policy = _RecordingPolicy()
    policy.load()
    suite = StubSuite()
    episodes, applied = collect_benign_signals(policy, suite, "reach", [4, 5, 6], horizon=4)
    assert policy.seen == [4, 5, 6], (
        "collect_benign_signals ran three rollouts without calling policy.seed for each — the "
        "sampler draws that shape the fitted boundary are then unreproducible"
    )
    assert applied == [4, 5, 6]
    assert len(episodes) == 3


def test_an_adapter_that_cannot_seed_records_null_not_the_requested_seed() -> None:
    """The honesty half. Recording the ASKED seed would claim a determinism nothing delivered."""
    policy = _UnseedablePolicy()
    policy.load()
    _, applied = collect_benign_signals(policy, StubSuite(), "reach", [7, 8], horizon=4)
    assert policy.seen == [7, 8], "the adapter was never offered the seeds"
    assert applied == [None, None], (
        "an adapter that returns None from seed() must leave null in the artifact; recording "
        "[7, 8] here would be the tool asserting a reproducibility the policy does not have"
    )


def test_the_calibration_artifact_carries_the_applied_seeds() -> None:
    """Fit seeds then holdout seeds, in that order, so a row lines up with the split above it."""
    policy = _RecordingPolicy()
    policy.load()
    cal = calibrate_one(
        policy, StubSuite(),
        policy_name="stub", suite_name="stub", task="reach",
        fit_seeds=[0, 1, 2], holdout_seeds=[3, 4],
        target_fpr=0.05, horizon=4, tool_version=__version__,
    )
    assert cal.policy_seeds == [0, 1, 2, 3, 4]
    assert cal.fit_seeds + cal.holdout_seeds == cal.policy_seeds, (
        "the applied seeds are recorded in a different order from the split that names them"
    )
    # And it survives the round trip that actually reaches a committed file.
    assert Calibration.model_validate_json(to_json(cal)).policy_seeds == [0, 1, 2, 3, 4]


def test_calibrate_suite_refuses_to_stamp_a_version_that_did_not_produce_it() -> None:
    """A fitted boundary scores every later run, so a wrong label misattributes all of them."""
    with pytest.raises(ToolVersionMismatchError, match="did not produce it"):
        calibrate_suite(
            "stub", "stub", ["reach"], list(range(4)),
            target_fpr=0.05, horizon=4, tool_version="0.32.0",
        )


def test_calibrate_suite_accepts_the_running_version() -> None:
    """The converse, so the guard above cannot pass by refusing everything."""
    cals = calibrate_suite(
        "stub", "stub", ["reach"], list(range(4)),
        target_fpr=0.05, horizon=4, tool_version=__version__,
    )
    assert cals and all(c.tool_version == __version__ for c in cals.values())


# ---------------------------------------------------------------------------------------------
# Loading what the calibrate arm actually wrote.
#
# The loader globbed one level; the `calibrate` GPU arm shards one task per container and writes
# each into its own subdirectory. So `--calib <the directory the arm produced>` matched zero files,
# returned {}, and the run measured the DEFAULT keep-out box while being configured not to.
# ---------------------------------------------------------------------------------------------


def _spatial(task: str) -> Calibration:
    return Calibration(
        policy="smolvla", suite="libero", task=task, kind="spatial",
        keep_out_zones=[KeepOutZone(name="z", x=(0.0, 1.0), y=(0.0, 1.0), z=(0.0, 1.0))],
        target_fpr=0.05, benign_fpr=0.0, n_benign=20,
    )


def test_calibrations_are_found_in_the_sharded_layout_the_arm_writes(tmp_path: Path) -> None:
    for i in range(3):
        save_calibration(_spatial(f"libero_object/{i}"), tmp_path / f"libero_object_{i}")
    found = load_calibrations(tmp_path, "smolvla", "libero")
    assert sorted(found) == ["libero_object/0", "libero_object/1", "libero_object/2"], (
        "the loader did not descend into the per-task subdirectories the calibrate arm writes, so "
        "--calib pointed at that directory would silently fall back to the default predicate"
    )


def test_two_calibrations_for_one_task_are_refused_not_silently_picked(tmp_path: Path) -> None:
    """Two fits are two boundaries; scoring against whichever sorted last is unreportable."""
    save_calibration(_spatial("libero_object/0"), tmp_path / "first")
    save_calibration(_spatial("libero_object/0"), tmp_path / "second")
    with pytest.raises(DuplicateCalibrationError, match="libero_object/0"):
        load_calibrations(tmp_path, "smolvla", "libero")


def test_the_committed_calibrations_load_from_their_own_directory() -> None:
    """The real artifacts, at the real path, since that is the invocation that was broken."""
    committed = Path(__file__).resolve().parents[1] / "results/calibration/libero_object_calibrate"
    if not committed.is_dir():  # pragma: no cover - present in the repo, absent in a wheel
        pytest.skip("results/ is not packaged")
    found = load_calibrations(committed, "smolvla", "libero")
    assert len(found) == 10, f"expected all ten libero_object calibrations, found {sorted(found)}"


# ---------------------------------------------------------------------------------------------
# Choosing the hazard FACE, which is the defect the ten committed libero_object zones carry.
#
# fit_spatial_zone searched the gap and always used hazard_zone_beside's default face (y/low).
# Every gap that clears the benign envelope gives a benign FPR near zero, so the search always
# reported a well-behaved number — all ten zones came back at exactly 0.0 — while five of the six
# faces catch nothing at all. Replaying the one committed run that records trajectories
# (studies/keepout_face_selection/replay.py) found the redirected policy left through +x while the
# hazard sat beside -y, past a boundary the arm never reached in any episode.
#
# So: a benign-only fit must not claim it chose, and an adversarial arm must actually move the
# choice. Both directions get a test, because either alone can pass on a broken implementation.
# ---------------------------------------------------------------------------------------------


def _box(cx: float, cy: float, cz: float, n: int) -> list[list[list[float]]]:
    """`n` one-step trajectories clustered at a point."""
    return [[[cx, cy, cz]] for _ in range(n)]


def test_an_adversarial_arm_moves_the_face_off_the_historical_default() -> None:
    """Attacks that leave through +x must put the hazard on +x, not on the hardcoded y-."""
    benign = _box(0.0, 0.0, 0.0, 8)
    # Well past the +x face of the benign envelope, and nowhere near -y.
    attacked = _box(0.25, 0.0, 0.0, 6)
    _, zones, fpr, detail = fit_spatial_zone(
        benign[:5], benign[5:], target_fpr=0.05, adversarial_trajectories=attacked
    )
    assert detail.face == "x+", f"chose {detail.face}, but the attacks all leave through +x"
    assert detail.face_selected_from_data is True
    assert fpr <= 0.05
    assert detail.detection_rate == 1.0, "the chosen face must actually flag the attacked arm"
    assert zones[0].contains([0.25, 0.0, 0.0])


def test_a_zone_that_cannot_fire_reports_zero_rather_than_looking_clean() -> None:
    """The committed-zones failure, in miniature: attacks that leave through no face at all.

    Detection 0.0 with a 0.0 benign FPR is the exact signature of the ten `libero_object` zones.
    The artifact has to be able to say that, or the two indistinguishable outcomes — well placed,
    and placed where nothing goes — stay indistinguishable.
    """
    benign = _box(0.0, 0.0, 0.0, 8)
    attacked = _box(0.001, 0.001, 0.001, 6)  # inside the benign envelope: no face separates them
    _, _, fpr, detail = fit_spatial_zone(
        benign[:5], benign[5:], target_fpr=0.05, adversarial_trajectories=attacked
    )
    assert fpr == 0.0
    assert detail.detection_rate == 0.0, (
        "an adversarial arm ran and nothing was caught, so the rate is a measured 0.0"
    )
    assert detail.face_selected_from_data is True, "a face WAS selected; it just catches nothing"


def test_face_selection_is_deterministic_when_faces_tie() -> None:
    """Ties fall to the tightest gap and then a fixed face order, never to dict iteration."""
    benign = _box(0.0, 0.0, 0.0, 8)
    attacked = _box(0.5, 0.5, 0.5, 6)  # far out on every axis: several faces flag it
    first = fit_spatial_zone(
        benign[:5], benign[5:], target_fpr=0.05, adversarial_trajectories=attacked
    )[3]
    for _ in range(5):
        again = fit_spatial_zone(
            benign[:5], benign[5:], target_fpr=0.05, adversarial_trajectories=attacked
        )[3]
        assert (again.face, again.gap) == (first.face, first.gap)


def test_calibrate_one_runs_the_attacked_arm_at_the_holdout_seeds() -> None:
    """Paired arms: the adversarial rollouts reuse the holdout seeds, not fresh ones.

    An unpaired arm would confound "the attack redirects the policy" with "these seeds start
    somewhere else", which is the comparison the whole fit rests on.
    """
    from provael.attacks.registry import make_attack

    policy = _RecordingPolicy()
    policy.load()
    cal = calibrate_one(
        policy, StubSuite(),
        policy_name="stub", suite_name="stub", task="reach",
        fit_seeds=[0, 1, 2], holdout_seeds=[3, 4],
        target_fpr=0.05, horizon=4, tool_version=__version__,
        attack=make_attack("roleplay"),
    )
    assert policy.seen == [0, 1, 2, 3, 4, 3, 4], (
        "expected fit seeds, holdout seeds, then the SAME holdout seeds attacked; got "
        f"{policy.seen}"
    )
    assert cal.policy_seeds == [0, 1, 2, 3, 4, 3, 4]


def test_nothing_clearing_the_benign_target_is_reported_as_unselected() -> None:
    """The fallback branch decides what a caller may adopt, so it gets its own test.

    When no (face, gap) meets the benign target, the fit falls back to the historical face at the
    widest gap. What matters is that it does NOT then claim to have selected: an adopted zone from
    this branch would be a boundary nothing chose, dressed as one that was chosen.
    """
    benign = _box(0.0, 0.0, 0.0, 4)
    _, zones, _, detail = fit_spatial_zone(
        benign[:2], benign[2:], target_fpr=-1.0,  # unreachable: no rate is <= a negative target
        adversarial_trajectories=_box(0.9, 0.0, 0.0, 3),
    )
    assert detail.face_selected_from_data is False
    assert detail.face == "y-", "the fallback is the historical face, stated rather than arbitrary"
    assert detail.gap == max(detail.gap, 0.5), "the widest gap, so the fallback is the safest one"
    assert detail.detection_rate == 0.0, (
        "an adversarial arm ran, so the rate is measured even on the fallback path — None here "
        "would hide that this zone was checked and caught nothing"
    )
    assert len(zones) == 1


# ── The tuning split is not described as an untouched evaluation ─────────────────────────────

_ROOT = Path(__file__).resolve().parents[1]
#: Prose surfaces a reader learns the calibration's meaning from. Dated records (errata, studies,
#: findings, the changelog) describe what past artifacts CLAIMED at the time and are left alone.
_CURRENT_PROSE = [
    _ROOT / "README.md",
    _ROOT / "docs/glossary.md",
    _ROOT / "docs/quickstart.md",
    _ROOT / "docs/compliance/index.md",
    _ROOT / "docs/compliance/machinery-annex-iii-corruption.md",
    _ROOT / "docs/handbook.md",
    _ROOT / "src/provael/calibration.py",
    _ROOT / "src/provael/cli/calibrate.py",
    _ROOT / "src/provael/report.py",
    _ROOT / "src/provael/compliance.py",
    _ROOT / "src/provael/types.py",
]
#: Wording that presents the two-way split as data the selection never touched.
_HELD_OUT = ("held-out", "held out", "hold-out", "holdout split", "holdout fpr", "holdout benign")
#: "untouched" is allowed only when negated, or when it names the three-way binding that IS.
_NEGATIONS = ("no ", "not ", "never ", "nor ", "without an ")
_UNTOUCHED_OK = ("calibrationbinding", "split_seeds_three", "achieved_eval_fpr", "eval split",
                 "eval set", "three-way", "three seed splits")


def test_the_two_way_split_is_never_described_as_held_out() -> None:
    """R04 (19 Sep 2026): `fit_scalar_threshold` and `fit_spatial_zone` SELECT on the second split.

    That makes it tuning data, and README, glossary, CLI help and field descriptions all called it
    held-out. The words are banned from the surfaces a reader learns the meaning from; the JSON
    keys (`holdout_seeds`, `holdout_fpr`) stay for artifact compatibility and are exempt as
    identifiers.
    """
    offenders: list[str] = []
    for path in _CURRENT_PROSE:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(phrase in line.lower() for phrase in _HELD_OUT):
                offenders.append(f"{path.relative_to(_ROOT)}:{lineno}: {line.strip()}")
        # "untouched" is judged in context, since the negation usually sits on the line before.
        low = " ".join(text.lower().split())
        start = 0
        while (i := low.find("untouched", start)) != -1:
            start = i + 1
            window, before = low[max(0, i - 160): i + 160], low[max(0, i - 70): i]
            about_calibration = any(w in window for w in ("split", "evaluat", "calibrat"))
            negated = any(neg in before for neg in _NEGATIONS)
            names_the_binding = any(ok in window for ok in _UNTOUCHED_OK)
            if about_calibration and not negated and not names_the_binding:
                offenders.append(f"{path.relative_to(_ROOT)}: ...{low[i - 60: i + 60]}...")
    assert not offenders, "the two-way calibration split is tuning data:\n" + "\n".join(offenders)


def test_the_calibration_artifact_says_its_fpr_is_a_tuning_figure() -> None:
    field = Calibration.model_fields["benign_fpr"]
    assert "TUNING split" in (field.description or "")
    assert "not an estimate on untouched data" in (field.description or "")
