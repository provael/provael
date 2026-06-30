---
title: Provael Demo
emoji: 🦾
colorFrom: indigo
colorTo: red
sdk: gradio
app_file: app.py
pinned: false
license: apache-2.0
---

# Provael interactive demo

A zero-install Gradio Space: pick a recipe, run a CPU red-team scan, see the ASR table + the
one-page scorecard. Numbers come from the deterministic **stub** (fixture properties, not a real
VLA). The conference-demo / drive-by surface that complements the
[leaderboard](../../leaderboard/).

```bash
pip install gradio provael
python app.py
```

Deploying as a Hugging Face Space is an external action (gated) — this folder is Space-ready
(front-matter + `app.py`); push it to a Space when ready.
