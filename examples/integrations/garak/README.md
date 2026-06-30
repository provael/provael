# garak integration (reference)

[garak](https://github.com/NVIDIA/garak) is the de-facto LLM vulnerability scanner — a plugin
model of **probes** (attacks), **detectors** (scorers), and **generators** (targets). It covers
LLM/agent *text I/O* and has nothing for a robot action policy. [`provael_garak.py`](provael_garak.py)
is a reference probe that brings Provael's *action-space* scan into a garak run.

```bash
pip install garak provael
garak --model_type test.Blank --probes provael_garak.ProvaelEmbodiedProbe
# or just run the bridge directly:
python provael_garak.py
```

**Status: reference integration.** The Provael measurement (`run(...)` → per-EAI ASR) is the same
code Provael unit-tests, but the garak base-class glue is written against garak's documented plugin
shape and is **not** validated against an installed garak in this repo's CI. Confirm the hooks
against your garak version. The file is importable with or without garak installed.

**Upstream:** a "garak plugin pack for embodied/VLA policies" is a natural upstream contribution
(garak actively adds probe families). That PR is **not** opened from this repo — it's drafted here
for review first.
