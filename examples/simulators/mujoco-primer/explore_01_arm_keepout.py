# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""MuJoCo step 1: drive the Panda from Python, watch it live, and draw a keep-out box.

What you learn: MjModel (the description) vs MjData (the state), the control vector, stepping the
physics, reading a body position, and drawing your own geometry into the viewer. The arm sweeps
its base joint; the box turns red the moment the hand is inside it. That is exactly the predicate
a red-team harness scores, drawn where you can see it.

Run:   python explore_01_arm_keepout.py            (live viewer; close the window to stop)
       python explore_01_arm_keepout.py --headless  (no window, prints only)
"""
import sys
import time

import mujoco
import numpy as np

SCENE = "mujoco_menagerie/franka_emika_panda/scene.xml"
# Keep-out box in world coordinates (metres): (x range, y range, z range).
KEEP_OUT = ((0.20, 0.60), (-0.55, -0.20), (0.20, 0.70))

model = mujoco.MjModel.from_xml_path(SCENE)
data = mujoco.MjData(model)
print(f"bodies={model.nbody} joints={model.njnt} actuators={model.nu} "
      f"timestep={model.opt.timestep}s  ({1 / model.opt.timestep:.0f} physics steps per second)")
for i in range(model.nu):
    print(f"  actuator {i}: {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i)}")

mujoco.mj_resetDataKeyframe(model, data, 0)  # the 'home' pose defined in the XML
home_ctrl = data.ctrl.copy()
hand = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand")


def inside(pos):
    return all(lo <= p <= hi for p, (lo, hi) in zip(pos, KEEP_OUT, strict=True))


def controller(t):
    """Position targets: sweep the base yaw and dip the elbow so the hand crosses the box."""
    ctrl = home_ctrl.copy()
    ctrl[0] = -0.9 * np.sin(0.5 * t)          # joint1: base yaw, radians
    ctrl[1] = 0.35 * (1 - np.cos(0.5 * t))    # joint2: shoulder pitch, lowers the hand
    ctrl[3] = -1.57 - 0.4 * (1 - np.cos(0.5 * t))  # joint4: elbow
    return ctrl


def draw_box(scene, hot):
    scene.ngeom = 1
    (x0, x1), (y0, y1), (z0, z1) = KEEP_OUT
    mujoco.mjv_initGeom(
        scene.geoms[0], mujoco.mjtGeom.mjGEOM_BOX,
        size=[(x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2],
        pos=[(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2],
        mat=np.eye(3).flatten(),
        rgba=[1, 0.1, 0.1, 0.45] if hot else [0.2, 0.5, 1.0, 0.25],
    )


headless = "--headless" in sys.argv
entered = None
if headless:
    for step in range(6000):
        data.ctrl[:] = controller(data.time)
        mujoco.mj_step(model, data)
        hot = inside(data.xpos[hand])
        if hot and entered is None:
            entered = step
            print(f"ENTERED the keep-out box at step {step} (t={data.time:.2f}s), "
                  f"hand at {np.round(data.xpos[hand], 3)}")
        if step % 500 == 0:
            print(f"step {step:5d}  t={data.time:6.2f}s  hand={np.round(data.xpos[hand], 3)}  "
                  f"inside={hot}")
else:
    import mujoco.viewer
    with mujoco.viewer.launch_passive(model, data) as viewer:
        step = 0
        while viewer.is_running():
            t0 = time.time()
            data.ctrl[:] = controller(data.time)
            mujoco.mj_step(model, data)
            hot = inside(data.xpos[hand])
            if hot and entered is None:
                entered = step
                print(f"ENTERED the keep-out box at step {step} (t={data.time:.2f}s)")
            draw_box(viewer.user_scn, hot)
            viewer.sync()
            step += 1
            time.sleep(max(0.0, model.opt.timestep - (time.time() - t0)))  # real-time pacing
print("first entry step:", entered)
