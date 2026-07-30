#!/usr/bin/env python3
"""Run the action-envelope study: the acceptance-gate sweep and the coverage map.

Defensive, sim-only. A thin driver over the public API — it reimplements no ASR, no confidence
interval and no credit rule, exactly like ``studies/cross_arch_transfer/run.py``. Everything it
prints comes from :func:`provael.runner.run` and
:func:`provael.defenses.measure.build_mitigation_report`.

    python studies/action_envelope/run.py

WHY A SWEEP AT ALL. The clamp's default bounds are derived from a committed measurement of the
BENIGN policy's own commanded envelope (see :mod:`provael.defenses.envelope`). On this fixture the
benign danger channel is *exactly zero*, so the benign-derived danger cap drives every
danger-channel family to 0% by construction — a tautology, not a result. The part that carries
information is what the envelope COSTS: at which bound does clamping start breaking the clean task,
and does the acceptance gate catch it? That is what this sweep measures, and it is why the study is
worth publishing at all.

The tighter bounds here are deliberately below the stub's clean-task-success floor, so the protocol
is made to REJECT the defense. A measurement harness that only ever runs the configuration that
passes has not tested the gate.
"""

from __future__ import annotations

from provael.config import RunConfig
from provael.defenses.envelope import (
    BENIGN_DANGER_MAX,
    BENIGN_MARGIN_FRACTION,
    BENIGN_MOTION_L2_MAX,
    ActionEnvelopeClamp,
)
from provael.defenses.measure import build_mitigation_report
from provael.defenses.registry import DEFENSES
from provael.runner import run
from provael.types import RunReport

#: The families swept. The full adversarial registry plus the ``none`` benign control, which both
#: arms must carry or the verdict is `insufficient` and nothing can be concluded.
ATTACKS = [
    "none", "instruction", "visual", "sensor_spoof", "injection", "action", "action_space",
    "backdoor", "authorization", "confidentiality", "misalignment", "humanoid", "optimized",
    "optimized_patch", "optimized_instruction",
]

#: Motion-L2 caps to sweep. The first is the shipped benign-derived bound; the rest are tighter and
#: exist to find where the clean task breaks. `provael.suites.stub.REACH_SUCCESS_FLOOR` is the line
#: they cross — deliberately NOT imported here, because a study that reads the pass mark from the
#: thing it is testing has measured nothing.
MOTION_CAPS = [
    BENIGN_MOTION_L2_MAX * (1.0 + BENIGN_MARGIN_FRACTION),  # shipped default
    0.06,
    0.04,
    0.02,
]

ISSUED_AT = "1970-01-01T00:00:00Z"  # fixed: the artifact must be byte-reproducible
COMMIT = "study"


def _register_sweep_variant(cap: float) -> str:
    """Register a bound-varied clamp under its own name and return that name.

    The shipped registry factory takes no arguments on purpose, so
    ``provael attack --defense action_envelope`` can only ever mean the committed benign-derived
    bounds. A study that wants a tighter bound therefore has to say so out loud — which is what this
    does: it registers a DISTINCT name carrying the bound in the name, so every artifact the sweep
    produces records which envelope it was measured under. Nothing here changes what the shipped
    name means.
    """
    key = f"action_envelope_motion_{cap:.4f}".replace(".", "_")
    DEFENSES[key] = lambda cap=cap: ActionEnvelopeClamp(max_motion_l2=cap)  # type: ignore[misc]
    return key


def _arm(suite: str, defense_name: str | None) -> RunReport:
    cfg = RunConfig(
        policy="stub", suite=suite, attacks=list(ATTACKS), episodes=10, seed=0,
        defense=defense_name,
    )
    return run(cfg)


def main() -> None:
    print(f"benign-derived bounds: danger={BENIGN_DANGER_MAX} motion_l2={BENIGN_MOTION_L2_MAX} "
          f"margin={BENIGN_MARGIN_FRACTION}")
    print()
    print("## Coverage map — full registry, shipped bounds")
    print()
    for suite in ("stub", "reach", "humanoid"):
        undef = _arm(suite, None)
        defended = _arm(suite, "action_envelope")
        rep = build_mitigation_report(
            defended, undef, defense="action_envelope", issued_at=ISSUED_AT, commit=COMMIT,
        )
        print(f"{suite:9} verdict={rep.verdict.value:22} position={rep.position:8} "
              f"credited={rep.credited_families or '[]'}")
        print(f"{'':9} adversarial {rep.pre_adversarial_asr} -> {rep.post_adversarial_asr}"
              f"  clean-task {rep.pre_clean_task_success} -> {rep.post_clean_task_success}"
              f"  gate_ok={rep.clean_task_success_ok}")
    print()
    print("## Acceptance-gate sweep — stub (the only CPU suite that surfaces task success)")
    print()
    undef = _arm("stub", None)
    for cap in MOTION_CAPS:
        name = _register_sweep_variant(cap)
        defended = _arm("stub", name)
        rep = build_mitigation_report(
            defended, undef, defense=name, issued_at=ISSUED_AT, commit=COMMIT,
        )
        print(f"motion_l2_cap={cap:<7.4f} verdict={rep.verdict.value:22} "
              f"clean-task {rep.pre_clean_task_success} -> {rep.post_clean_task_success} "
              f"gate_ok={rep.clean_task_success_ok} credited={len(rep.credited_families)}")


if __name__ == "__main__":
    main()
