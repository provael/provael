# Machinery Regulation Annex I Part A — conformity-assessment evidence dossier

`provael certify` produces the adversarial-robustness **evidence dossier** a notified body reviews
for an **ML-based safety component** under the EU Machinery Regulation. It extends the
[`provael attest`](../ATTESTATION.md) bundle and the [Machinery Annex III pack](machinery-reg-2027.md)
into the assessor-facing artifact a buyer hands over — as machine-readable **OSCAL** and a single
self-contained, print-to-PDF **HTML** page a safety engineer can read without ever having used
Provael.

> ## What this is NOT — read this first
>
> This dossier is **evidence *input* to a conformity assessment. It is NOT a conformity assessment,
> and it is NOT a certificate.** It confers **no** presumption of conformity. **Provael is not a
> notified body**, is not accredited, and issues no certification of any kind. The operator **must
> not represent this document as certification**, as a declaration of conformity, or as evidence
> that a conformity assessment has been carried out. It is one technical input a manufacturer or its
> notified body may choose to consider. **Not legal advice** — confirm every instrument, article,
> and date against the primary text.

## Why this matters, and when

An ML model that chooses a robot's actions is, under the new EU regime, a **safety-related component
of machinery**. Regulation (EU) 2023/1230 (the Machinery Regulation) **applies from 20 January
2027** (EUR-Lex **CELEX 32023R1230**, **Article 54** — entry into force and application). Machinery
and safety components with fully or partially **self-evolving behaviour** using machine-learning
approaches that ensure safety functions are listed in **Annex I Part A**, and Annex I Part A
categories are subject to the **third-party conformity-assessment procedure of Article 25(2)** (via
**Article 6(1)**) — i.e. a notified body is involved, rather than manufacturer self-assessment.

**Which point you are filing under.** Annex I Part A names the machine-learning safety cases at two
adjacent points, verified verbatim against CELEX 32023R1230 on 2026-08-01:

| Point | Verbatim scope | Who this is |
| --- | --- | --- |
| **Part A, point 5** | "Safety components with fully or partially self-evolving behaviour using machine learning approaches ensuring safety functions" | You place the **ML safety component itself** on the market — a policy, a perception-driven safety function, sold as a component. |
| **Part A, point 6** | Machinery having **embedded systems** with fully or partially self-evolving behaviour using machine learning approaches ensuring safety functions | You place the **whole machine** on the market with the ML safety system inside it — a humanoid, an AMR, a cell. This is the integrator's row. |

Both route to the same Article 25(2) third-party procedure via Article 6(1), and `provael certify`
emits both rows so the operator makes the determination rather than inheriting ours.

> **Part B point 19 is not a substitute for either.** It is the **Article 25(3)** sibling, a
> different procedure. Citing it in place of a Part A point routes the file down the wrong
> conformity path, which is the kind of error that surfaces late and expensively. The requirement
> catalogue says so in terms, and `tests/test_compliance.py` pins both point numbers by literal.

The dossier is a dated, digest-bound record of how a policy behaved under red-team, assembled the
way that assessment consumes it.

## What the dossier contains

Each item is separately addressable in `dossier.json` (and rendered in `dossier.html`):

1. **Component identification, intended use & operating envelope** — run-derived fields (policy,
   suite, tool version, device/precision, seeds) plus an operator-supplied overlay (manufacturer,
   model, serial/UDI, safety-component version, intended use, reasonably foreseeable misuse, and the
   operating envelope). Fields the operator has not completed render as `[operator to complete]` —
   the dossier never invents them.
2. **Adversarial evidence** — per attack **family**: the ASR with its **n**, the fixed-n **Wilson
   95%** interval *and* the anytime-valid **Robbins Beta-mixture** confidence sequence, the matched
   benign FPR, **Succ-But-Unsafe**, and **Benjamini-Hochberg FDR** across families. Every number
   carries its n, and a run with fewer than 5 distinct seeds is flagged **preliminary**.
3. **Transfer statement** — for each family, whether it was **demonstrated on a real policy** and, if
   not, the words **"not demonstrated on a real policy" in the same sentence as its ASR**. This
   honesty discipline is non-negotiable: it is what makes the document credible to an assessor.
4. **Residual-risk statement** — what was **not** tested, stated plainly: attack classes deferred per
   [SAFETY.md](https://github.com/provael/provael/blob/main/SAFETY.md), families and suites not run
   this run, and embodiments not covered.
5. **Standards crosswalk** — each evidence item mapped to its clause: Machinery Regulation **Annex I
   Part A points 5 and 6** (Article 6(1) → Article 25(2)) and **Annex III** essential health & safety
   requirements; **ISO 10218-1/-2:2025** cyber (which defers detailed cyber requirements to
   **IEC 62443**); the functional-safety standards an accredited AI-safety inspection programme
   assesses robot software against — **IEC 61508**, **ISO 13849-1/-2**, **ISO/IEC TR 5469:2024** (see
   the [Halos / ANAB integrator card](../crosswalk/halos-integrator.md)); the in-development
   **ISO 25785-1** for dynamically stable robots, carried as an anticipatory row because the
   standard is an unpublished Working Draft; and the **NIST AI 100-2e2025** adversarial-ML taxonomy.

   Article and annex numbers are cited from CELEX 32023R1230, verified against the primary text. A
   clause that cannot be verified is **not shipped as a placeholder**: `tests/test_compliance.py`
   fails the build if any requirement's clause defers itself to a later verification, because a
   compliance document that tells an assessor its own citation is unverified is worse than one that
   omits the row. Rows whose *sub-clause* precision depends on the full standard text stay marked
   *(indicative)* — that is a different and honest state.

   **Provael determines no SIL and no Performance Level.** The IEC 61508 and ISO 13849 rows are
   inputs to a systematic-capability or validation argument. A PL comes from architecture, MTTFd,
   diagnostic coverage and CCF; an attack-success rate is none of those and must never be presented
   as one.
6. **Referenced artifacts** — the CycloneDX **ML-BOM** and the PEP 740 **attestation** are
   *referenced* by filename and bound by the run's SHA-256 digest, not duplicated.

The command **reuses** every statistic from `provael.scoring.asr` and `provael.calibration` — no
scoring is reimplemented — and re-runs nothing: it consumes a `report.json`, exactly like the
compliance export and `attest`.

## Reproduce

```bash
# From a stub run (CPU, deterministic) — writes dossier.json + dossier.oscal.json + dossier.html
uv run provael certify --profile annex-i-part-a --out runs/dossier

# From a prior run directory, with an operator component overlay
uv run provael certify --in runs/calib --profile annex-i-part-a \
  --component-metadata component.json --out runs/dossier

# The Annex III EHSR pack shares the same code path
uv run provael certify --profile annex-iii --out runs/dossier-annex-iii
```

`component.json` is an operator-supplied `ComponentProfile` (all fields optional):

```json
{
  "manufacturer": "Acme Robotics GmbH",
  "machine_model": "AR-7 collaborative arm",
  "safety_component": "vla-policy-guard",
  "safety_component_version": "2026.07",
  "serial_or_udi": "…",
  "intended_use": "Bin picking within a fenced cell; operator-attended.",
  "foreseeable_misuse": "Operation with the fence interlock bypassed.",
  "operating_envelope": {
    "max_speed": "1.5 m/s (TCP)",
    "payload": "7 kg",
    "workspace": "1.3 m reach",
    "keepout_zones": "Operator approach corridor, 0.5 m"
  }
}
```

The **HTML is the product**: open `runs/dossier/dossier.html` in any browser and print / save as PDF.
It is self-contained (no network, no external assets) and styled for print.

## Honest scope

- Provael measures **redirection / activation in simulation** — a robustness signal, not physical
  harm and not a real-world exploit.
- **Cross-model transfer is only claimed where a real policy was run.** On the deterministic CPU
  stub, every family is `stub-validated-scaffolding` and is labelled *not demonstrated on a real
  policy*; the real SmolVLA × LIBERO path is GPU-gated.
- The dossier is **evidence, not certification**, and Provael is an independent project — not
  affiliated with ISO, the EU, NIST, IEC, OWASP, or MITRE. The "Embodied AI Security Top 10" is an
  independent community list, not an OWASP project.

## The protective measure, not only the hazard

A dossier that states a hazard and a residual risk answers half the question. Annex III's
"protection against corruption" and ISO 10218-2:2025's requirement for a **precise description of
safety-relevant functions AND their validation** are both about the *measure*: what was installed,
where it acts, and what measuring it actually showed.

`provael certify --mitigation <report.mitigation.json>` emits a `risk_reduction_measures` section
carrying the measure's name, kind and **position** (input-side filter vs action-side monitor — different
protective measures with different failure modes), the per-family pre/post ASR with both 95% Wilson
intervals, the benign controls, the acceptance gate, the verdict **verbatim**, and both arm digests so
an assessor can re-derive the comparison rather than trust the document.

Four things it will not do:

* It never summarises `not-credited`, `insufficient` or `rejected-benign-cost` as "mitigated". A
  four-valued verdict exists because "did it work?" has four honest answers.
* A `stub-validated-scaffolding` measure carries a sentence saying it was validated on a CPU fixture
  and is **not** evidence of protection on a real policy.
* It carries the **coverage map**: which EAI risks the measure does not address. A measure credited on
  EAI04 must not read as covering EAI08.
* Without `--mitigation` the section is still present and says no protective measure was measured. An
  absent section reads as covered.

None of this is a conformity assessment, and Provael is not a notified body.
