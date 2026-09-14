# MuJoCo primer — the harness's three ideas, in raw MuJoCo, on any laptop

Four short scripts that show what provael measures at the engine level, with nothing from provael
imported: a keep-out predicate you can see, an episode clip made from the frames a camera saw, a
floating-base robot and an external force, and the observation → action → reward loop every VLA
evaluation is built on. They run on Windows, macOS and Linux with no GPU.

```bash
pip install mujoco dm_control imageio imageio-ffmpeg numpy
git clone https://github.com/google-deepmind/mujoco_menagerie   # the robot models (Apache/BSD, per directory)
```

| script | what it shows | run |
| --- | --- | --- |
| `explore_01_arm_keepout.py` | Franka Panda driven from Python, live viewer, a keep-out box drawn into the scene that turns red when the hand enters it — the predicate `LiberoSuiteAdapter.is_unsafe` scores, made visible | `python explore_01_arm_keepout.py` (`--headless` prints only) |
| `explore_02_record_video.py` | the same arm rendered offscreen into `arm_keepout.mp4` — what `provael attack --video-dir` does per episode | `python explore_02_record_video.py` |
| `explore_03_humanoid_push.py [N]` | Unitree G1 standing on its position actuators (the PD lives in the actuator; you set targets), pushed after 3 s: 250 N topples it, 20 N does not — a fixed pose has no balance feedback | `python explore_03_humanoid_push.py 20` |
| `explore_04_policy_in_sim.py` | dm_control's humanoid-walk task driven by a policy function — random or zero; neither walks, and that is the point: the loop, the observation dict and the reward are where a learned policy plugs in | `python explore_04_policy_in_sim.py` (`--headless` prints rewards) |

Every script prints what it does. The keep-out box coordinates and the push force are the two
things worth changing first. Nothing here is a measurement of anything; it is the vocabulary.
