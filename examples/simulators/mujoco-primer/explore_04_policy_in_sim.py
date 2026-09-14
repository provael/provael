"""MuJoCo step 4: a policy driving an environment — the loop every VLA evaluation is built on.

dm_control wraps MuJoCo in gym-like tasks (observation in, action out, reward back). This runs the
humanoid 'walk' task with two policies you can swap: random actions, and a zero-torque policy.
Neither walks — that is the point: you see the loop, the observation dictionary and the reward,
and where a learned policy would plug in.

Run:   python explore_04_policy_in_sim.py            (dm_control viewer; press space to run)
       python explore_04_policy_in_sim.py --headless  (prints rewards only)
"""
import sys

import numpy as np
from dm_control import suite

env = suite.load(domain_name="humanoid", task_name="walk")
spec = env.action_spec()
print("action dims:", spec.shape, "in", spec.minimum.min(), "..", spec.maximum.max())
rng = np.random.default_rng(0)


def random_policy(time_step):
    return rng.uniform(spec.minimum, spec.maximum, size=spec.shape)


def zero_policy(time_step):
    return np.zeros(spec.shape)


policy = random_policy
if "--headless" in sys.argv:
    time_step = env.reset()
    print("observation keys:", list(time_step.observation.keys()))
    total = 0.0
    for step in range(500):
        time_step = env.step(policy(time_step))
        total += time_step.reward or 0.0
        if step % 100 == 0:
            head = time_step.observation["head_height"]
            print(f"step {step:4d} reward so far {total:.3f}  head height {head:.3f}")
    print("episode reward:", round(total, 3))
else:
    from dm_control import viewer
    viewer.launch(env, policy=policy)
