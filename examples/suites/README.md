# Simulator suites — what ships, and how to add more

A Provael *suite* wraps an environment behind a Gym-like `reset`/`step` plus an `is_unsafe`
predicate ([`SuiteAdapter`](../../src/provael/suites/base.py)). Provael's predicates need an
**end-effector position** (spatial keep-out) or a **scalar danger signal** plus a success flag.

## Shipped

| Suite | Predicate | Engine | Runs on | Status |
| --- | --- | --- | --- | --- |
| `stub` | scalar (per-seed threshold) | none | **CPU** | shipped, deterministic |
| `reach` | spatial (keep-out zone) | none | **CPU** | shipped, deterministic |
| `libero` | spatial (keep-out / grasp) | robosuite/MuJoCo | GPU | shipped, gated `[lerobot]` |
| `metaworld` | spatial (keep-out) | MuJoCo | CPU-render | **scaffolding**, gated `[lerobot]` * |

\* `metaworld` is registered scaffolding: its predicate logic is CPU-unit-tested, but its simulator
wiring is written against Meta-World's documented obs layout and has never been introspected
against an installed package, and no benchmark has been run through it. From the CLI it raises at
reset (LIBERO's default keep-out box lies behind the Sawyer arm, and there is no zone option); from
the Python API, pass a `keep_out_zone` derived from the suite's own benign envelope. It also needs
LeRobot's own `metaworld` extra. Confirm the end-effector obs key against your installed version
(see the module docstring).

## How to add a suite

Subclass `SuiteAdapter` and register it — see the runnable
[`../python-api/custom_suite_adapter.py`](../python-api/custom_suite_adapter.py) (CPU, ~40 lines),
and `reach.py` / `metaworld.py` for spatial examples. Import any heavy/optional dependency
**inside** `reset`/`step` (never at module top) so the CPU core stays importable.

## Roadmap (research-backed; not yet shipped)

These are the highest-value next suites (each exposes an end-effector pose + success, so Provael's
predicates port with near-zero change). Contributions welcome via the pattern above.

| Suite | Why | Engine | CPU render | License |
| --- | --- | --- | --- | --- |
| **RoboCasa** | hottest 2025–26 manip benchmark; reuses LIBERO's robosuite plumbing | robosuite/MuJoCo | yes (osmesa) | MIT-based |
| **CALVIN** | long-horizon, language-conditioned (ideal for instruction/injection chains) | PyBullet | yes | MIT |
| **SimplerEnv** | the real-to-sim benchmark every VLA paper cites (Google Robot, WidowX) | SAPIEN | GPU (Vulkan) | MIT |
| **AI2 vla-evaluation-harness bridge** | one adapter ⇒ inherit ~18 benchmarks behind one `predict()` | various | mixed | Apache-2.0 |

The harness bridge is the strategic multiplier: implement Provael's attack/predicate layer as a
wrapper around the harness's `predict()` and read its exposed state for the predicate. Pair it
with the CPU suites above so the CPU-first promise survives.
