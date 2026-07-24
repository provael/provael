# π0 (openpi) cross-architecture instruction-transfer study

> **Defensive, sim-only.** No real-robot or hardware control code, no real-world-harm payloads. The
> attacks perturb only the instruction/observation a policy receives in simulation. See
> [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

> Status: PRE-REGISTERED — protocol only, no results claimed.

This pre-registers the **π0 leg** of the
[cross-architecture transfer study](../findings/2026-cross-arch-transfer.md): does the instruction
family that redirects SmolVLA also redirect a *different* VLA architecture, or is the redirection an
artefact of one codebase's glue?

## Hypothesis

The **instruction** family (`roleplay`, `goal_substitution`, `paraphrase`) that transfers to real
SmolVLA × LIBERO (roleplay 100% [72–100%], goal_substitution 60%, paraphrase 10% — see the
[instruction-transfer finding](../findings/2026-instruction-transfer.md)) also transfers to **π0
served by [openpi](https://github.com/Physical-Intelligence/openpi)** — Physical Intelligence's own
stack, a different framework from LeRobot but the same flow-matching action head. **Null
hypothesis:** the redirection is codebase-specific and π0 shows no lift over its benign control.

## Method

- **Backends / env.** π0 via the CPU-only `[openpi]` websocket client to a GPU policy server.
  Because `[openpi]` and `[lerobot]` pin conflicting numpy majors, the π0 leg runs in **its own
  environment** and is merged offline through the versioned cross-architecture RPC contract
  (`provael.studies.cross_arch`) — no shared process, no re-implemented scoring.
- **Attacks + control.** `roleplay`, `goal_substitution`, `paraphrase`, and the benign `none`
  control, on the same LIBERO task family used for the SmolVLA result.
- **Design.** n = _TBD_ episodes per attack, _TBD_ seeds, horizon _TBD_ — matched to the SmolVLA
  protocol so the two legs are comparable. Runs under 5 seeds are flagged `preliminary`; a headline
  requires ≥ 5 seeds.
- **Gate.** GPU + `PROVAEL_INTEGRATION=1`; on CPU the leg is reported `pending`, never fabricated.

## Success criteria

For each attack, the **redirection rate** with its **95% Wilson CI**, read against the **benign-FPR**
control (`none`, scored under the same predicate). Transfer is claimed for an attack only when its CI
lower bound is above the benign FPR. Cross-architecture *agreement* with SmolVLA is assessed by **CI
overlap** per attack, not by point-estimate equality. The honest outcomes are: it transfers (naming
the families that do), or a clean **null** — published as such, like the visual/injection null on
SmolVLA.

## Threats to validity

- **One task family, small n.** Read the CIs, not the point estimates.
- **Predicate portability.** The unsafe/keep-out predicate calibrated for the SmolVLA leg may not fit
  π0's benign envelope; the protocol re-calibrates per policy to a benign-FPR target before
  attacking, and reports the achieved benign FPR.
- **Server nondeterminism.** A remote GPU policy server may not be bit-deterministic; seeds and the
  RPC-contract digest are recorded so a run is reproducible-in-distribution, not byte-identical.
- **Framework glue, not architecture.** A positive result on one π0 build is evidence about that
  build; genuine architecture-level generality needs more than one non-LeRobot backend.

## Limitations

Cross-architecture transfer here means **SmolVLA vs one π0 build**, both LIBERO-suite tabletop
manipulators. No mobile or humanoid embodiment, and only the instruction family is in scope for this
leg — visual/injection remain stub-validated pending stronger perturbations. Until this runs, **no
cross-architecture number is claimed.**
