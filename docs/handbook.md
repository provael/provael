# The VLA Red-Teaming Handbook (outline)

A standalone guide that teaches the *practice* of red-teaming Vision-Language-Action policies —
the Trail-of-Bits-Testing-Handbook model that drove tool adoption. This is the chapter outline;
each chapter expands into a docs page.

1. **Why red-team a VLA?** — the action-space is the new attack surface; the incident record
   (RoboPAIR on a deployed Go2, FreezeVLA, BadVLA, the Unitree CVEs); what sim measurement does and
   doesn't tell you ([sim predicts real](SIM_PREDICTS_REAL.md)).
2. **Threat model** — the [Embodied AI Security Top-10](TOP10.md); instruction vs. perception vs.
   injection vs. action-integrity; attacker capabilities and where they enter (user, environment,
   actuation).
3. **Your first scan** — install, the CPU stub, reading ASR + the benign control
   ([quickstart](quickstart.md)).
4. **Calibration** — fit a per-task predicate to a benign-FPR target so "unsafe" is meaningful;
   why uncalibrated rates mislead ([MEASURE 2.7](MEASURE-2-7.md)).
5. **Red-teaming a real policy** — adapters (SmolVLA / π0 / GR00T / OpenVLA / BYO), suites
   (LIBERO / Meta-World), GPU + the gated path; honest scope (`n`, CIs, one task).
6. **Reproducing the literature** — `provael reproduce`; mapping a paper's threat class to a
   family; citing the paper number separately from yours.
7. **Hardening loop** — the [runtime firewall](https://github.com/provael/provael/tree/main/examples/runtime);
   measuring ASR before/after; what an envelope can and can't stop.
8. **Putting it in CI** — gates, the regression-gate, SARIF to code scanning, the scorecard.
9. **Evidence & compliance** — SARIF / OSCAL / AVID / the [crosswalk](COMPLIANCE.md); evidence vs.
   certification; the per-persona cards.
10. **Extending Provael** — write an attack, a suite, an adapter; contribute to the Top-10.

> Status: outline. Chapters land incrementally as docs pages — same honesty discipline as the rest
> of the project (no fabricated capability, paper numbers cited not claimed).
