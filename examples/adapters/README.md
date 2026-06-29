# Model adapters — red-team any open VLA

Provael is **model-agnostic**: a policy is anything that maps `(observation, instruction) → action`
(the tiny [`PolicyAdapter`](../../src/provael/policies/base.py) ABC). Three ways to plug one in:

| Path | Models | How | Extra |
| --- | --- | --- | --- |
| **LeRobot-native** | `smolvla`, `pi0`, `pi05`, `pi0fast`, `groot` | already registered — pick with `--policy` | `provael[lerobot]` (GPU) |
| **HF `transformers`** | `openvla` (OpenVLA / OpenVLA-OFT) | already registered — `--policy openvla` | `provael[openvla]` (GPU) |
| **Bring your own** | anything | ~30 lines subclassing `PolicyAdapter` | — |

```bash
provael list-policies     # every registered policy + whether it's runnable here
```

- [`pi0_lerobot.md`](pi0_lerobot.md) — red-team π0 / π0.5 / π0-FAST (config-level reuse of the SmolVLA harness).
- [`groot_lerobot.md`](groot_lerobot.md) — red-team NVIDIA GR00T N1.5 / N1.7.
- [`openvla_adapter.py`](openvla_adapter.py) — standalone OpenVLA example (the non-LeRobot path).
- [`cookbook.md`](cookbook.md) — **bring your own VLA** across 3 backends.
- [`../python-api/custom_policy_adapter.py`](../python-api/custom_policy_adapter.py) — a runnable
  ~30-line custom adapter (CPU, no deps).

> **Honesty.** The LeRobot-native and OpenVLA adapters share one generic load path each and are
> exercised structurally on CPU (construction + missing-dependency errors are unit-tested); the
> real forward passes need a GPU + the extra + `PROVAEL_INTEGRATION=1` and are **not** run in this
> repo's CI. Pin a checkpoint you've validated, and read every ASR against its benign control.
