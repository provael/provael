# Provael examples gallery

Copy-paste runnable examples, simplest first. Everything in the **CPU** column needs only
`pip install provael` — no GPU, no model download. The **GPU** rows need the `[lerobot]` extra
and `PROVAEL_INTEGRATION=1`.

| # | Example | What it shows | Runtime | Needs |
| --- | --- | --- | --- | :---: |
| 01 | [first-scan-cpu](01-first-scan-cpu/) | Your first scan — all four attack families on the stub | < 1 s | CPU |
| 02 | [redteam-smolvla-libero](02-redteam-smolvla-libero/) | Red-team a real SmolVLA policy in LIBERO | minutes | GPU |
| — | [reproductions/](reproductions/) | Reproduce FreezeVLA / OpenVLA-patch / BadVLA / RoboPAIR in one command | < 1 s | CPU |
| — | [cross_suite_validation/](cross_suite_validation/) | Same attacks, two suites — generality shown with data | < 1 s | CPU |
| — | [adapters/](adapters/) | Red-team any VLA — π0, GR00T, OpenVLA, bring-your-own | varies | varies |
| — | [suites/](suites/) | The shipped suites + how to add a simulator | — | — |
| — | [python-api/](python-api/) | Runnable BYO policy & BYO suite in ~30–40 lines | < 1 s | CPU |
| — | [scorecard/](scorecard/) | One-page pre-deployment ASR scorecard (verdict + heatmap) | < 1 s | CPU |
| — | [recipes/](recipes/) | Named run presets (`provael list-recipes` / `--recipe`) | < 1 s | CPU |
| — | [integrations/](integrations/) | promptfoo / garak / PyRIT + SARIF aggregators | varies | — |
| — | [ci/](ci/) | CI gates: GitHub / GitLab / Azure + regression-gate | — | — |
| — | [mlops/](mlops/) | Log ASR to MLflow / W&B (track + gate promotion) | < 1 s | CPU |
| — | [hf/](hf/) | Push ASR onto a HF model card (eval-results) | < 1 s | CPU |
| — | [gpu-ci/](gpu-ci/) | Fork-safe real-model GPU CI via Modal (~$0.02/run) | minutes | GPU |
| — | [supply-chain/](supply-chain/) | Verify the model (safetensors/Sigstore) + emit an ML-BOM | < 1 s | CPU |
| — | [evidence/eu-ai-act-art15/](evidence/eu-ai-act-art15/) | Worked EU AI Act Art. 15 robustness evidence pack | < 1 s | CPU |
| — | [runtime/](runtime/) | Action-stream firewall (defense) — ASR with vs. without | < 1 s | CPU |
| — | [hf-space/](hf-space/) | Zero-install Gradio demo — run a scan in the browser | < 1 s | CPU |

## Fastest possible start

```bash
pip install provael
provael attack --recipe quick          # instruction family, 5 episodes, on the CPU stub
provael list-recipes                   # see every built-in preset
```

Prefer not to install anything? **[Open the 5-minute Colab notebook →](https://colab.research.google.com/github/provael/provael/blob/main/notebooks/01_provael_in_5_minutes.ipynb)**

## How the pieces fit

- **Policy × Suite × Attacks → ASR.** A *policy* acts in a *suite* (simulator); *attacks* perturb
  what it sees/reads; the *Attack Success Rate* is how often that drives it unsafe. Swap any axis.
- **CPU-first.** The `stub` policy + `stub` suite are deterministic fixtures so the whole engine is
  testable with no GPU. Real models (`smolvla`) and sims (`libero`) are opt-in extras.
- **Honest numbers.** Stub ASRs are a property of the fixture, not of any real VLA. Real-model
  results (example 02) are produced by *your* run and come with 95% CIs and a benign-FPR control.

More to come: model adapters (π0, OpenVLA), a second simulator suite, attack reproductions,
buyer-facing scorecards, and compliance evidence packs.
