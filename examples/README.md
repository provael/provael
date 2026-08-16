# Provael examples gallery

Copy-paste runnable examples, simplest first. Everything in the **CPU** column needs only
`pip install provael` — no GPU, no model download. The **GPU** rows need the `[lerobot]` extra
and `PROVAEL_INTEGRATION=1`.

| # | Example | What it shows | Runtime | Needs |
| --- | --- | --- | --- | :---: |
| ★ | [lerobot_eval_smolvla_libero.py](lerobot_eval_smolvla_libero.py) | **Reproduce the headline result**, one file, nothing to edit | 15.4 GPU-h | GPU |
| ★ | [matched_pairs.py](matched_pairs.py) | **The matched pair** — 2×2 table, exact McNemar p, and the CI declining on one task | < 1 s | CPU |
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

## Reproducing the headline result

[`lerobot_eval_smolvla_libero.py`](lerobot_eval_smolvla_libero.py) reproduces the SmolVLA × LIBERO
result end to end. It is one file with [PEP 723](https://peps.python.org/pep-0723/) inline
dependency metadata, so there is nothing to install and no path to edit:

```bash
uv run examples/lerobot_eval_smolvla_libero.py --dry-run   # validates on any laptop, seconds
uv run examples/lerobot_eval_smolvla_libero.py             # the real run — read the table first
```

`uv run` builds an isolated environment from the pinned header and executes the file. The dry run
imports no torch and downloads no weights: it resolves the registries, validates the `RunConfig`,
and confirms the benign control arm is present — the checks that would otherwise fail at minute 0
of a 15-hour run.

### Expected wall-clock, and the hardware it was measured on

| | value |
| --- | --- |
| GPU | **NVIDIA L4** (Modal), single GPU per shard |
| Episodes | 400 records, **350 measured** (`mcp_tool_desc` is N/A in this suite, 0 attempts) |
| GPU-hours | **15.4** |
| Cost | **$12.29**, measured — $0.031/episode |
| Wall clock | **2.04 h** sharded one task per container ×10; **~15.4 h** unsharded on one GPU |
| provael | 0.32.0 + the post-tag `--episodes-per-seed` commit |
| lerobot | **0.5.1** |

The cost row is measured, not projected: the pre-run estimate was $10.17 against an actual $12.29,
**21% low**. Budget accordingly.

### What it prints, and why

The matched-pair table and the McNemar p-value for every arm, computed by
`provael.scoring.paired` rather than reimplemented. The benign control is structurally impossible
to drop: every comparison is built from the `(task, seed)`-matched benign twin, so an arm without a
twin simply has no row. It then compares your run against the committed reference
(`roleplay` 44/50, control 2/50) and says whether you reproduced it.

### Two things that will surprise you

- **Your numbers will differ by a few episodes.** SmolVLA's flow-matching sampler is not fully
  seeded (`stochastic: true`), so provael's determinism contract covers the stub path and not this
  one. The committed 44/50 is one draw, and so is yours.
- **lerobot is pinned at 0.5.1, not the newer 0.6.x.** 0.6.0 and 0.6.1 exist; the committed result
  was measured on 0.5.1 and has never been re-measured on 0.6.x. Pinning forward would make this a
  script that runs rather than one that reproduces. Re-measuring on 0.6.x is welcome — report the
  difference.

## How the pieces fit

- **Policy × Suite × Attacks → ASR.** A *policy* acts in a *suite* (simulator); *attacks* perturb
  what it sees/reads; the *Attack Success Rate* is how often that drives it unsafe. Swap any axis.
- **CPU-first.** The `stub` policy + `stub` suite are deterministic fixtures so the whole engine is
  testable with no GPU. Real models (`smolvla`) and sims (`libero`) are opt-in extras.
- **Honest numbers.** Stub ASRs are a property of the fixture, not of any real VLA. Real-model
  results (example 02) are produced by *your* run and come with 95% CIs and a benign-FPR control.

More to come: model adapters (π0, OpenVLA), a second simulator suite, attack reproductions,
buyer-facing scorecards, and compliance evidence packs.
