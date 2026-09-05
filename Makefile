# Provael — one name for each gate that already exists.
#
# WHAT THIS IS. A thin wrapper over `scripts/` and the CI gate, so a contributor does not have to
# reconstruct an invocation from a workflow file. Every recipe below is the command CI actually
# runs; where CI and this file could drift, CI is the authority and this is the convenience.
#
# WHAT THIS IS NOT. New enforcement. Nothing here gates anything that was not already gated —
# `make check-doc-counts` is the same `--check` that `tests/test_counted_claims.py` already calls,
# and `make check` is the same three commands `.github/workflows/ci.yml` runs. Adding a Makefile
# that quietly introduced a NEW rule would be the worst version of this file, because the rule
# would live somewhere no reviewer looks.
#
# WHY doc-counts HAS ITS OWN TARGET AND ITS OWN CI STEP. It is already enforced inside pytest, and
# that is where the enforcement stays. What the dedicated step buys is the signal: a stale
# inventory line currently surfaces as one assertion inside a 1300-test, ~25 s run, and as a
# named 1 s step it says what is wrong in its own title. Same rule, legible failure.

PY := uv run python

.DEFAULT_GOAL := help
.PHONY: help install lint typecheck test check check-docs check-doc-counts fix-doc-counts \
	check-links check-leaderboard check-issue-labels gen-registry gen-schemas \
	check-measurement-ledger gen-measurement-ledger

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

install: ## Sync the dev environment (CPU-only; never pulls torch)
	uv sync

# ── The pre-push gate — the three commands .github/workflows/ci.yml runs ──────
# `mypy src scripts/action` and not `mypy src`: scripts/action holds the five scripts that decide
# whether a release passes, and they spent their whole life as shell heredocs where no type-checker
# could see them. Narrowing this to `src` would silently stop checking them.

lint: ## ruff (lint + import order)
	uv run ruff check .

typecheck: ## mypy, strict, including scripts/action
	uv run mypy src scripts/action

test: ## pytest (GPU/LIBERO integration tests auto-skip)
	uv run pytest -q

check: lint typecheck test ## The full pre-push gate

# ── Documentation integrity ──────────────────────────────────────────────────

check-docs: check-doc-counts check-measurement-ledger check-links ## Every doc gate that runs offline

check-doc-counts: ## Fail if a generated inventory line is stale
	$(PY) scripts/gen_doc_counts.py --check

fix-doc-counts: ## Rewrite the generated inventory lines from the registries
	$(PY) scripts/gen_doc_counts.py

check-measurement-ledger: ## Fail if watch/measurements.json is stale
	$(PY) scripts/gen_measurement_ledger.py --check

gen-measurement-ledger: ## Rewrite watch/measurements.json from the committed execution manifests
	$(PY) scripts/gen_measurement_ledger.py

check-links: ## Fail if a relative markdown link does not resolve case-exactly
	$(PY) scripts/check_links.py

check-leaderboard: ## Refuse a published board whose rows aged out silently
	$(PY) scripts/check_leaderboard_staleness.py

check-issue-labels: ## Fail if an issue form declares a label that does not exist
	$(PY) scripts/check_issue_labels.py

# ── Generators (commit what they write) ──────────────────────────────────────

gen-registry: ## Regenerate the registry artifact the website mirrors
	$(PY) scripts/gen_registry_artifact.py

gen-schemas: ## Regenerate the published JSON schemas after a model change
	$(PY) scripts/gen_schemas.py
