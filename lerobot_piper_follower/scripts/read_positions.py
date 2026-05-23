#!/usr/bin/env python3
"""
Piper 机械臂 — 读取当前关节位置

用法：
    python scripts/read_positions.py --port /dev/ttyACM0
"""

import argparse
import logging

from lerobot.robots.piper_follower import PiperFollowerConfig
from lerobot.robots.utils import make_robot_from_config

logging.basicConfig(level=logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="读取 Piper 机械臂关节位置")
    parser.add_argument("--port", default="/dev/ttyACM0", help="舵机总线串口 (默认: /dev/ttyACM0)")
    args = parser.parse_args()

    cfg = PiperFollowerConfig(port=args.port)
    robot = make_robot_from_config(cfg)
    robot.connect()

    obs = robot.get_observation()
    print("\n当前关节位置：")
    for key, val in obs.items():
        if key.endswith(".pos"):
            print(f"  {key:20s}  {val:8.1f}")

    robot.disconnect()


if __name__ == "__main__":
    main()
