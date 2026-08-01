"""Show defense, not just offense — driven through the measurement protocol.

Runs Provael's **registered** action-side defense (``action_envelope``) against the attack battery
in both arms and reports what ``provael mitigation`` reports: a per-family pre/post attack-success
rate with 95% Wilson confidence intervals, the benign controls, the acceptance gate, and a verdict.

IMPORTANT — HONEST SCOPE: this is a **sim / reference monitor**, NOT a certified safety controller.
The real functional-safety bar (NVIDIA Halos, ISO 26262 / IEC 61508) is out of scope and Provael
does not claim it. This demonstrates that the measured ASR *moves* when a defense is applied — the
point of a red-team + harden loop.

WHY THIS FILE WAS REWRITTEN (0.28.0)
------------------------------------
It used to wrap the policy in an ad-hoc clamp, print ``base - firewalled`` as a percentage, and end
with ``assert fw_s < base_s``. That is a bare point-estimate comparison — precisely the reasoning
``docs/defenses.md`` and :mod:`provael.defenses.measure` exist to forbid: no confidence interval, no
credit rule, no benign false-positive control, no acceptance gate. It was the project's "show
defense" demo the whole time, arguing for a defense in the one style the project tells everyone else
not to use.

Two specifics, because they are instructive rather than cosmetic:

* **Its clamp sat below the fixture's own unsafe threshold** (danger cap ``0.4`` against a per-seed
  threshold drawn from ``[0.5, 0.9)``), which drives the ASR to zero *by construction*. The
  registered defense derives its bounds from a measured benign envelope instead, and
  ``tests/test_defenses.py`` structurally forbids it from importing a suite's predicate.
* **It ran no benign control.** Without the ``none`` arm the protocol returns ``insufficient`` and
  nothing can be concluded in either direction — so the old comparison could not have been valid
  even with intervals bolted on.

What this prints now is a verdict, and on some suites that verdict is ``not-credited``. See
``docs/studies/action-envelope.md``, which leads with how much of the credit is tautological on a
fixture and publishes the coverage map of families one envelope provably cannot address.

The runtime monitor this file used to define is still useful as a *shape* — see
``examples/runtime/ros2_guard_node.py`` for a reference node that makes no measurement claim. The
taxonomy rows it gestured at (trajectory anomaly detection, rate limiting, output screening) remain
**specified and unproven** and are deliberately unregistered.

    python examples/runtime/robot_firewall.py
"""

from __future__ import annotations

from provael.config import RunConfig
from provael.defenses.measure import build_mitigation_report, to_mitigation_markdown
from provael.runner import run

#: The battery. ``none`` is first and is not optional: it is the benign control, and both arms need
#: it or the verdict is ``insufficient``.
ATTACKS = ["none", "instruction", "visual", "injection", "action"]

#: Fixed, so the demo is byte-reproducible — the protocol is pure and takes these from the caller.
ISSUED_AT = "1970-01-01T00:00:00Z"
COMMIT = "example"


def main() -> None:
    for suite in ("stub", "reach"):
        base = {"policy": "stub", "suite": suite, "attacks": list(ATTACKS),
                "episodes": 10, "seed": 0}
        # Byte-identical config in both arms except for the defense. Anything else differing would
        # make the comparison meaningless.
        undefended = run(RunConfig(**base))  # type: ignore[arg-type]
        defended = run(RunConfig(**base, defense="action_envelope"))  # type: ignore[arg-type]

        report = build_mitigation_report(
            defended, undefended, defense="action_envelope",
            issued_at=ISSUED_AT, commit=COMMIT,
        )
        print(f"\n{'=' * 78}\nsuite: {suite}\n{'=' * 78}")
        print(to_mitigation_markdown(report))

    print(
        "\nRead the verdict, not the delta. A credited family means the post-attack 95% "
        "interval was separated from the pre-attack interval; overlapping intervals are NOT "
        "credited however good the point estimate looks. See docs/studies/action-envelope.md "
        "for how much of this credit is tautological on a CPU fixture, and for the families "
        "an envelope cannot address."
    )
    print("\n(Sim/reference monitor — not a certified safety controller. See the docstring.)")


if __name__ == "__main__":
    main()
