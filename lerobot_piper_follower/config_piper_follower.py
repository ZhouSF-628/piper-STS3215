from dataclasses import dataclass, field

from lerobot.cameras import CameraConfig

from ..config import RobotConfig


@RobotConfig.register_subclass("piper_follower")
@dataclass
class PiperFollowerConfig(RobotConfig):
    """Configuration for Piper 6-DOF arm + gripper follower robot."""

    port: str
    """Serial port for the Feetech motor bus (e.g., '/dev/ttyACM0')."""

    disable_torque_on_disconnect: bool = True

    max_relative_target: float | dict[str, float] | None = None
    """Limits the magnitude of the relative positional target vector for safety purposes.
    Set to a positive scalar to apply the same limit to all motors, or a dict mapping
    motor names to individual limits."""

    cameras: dict[str, CameraConfig] = field(default_factory=dict)

    use_degrees: bool = True
    """If True, joint positions are in degrees. If False, uses normalized [-100, 100] range."""
