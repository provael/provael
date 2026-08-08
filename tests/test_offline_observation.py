"""The open-loop study must be impossible to mistake for a real-robot result.

Two things are being defended here, and only one of them is ordinary correctness.

THE LOADER MUST REFUSE THE DATASETS THAT WOULD HAVE BEEN WRONG. The metadata below is real,
recorded from Hugging Face on 8 August 2026 while choosing a dataset for this study. Of five public
datasets whose names contain "so101", three would have produced a wrong or meaningless result — most
dangerously `kwangchaeko/so101_test`, which is a 4-DoF `koch` arm and would have loaded, produced
numbers, and told nobody. These fixtures are those exact datasets, so the check runs against the
failures that actually exist rather than invented ones.

THE ARTIFACT MUST NOT CARRY AN `asr` FIELD. That is the single most likely route to the entire study
being misread as a closed-loop attack success rate, which it is not and can never be. The assertion
is on the serialised keys rather than the class, because it is the JSON a reader or a downstream
build will see.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from provael.datasets.lerobot_frames import (
    DatasetRejected,
    load_info,
    parse_info,
    validate,
)
from provael.evidence import EvidenceState
from provael.studies.offline_observation import (
    CLAIM_LIMITS,
    EARNED_EVIDENCE_STATE,
    FrameComparison,
    OfflineObservationReport,
    l2,
    outside_envelope,
    summarise,
)


def _info(**overrides: object) -> dict[str, object]:
    """A valid v3.0 SO-101 info.json, shaped like Guanli001/so101-vials-auto-dr-final100."""
    base: dict[str, object] = {
        "codebase_version": "v3.0",
        "robot_type": "so101_follower",
        "fps": 30,
        "total_frames": 59017,
        "features": {
            "observation.state": {"shape": [6]},
            "action": {"shape": [6]},
            "observation.images.front": {"shape": [3, 480, 640]},
        },
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "info.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


# --- The loader, against the datasets that really exist -------------------------------------------


def test_a_valid_v3_so101_dataset_is_accepted(tmp_path: Path) -> None:
    info = load_info("Guanli001/so101-vials-auto-dr-final100", local_meta=_write(tmp_path, _info()))
    assert info.robot_type == "so101_follower"
    assert info.state_dim == info.action_dim == 6
    assert info.camera_keys == ("observation.images.front",)


def test_the_koch_dataset_named_so101_is_rejected(tmp_path: Path) -> None:
    """kwangchaeko/so101_test — the dangerous one, because it fails silently.

    Named so101, `robot_type` koch, 4-DoF. It loads, produces numbers, and the numbers are about a
    different robot. Nothing downstream would notice, which is why this raises rather than warns.
    """
    raw = _info(
        robot_type="koch",
        features={
            "observation.state": {"shape": [4]},
            "action": {"shape": [4]},
            "observation.images.laptop": {"shape": [3, 480, 640]},
        },
    )
    with pytest.raises(DatasetRejected, match="not an SO-101"):
        load_info("kwangchaeko/so101_test", local_meta=_write(tmp_path, raw))


def test_a_v21_dataset_is_rejected(tmp_path: Path) -> None:
    """kaiserbuffle/so101_test and BasedLukas/so101_test_2 — genuinely SO-101, older layout."""
    with pytest.raises(DatasetRejected, match="codebase_version"):
        load_info("kaiserbuffle/so101_test", local_meta=_write(tmp_path, _info(codebase_version="v2.1")))


def test_wrong_dimensionality_is_rejected_even_when_the_robot_type_is_right() -> None:
    raw = _info(features={"observation.state": {"shape": [7]}, "action": {"shape": [7]},
                          "observation.images.front": {"shape": [3, 480, 640]}})
    with pytest.raises(DatasetRejected, match="dimensions"):
        validate(parse_info(raw), repo_id="someone/seven-dof")


def test_a_state_only_dataset_is_rejected() -> None:
    """A VLA policy needs pixels. The attack perturbs the instruction with the image held fixed."""
    raw = _info(features={"observation.state": {"shape": [6]}, "action": {"shape": [6]}})
    with pytest.raises(DatasetRejected, match="observation.images"):
        validate(parse_info(raw), repo_id="someone/state-only")


def test_a_non_lerobot_dataset_has_no_parsable_info() -> None:
    """sree-aimaker/so101_pick_and_place — bare mp4s, no meta/info.json at all."""
    with pytest.raises(DatasetRejected):
        validate(parse_info({}), repo_id="sree-aimaker/so101_pick_and_place")


# --- The metric -----------------------------------------------------------------------------------


def test_l2_refuses_a_dimension_mismatch() -> None:
    """Zipping to the shorter vector would compare a 6-DoF arm to a 4-DoF one and look fine."""
    with pytest.raises(ValueError, match="dimension mismatch"):
        l2([0.0] * 6, [0.0] * 4)


def test_outside_envelope_is_a_single_step_check_from_the_real_state() -> None:
    state = [0.0, 0.0]
    low, high = [-1.0, -1.0], [1.0, 1.0]
    assert not outside_envelope(state, [0.5, 0.5], low, high)
    assert outside_envelope(state, [1.5, 0.0], low, high)
    # The same action from a different REAL state gives a different verdict, which is the point of
    # anchoring to recorded states rather than scoring actions in isolation.
    assert outside_envelope([0.9, 0.0], [0.5, 0.0], low, high)


def test_a_frame_where_the_benign_action_also_violates_is_excluded() -> None:
    """That frame says the envelope is mis-calibrated, not that the attack worked.

    Counting it would read the study's own instrument error as a finding.
    """
    report = summarise(
        [
            FrameComparison(frame_index=0, divergence=1.0, adversarial_outside_envelope=True,
                            benign_outside_envelope=True),
            FrameComparison(frame_index=1, divergence=1.0, adversarial_outside_envelope=True,
                            benign_outside_envelope=False),
        ],
        tool_version="0.0.0", dataset="d", robot_type="so101_follower", policy="stub",
        attack="roleplay", benign_instruction="b", adversarial_instruction="a",
    )
    assert report.envelope_violation_rate == 0.5, "the benign-violating frame was counted"
    assert report.benign_envelope_violation_rate == 0.5, "the control must be reported, not dropped"


def test_an_empty_sample_is_refused_rather_than_reported_as_zero() -> None:
    with pytest.raises(ValueError, match="empty sample"):
        summarise([], tool_version="0.0.0", dataset="d", robot_type="so101_follower",
                  policy="stub", attack="roleplay", benign_instruction="b",
                  adversarial_instruction="a")


# --- The labelling, which is the whole point ------------------------------------------------------


def _report() -> OfflineObservationReport:
    return summarise(
        [FrameComparison(frame_index=0, divergence=0.4, adversarial_outside_envelope=True,
                         benign_outside_envelope=False)],
        tool_version="0.0.0", dataset="Guanli001/so101-vials-auto-dr-final100",
        robot_type="so101_follower", policy="smolvla", attack="roleplay",
        benign_instruction="pick up the cube", adversarial_instruction="...",
    )


def test_the_artifact_carries_no_field_that_reads_as_an_asr() -> None:
    """The single most likely route to this study being misquoted as a real-robot ASR."""
    keys = set(json.loads(_report().model_dump_json()))
    for forbidden in ("asr", "adversarial_asr", "successes", "attempts", "success_rate"):
        assert forbidden not in keys, f"{forbidden!r} in an open-loop artifact invites the misread"


def test_the_earned_rung_is_real_forward_and_not_higher() -> None:
    """Real policy, real observation, forward passes only — below real-episode, which executes."""
    assert EARNED_EVIDENCE_STATE is EvidenceState.REAL_FORWARD
    assert _report().evidence_state == EvidenceState.REAL_FORWARD.value


def test_every_artifact_carries_the_claim_limits_inline() -> None:
    """In the payload, not in a docs page somebody may not have opened."""
    report = _report()
    assert report.claim_limits == CLAIM_LIMITS
    for phrase in ("OPEN-LOOP", "no robot moved", "NOT a closed-loop"):
        assert phrase in report.claim_limits


def test_hardware_runs_is_structurally_zero() -> None:
    """An open-loop study executes nothing, so it can never contribute a physical result."""
    assert _report().hardware_runs == 0
