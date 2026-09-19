# Python API

Provael is model- and suite-agnostic via two tiny abstractions. Use it as a library, not just a
CLI.

The names below are also importable from the package root, if you prefer the shorter spelling:

```python
from provael import RunConfig
from provael import run
```

They are resolved lazily, so `import provael` stays fast and pulls in nothing you do not touch.
`provael.__all__` is the full list, and a test fails if it and this page ever disagree.

## Run a scan

```python
from provael.config import RunConfig
from provael.runner import run

report = run(RunConfig(policy="stub", suite="stub", attacks=["instruction"], episodes=10, seed=0))
print(report.headline())          # Attack Success Rate (ASR): ...
print(report.by_attack)           # per-attack ASRStat
```

## Bring your own policy

A policy maps `(observation, instruction) -> action` — the
[`PolicyAdapter`](https://github.com/provael/provael/blob/main/src/provael/policies/base.py) ABC:

```python
from provael.policies.base import PolicyAdapter
from provael.policies.registry import POLICIES

class MyVLA(PolicyAdapter):
    name = "my-vla"
    def load(self): ...                       # load weights (raise on missing dep)
    def act(self, observation, instruction):  # return a 1-D numpy action
        ...

POLICIES["my-vla"] = lambda **_: MyVLA()
```

Runnable example: [`custom_policy_adapter.py`](https://github.com/provael/provael/blob/main/examples/python-api/custom_policy_adapter.py).
Three real backends (LeRobot / HF AutoModel / policy-server) in the
[cookbook](https://github.com/provael/provael/blob/main/examples/adapters/cookbook.md).

## Bring your own suite

A suite wraps an env behind `reset`/`step` + an `is_unsafe` predicate
([`SuiteAdapter`](https://github.com/provael/provael/blob/main/src/provael/suites/base.py)).
Runnable example: [`custom_suite_adapter.py`](https://github.com/provael/provael/blob/main/examples/python-api/custom_suite_adapter.py).

## Decide release acceptance under a named protocol

A run is a measurement. Whether it is *acceptable* is a separate statement, and it is only made
against criteria somebody wrote down and named. With no protocol, `release_verdict` returns
`incomplete` with `assessed=False` — nothing was decided, and every emitter says so. A `pass` means
one thing: the named protocol was satisfied. There is no built-in "safe ASR".

```python
from provael.verdict import AcceptanceProtocol, release_verdict

protocol = AcceptanceProtocol.load("examples/assessment/protocol.example.yml")  # or build it in code
decision = release_verdict(report, protocol)   # a real-policy report; the stub is never release-grade
print(decision.verdict, decision.protocol, decision.reasons)
```

A protocol may carry one bounded exception — a named approver, a timezone-aware expiry, a
remediation, and the requirement keys it covers. Pass `as_of=datetime.now(UTC)` so the expiry can
be judged; an expired exception is refused, an uncovered gap stays `incomplete`, and a failed
threshold is never softened. `provael attack --protocol <file>` writes the decision beside the
report as `report.decision.json`, and every export reads that same decision.

## Evidence helpers

```python
from provael.scorecard import to_scorecard_markdown
from provael.oscal import to_oscal_json
from provael.avid import to_avid_json

print(to_scorecard_markdown(report, threshold=0.5, decision=decision))  # threshold is descriptive
open("report.oscal.json", "w").write(to_oscal_json(report))
open("report.avid.json", "w").write(to_avid_json(report))
```
