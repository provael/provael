"""Fail the job on a mitigation verdict that must not ship, and explain which one.

THREE FAILING VERDICTS, ONE PASSING ONE, AND ONE THAT ONLY LOOKS LIKE A FAILURE.

``rejected-benign-cost``  the defense broke the benign task — the FPR rose or clean-task success
                          fell outside its interval. Rejected regardless of what it did to the ASR,
                          mirroring `provael mitigation`'s own non-zero exit. A protective measure
                          that stops the robot doing its job is not a mitigation.
``insufficient``          one or both arms lacked the benign control, so nothing could be compared.
                          Nothing measured is not a pass — the same rule `enforce_gate.py` applies
                          to an empty ASR.
``""`` (absent)           the measurement step itself failed.
``not-credited``          A REAL MEASURED RESULT, NOT A FAILURE: no attack family's confidence
                          intervals separated. Reported as a notice, never gated on. Treating it as
                          a failure would push users toward defenses that look effective rather
                          than ones that are.

Reads ``PROVAEL_VERDICT`` and ``PROVAEL_DEFENSE`` from the environment.
"""

from __future__ import annotations

import os
import sys

from _github import error, notice

#: Verdict -> the message a user needs to act on it. Membership is the gate; a verdict absent from
#: this mapping passes, so a NEW verdict added upstream fails open by default. That is deliberate:
#: an unrecognised verdict is not evidence of a problem, and inventing a failure from a string this
#: script does not understand would block releases on a vocabulary change.
FAILING = {
    "rejected-benign-cost": (
        "Provael REJECTED the defense {defense!r} (rejected-benign-cost): the benign "
        "false-positive rate rose or clean-task success fell outside its confidence interval. "
        "A protective measure that breaks the benign task is not a mitigation."
    ),
    "insufficient": (
        "Provael could not evaluate the defense {defense!r}: verdict `insufficient`, which means "
        "one or both arms lacked the BENIGN CONTROL. Add `none` to `attacks` so the benign "
        "false-positive rate and the clean-task acceptance gate can be computed. "
        "Nothing measured is not a pass."
    ),
}


def main() -> int:
    verdict = os.environ.get("PROVAEL_VERDICT", "").strip()
    defense = os.environ.get("PROVAEL_DEFENSE", "")

    if not verdict:
        error("Provael emitted no mitigation verdict; the measurement step failed.")
        return 1
    if verdict in FAILING:
        error(FAILING[verdict].format(defense=defense))
        return 1

    print(f"Provael mitigation verdict for {defense!r}: {verdict}")
    if verdict == "not-credited":
        notice(
            "`not-credited` is a real measured result, not a failure: no attack family's "
            "confidence intervals separated. It is reported, not gated on."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
