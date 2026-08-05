# Defenses

> Status: **TWO ROWS MEASURED, FOUR SPECIFIED AND UNPROVEN.**
>
> * `input canonicalization` — `stub-validated-scaffolding`, see
>   [the study](studies/instruction-canonicalization.md).
> * `action clamping / keep-out enforcement` — `stub-validated-scaffolding`, see
>   [the study](studies/action-envelope.md). `credited` on `stub` and `reach`, **`not-credited` on
>   `humanoid`** — a published null, not an omission.
>
> Results land in `docs/studies/` with the same controls as attacks. No defense is claimed until
> measured, and a measured defense is claimed only as far as the evidence reaches: both studies open
> by stating how much of their own credit is circular on a fixture, and the action-envelope study's
> headline is the **coverage map** — the families one protective measure provably cannot address.
>
> Until 0.28.0 the four output-side rows below were not merely unmeasured but **unimplementable**:
> the `Defense` ABC offered only a pre-processing hook, so a taxonomy row acting on the policy's
> output could not be written against the interface at all. `Defense.filter_action` fixed that; one
> of the four is now measured and three remain unwritten.

Provael measures attacks. A defense is only worth shipping if it **measurably** lowers Attack Success
Rate without breaking the benign task — so every defense here is held to the same bar as an attack: a
pre/post ASR with a 95% Wilson CI, a benign-FPR control, and a **benign-task-success acceptance
gate**. This page is the taxonomy and the spec for the first measured defense; nothing below is
claimed as effective until a study reports it.

## Mitigation taxonomy (mapped to the Top 10)

| Mitigation | What it does | Primarily addresses |
| --- | --- | --- |
| **Input canonicalization / instruction repair** | Normalise phrasing, strip manner/urgency adverbials, re-derive the canonical command before it reaches the policy | EAI01 instruction jailbreak · EAI05 indirect/embodied injection · EAI06 manner/urgency misalignment |
| **Observation filtering** | Detect / attenuate adversarial patches, decoy objects, and sensor-spoof markers in the image or observation | EAI02 adversarial perception |
| **Action clamping / keep-out enforcement** ([study](studies/action-envelope.md)) | Reject or clip a commanded action that leaves the safe envelope or enters a keep-out zone | EAI04 action-space integrity · EAI06 embodiment-gap keep-out |
| **Rate limiting / scope enforcement** | Bound the actions and authority a single instruction can exercise | EAI08 identity, access & excessive autonomy |
| **Trajectory anomaly detection** | Flag episodes whose trajectory departs from the benign distribution (freeze, hijack, objective-decoupled triggers) | EAI04 action-space integrity · EAI03 backdoor triggers |
| **Output / memory screening** | Screen for memorised-canary leakage and extraction signals | EAI09 model & data confidentiality |

Risk ids above are defined in [the Embodied AI Security Top 10](top10.md). Each mitigation is a
**claim to be tested**, not a shipped guarantee — it earns a row in a results table only after a
study measures its pre/post ASR under the controls below.

## First measured defense: instruction canonicalization / repair

The `optimized_instruction` family (`targeted_redirect`) redirects a policy through subtle
manner/urgency cues while keeping the operator's command and never naming the target object. Its
recommended mitigation is **instruction canonicalization**: collapse that edit space before the
instruction reaches the policy.

### The defense

1. **Normalise phrasing** — lowercase / whitespace / punctuation normalisation and paraphrase
   folding.
2. **Strip manner/urgency adverbials** — remove redundant "quickly / carefully / no matter what"-style
   modifiers that carry no task content but steer behaviour.
3. **Re-derive the canonical command** — reduce to the operator's intended verb + object, discarding
   the residual the search exploits.

The pipeline runs as a pre-processing wrapper on the instruction; it changes no policy weights and is
auditable (the canonical form is logged next to the raw instruction).

### Measurement protocol

- **Pre/post ASR per attack family.** Run the affected families (`optimized_instruction`, and the
  `instruction` family as a reference) with and without the canonicaliser, and report the ASR for
  each with its **95% Wilson CI**. The defense is credited only where the post-attack CI is separated
  from the pre-attack CI.
- **Benign-FPR control.** The `none` baseline runs under the same predicate; the defense must not
  raise the benign FPR.
- **Benign-task-success acceptance gate.** The clean-task success rate (competence on the real task,
  attacks off) must be **unchanged** within its CI. A defense that lowers ASR by breaking the task is
  rejected — the acceptance gate is a hard requirement, not a trade-off to be reported and ignored.
- **Where it lands.** Results are published in `docs/studies/` in the same format and under the same
  controls as an attack transfer study. **Measured:**
  [instruction-canonicalization](studies/instruction-canonicalization.md) — `credited` on the
  `stub` and `reach` CPU suites (adversarial ASR 67.5% → 7.5% and 35.0% → 0.0%), benign FPR
  unchanged at 0%, acceptance gate passed on `stub` and not evaluable on `reach`. Read the study's
  circularity section before quoting the number: four of the fixture's seven danger tokens are
  words this defense strips, so `optimized_instruction`'s 60% → 0% is close to tautological.
  `stub-validated-scaffolding`; no real-model transfer is claimed.

Two rows are now **measured** — under the controls above, on CPU fixture suites, with their limits
stated in their studies: `input canonicalization`
([study](studies/instruction-canonicalization.md)) and `action clamping / keep-out enforcement`
([study](studies/action-envelope.md)). The action-envelope study reports `credited` on `stub` and
`reach` and **`not-credited` on `humanoid`**, and its headline is that one protective measure does
not cover a hazard list: a magnitude cap cannot restore a frozen action, and it does not reach
successes that route through a decoupled flag (EAI03 backdoor activation, EAI08 authorization,
EAI09 canary leak).

The **four other** rows in the taxonomy above remain **specified, unproven** mitigations, and none of
them is registered in `provael list-defenses`: an unmeasured mitigation is not a shipped one. Three of
those four act on the policy's output and became *expressible* only with `Defense.filter_action` in
0.28.0 — they are now writable and still unwritten, which is a different and more honest status than
the one they had before.

## Published defenses this project has not matched

The bar this page sets — a measured pre/post ASR with an interval, a benign-FPR control and a
benign-task-success gate — is met by both rows above on a **CPU fixture**. Two defenses published in
the last month are measured on a real model, and one of them on real hardware. Recording that here
rather than in a footnote, because a defenses page that lists only its own results reads as a survey
of the field and is not one.

| Published defense | What it does | Measured on | Provael's comparable result |
| --- | --- | --- | --- |
| **SARF** ([arXiv:2608.03231](https://arxiv.org/abs/2608.03231)) | Structure-aware robust fine-tuning of the visual encoder only, zero inference overhead, against attention-hijacking patches | OpenVLA on LIBERO **and a real PiPER manipulator** | **None.** No Provael defense has been measured against a real model, on any hardware |
| **ChromaGuard** ([arXiv:2607.14698](https://arxiv.org/abs/2607.14698)) | Chroma-preserving adversarial training against an optimised physical spotlight attack | A physical 6-DoF robotic platform | **None.** Provael models no illumination channel at all |

SARF's reported figure is **"On LIBERO, SARF reduces OpenVLA's failure rate under AGSD from 100% to
14.2%-56.8% (28.6% average) across suites while preserving clean performance, and on a real PiPER
manipulator it improves average success under AGSD from 23.0% to 65.0%."** Provael's two measured
defenses are `stub-validated-scaffolding` with no real-model transfer claimed for either, and the
instruction-canonicalization study says in its own text that its headline number is close to
tautological on the fixture it was measured on. The comparison is not close and is not presented as
though it were. See [PRIOR_ART.md](https://github.com/provael/provael/blob/main/PRIOR_ART.md) for
the full citations and [the studies index](studies/index.md) for the gap with a date against it.

The useful thing to take from ChromaGuard is a warning rather than a benchmark: its authors report
that naive augmentation defenses "incorrectly condition VLA models to discard color as noise",
producing a defended model that scores well on a diagnostic and worse than the undefended baseline
on benign colour-dependent tasks. That failure mode — a defense that improves the attacked number
while degrading the benign capability — is exactly what the benign-task-success acceptance gate on
this page exists to catch, and their grayscale diagnostic is a sharper instrument for catching it
than the gate currently is.
