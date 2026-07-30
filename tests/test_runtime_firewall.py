"""The runtime examples: the mitigation demo runs the protocol, and the guard node still clamps.

This file used to assert a DIRECTION OF EFFECT — `assert fw < base`, plus frozen point estimates
`base == 67 and fw == 20`. That mirrored the example it was testing, and it was the same mistake: a
bare pre/post comparison with no interval, no credit rule and no benign control is exactly the
reasoning `docs/DEFENSES.md` and `provael.defenses.measure` exist to forbid.

A test may legitimately pin what a fixture does. It may not encode "a defense lowers ASR" as a
property, because that is the empirical question the protocol answers and the answer is allowed to be
`not-credited` — as it is for `action_envelope` on the `humanoid` suite. So what is asserted here is
that the demo drives the protocol and emits a well-formed verdict, not which verdict it gets.
"""

from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parent.parent / "examples" / "runtime"
sys.path.insert(0, str(_RUNTIME))

import robot_firewall  # noqa: E402
from ros2_guard_node import clamp_twist  # noqa: E402

from provael.config import RunConfig  # noqa: E402
from provael.defenses.measure import (  # noqa: E402
    MitigationReport,
    MitigationVerdict,
    build_mitigation_report,
)
from provael.runner import run  # noqa: E402


def _mitigation(suite: str) -> MitigationReport:
    base = {"policy": "stub", "suite": suite, "attacks": list(robot_firewall.ATTACKS),
            "episodes": 10, "seed": 0}
    undefended = run(RunConfig(**base))  # type: ignore[arg-type]
    defended = run(RunConfig(**base, defense="action_envelope"))  # type: ignore[arg-type]
    return build_mitigation_report(
        defended, undefended, defense="action_envelope",
        issued_at=robot_firewall.ISSUED_AT, commit=robot_firewall.COMMIT,
    )


def test_the_demo_battery_carries_the_benign_control() -> None:
    """Without the `none` arm the verdict is `insufficient` and nothing can be concluded.

    The previous version of the example ran `instruction,visual,injection,action` and NO control, so
    its comparison could not have been valid even with intervals bolted on. This pins the fix.
    """
    assert robot_firewall.ATTACKS[0] == "none"


def test_the_demo_produces_a_well_formed_verdict_not_a_bare_delta() -> None:
    """A verdict, intervals and controls — the shape of the claim, not its direction."""
    report = _mitigation("stub")
    assert isinstance(report.verdict, MitigationVerdict)
    assert report.verdict is not MitigationVerdict.insufficient, "the control arm went missing"
    assert report.position == "action"
    # Every measured family carries an interval in both arms, which is what makes the credit rule
    # applicable at all.
    measured = [r for r in report.rows if r.pre_asr is not None]
    assert measured, "no family scored in either arm"
    for row in measured:
        assert row.pre_ci95 is not None and row.post_ci95 is not None
    # The controls exist and are reported, whatever they say.
    assert report.pre_benign_fpr is not None
    assert report.acceptance_gate


def test_a_credited_family_really_has_separated_intervals() -> None:
    """The credit rule, checked against the rows rather than assumed.

    This is the property worth testing: not that the ASR fell, but that anything claiming credit
    satisfies the rule. Overlapping intervals must never be credited however good the point estimate.
    """
    report = _mitigation("stub")
    for row in report.rows:
        if not row.credited:
            continue
        assert row.pre_ci95 is not None and row.post_ci95 is not None
        # Separated: the post-attack upper bound sits below the pre-attack lower bound.
        assert row.post_ci95[1] < row.pre_ci95[0], f"{row.family} credited on overlapping intervals"
        assert row.post_asr is not None and row.pre_asr is not None
        assert row.post_asr < row.pre_asr


def test_a_not_credited_verdict_is_a_valid_outcome_of_the_demo() -> None:
    """`humanoid` genuinely yields `not-credited` against this defense — and that must be fine.

    Encoding "the defense works" as a test property would have made this suite unrepresentable.
    """
    report = _mitigation("humanoid")
    assert report.verdict is MitigationVerdict.not_credited
    assert report.credited_families == []


def test_clamp_twist_envelope() -> None:
    clamped, violated = clamp_twist((1.0, 0.0, 0.0), max_speed=0.15)
    assert violated is True
    assert abs(clamped[0] - 0.15) < 1e-6
    safe, ok = clamp_twist((0.05, 0.0, 0.0), max_speed=0.15)
    assert ok is False and safe == (0.05, 0.0, 0.0)
