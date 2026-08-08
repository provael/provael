---
title: Provael ASR Leaderboard
emoji: 🦾
colorFrom: red
colorTo: indigo
sdk: gradio
sdk_version: 6.16.0
app_file: app.py
pinned: false
license: apache-2.0
---

# Provael — VLA Red-Team ASR Leaderboard

Attack Success Rate (ASR) of instruction / visual / injection attacks against
Vision-Language-Action (VLA) robot policies in simulation, built with
[`provael`](https://github.com/provael/provael). Lower ASR = more robust.

> ✅ **Real data.** `results/leaderboard.json` holds the first real SmolVLA-on-LIBERO
> result (`HuggingFaceVLA/smolvla_libero`, `libero_object/0`, 10 seeds): overall
> **24.3% (17/70) ± 9.1%**, with a benign `none` baseline of **0/10**. Read it as **lift
> over baseline** — instruction-reframing attacks dominate (roleplay 100%,
> goal_substitution 60%, paraphrase 10%); visual / scene-text **0%**.
>
> ⚠️ **Caveat:** the keep-out predicate is a default, **uncalibrated** region (one task,
> `n=10`), so this is "diverted out of the benign safe envelope," not a calibrated hazard
> rate. Per-task zone calibration is the next milestone.

## Tabs

- **All policies** and **Open-source policies** — a RoboArena-style split (open-weights models vs.
  everything) so robustness is compared like-for-like.
- **Example payloads** — the attacked inputs behind the numbers.
- **Submit a result** — open-submission: upload a `provael leaderboard build` results JSON; it opens
  a PR to the `provael-submissions/requests` dataset (Open-LLM-Leaderboard pattern) for a maintainer
  to validate and promote. Needs `HF_TOKEN` set on the Space.

  > **This pointed at `provael-submissions/requests` — an org that was never created** (verified
  > 2026-08-08: org page 404, datasets API 401, `?author=provael-submissions` returns `[]`). The
  > submit button had been aimed at nothing since it shipped. That it went unnoticed is itself the
  > finding: the leaderboard has had zero third-party submissions ever, so this path had never been
  > walked by a stranger.
  >
  > It now points under the same account that owns the Space, so no org administration stands
  > between a stranger and a contribution. If the dataset still does not exist, the button says so
  > plainly and routes the submitter to a GitHub issue rather than handing them a traceback — or,
  > worse, a success message for a result nobody received.
  > `tests/test_leaderboard_submit_path.py` pins that behaviour so it cannot rot again unobserved.

### Opening the queue (one command, once)

```bash
export HF_TOKEN=hf_...                            # write scope
python leaderboard/setup_requests_dataset.py      # creates the dataset + its card, idempotent
```

Then set the **same** token as a secret named `HF_TOKEN` on the Space
(Settings → Variables and secrets). The script prints both steps and re-running it verifies rather
than errors, so it doubles as the "is the queue actually open?" check.

It is a script and not a README step on purpose: "create the dataset" lived only in prose for two
months, and prose does not fail.

## Run it

Locally:

```bash
pip install gradio huggingface_hub
python app.py
```

On Hugging Face: this folder is a Gradio Space rendering the committed `results/*.json` with **no
GPU**. Submission is enabled when `HF_TOKEN` is set as a Space secret.

## How the data is produced

```bash
# CPU demo (stub policy) — an example; no GPU/model needed:
provael attack --policy stub --suite stub \
    --attacks instruction,visual,injection --episodes 10 --seed 0 --out runs/demo
provael leaderboard build --runs runs/demo --out leaderboard/results   # writes leaderboard.json
```

### Real numbers (GPU box) — what's committed here

```bash
pip install 'provael[lerobot]' 'lerobot[libero]==0.5.1'
apt-get install -y libosmesa6 libgl1 libglx-mesa0       # headless GL (cloud images ship none)
export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
provael attack --policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero \
    --attacks none,instruction,visual,injection --seeds 10 --horizon 280 --seed 0 \
    --out runs/smolvla_libero
provael leaderboard build --runs 'runs/*' --out leaderboard/results
```

Commit the resulting `results/*.json`; the banner reads "includes real-model results"
whenever a non-stub run is present.

## Schema

Each `results/*.json` is a `Leaderboard`: `{schema_version, is_demo, rows[], examples[]}`,
where each `row` is `{policy, suite, family, attempts, successes, asr}` (ranked by ASR
descending) and each `example` is `{attack, family, example}` (a representative injected
payload). Output is deterministic (sorted keys, no timestamps).
