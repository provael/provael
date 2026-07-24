# Defenses

> Status: IN PROGRESS — results land in `docs/studies/` with the same controls as attacks. No
> defense is claimed until measured.

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
| **Action clamping / keep-out enforcement** | Reject or clip a commanded action that leaves the safe envelope or enters a keep-out zone | EAI04 action-space integrity · EAI06 embodiment-gap keep-out |
| **Rate limiting / scope enforcement** | Bound the actions and authority a single instruction can exercise | EAI08 identity, access & excessive autonomy |
| **Trajectory anomaly detection** | Flag episodes whose trajectory departs from the benign distribution (freeze, hijack, objective-decoupled triggers) | EAI04 action-space integrity · EAI03 backdoor triggers |
| **Output / memory screening** | Screen for memorised-canary leakage and extraction signals | EAI09 model & data confidentiality |

Risk ids above are defined in [the Embodied AI Security Top 10](TOP10.md). Each mitigation is a
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
  controls as an attack transfer study, and this page links them once they exist.

Until that study reports, instruction canonicalization is a **specified, unproven** mitigation — the
honest status for every row in the taxonomy above.
