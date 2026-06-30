# Roadmap

Provael is CPU-first and model-agnostic. Shipped vs. planned, honestly marked.

## Shipped

- **Attacks:** 4 families (instruction / visual / injection / action) + a `none` baseline, mapped
  to the [Embodied AI Security Top 10](TOP10.md).
- **Policies:** `stub` (CPU); `smolvla`, `pi0`, `pi05`, `pi0fast`, `groot` (LeRobot); `openvla`
  (HF transformers). Bring-your-own via the `PolicyAdapter` ABC.
- **Suites:** `stub` (scalar, CPU), `reach` (spatial, CPU), `libero` + `metaworld` (gated).
- **Evidence:** SARIF, compliance crosswalk, pre-deployment scorecard, OSCAL export, AVID export.
- **Reproductions:** FreezeVLA, OpenVLA-patch, BadVLA, RoboPAIR.
- **Integrations:** promptfoo provider; garak/PyRIT reference plugins; multi-CI (GitHub/GitLab/
  Azure) SARIF; pre-commit; MLflow/W&B logging; HF eval-results; Modal GPU-CI; Docker/devcontainer;
  supply-chain (model-signing + ML-BOM).
- **Defense demo:** action-stream firewall + ROS 2 guard node (sim/reference).

## Planned (contributions welcome)

- **Suites:** RoboCasa, CALVIN, SimplerEnv, and the AI2 vla-evaluation-harness bridge (one adapter
  → ~18 benchmarks). See [examples/suites](https://github.com/provael/provael/tree/main/examples/suites).
- **Public leaderboard** with open submission; **docs site** versioning.
- **Standards:** MITRE ATLAS case study, OWASP Agentic embodied annex, OECD.AI listing (drafts in
  [docs/standards](https://github.com/provael/provael/tree/main/docs/standards)).
- **Stronger attacks:** gradient/search-optimised variants beyond the templated screen.

!!! note
    "Planned" means not yet shipped — we don't ship fabricated capability. Each lands behind tests
    and the same honesty discipline as the rest of the project.
