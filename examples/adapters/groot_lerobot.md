# Red-team NVIDIA GR00T N1.5 / N1.7 (LeRobot)

NVIDIA **GR00T** is a native LeRobot policy (`--policy.type=groot`) since LeRobot v0.4.0, so it
red-teams through the same harness as SmolVLA/π0. GR00T N1.7 weights are Apache-2.0 (commercial-OK).

```bash
pip install 'provael[lerobot]'        # GPU machine; GR00T also needs LeRobot's groot extra
export PROVAEL_INTEGRATION=1
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl

provael attack \
    --policy groot \
    --model nvidia/GR00T-N1.5-3B \
    --suite libero \
    --attacks none,instruction,visual,injection,action \
    --seeds 10 --horizon 280 --seed 0 \
    --out runs/groot_libero
```

Notes:
- GR00T's LeRobot integration may need LeRobot's GR00T extra/weights set up per NVIDIA's
  Isaac-GR00T-in-LeRobot guide; pin a checkpoint validated on your suite.
- Reported LeRobot LIBERO numbers vary by suite (e.g. ~82% spatial) — run the `none` baseline and
  read each attack rate against it.
- This adapter is structurally exercised on CPU; the real forward pass is GPU-only and not run in
  this repo's CI.
