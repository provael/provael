"""Read an attack-success rate and its benign floor out of one report.

CPU-only, no GPU, no model download, no arguments, under a second on the deterministic stub.

    python examples/python-api/benign_floor_beside_asr.py

WHY THIS EXAMPLE EXISTS. 0.38.0 added `RunReport.benign_headline()` as the exact mirror of
`adversarial_headline()`, and `scoring.asr.benign_control()` to resolve it once for every exporter.
Nothing showed a reader how to get both out of a report, which is the one thing you have to do
before an ASR means anything: an attack-success rate is a DIFFERENCE against the benign floor, so a
rate quoted without its control arm is a number with nothing behind it.
"""

from __future__ import annotations

from provael.config import RunConfig
from provael.report import benign_control_text
from provael.runner import run
from provael.scoring.asr import benign_control

report = run(
    RunConfig(
        policy="stub",
        suite="stub",
        # `none` is the benign control. Without it there is no floor to read the rest against, and
        # the two lines below would have nothing to compare.
        attacks=["none", "instruction", "visual", "injection"],
        episodes=10,
        seed=0,
    )
)

# Both headlines are (rate, successes, attempts) over the SAME `applicable` filter, on opposite
# sides of the `baseline` family — so they partition the run and cannot double-count an episode.
adv_rate, adv_successes, adv_attempts = report.adversarial_headline()
ben_rate, ben_successes, ben_attempts = report.benign_headline()

print(f"adversarial ASR   {100 * adv_rate:5.1f}%  ({adv_successes}/{adv_attempts})")
print(f"benign floor      {100 * ben_rate:5.1f}%  ({ben_successes}/{ben_attempts})")
print()

# The interval matters more than the rate when the denominator is small: 0/5 and 0/500 are both
# "0.0%", and only one of them is evidence. `benign_control()` is what every exporter uses, so what
# it returns here is exactly what lands in the SARIF run, the ML-BOM and the leaderboard row.
control = benign_control(report)
if control is None:
    # Not a formality. A run with no benign arm has an UNMEASURED floor, which is a different
    # claim from a floor measured at zero — and only one of them is a clean bill of health. The
    # rate above is not readable on its own, so this stops rather than printing it as if it were.
    raise SystemExit(
        "no benign control arm in this run — the ASR above has nothing to be read against"
    )

print(f"benign floor, as every exporter publishes it:  {benign_control_text(report)}")
print()
print(
    "An attack-success rate is a difference against that floor. Read alone, the first line is a\n"
    "rate with no control arm — which is why nothing in this package prints one without the other."
)
