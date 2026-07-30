# Roadmap

Provael is CPU-first and model-agnostic. Shipped vs. planned, honestly marked.

## Shipped

- **Attacks:** 14 adversarial families + a `none` benign control, mapped
  to the [Embodied AI Security Top 10](TOP10.md).
- **Policies:** `stub` (CPU); `smolvla`, `pi0`, `pi05`, `pi0fast`, `groot` (LeRobot); `openvla`
  (HF transformers). Bring-your-own via the `PolicyAdapter` ABC.
- **Suites:** `stub` (scalar, CPU), `reach` (spatial, CPU), `libero` + `metaworld` (gated).
- **Evidence:** SARIF, compliance crosswalk, pre-deployment scorecard, OSCAL export, AVID export.
- **Reproductions:** FreezeVLA, OpenVLA-patch, BadVLA, RoboPAIR.
- **Integrations:** promptfoo provider; garak/PyRIT reference plugins; multi-CI (GitHub/GitLab/
  Azure) SARIF; pre-commit; MLflow/W&B logging; HF eval-results; Modal GPU-CI; Docker/devcontainer;
  supply-chain: **checkpoint-integrity verification shipped in 0.27.0** (pinned-digest + pickle
  refusal, fail-closed, in the reusable Action — see
  [checkpoint-integrity](checkpoint-integrity.md)); model-*signing* (Sigstore) and ML-BOM remain
  planned. The public leaderboard is Ed25519-signed as of 0.27.0.
- **Defenses — what is measured and what is not.** Two of the six `docs/DEFENSES.md` taxonomy rows
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
- **Public leaderboard** with open submission; **docs site** versioning.
- **Standards:** MITRE ATLAS case study, OWASP Agentic embodied annex, OECD.AI listing (drafts in
  [docs/standards](https://github.com/provael/provael/tree/main/docs/standards)).
- **Stronger attacks:** white-box gradient variants (GCG-style suffixes, transferable pixel/patch
  search) and a real-model transfer of the `optimized` family beyond the stub.

!!! note
    "Planned" means not yet shipped — we don't ship fabricated capability. Each lands behind tests
    and the same honesty discipline as the rest of the project.
