# Roadmap

Provael is CPU-first and model-agnostic. Shipped vs. planned, honestly marked.

## Shipped

- **Attacks:** 17 adversarial families + a `none` benign control, mapped
  to the [Embodied AI Security Top 10](top10.md).
- **Policies:** `stub` (CPU); `smolvla`, `pi0`, `pi05`, `pi0fast`, `groot` (LeRobot); `openvla`
  (HF transformers); `openpi` (websocket client to a π0 policy *server*). Bring-your-own via the
  `PolicyAdapter` ABC. **`groot`, `openvla` and `openpi` are registered scaffolding** — no
  checkpoint has been loaded through any of them here, and `provael list-policies` says so per
  backend. Only `smolvla` has produced a committed real-model result.
- **Suites:** `stub` (scalar, CPU), `reach` (spatial, CPU), `humanoid` (whole-body, CPU),
  `libero` + `metaworld` (real simulators, gated). `provael list-suites` marks which is which.
- **Evidence:** SARIF, compliance crosswalk, pre-deployment scorecard, OSCAL export, AVID export.
- **Reproductions:** FreezeVLA, OpenVLA-patch, BadVLA, RoboPAIR.
- **Integrations:** promptfoo provider; garak/PyRIT reference plugins; multi-CI (GitHub/GitLab/
  Azure) SARIF; pre-commit; MLflow/W&B logging; HF eval-results; Modal GPU-CI; Docker/devcontainer;
  supply-chain: **checkpoint-integrity verification shipped in 0.27.0** (pinned-digest + pickle
  refusal, fail-closed, in the reusable Action — see
  [checkpoint-integrity](checkpoint-integrity.md)); the CycloneDX **ML-BOM ships** (`provael report
  --format mlbom`), while model-*signing* (Sigstore) remains planned. The public leaderboard is
  Ed25519-signed as of 0.27.0.
- **Public leaderboard with open submission — SHIPPED, and this line was wrong until 22 Aug 2026.**
  `provael submit` has been in every release since **0.32.0**, `CONTRIBUTING-leaderboard.md` documents
  the PR route, and `leaderboard-submission.yml` validates submissions on `results/**`. It sat under
  *Planned* while the Shipped section above already said the board is Ed25519-signed — the file
  contradicted itself. **Zero external submissions have arrived**, which is the honest reason it felt
  unshipped, and is a fact about adoption rather than about the code.
- **Defenses — what is measured and what is not.** Two of the six `docs/defenses.md` taxonomy rows
  are measured under the protocol, both `stub-validated-scaffolding` on CPU fixtures:
  `instruction_canonicalization` (input side) and `action_envelope` (action side). The action-envelope
  study is `credited` on `stub` and `reach` and **`not-credited` on `humanoid`**, and both studies
  open by stating how much of their own credit is circular on a fixture. **No real-model transfer is
  claimed for either defense.** The four remaining rows are *specified and unproven*; three of them
  act on the policy's output and became expressible only with `Defense.filter_action` in 0.28.0.
  The ROS 2 guard node stays a sim/reference node that makes no measurement claim.
- **Optimized attacks (in progress):** the `optimized` family — `targeted_hijack`, a black-box,
  query-budgeted search — is the first non-templated attack (stub-validated; real transfer gated).

## Blocked on hardware — sim-to-real (SO-ARM101)

**Runs executed to date: 0**, and none will run until both prerequisites below exist. The protocol
is pre-registered in [docs/studies/sim-to-real-so101.md](studies/sim-to-real-so101.md) and published
at [provael.com/sim-to-real](https://www.provael.com/sim-to-real/); it was amended on
**1 September 2026, before any trial**, and the amendment created these two blockers. They are
recorded here because a dependency visible only inside the study it blocks is not visible at all.

- **An inline cut on the DC supply.** The STS3215's own over-current protection is not a latch — the
  output is disabled only until the next position command arrives. This study's threat model is a
  policy that keeps streaming commands, so it re-arms the servo it just faulted. The protection
  holds under benign teleop and fails under precisely the condition being tested, so the e-stop this
  protocol depends on has to be a physically operated inline cut on the supply. **No kit ships one**;
  it is a required addition, not an assumption.
- **A per-trial servo-bus voltage trace.** The kits ship a 12 V 7.5 A supply while per-servo
  over-current protection trips above ~2 A, so six servos accelerating together can demand more than
  the supply delivers. The failure is voltage sag, torque loss mid-motion, and the arm falling — and
  it is **biased toward the hypothesis**, because adversarial action sequences are jerkier and drive
  more joints at once than benign teleop, making the attacked condition the more likely one to brown
  out. An arm that loses torque above a keep-out zone falls into it. Unmeasured, a power fault is
  indistinguishable from a successful redirection, in the direction that flatters the result.

Neither is a software task, so neither can be closed by anything in this repository. Until both are
in place, the honest state of the real-robot arm of this work is zero trials, and any sim/real
comparison here would be reporting a hardware fault as a finding.

## Planned (contributions welcome)

- **Suites:** RoboCasa, CALVIN, SimplerEnv, and the AI2 vla-evaluation-harness bridge (one adapter
  → ~18 benchmarks at the harness's v0.4.0; v0.5.0 exposes 20). See
  [examples/suites](https://github.com/provael/provael/tree/main/examples/suites).

    **Scaffolding exists, and it is not a bridge yet.** The `ai2_bridge` suite is registered and
    listed as *scaffolding — no benchmark ever run*; every contract method raises. The interface was read at
    v0.5.0 and the blocker is in the harness's public surface, not in the effort: it returns
    per-episode success only (LIBERO's `get_step_result` is `{"success": ...}`, its recorder filtered
    to `{reward, done, success}`), and the end-effector pose flows outward to the model server rather
    than back to a caller. So `is_unsafe()` has no state to score, and with it the keep-out zone, the
    calibration signal and the EAI02/04/06 predicates. The benign control arm, by contrast, **is**
    expressible. Full notes, with the three ways round the predicate gap and their costs, in
    [docs/studies/ai2-bridge-notes.md](studies/ai2-bridge-notes.md).
- **Docs-site versioning** (`mike`). **Decided against, 2 September 2026.** The dependency has been
  removed rather than left installed and unwired.

    `mike` publishes every build under a version path and leaves a redirect at the root, so wiring
    it moves `docs.provael.com/top10/` to `docs.provael.com/latest/top10/` and 404s the old URL.
    There is no configuration that avoids this: `alias_type` chooses how the alias is stored, not
    whether content is namespaced. Those URLs are published, cited from the marketing site and
    named in the Top 10's own BibTeX, and this repo already carries a redirect map and the rule
    that [an old URL stays old forever](https://github.com/provael/provael/blob/main/mkdocs.yml).
    Trading that for a version selector nobody has asked for, on a project three months old whose
    docs describe one supported release, is the wrong side of the trade.

    **What would reopen it:** a second supported release line, or a reader who needs the docs for a
    version they are pinned to. At that point the migration is worth doing properly — every retired
    URL gets a stub, the same way the uppercase→lowercase rename was handled — rather than done
    cheaply now and paid for in dead links.
- **Standards:** MITRE ATLAS case study, OWASP Agentic embodied annex, OECD.AI listing (drafts in
  [docs/standards](https://github.com/provael/provael/tree/main/docs/standards)).
- **Stronger attacks:** white-box gradient variants (GCG-style suffixes, transferable pixel/patch
  search) and a real-model transfer of the `optimized` family beyond the stub.

!!! note
    "Planned" means not yet shipped — we don't ship fabricated capability. Each lands behind tests
    and the same honesty discipline as the rest of the project.
