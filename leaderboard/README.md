---
title: RoboPwn ASR Leaderboard
emoji: 🦾
colorFrom: red
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
license: apache-2.0
---

# RoboPwn — VLA Red-Team ASR Leaderboard

Attack Success Rate (ASR) of instruction / visual / injection attacks against
Vision-Language-Action (VLA) robot policies in simulation, built with
[`vla-redteam`](https://github.com/sattyamjjain/vla-redteam). Lower ASR = more robust.

> ⚠️ **The committed data is stub/demo until real runs are added.** `results/_demo.json`
> is produced from the deterministic CPU **stub** policy — it shows the harness works and
> what the table looks like, but the numbers are **not** a real model's robustness. Add
> real SmolVLA / OpenVLA results with the GPU command below; the "demo data" banner clears
> automatically once a non-stub run is present.

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
# CPU demo (stub policy) — what's committed here:
robopwn attack --policy stub --suite stub \
    --attacks instruction,visual,injection --episodes 10 --seed 0 --out runs/demo
robopwn leaderboard build --runs runs/demo --out leaderboard/results   # writes leaderboard.json
```

### Real numbers (GPU box) — replaces the demo data

```bash
pip install 'vla-redteam[lerobot]' 'lerobot[libero]==0.5.1'
ROBOPWN_INTEGRATION=1 robopwn attack --policy smolvla --suite libero \
    --attacks instruction,visual,injection --episodes 10 --seed 0 --out runs/smolvla_libero
robopwn leaderboard build --runs 'runs/*' --out leaderboard/results
```

Commit the resulting `results/*.json` and the banner switches to "includes real-model
results".

## Schema

Each `results/*.json` is a `Leaderboard`: `{schema_version, is_demo, rows[], examples[]}`,
where each `row` is `{policy, suite, family, attempts, successes, asr}` (ranked by ASR
descending) and each `example` is `{attack, family, example}` (a representative injected
payload). Output is deterministic (sorted keys, no timestamps).
