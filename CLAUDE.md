# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- AUTO-MANAGED: project-description -->
## Overview

Provael™ — a model-agnostic tool to red-team open Vision-Language-Action (VLA) robot policies in simulation and report an Attack Success Rate (ASR). Ships as a Python CLI (`provael`, Typer-based) that runs a policy × suite × attack matrix, scores outcomes deterministically, and emits evidence: `report.json`, a pass/fail scorecard, SARIF (tagged with Embodied-AI Top-10 rule ids), OSCAL, CycloneDX ML-BOM, and optionally Ed25519-signed attestations.

Design pillars:

- **CPU-first, open-core**: the default install stays light. GPU/ML stacks arrive only via optional extras — `[lerobot]` (SmolVLA × LIBERO), `[openvla]`, `[openpi]` (CPU client → GPU policy server), `[attest]` (cryptography), `[hosted]` (FastAPI reference server; the operated instance is the paid tier).
- **Determinism contract**: a run report is a pure function of (config, registered policy/suite/attacks) — no wall-clock values; the same seed produces a byte-identical report.
- **Honesty**: measured transfers and honest nulls are both reported; stub-only results never masquerade as real-model claims (every attack carries threat-model metadata).

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: build-commands -->
## Build & Development Commands

```bash
uv sync                      # install core + dev group (CPU-only; never pulls torch)
uv run provael --help        # run the CLI

# The gate — must be green before pushing (mirrors CI):
uv run ruff check .          # lint + import order
uv run mypy src              # strict type-check (pydantic plugin)
uv run pytest -q             # tests; GPU/LIBERO integration tests auto-skip

# Focused test run:
uv run pytest tests/test_attacks.py -q

# Docs site (separate dependency group, strict build):
uv run --group docs mkdocs build --strict

# Package build + metadata check (as in CI):
uv build && uvx twine check dist/*

# GPU-gated integration tests (require the [lerobot] extra installed):
PROVAEL_INTEGRATION=1 pytest tests/test_lerobot_adapter.py tests/test_libero_adapter.py -q
```

CI (`.github/workflows/ci.yml`) is CPU-only by design and never installs GPU extras; `gpu-nightly.yml` covers the real-model path. The rest of the wall: `checkpoint-security-gate.yml` (per-checkpoint regression + supply-chain integrity, emitting signed attestations), `scorecard.yml`, `leaderboard-submission.yml`, `docs.yml`, `release.yml`. Use `uv sync --locked` to reproduce CI exactly.

Optional extras: `[lerobot]`, `[openvla]`, `[openpi]`, `[attest]`, `[hosted]`. Dependency groups: `dev`, `docs`.

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: architecture -->
## Architecture

```
src/provael/
├── cli.py            Typer app — the `provael` entry point
├── runner.py         core loop: policy × suite × attacks → attack results
├── config.py         RunConfig — the deterministic input
├── types.py          Observation/State/Action aliases + pydantic result models
├── attacks/          attack families (instruction, visual, injection, backdoor,
│                     sensor_spoof, humanoid, misalignment, confidentiality,
│                     authorization, action / action_space, targeted_redirect,
│                     baseline, optimized + optimized_patch / universal_patch)
│                     + registry.py; base.py defines Attack / OptimizedAttack
├── defenses/         measured mitigations, held to the same evidential bar as attacks:
│                     canonicalize, envelope, measure + registry.py
├── policies/         adapters: lerobot (SmolVLA), openvla, openpi, groot (GR00T-N1),
│                     stub (deterministic CPU) + registry.py; base.py is the ABC
├── suites/           simulators: libero, metaworld, reach, humanoid, keepout_zones, stub
├── scoring/          per-family scorers + asr.py (ASR + Wilson CI)
├── hosted/           FastAPI reference attestation server (open-core paid tier)
├── studies/          pre-registered studies (e.g. cross-architecture transfer)
├── evidence.py       evidence-state ladder — how far a result has actually been verified
├── verdict.py        typed release verdict — deliberately not a binary pass/fail
├── endpoints.py      independent semantic endpoints — the distinct questions a run answers
├── execution.py      ExecutionManifest — runtime provenance, bound to the report by digest
├── ledger.py         append-only, resumable trial ledger
├── integrity.py      checkpoint supply-chain integrity — a pre-load control for the CI gate
├── regression.py     per-checkpoint baseline-regression diff
├── recipes.py        named RunConfig presets for the CLI
├── reproductions.py  named reproductions of published VLA attacks, mapped onto families
└── report / sarif / oscal / mlbom / attest / assurance / certify / compliance /
    crosswalk / avid / scorecard / leaderboard / calibration …  evidence emitters
```

- Attacks, defenses, policies, and suites self-register into registries; the runner resolves them by string key.
- `attacks/base.py` carries threat-model metadata per attack: `eai_id`/`eai_name` (Embodied-AI Top-10 mapping), `attacker_access`, `action_head_class` — results are self-describing.
- A result is not just a number: `evidence.py` records how far it was verified, `endpoints.py` separates the questions a run can answer, and `verdict.py` refuses to collapse them into one boolean. Preserve that separation — flattening it back into pass/fail is the failure mode these modules exist to prevent.
- `tests/` mirrors modules 1:1 (`test_<module>.py`) with golden/drift-guard tests pinning the registry, manifest, and assurance schema.
- `docs/` is the MkDocs-Material site (docs.provael.com); `examples/` holds runnable scenario dirs; `leaderboard/` + `action.yml` power submissions and the GitHub Action.

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: conventions -->
## Code Conventions

- Python 3.12+ only. `from __future__ import annotations` at the top of modules; PEP 695 `type` aliases for core types (e.g. `type Observation = dict[str, Any]`).
- Ruff is the lint authority: line length 100, rules `E,F,I,B,UP,W,C4,SIM` (tests exempt from E501). Import order is ruff-managed.
- Mypy strict on `src/` with the pydantic plugin; every function signature is typed. Optional heavy deps (`lerobot`, `torch`, `transformers`, `cryptography`, `fastapi`, …) are `ignore_missing_imports` overrides and must be imported lazily behind guards — they are absent from the CPU build.
- Value objects are frozen dataclasses; anything serialized into `report.json` is a pydantic `BaseModel`.
- Docstrings are Sphinx-style with cross-references (`:class:`, `:mod:`, `:meth:`) and document contracts/invariants, not mechanics.
- Never introduce wall-clock time, unseeded randomness, or process-varying values into report-producing code — determinism is tested.
- New attacks: subclass `Attack` (or `OptimizedAttack`), set `name`/`family`/`eai_id` plus threat-model fields, register in `attacks/registry.py`, add the mirrored test, and refresh golden manifests via the drift-guard tests.
- New defenses follow the same shape through `defenses/registry.py`, and carry the same burden of proof: a defense that is only *specified* must be labelled as such and never counted as measured risk reduction.

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: patterns -->
## Detected Patterns

- Registry pattern throughout: attacks, defenses, policies, and suites resolve by name; goldens pin registry contents so additions are deliberate.
- ABC contracts with adapters wrapping third-party stacks; the stub adapter keeps the full pipeline runnable on CPU in seconds.
- Optional-extra discipline: extras that cannot coexist (`lerobot` vs `openpi`, over numpy) are declared as uv conflicts instead of being left to break resolution.
- Environment-gated integration: `PROVAEL_INTEGRATION=1` switches real-model tests from auto-skip to must-run (release/nightly lanes).
- Signed evidence: Ed25519 attestation (`provael attest`, per-checkpoint regression attestations in CI) with the cryptography dep kept out of the default install but exercised by the dev group.
- Claims are typed by strength, not asserted flatly — the evidence ladder, semantic endpoints, and a non-binary verdict all exist so an unverified result cannot be read as a verified one. Symmetrically, defenses are measured or explicitly labelled unproven.
- Provenance is bound to results by digest (`ExecutionManifest`) rather than recorded alongside them, so a report cannot be paired with the wrong run.

<!-- END AUTO-MANAGED -->

<!-- AUTO-MANAGED: git-insights -->
## Git Insights

- Work lands via PR branches (`feat/…`, `docs/…`) merged to `main`; commits use conventional prefixes (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) with scopes like `(policies)`, `(ci)`, `(attacks)`, `(defenses)`, `(leaderboard)`.
- Recent direction: measured defenses (action-side mitigation hook, action envelope, risk-reduction evidence in the dossier), the `universal_patch` family alongside a corrected prior-art record, a signed public leaderboard, and checkpoint supply-chain integrity folded into the CI security gate.
- **A large share of `fix:` commits are self-corrections of the project's own claims** — a family count that was wrong, backends silently shown as run, a leaderboard signed/unsigned statement that contradicted its data, unresolvable Top-10 citations. The pattern to copy: correct the claim *and* land the guard that makes the error impossible to repeat.
- Releases bump the version in `src/provael/__init__.py` (hatch reads it) and refresh goldens/manifest in the same PR; the website's public-evidence manifest is re-pinned after each release.
- The project reports honest nulls (attack families that did NOT transfer) alongside positive findings — preserve that framing in README and docs edits.

<!-- END AUTO-MANAGED -->

<!-- MANUAL -->
## Custom Notes

Add project-specific notes here. This section is never auto-modified.

<!-- END MANUAL -->
