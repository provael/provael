# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""MuJoCo step 2: render the same arm offscreen and write an MP4 — how episode videos are made.

What you learn: the offscreen Renderer, cameras, the frame rate you choose vs the physics rate,
and that a video is just the frames a camera saw, encoded. The keep-out box is drawn here too.

Run:   python explore_02_record_video.py            -> arm_keepout.mp4 (about 15 s)
"""
import imageio
import mujoco
import numpy as np

SCENE = "mujoco_menagerie/franka_emika_panda/scene.xml"
KEEP_OUT = ((0.20, 0.60), (-0.55, -0.20), (0.20, 0.70))
FPS, SECONDS = 30, 15

model = mujoco.MjModel.from_xml_path(SCENE)
data = mujoco.MjData(model)
mujoco.mj_resetDataKeyframe(model, data, 0)
home_ctrl = data.ctrl.copy()
hand = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand")
renderer = mujoco.Renderer(model, height=480, width=640)

camera = mujoco.MjvCamera()
camera.type = mujoco.mjtCamera.mjCAMERA_FREE
camera.lookat[:] = [0.3, -0.2, 0.4]
camera.distance, camera.azimuth, camera.elevation = 2.2, 150, -25


def controller(t):
    ctrl = home_ctrl.copy()
    ctrl[0] = -0.9 * np.sin(0.5 * t)
    ctrl[1] = 0.35 * (1 - np.cos(0.5 * t))
    ctrl[3] = -1.57 - 0.4 * (1 - np.cos(0.5 * t))
    return ctrl


def inside(pos):
    return all(lo <= p <= hi for p, (lo, hi) in zip(pos, KEEP_OUT, strict=True))


def draw_box(scene, hot):
    (x0, x1), (y0, y1), (z0, z1) = KEEP_OUT
    i = scene.ngeom
    scene.ngeom += 1
    mujoco.mjv_initGeom(
        scene.geoms[i], mujoco.mjtGeom.mjGEOM_BOX,
        size=[(x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2],
        pos=[(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2],
        mat=np.eye(3).flatten(),
        rgba=[1, 0.1, 0.1, 0.45] if hot else [0.2, 0.5, 1.0, 0.25],
    )


steps_per_frame = int(round(1 / (FPS * model.opt.timestep)))
writer = imageio.get_writer("arm_keepout.mp4", fps=FPS, codec="libx264", pixelformat="yuv420p")
frames = 0
while data.time < SECONDS:
    for _ in range(steps_per_frame):
        data.ctrl[:] = controller(data.time)
        mujoco.mj_step(model, data)
    renderer.update_scene(data, camera=camera)
    draw_box(renderer.scene, inside(data.xpos[hand]))
    writer.append_data(renderer.render())
    frames += 1
writer.close()
renderer.close()
print(f"wrote arm_keepout.mp4: {frames} frames at {FPS} fps, "
      f"{steps_per_frame} physics steps per frame")
