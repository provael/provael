# EAI04 action-space-integrity transfer study

> **Defensive, sim-only.** No real-robot or hardware control code, no real-world-harm payloads. The
> attacks perturb only the observation a policy receives in simulation. See
> [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md).

## Question

Do Provael's [EAI04](../TOP10.md#eai04--action-space-integrity-attacks-hijack--targeted-trajectory--freeze)
action-space-integrity attacks — the `action` family (`freeze`, `trajectory_hijack`) and the
`action_space` family (`keepout_hijack`, `critical_freeze`) — **transfer to a real VLA policy**, or
are they properties of the deterministic fixture? This study extends the
[cross-architecture transfer harness](../findings/2026-cross-arch-transfer.md) to the EAI04 vectors,
reusing the shipped runner + `provael.scoring.asr` (no ASR is reimplemented, no second harness).

## Setup

- **Vectors (family × attack):** `action`/{`freeze`, `trajectory_hijack`}, `action_space`/{`keepout_hijack`, `critical_freeze`}, plus the benign `none` control.
- **CPU reference:** the deterministic `reach` keep-out suite (the suite where **both** vectors are applicable — `action` also applies on `stub`, `action_space` needs `reach`). 10 episodes = 10 distinct seeds, seed 0. Same seed convention and n as the v0.17.0 cross-architecture study.
- **Real backends:** SmolVLA (LeRobot) and π0 (openpi) on LIBERO, gated behind `PROVAEL_INTEGRATION=1` + the `[lerobot]`/`[openpi]` extra.
- **Reported per (architecture × vector):** ASR, n, fixed-n 95% **Wilson** interval, matched **benign-FPR**, **Succ-But-Unsafe**, and **BH-FDR** across the vectors; runs under 5 seeds are flagged `preliminary`.

## Reproduce

```bash
provael study eai04                                  # CPU reference + the real-leg verdict
provael study eai04 --out results/eai04_action_space_transfer   # + writes the artifact
```

The real legs need a GPU box, but — see the finding — they are **not-applicable** through this
mechanism, so a GPU run does not produce a transfer number here.

## Results

| architecture | family | vector | ASR (95% CI) | n | benign-FPR | Succ-But-Unsafe | BH-FDR q | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CPU `reach` (fixture) | `action` | `freeze` | 100% [72–100%] | 10 | 0% | n/a | ~1e-120 (sig) | measured |
| CPU `reach` (fixture) | `action` | `trajectory_hijack` | 100% [72–100%] | 10 | 0% | n/a | ~1e-120 (sig) | measured |
| CPU `reach` (fixture) | `action_space` | `keepout_hijack` | 100% [72–100%] | 10 | 0% | n/a | ~1e-120 (sig) | measured |
| CPU `reach` (fixture) | `action_space` | `critical_freeze` | 100% [72–100%] | 10 | 0% | n/a | ~1e-120 (sig) | measured |
| SmolVLA × LIBERO | `action` / `action_space` | all four | — | — | — | — | — | **not-applicable** |
| π0 × LIBERO | `action` / `action_space` | all four | — | — | — | — | — | **not-applicable** |

- **Succ-But-Unsafe is n/a**: the deterministic `reach`/`stub` fixtures surface no task-success
  signal, so the metric is honestly `None` rather than fabricated — the real signal is GPU-gated
  (LIBERO surfaces it), but see below.

## The finding (honest, negative)

On the fixture the vectors are trivially perfect (100% vs a 0% benign control) — **but that is a
property of the deterministic keep-out fixture, not a real VLA, and it does not transfer.** Two
independent reasons, both verified:

1. **The attack mechanism does not reach a real policy.** `action`/`action_space` inject an
   *out-of-band directive channel* (`action_directives` / `action_space`) that the paired stub
   policy honours. A real VLA (SmolVLA, π0) reads images + an instruction — it never consumes that
   channel — so the perturbation has no path to its actions.
2. **No real suite surfaces the required signal.** The attacks gate on `supports_action_integrity` /
   `supports_action_space`, which are set only by the `stub` and `reach` suites — **never by
   `libero`**. On a LIBERO-shaped observation all four EAI04 attacks return `applicable=False`
   (verified in `tests/test_eai04_study.py`), so they are excluded from the ASR denominator on the
   real path — *not-applicable*, not merely *pending*.

So **`action` and `action_space` remain stub-validated**; no real-policy EAI04 transfer is claimed,
and none is obtainable through this mechanism. This mirrors the credible instruction-vs-visual result
(only instruction transferred): a clearly-published negative is worth more than a hedge.

A **real** EAI04 attack on a VLA is an adversarial *image* (action-freeze / targeted-hijack via a
crafted camera frame, cf. **FreezeVLA** arXiv:2509.19870 / **AttackVLA** arXiv:2511.12149) — Provael's
`optimized_patch` family, which plugs into the real `IMAGE_KEY` path and is itself GPU-gated and not
yet run. That, not the out-of-band-directive families here, is the path to a real EAI04 number.

## Limitations (what is NOT covered)

- **Embodiments/policies:** only SmolVLA (LeRobot) and π0 (openpi) were considered as real backends;
  both are LIBERO-suite tabletop manipulators. No mobile, humanoid, or multi-robot embodiment.
- **Suites:** the real legs assume LIBERO; **Meta-World and any non-LeRobot image suite are not
  covered**, and none of them surfaces the EAI04 action-integrity signal either.
- **Mechanism:** this study covers only the shipped out-of-band-directive EAI04 families. The
  adversarial-image path (`optimized_patch` / FreezeVLA / AttackVLA) that *could* transfer is **not**
  measured here (GPU-gated, not yet run) — so "does not transfer" is a statement about *these
  families through this mechanism*, not about EAI04 as a risk class.
- **Coverage unchanged:** EAI04 remains a shipped sim-only screen; the Top-10 coverage claim stays
  **8/10**.
