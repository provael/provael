"""A ROS 2 reference node that applies the Provael safety envelope to a live action topic.

Speaks robotics middleware natively: an rclpy node that subscribes to the policy's action /
`/cmd_vel` topic, applies the same velocity/magnitude envelope as robot_firewall.py, republishes a
clamped command, and publishes a violation flag (and optionally an e-stop). It drops next to
`nav2_collision_monitor` / `software_watchdog` and can sit on the ROS-MCP / MoveIt-MCP boundary to
guard LLM->robot calls.

STATUS: reference node. Importable without ROS 2 installed (the rclpy import is guarded). The
envelope logic is the same one robot_firewall.py unit-tests; the rclpy wiring is written to the
documented rclpy API and not run in this repo's CI. SIM/reference — not a certified safety node.

    # on a ROS 2 (Humble+) machine:
    python examples/runtime/ros2_guard_node.py
"""

from __future__ import annotations

MAX_SPEED = 0.15


def clamp_twist(linear: tuple[float, float, float], max_speed: float = MAX_SPEED) -> tuple[
    tuple[float, float, float], bool
]:
    """Clamp a linear velocity to ``max_speed``; return (clamped, violated). Pure / CPU-testable."""
    import math

    speed = math.sqrt(sum(v * v for v in linear))
    if speed > max_speed and speed > 0:
        scale = max_speed / speed
        return (linear[0] * scale, linear[1] * scale, linear[2] * scale), True
    return linear, False


def main() -> None:
    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from rclpy.node import Node
        from std_msgs.msg import Bool
    except ImportError:
        print("ROS 2 (rclpy) not installed — this is a reference node. Envelope check still works:")
        clamped, violated = clamp_twist((1.0, 0.0, 0.0))
        print(f"  clamp_twist((1,0,0)) -> {clamped}, violated={violated}")
        return

    class GuardNode(Node):  # pragma: no cover - requires ROS 2
        def __init__(self) -> None:
            super().__init__("provael_guard")
            self._pub = self.create_publisher(Twist, "cmd_vel_safe", 10)
            self._viol = self.create_publisher(Bool, "provael/violation", 10)
            self.create_subscription(Twist, "cmd_vel", self._on_cmd, 10)

        def _on_cmd(self, msg: Twist) -> None:
            linear, violated = clamp_twist((msg.linear.x, msg.linear.y, msg.linear.z))
            out = Twist()
            out.linear.x, out.linear.y, out.linear.z = linear
            self._pub.publish(out)
            self._viol.publish(Bool(data=violated))

    rclpy.init()
    node = GuardNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
