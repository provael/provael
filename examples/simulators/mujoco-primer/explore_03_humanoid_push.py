# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""MuJoCo step 3: a humanoid (Unitree G1) held standing by its position actuators, then pushed.

What you learn: a floating-base robot (the first 7 qpos entries are position + quaternion of the
pelvis), position actuators (the PD controller lives INSIDE the actuator: kp=500 in the XML, you
only set targets), external forces (xfrc_applied), and why balance is hard: the standing pose is a
fixed point with no feedback: it stands forever untouched, survives a 20 N nudge, and a push of
~50 N or more for 0.2 s topples it. A balance controller would be the thing that closes that loop.

Run:   python explore_03_humanoid_push.py            (live viewer; a 250 N push after 3 s)
       python explore_03_humanoid_push.py 20            (a 20 N nudge — watch it hold)
       python explore_03_humanoid_push.py --headless
"""
import sys
import time

import mujoco

SCENE = "mujoco_menagerie/unitree_g1/scene.xml"
PUSH_AT, PUSH_FOR = 3.0, 0.2   # seconds
# Newtons, along +x; the first numeric command-line argument overrides it.
PUSH_N = next((float(a) for a in sys.argv[1:] if a.replace(".", "").isdigit()), 250.0)

model = mujoco.MjModel.from_xml_path(SCENE)
data = mujoco.MjData(model)
mujoco.mj_resetDataKeyframe(model, data, 0)      # 'stand'
q_target = data.qpos[7:].copy()                  # joint targets = the standing pose
torso = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "torso_link")
print(f"nq={model.nq} (7 floating-base + {model.nq - 7} joints)  actuators={model.nu} "
      f"(position actuators, kp={model.actuator_gainprm[0, 0]:.0f})  "
      f"push={PUSH_N:.0f} N at {PUSH_AT}s")


def maybe_push():
    active = PUSH_AT <= data.time < PUSH_AT + PUSH_FOR
    data.xfrc_applied[torso, :3] = [PUSH_N, 0.0, 0.0] if active else 0.0
    return active


def run_step():
    data.ctrl[:] = q_target          # hold the standing pose; try adding a slow sway yourself
    pushed = maybe_push()
    mujoco.mj_step(model, data)
    return pushed


headless = "--headless" in sys.argv
if headless:
    for step in range(8000):
        pushed = run_step()
        if step % 1000 == 0 or (pushed and step % 50 == 0):
            print(f"t={data.time:5.2f}s pelvis height={data.qpos[2]:.3f} m  push={pushed}")
    print("final pelvis height:", round(float(data.qpos[2]), 3),
          "(0.79 standing; below 0.4 means it fell)")
else:
    import mujoco.viewer
    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            t0 = time.time()
            run_step()
            viewer.sync()
            time.sleep(max(0.0, model.opt.timestep - (time.time() - t0)))
