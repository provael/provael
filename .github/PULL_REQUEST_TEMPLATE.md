## Summary

<!-- What does this change and why? -->

## Test plan

<!-- How did you verify it? For code changes: -->
<!-- `uv run ruff check . && uv run mypy src && uv run pytest -q` -->

## Evidence & claims checklist

<!-- Provael's product is trustworthy evidence semantics. Confirm this change keeps them honest: -->

- [ ] No new claim of hardware / calibration / external-reproduction / real-transfer beyond the
      `evidence_state` a run actually earned
- [ ] The benign control is not folded into any "adversarial ASR"; N/A stays N/A (never a 0%)
- [ ] `attest --verify` still fails closed (unsigned / untrusted ≠ verified)
- [ ] No legacy result JSON was edited to match a new schema (schema change → migration + regen)
- [ ] Determinism preserved (no wall-clock / randomness in `report.json`); canary `47/70` unchanged
- [ ] Any new attack records `attacker_access` + `action_head_class`; the Top-10 is not branded OWASP

---

### Leaderboard submission? (delete this section if N/A)

- [ ] Adds `results/<name>/report.json` produced by `provael attack` (with a `none` baseline)
- [ ] `python scripts/validate_submission.py` passes locally
- [ ] Reproducible: checkpoint, suite/task(s), seeds, horizon, and hardware noted below

<!-- policy/checkpoint:
     suite/tasks:
     seeds / horizon / hardware: -->
