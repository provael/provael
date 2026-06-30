# Python API

Provael is model- and suite-agnostic via two tiny abstractions. Use it as a library, not just a
CLI.

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

## Evidence helpers

```python
from provael.scorecard import to_scorecard_markdown
from provael.oscal import to_oscal_json
from provael.avid import to_avid_json

print(to_scorecard_markdown(report, threshold=0.5))
open("report.oscal.json", "w").write(to_oscal_json(report))
open("report.avid.json", "w").write(to_avid_json(report))
```
