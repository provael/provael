# Runtime defense — show hardening, not just attacks

Provael's lane is the **pre-deployment scanner**, but it can demo a defense to prove the red-team →
harden loop measurably works. **Honest scope:** these are **sim / reference monitors**, NOT
certified safety controllers — the real functional-safety bar (NVIDIA Halos, ISO 26262 / IEC
61508) is out of scope and Provael does not claim it.

| File | What it does |
| --- | --- |
| [`robot_firewall.py`](robot_firewall.py) | Wrap any policy with a velocity/magnitude envelope + reversal-rate/jerk monitor + watchdog; measure ASR **with vs. without** |
| [`ros2_guard_node.py`](ros2_guard_node.py) | A ROS 2 (rclpy) node applying the same envelope to a live `/cmd_vel` topic; reference |

```bash
python examples/runtime/robot_firewall.py
# ASR without firewall: 67/90 (74%)
# ASR with    firewall: 20/90 (22%)   <- the envelope makes 52% of episodes safe
```

The residual 20/90 are mostly **action-integrity** attacks (freeze / trajectory hijack) that a
velocity clamp doesn't fully neutralize — an honest demonstration that an envelope is a partial
defense, not a cure. The checks (direction-reversal-rate, jerk, velocity bound) are the
black-box failure predictors from arXiv:2605.28726 + the nav2 safety-envelope pattern.
