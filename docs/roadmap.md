# Roadmap

Provael is CPU-first and model-agnostic. Shipped vs. planned, honestly marked.

## Shipped

- **Attacks:** 16 adversarial families + a `none` benign control, mapped
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

## Planned (contributions welcome)

- **Suites:** RoboCasa, CALVIN, SimplerEnv, and the AI2 vla-evaluation-harness bridge (one adapter
  → ~18 benchmarks). See [examples/suites](https://github.com/provael/provael/tree/main/examples/suites).
- **Docs-site versioning** (`mike`). The dependency is installed; nothing is wired to it yet.
- **Standards:** MITRE ATLAS case study, OWASP Agentic embodied annex, OECD.AI listing (drafts in
  [docs/standards](https://github.com/provael/provael/tree/main/docs/standards)).
- **Stronger attacks:** white-box gradient variants (GCG-style suffixes, transferable pixel/patch
  search) and a real-model transfer of the `optimized` family beyond the stub.

!!! note
    "Planned" means not yet shipped — we don't ship fabricated capability. Each lands behind tests
    and the same honesty discipline as the rest of the project.
