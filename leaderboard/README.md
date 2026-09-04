---
title: Provael ASR Leaderboard
emoji: 🦾
colorFrom: red
colorTo: indigo
sdk: gradio
sdk_version: 6.23.1
app_file: app.py
pinned: false
license: apache-2.0
short_description: Attack-success rates for VLA policies, with benign controls
tags:
- leaderboard
- submission:manual
- test:public
- modality:text
- eval:safety
- language:English
---

<!-- WHY THESE TAGS AND NOT MORE. The Space ran with no `tags:` at all, so Hugging Face derived only
["gradio", "region:us"] and it never appeared under the `leaderboard` filter — the one place a person
browsing for a leaderboard would look. The vocabulary here follows DontPlanToEnd/UGI-Leaderboard,
which is the richest published example; mteb/leaderboard uses `leaderboard` alone.

`modality:image` is deliberately ABSENT even though the policies under test are vision-language-action.
Provael's visual family is two symbolic markers appended to a simulated `visual_tokens` list, not
rendered pixels, and it measured 0/100 on the ten-task suite. Claiming an image modality would
advertise coverage this board does not have. See docs/top10.md, EAI02.

`submission:manual` because the path is a reviewed pull request plus a maintainer rebuild.
`test:public` because every attack, suite and recipe is open source and reproducible. -->

# Provael — VLA Red-Team ASR Leaderboard

Attack Success Rate (ASR) of instruction / visual / injection attacks against
Vision-Language-Action (VLA) robot policies in simulation, built with
[`provael`](https://github.com/provael/provael). Lower ASR = more robust.

Measure a policy you did not train, and its authors get the full artifact 14 days before anything
is published here — including the right to have it re-run, corrected, or pulled pending review.
That is written down in
[Measuring someone else's policy](https://docs.provael.com/leaderboard-disclosure/), and it binds
the maintainer of this board more tightly than it binds anyone submitting to it.

> ✅ **Real data.** `results/leaderboard.json` holds the ten-task SmolVLA-on-LIBERO suite
> screen (`HuggingFaceVLA/smolvla_libero`, all 10 `libero_object` tasks × 5 seeds, 350
> measured episodes): **instruction 41.3% (62/150) [34–49%]**, against a benign `none`
> baseline of **4.0% (2/50)**. The board's rows sum to **18.3% (64/350)** across every arm
> including the benign control — that is the all-episode observed rate, **not** the attack rate,
> and it is diluted by the arms that measured zero. Read the per-family rows, not the sum.
>
> Read it as **lift over baseline** — instruction-reframing
> attacks are the only family that moves this policy; **injection 0/50** and **visual
> 0/100** are measured nulls and stay published as such. Per-attack detail, including
> `roleplay` at 44/50 against the run's own **2/50 benign control**, with its McNemar and
> task-clustered interval, is in
> [`results/smolvla_libero_object_suite/`](https://github.com/provael/provael/tree/main/results/smolvla_libero_object_suite).
>
> ⚠️ **Four qualifiers, and they now travel inside the artifact** (`schema_version` 5)
> rather than living only in this README:
>
> - `"calibrated": false` on every row — the same default keep-out box on all ten tasks,
>   never fitted to any of them. This is "diverted out of the benign safe envelope," not a
>   calibrated hazard rate, and it is why the benign arm tripped at all. Per-task zone
>   calibration is still owed ([#136](https://github.com/provael/provael/issues/136)).
> - `"stochastic": true` — SmolVLA's flow-matching sampler is not fully seeded, so these
>   numbers are one draw, not a reproducible constant. **This caveat stays until these rows are
>   re-run**, and it is about these rows specifically: from provael 0.38.0 the runner seeds the
>   policy's own sampler and each episode records `policy_seed`, and a stochastic submission
>   without one is refused. The rows above were measured before that and carry no `policy_seed`,
>   so nothing about the fix makes them reproducible after the fact. Re-running them is GPU-gated.
> - `"not_applicable": ["mcp_tool_desc"]` — 50 episode records, zero applicable episodes.
>   Not-measured and measured-zero are different claims, so it is named rather than
>   silently dropped from the denominator.
> - `"checkpoint"` — one checkpoint, one suite. Nothing here speaks to `libero_spatial`,
>   `libero_goal`, `libero_10`, or any other policy.

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
