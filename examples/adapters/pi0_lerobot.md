# Red-team π0 / π0.5 / π0-FAST (LeRobot)

Physical Intelligence's **π0** family is Apache-2.0 and LeRobot-native, so Provael red-teams it
through the *same* generic harness as SmolVLA — only the checkpoint changes. No new code.

```bash
pip install 'provael[lerobot]'        # GPU machine
export PROVAEL_INTEGRATION=1
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl   # headless LIBERO render (or osmesa)

# π0 on LIBERO — pass a LIBERO-fine-tuned checkpoint with --model:
provael attack \
    --policy pi0 \
    --model lerobot/pi0_libero_finetuned \
    --suite libero \
    --attacks none,instruction,visual,injection,action \
    --seeds 10 --horizon 280 --seed 0 \
    --out runs/pi0_libero
```

`--policy pi05` and `--policy pi0fast` work the same way (pass the matching checkpoint via
`--model`). Always include the `none` baseline so every attack rate is read against its benign
control.

## Checkpoint caveat (read this)

LeRobot's π0/π0.5 LIBERO checkpoints have **open reproduction issues** (e.g. zero benign success
on some `pi05_libero_base` snapshots — LeRobot issues #2114 / #2375 / #2533). **Pin a checkpoint
you have validated with a benign rollout first** (run the `none` baseline and confirm a non-zero
task-success / a 0% benign FPR) before trusting any ASR. The default `--model lerobot/pi0` is the
*base* model and is generally **not** directly evaluable on LIBERO — pass a fine-tuned checkpoint.

## Why this is one line of config

`smolvla`, `pi0`, `pi05`, `pi0fast` and `groot` all load through LeRobot's generic
`PreTrainedConfig.from_pretrained(...) → make_policy(...)` path
([`src/provael/policies/lerobot_adapter.py`](../../src/provael/policies/lerobot_adapter.py)),
which selects the right policy class from the checkpoint's own config. Adding a LeRobot-native
model to Provael is therefore a registry entry with a different default checkpoint — see
[`src/provael/policies/registry.py`](../../src/provael/policies/registry.py).

## A leaderboard you can build

Run the same attacks across models and compare ASR per family:

```bash
provael leaderboard build --runs 'runs/*' --out leaderboard/results
```
