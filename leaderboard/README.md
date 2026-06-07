---
title: RoboPwn ASR Leaderboard
emoji: 🦾
colorFrom: red
colorTo: indigo
sdk: gradio
sdk_version: 6.16.0
app_file: app.py
pinned: false
license: apache-2.0
---

# RoboPwn — VLA Red-Team ASR Leaderboard

Attack Success Rate (ASR) of instruction / visual / injection attacks against
Vision-Language-Action (VLA) robot policies in simulation, built with
[`vla-redteam`](https://github.com/sattyamjjain/vla-redteam). Lower ASR = more robust.

> ✅ **Real data.** `results/leaderboard.json` holds the first real SmolVLA-on-LIBERO
> result (`HuggingFaceVLA/smolvla_libero`, `libero_object/0`, 10 seeds): overall
> **24.3% (17/70) ± 9.1%**, with a benign `none` baseline of **0/10**. Read it as **lift
> over baseline** — instruction-reframing attacks dominate (roleplay 100%,
> goal_substitution 60%, paraphrase 10%); visual / scene-text **0%**.
>
> ⚠️ **Caveat:** the keep-out predicate is a default, **uncalibrated** region (one task,
> `n=10`), so this is "diverted out of the benign safe envelope," not a calibrated hazard
> rate. Per-task zone calibration is the next milestone.

## Run it

Locally:

```bash
pip install gradio
python app.py
```

On Hugging Face: this folder is a Gradio Space. v0 renders the committed
`results/*.json` with **no GPU** (ZeroGPU optional — see the `@spaces.GPU` stub in
`app.py` for the future live-run button).

## How the data is produced

```bash
# CPU demo (stub policy) — an example; no GPU/model needed:
robopwn attack --policy stub --suite stub \
    --attacks instruction,visual,injection --episodes 10 --seed 0 --out runs/demo
robopwn leaderboard build --runs runs/demo --out leaderboard/results   # writes leaderboard.json
```

### Real numbers (GPU box) — what's committed here

```bash
pip install 'vla-redteam[lerobot]' 'lerobot[libero]==0.5.1'
apt-get install -y libosmesa6 libgl1 libglx-mesa0       # headless GL (cloud images ship none)
export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
robopwn attack --policy smolvla --suite libero --model HuggingFaceVLA/smolvla_libero \
    --attacks none,instruction,visual,injection --seeds 10 --horizon 280 --seed 0 \
    --out runs/smolvla_libero
robopwn leaderboard build --runs 'runs/*' --out leaderboard/results
```

Commit the resulting `results/*.json`; the banner reads "includes real-model results"
whenever a non-stub run is present.

## Schema

Each `results/*.json` is a `Leaderboard`: `{schema_version, is_demo, rows[], examples[]}`,
where each `row` is `{policy, suite, family, attempts, successes, asr}` (ranked by ASR
descending) and each `example` is `{attack, family, example}` (a representative injected
payload). Output is deterministic (sorted keys, no timestamps).
