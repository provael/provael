# Contributing to provael

Thanks for your interest in improving **provael** (Provael). This is a defensive,
sim-only security-research tool — please read [SAFETY.md](SAFETY.md) first.

## Ground rules

- **CPU-first.** The entire core runs and is tested on a plain CPU with **no GPU and no
  model/dataset download**. Real policies (SmolVLA via LeRobot) and the LIBERO simulator
  live behind the optional `[lerobot]` extra and a `PROVAEL_INTEGRATION=1` gate. **CI never
  installs `lerobot`** — keep it that way.
- **Verify, don't fabricate.** Numbers in the README/CHANGELOG must come from a real run.
  When a third-party API is involved, read/introspect the installed source rather than
  guessing; if something can't be verified (no GPU/sim), say so and ship a clearly-skipped
  gated test instead of a guess.
- **Determinism.** The stub policy/suite are byte-deterministic; real policies are seeded
  but model-stochastic (reported as mean ± per-seed std). Don't put wall-clock into
  `report.json`.

## Dev setup

```bash
# uv (recommended): https://docs.astral.sh/uv/
uv sync                      # core + dev tools (no GPU stack)
uv run provael --help
```

## The gate (must be green before you push)

```bash
uv run ruff check .          # lint + import order
uv run mypy src              # strict type-check
uv run pytest -q             # tests (GPU/LIBERO tests auto-skip without the extra)
```

The optional, GPU-gated integration tests:

```bash
pip install 'provael[lerobot]' 'lerobot[libero]==0.5.1'
PROVAEL_INTEGRATION=1 pytest tests/test_lerobot_adapter.py tests/test_libero_adapter.py -q
```

## Conventions

- **Python 3.12+**, type hints on all signatures, pydantic v2 for data models.
- **Commits**: imperative, conventional-style prefixes (`feat:`, `fix:`, `docs:`,
  `test:`, `chore:`), concise subject (< 72 chars), body for context.
- **Architecture**: ports-and-adapters — new policies subclass `PolicyAdapter`, new suites
  `SuiteAdapter`, new attacks `Attack`; register them in the relevant registry and add a
  CPU test (use the stub) plus a gated test if a GPU/sim is required.
- Keep optional dependencies imported **only inside methods**, never at module scope.

## Pull requests

1. Branch (`feature/…`, `fix/…`), make the change, keep the gate green.
2. Add/extend tests; for new attacks, include the deterministic stub ASR.
3. Update `CHANGELOG.md` (`[Unreleased]`) and any affected docs.
4. Open the PR with a **Summary** and a **Test Plan**.

## Reporting bugs / requesting features

Open a GitHub issue (templates provided). For security vulnerabilities, see
[SECURITY.md](SECURITY.md) — please do **not** open a public issue for those.

## Contributing to the Embodied AI Security Top 10

[docs/TOP10.md](docs/TOP10.md) — *The Embodied AI Security Top 10* — is a community draft we
actively want challenged. **You don't need to touch any code to contribute.**

- **Propose / dispute / fix a mapping** via the issue form:
  [Top 10: propose / dispute / fix a mapping](https://github.com/provael/provael/issues/new?template=top10-feedback.yml)
  — argue a rank, a category, a framework cross-map, or a missing risk.
- **Or open a PR** editing `docs/TOP10.md` directly (small fixes, fresh evidence, clearer wording).
- **Licensing.** The Top 10 is **CC-BY-SA 4.0** (the code is Apache-2.0). By contributing you agree
  your contribution is licensed CC-BY-SA 4.0, so the list stays freely shareable and donatable.
- **Versioning.** It's at **v0.x** — deliberately a draft, made to be argued with; material changes
  bump the minor draft version.
- **Where it's headed.** The goal is a living, vendor-neutral list, ideally routed into the **OWASP
  GenAI / Agentic Security Initiative** over time. Contributors and the researchers behind each cited
  attack are credited in the doc.
