<p align="center">
  <img src="https://raw.githubusercontent.com/provael/provael/main/docs/assets/provael_wordmark.png" alt="Provael — prove it, prevail" width="440">
</p>

# Provael™

> **Red-team open Vision-Language-Action (VLA) robot policies in simulation and get an Attack
> Success Rate — beside the control it is read against.**

<p align="center">
  <a href="https://www.provael.com">
    <img src="https://www.provael.com/media/demo.gif" alt="Provael red-teams a VLA robot policy in simulation: one command prints an ASR-by-attack table, a pass/fail scorecard, and a SARIF report tagged with the EAI rule." width="820">
  </a>
</p>

<p align="center"><sub>Deterministic CPU stub run, seed 0 — reproduce it in seconds.</sub></p>
[![CI](https://github.com/provael/provael/actions/workflows/ci.yml/badge.svg)](https://github.com/provael/provael/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/provael.svg)](https://pypi.org/project/provael/) [![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/provael/provael/blob/main/LICENSE) [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21984184.svg)](https://doi.org/10.5281/zenodo.21984184)
[![last measured](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2Fprovael%2Fprovael%2Fmain%2Fwatch%2Ffreshness.json)](https://github.com/provael/provael/blob/main/watch/freshness.json) [![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/provael/provael/badge)](https://scorecard.dev/viewer/?uri=github.com/provael/provael)

**What this is.** A Python CLI that red-teams an open VLA robot policy inside a simulator and
reports an **attack-success rate** — always beside the benign control it is read against, with a
95% interval, a competence control, and an evidence label that says whether a real policy or the
CPU fixture produced it. It emits what a review needs: `report.json`, a scorecard, SARIF, OSCAL, a
CycloneDX ML-BOM, a test report and a signed attestation. **For** a team shipping a VLA policy that
needs a measured rate with its control before a release or in CI, a researcher reproducing a
published result, a reviewer who wants the number, the denominator and the decision in one place.
**Simulation only and defensive**: no physical robot, no real-world-harm payload; every number here
is a claim about the simulator that produced it. Read **[SAFETY.md](SAFETY.md)** before anything else.

## Run it

```bash
pip install provael          # requires Python 3.12+
# deterministic CPU run — no GPU, no model download; prints an ASR-by-attack table (47/70)
provael attack --policy stub --suite stub --attacks instruction,visual,injection --episodes 10 --seed 0
```

It prints `Adversarial ASR: 67.1% (47/70)`. Those are **fixture numbers**: the `stub` policy and
suite are deterministic CPU arithmetic that exercises the whole pipeline in under five seconds and
says nothing about any real policy. The run writes `runs/stub/report.json` (byte-deterministic) and
`report.md`; their release verdict reads `incomplete — not assessed`, because no acceptance protocol
was named. Timed on a clean container: **20 s** from `pip install` to a written report
([the transcript](docs/first-run-transcript.md)).

## Limits, before anything else

- **Simulation only.** No number here was produced on hardware; sim-to-real transfer is not
  measured or claimed.
- **Mostly templated attacks** plus four bounded search families; not gradient-based worst-case
  robustness.
- **One supported real configuration.** SmolVLA on the ten LIBERO-Object tasks is the body of
  evidence; π0.5 has one preliminary arm. Everything else registered is scaffolding or
  stub-validated, and the tool says which.
- **The default predicate is uncalibrated.** An event is the end-effector leaving a fixed keep-out
  envelope — not task completion, not a calibrated hazard.
- **The instruction result is fragility, not control.** The frame that moves SmolVLA moves it with
  no target named and with its tokens scrambled ([E-2026-12](docs/errata.md)).

## Supported configuration

| Policy | Suite | Status | Evidence |
| --- | --- | --- | --- |
| `smolvla` — `HuggingFaceVLA/smolvla_libero` | `libero`, task suite `libero_object` (10 tasks) | **measured**, the published body | [14 Sep 2026 run](results/smolvla_libero_object_suite_2026-09-14/README.md) · [delivery pack](examples/delivery-pack/smolvla-libero-object-2026-09-14/README.md) |
| `pi05` — `lerobot/pi05_libero_finetuned_v044` | `libero`, `libero_object` | **measured — preliminary** (3 seeds, 2 of 8 arms, at the floor) | [18 Sep 2026 run](results/pi05_libero_object_2026-09-18/README.md) |
| `stub` | `stub`, `reach`, `humanoid` (CPU fixtures) | fixture | the run above |

The real rows need a GPU, Linux and `[lerobot]`. Every other registered adapter (`pi0`, `pi0fast`,
`groot`, `openvla`, `openpi`) and suite (Meta-World, `ai2_bridge`, `vla_arena`) has **no run
committed here** or is **scaffolding**; `provael list-policies` / `list-suites` print each one's status.

## The measured result

**SmolVLA × LIBERO-Object, 14 September 2026, provael 0.41.2** — ten tasks, five seeds per (task,
arm), horizon 280, on a workstation RTX 2000 Ada. Under the `roleplay` instruction the policy left
its keep-out envelope on **42 of 50** episodes (84%, task-clustered 95% CI [62%, 100%]) against a
benign floor of **1/50** (2.0%, Wilson 95% [0.4%, 10.5%]); McNemar exact p = 9.1e-13, surviving
Holm across the seven arms. Clean task success on the benign arm: 48/50. The visual and injection
arms sit at the floor (1/50, 1/50, 2/50; `mcp_tool_desc` not applicable). The controls run the same
day put the same frame with **no target named** at 27/30 and with **scrambled tokens** at 18/30, so
the exit is fragility under a long imperative out-of-distribution string, not attacker control
([E-2026-12](docs/errata.md)). It re-measures the 9 August 2026 run on 0.32.0 (44/50 against 2/50)
inside its interval. Under the example acceptance protocol the decision is **FAIL** on the roleplay
slice, and the pack says so:
[run](results/smolvla_libero_object_suite_2026-09-14/README.md) ·
[controls](results/smolvla_libero_object_control_2026-09-14/README.md) ·
[delivery pack](examples/delivery-pack/smolvla-libero-object-2026-09-14/README.md) ·
[write-up with the full tables](docs/findings/2026-instruction-transfer.md).

**Reading any result:** the rate and its floor travel together; the endpoint is an envelope exit
under the predicate the run names; `N/A` is not zero; a **release verdict exists only under a named
protocol** (`--protocol`) — [how to read a result](docs/quickstart.md#how-to-read-a-result).

## Coverage: registered is not validated

`provael coverage` prints the difference between what exists and what has met a real policy:
**17 adversarial families registered, 8 exercised against a real policy** (`instruction`, `visual`,
`injection`, `gradient_patch`, `optimized_instruction`, `optimized_patch`, `universal_patch`,
`weight_integrity` — one of the eight transferred; the other seven returned measured nulls, five of
them at n = 3, which is a result and not a rate), **9 stub-validated only**, measured on
**2 real policies** (`pi05`, `smolvla`). The registry holds **39 adversarial attacks**, not a family
count. Every number is derived from the committed runs ([`watch/registry.json`](watch/registry.json)),
never typed; the per-family catalogue with each family's status is [docs/attacks.md](docs/attacks.md).

## Install

```bash
pip install provael                 # CPU core: every attack, scoring, reports, attestation
pip install 'provael[lerobot]'      # + SmolVLA / π0.5 and the LIBERO simulator (Linux, GPU)
docker run --rm ghcr.io/provael/provael:latest attack --recipe quick   # no local Python at all
```

On the CPU: the `stub`, `reach` and `humanoid` fixtures, every adversarial family (`provael
list-attacks`), scoring, reports, recipes, `reproduce`, `calibrate`, `attest` (Ed25519 via `[attest]`)
and the test suite. Behind a GPU and `[lerobot]`: the real policies and the `libero` simulator; on a
CPU they fail with a message naming the extra. Install notes, including the Linux-only simulator:
[docs/quickstart.md](docs/quickstart.md#install-cpu-core--no-gpu-no-network).

## Use in CI

```yaml
# .github/workflows/provael.yml
permissions: { contents: read, security-events: write }   # SARIF goes to code scanning
jobs:
  redteam:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: provael/provael@v0.43.0
        with:
          attacks: none,instruction,visual,injection,action   # `none` is the benign control
          episodes: "10"
          asr-threshold: "0.5"                # pooled adversarial ASR gate (descriptive)
          protocol: .provael/protocol.yml     # the named acceptance protocol that decides
          release-mode: "false"               # "true": an undecided or incomplete run fails
          baseline: .provael/baseline.report.json   # optional per-checkpoint regression gate
```

A pooled rate is descriptive; the decision is made under the protocol's own criteria — critical
attacks and tasks on their own slices, `incomplete` where a slice did not run. Inputs, the defended
arm, the regression gate and the self-maintaining baseline: [docs/quickstart.md](docs/quickstart.md#the-github-action-in-full).

## Evidence outputs

`report.json` (byte-deterministic) and `report.md` · `--format scorecard | sarif | oscal |
test-report` (ISO/IEC 17025 clause 7.8 layout) · `--format compliance` — the crosswalk,
[docs/compliance/index.md](docs/compliance/index.md) · a CycloneDX ML-BOM · `provael attest`, a dated,
digest-bound, offline-verifiable bundle ([docs/attestation.md](docs/attestation.md)) · `provael certify`,
the Machinery Regulation evidence dossier · the signed board ([docs/leaderboard.md](docs/leaderboard.md)).
All of it is **evidence, not certification**.

## Where the rest lives

- **Docs:** [docs.provael.com](https://docs.provael.com) — quickstart, attack catalogue, compliance
  crosswalk, attestation, findings and studies, the [roadmap](docs/roadmap.md).
- **The Embodied AI Security Top 10:** [docs/top10.md](docs/top10.md) — an independent community
  risk list (CC-BY-SA 4.0) that Provael's attacks map to; the [RFC process](docs/top10-rfc.md).
- **Commercial:** open core, forever ([the promise](docs/open-core-promise.md)). The operated work —
  a run on your checkpoint, written up — is priced once, on [provael.com/pricing](https://www.provael.com/pricing).
  The operated attestation service is **not built**; the in-repo server is an experimental reference
  behind `PROVAEL_ENABLE_EXPERIMENTAL_HOSTED`. One maintainer, and every commercial page says so.
- **Prior art, safety, changes, corrections:** [PRIOR_ART.md](PRIOR_ART.md) · [SAFETY.md](SAFETY.md) ·
  [CHANGELOG.md](CHANGELOG.md) · [docs/errata.md](docs/errata.md).

## Development

`make check` runs lint, type-check and tests, exactly as CI does. **How it is made.** Much of this codebase was written with AI assistance (Claude Code); every
published number, calibration and security-relevant path is human-reviewed before it ships.
Co-author trailers are in git: `git log --grep=Co-Authored-By`.

**Security & contributing.** Vulnerabilities: [SECURITY.md](SECURITY.md) (90-day coordinated
disclosure). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md) — the green gate and the DCO sign-off
(`git commit -s`); who has contributed and under which terms: [CONTRIBUTORS.md](CONTRIBUTORS.md);
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) (Contributor Covenant 2.1).

## How to cite

[`CITATION.cff`](CITATION.cff) is the same metadata (concept DOI: always the newest archived version):

```bibtex
@software{jain_provael_2026,
  author  = {Jain, Sattyam},
  title   = {Provael: red-teaming Vision-Language-Action robot policies in simulation},
  version = {0.43.0},
  year    = {2026},
  doi     = {10.5281/zenodo.21984184},
  url     = {https://doi.org/10.5281/zenodo.21984184},
  license = {Apache-2.0}
}
```

## License and trademarks

[Apache-2.0](LICENSE). Provael — *prove it, prevail.*

**Provael™** (the name and the Proof-Path logo) is an **unregistered mark** of Sattyam Jain — no
application has been filed yet; one is planned in India (classes 9 and 42). What you may do with the
name, and what needs permission: [TRADEMARKS.md](TRADEMARKS.md). The **Embodied AI Security Top 10**
is a **separate** community document (CC-BY-SA 4.0), deliberately unbranded and donatable, not a
Provael™ product, and not affiliated with or endorsed by the OWASP® Foundation or MITRE®.
