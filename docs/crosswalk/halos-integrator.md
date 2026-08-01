# Halos / ANAB integrator card

> **Independent project. Not affiliated with or endorsed by NVIDIA, ANAB, ISO, IEC, or any of the
> certification bodies named below. Not legal advice.** Provael produces adversarial-robustness
> **evidence**. It is not an inspection, not an accreditation, and not a functional-safety
> determination. See [COMPLIANCE.md](../COMPLIANCE.md) for the full crosswalk and
> [the per-persona cards](README.md) for the other robot categories.

## Why this card exists

On **2026-06-22** NVIDIA announced Halos for robotics. The release describes an inspection
programme, and it names the standards that programme assesses robot software against — which tells
an integrator, in public and in advance, what its file will be read against.

Quoted verbatim from the announcement:

> "the world's first ANSI National Accreditation Board (ANAB)-accredited program for functional and
> AI safety for physical AI"

recognised by

> "TÜV Rheinland, UL Solutions, TÜV SÜD, exida, SGS and CertX"

with Agility Robotics' Digit assessed against

> "rigorous standards such as IEC 61508, ISO 13849 and ISO/IEC TR…"

Source:
<https://nvidianews.nvidia.com/news/nvidia-announces-halos-for-robotics-the-industrys-first-full-stack-safety-system-for-physical-ai>

Two notes on that quotation, because both matter:

- **The "first" claims are NVIDIA's, quoted as theirs.** Provael makes no priority claim of its own
  here or anywhere — not about this programme, not about its own taxonomy, not about its tooling.
- **The third standard is truncated in the quoted fragment.** It is reproduced with its ellipsis
  rather than completed, because guessing the number would be exactly the unresolvable citation
  this repo's own [citation guard](https://github.com/provael/provael/blob/main/tests/test_citations_resolvable.py)
  exists to prevent. Provael separately carries an **ISO/IEC TR 5469:2024** row on its own merits;
  that is not an assertion about what the fragment says.

## The obligation → instrument → artifact map

| Obligation | Instrument · date | Provael artifact |
| --- | --- | --- |
| Systematic-capability argument for the ML element in a safety-related function | **IEC 61508** (E/E/PE functional safety) | `report.json#/by_attack` — EAI04 action-channel ASR with 95% Wilson CI and benign-FPR control; `report.mitigation.json` where a defence was applied; `attestation.json` binding both to the run digest |
| Validation of the safety-related parts of the control system | **ISO 13849-1/-2** | The same EAI04 evidence, filed as fault cases the Part 2 validation plan can cite: `dossier.json#/adversarial_evidence/per_family` |
| V&V evidence for an AI element used in or alongside a safety function | **ISO/IEC TR 5469:2024** | ASR + benign-FPR control as one input to the AI-safety lifecycle |
| Third-party conformity assessment of the machine you actually ship | **EU Machinery Regulation 2023/1230, Annex I Part A point 6** · applies **2027-01-20** | `provael certify` dossier (OSCAL + print HTML). Point 6 is the embedded-system row — see [the Annex I Part A dossier](../compliance/machinery-annex-i-part-a.md) |
| Cyber-risk assessment for the robot | **ISO 10218-1/-2:2025** (cyber clauses, deferring detail to **IEC 62443**) | Per-EAI measured rate as risk-assessment input; `report.sarif` for the security file |
| Balance / fall hazards specific to a legged machine | **ISO 25785-1** — ISO/TC 299 WG 12, **Working Draft, not published** | The humanoid family (`balance_spoof`, `whole_body_hijack`, `stride_freeze`) on the whole-body suite. **Anticipatory, not a conformity claim**, and **stub-validated with no real-model transfer claimed** |

## What Provael does not do here

This is the part an assessor will check first, so it is stated before the evidence rather than after:

- **No SIL.** Provael does not determine, estimate, or imply a Safety Integrity Level.
- **No Performance Level.** No PL, no PLr, no MTTFd, no diagnostic coverage, no CCF. A PL is
  determined from architecture and those quantities by the designer and confirmed by validation. An
  attack-success rate is not one of those inputs and cannot be converted into one.
- **No functional-safety claim of any kind**, and no inspection, accreditation, or notified-body
  opinion. Provael is not part of the Halos programme and holds no accreditation from ANAB or from
  any body named above.
- **Adversarial security only.** Functional and mechanical safety are out of scope by design — see
  the [honest-scope box](../COMPLIANCE.md#honest-scope--what-this-does-not-cover).

What Provael *does* is narrower and checkable: it measures how often a perturbation drove a policy
out of its benign envelope, reports that rate with a 95% Wilson confidence interval against a
matched benign false-positive control, and labels honestly whether the result transferred on a real
policy or is stub-validated scaffolding. That is an **input** to the arguments above. The arguments
remain the assessor's to make.

## The honest state of the evidence today

Only the **instruction** family has a measured real-policy transfer (SmolVLA × LIBERO, one task,
n=10 — see [the finding](../findings/2026-instruction-transfer.md)). The **EAI04 action-channel**
evidence this card maps to IEC 61508 and ISO 13849 is **stub-validated**: the
[EAI04 action-space transfer study](../studies/eai04-action-space-transfer.md) records it as
*not-applicable* on the real policies tested, because the out-of-band directive channel it uses is
honoured by the deterministic stub and not by a real VLA, which reads images and instructions only.

That is a published null, and it is stated here rather than in a footnote: an integrator filing
against IEC 61508 today is filing fixture evidence with a transfer statement attached, not a
real-policy result. Closing it needs an adversarial image via `optimized_patch` on a GPU run —
scoped, unrun, and not claimed until it is.

---

*Independent · not legal advice · evidence, not certification.*
