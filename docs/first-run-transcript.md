# First run, timed, on a clean machine

**Result: 20 seconds.** Install to a written `report.json`, on a container with no CUDA, no conda,
no pip cache and no repo checkout. Nothing needed a decision, a lookup, a version guess or a fix.

That is not the result this page was created to report. It was created on the assumption that a
slow, fiddly first run explained the project's zero forks and zero third-party reproductions, and
that timing it would produce a list of things to fix. The timing does not support that. **The
finding is that runnability is not this project's constraint, and the real wall is one page of
documentation further in and costs about $12.** Both halves are recorded below.

## Method

A container with no CUDA, no conda, no prior pip cache and no repo checkout. Follow `README.md`
from the top. Wall clock starts at the first command and stops when a `report.json` exists on disk.
Every step that needed a decision, a lookup, a version guess or a fix is recorded, including the
ones that were our fault.

- **Image:** `python:3.12-slim` (Python 3.12.14, pip 25.0.1)
- **Host:** Docker Desktop 29.4.3 on macOS, `linux/aarch64`, 10 CPUs available to the container
- **Isolation:** `docker run --rm`, so each run starts from an empty pip cache and no checkout
- **Date:** 19 August 2026, against `provael` 0.35.0 from PyPI
- **Commands:** exactly the two in the README's opening block, unmodified

Run twice. The wall clock is dominated by package download, so a single number would overstate its
own precision.

| # | Step | Command | Run 1 | Run 2 | Needed a decision? |
|---|---|---|---|---|---|
| 1 | Install from PyPI | `pip install provael` | 48.5 s | 19.6 s | No |
| 2 | First adversarial run | `provael attack --policy stub --suite stub --attacks instruction,visual,injection --episodes 10 --seed 0` | 0.33 s | 0.28 s | No |
| | **Total to a first ASR number** | | **48.8 s** | **19.9 s** | |

**Time to a first ASR number: 20 seconds, or 49 on a cold cache.** The spread is entirely pip
fetching 15 wheels; the measured step is a third of a second either way.

Both runs printed `Adversarial ASR: 67.1% (47/70)` — the exact figure the README advertises one
line above the command — and both wrote `runs/stub/report.json`. Exit codes were 0 and 0. The core
has no GPU, no network and no model download in its path, which is why the number is what it is.

## Why this document exists

A census of all 31 LLM-safety benchmarks published between 30 November 2022 and 1 November 2024,
against 382 non-benchmark papers as a control group and over 220 person-hours of hands-on
runnability testing, found that **only 39% of benchmark repositories run without modification**.
Comparing citation density against papers with no accessible code, code that runs with no
additional modification showed a significant advantage (p = 0.005), while **code requiring any
modification showed no significant difference from having no code at all**. Code-quality standards
— Pylint score, maintainability index — showed no significant correlation with adoption
([arXiv:2603.04459](https://arxiv.org/abs/2603.04459), Chu, Shen, Leng, Backes, Shen, Zhang).

The same paper surveyed 42 researchers with LLM-safety experience: 32 were willing to spend under
two hours on usability checking, and no respondent accepted more than six. The authors state
plainly that this survey *"serves as a corroborative check rather than a primary source of
evidence"*, and it is repeated here under that caveat rather than as a measurement.

**Two limits on borrowing any of this.** The census covers prompt injection, jailbreak and
hallucination — text-only LLM safety, containing zero embodied or VLA benchmarks — so applying it
here is an extrapolation of ours, not a claim of theirs. And it measures *citation density*, not
forks or reproductions, which are the numbers this project is short of.

## What the number does and does not explain

At the time of writing this project has **4,667 PyPI downloads** (pypistats, 180-day window, mirrors
excluded), **5 stars**, **0 forks** and **0 third-party reproductions**.

A 20-second install that reproduces the advertised figure on the first try puts this project in the
39% that run without modification. Whatever explains 0 forks, it is not the thing this page was
written to find. The honest conclusion is that **the first run was never the barrier, so improving
it further would buy nothing** — and that a project can be trivially installable and still
unreproduced, which is a case the census's framework does not distinguish.

The barrier is one step later, and it is not a documentation defect:

> Reproducing the **headline SmolVLA result** — the 44/50 figure the README leads with — takes ten
> containers, roughly 2 hours wall clock, **15.4 GPU-hours, and about $12 on an L4**. That is
> stated, with the exact command, in
> [`results/smolvla_libero_object_suite/README.md`](https://github.com/provael/provael/blob/main/results/smolvla_libero_object_suite/README.md).

Twenty seconds gets a stranger a fixture result. The claim worth reproducing costs them a GPU
budget and a Modal account. No amount of README polish moves that line, and pretending the gap is
about onboarding would be the comfortable answer rather than the true one.

## The three friction points found, and what was done about them

**1. The Python floor is stated eleven lines after the install command. Fixed.**
`pip install provael` appeared at README line 43; the `Python 3.12+` badge at line 54. On Python
3.11 — still a very common default — `pip install provael` emits 38 consecutive
`Requires-Python >=3.12` lines followed by `No matching distribution found for provael`, which
reads like a broken package rather than a version floor. Verified by running it. The README now
states the requirement at the install command.

**2. The README says `libero_object`; the CLI suite is `libero`. Named, not changed.**
README prose names the measured thing `libero_object` six times, and `--suite libero_object` is not
valid. The failure is well handled — the CLI answers
`unknown suite 'libero_object'; available: ['humanoid', 'libero', 'metaworld', 'reach', 'stub']`,
which is a good error — and the correct command is documented in `docs/quickstart.md`,
`leaderboard/README.md`, `CONTRIBUTING-leaderboard.md` and the results README. Renaming a CLI
surface or a results directory to close a prose mismatch is a bigger change than this exercise
justifies, so it is recorded rather than fixed.

**3. The real wall is a GPU bill, not a papercut. Not fixable here.**
See the block above. It is already documented with its exact cost, which is the most that
documentation can do about it.

## Honest scope of this measurement

- One path was timed: the README's opening two commands, the CPU-only core against the `stub`
  policy and `stub` suite. The `[lerobot]` extra, the `uv sync` developer path, the Docker image
  and the Colab notebook were **not** timed.
- `linux/aarch64` under Docker Desktop on macOS. An `x86_64` CI runner or a cold Docker image pull
  would differ; the image pull is excluded from the clock, matching the stated method.
- Two runs is enough to show the download dominates and not enough to characterise a distribution.
- `stub` is a fixture, not a model. This measures time-to-first-number, which is what the census
  measures. It is not evidence about any policy.
