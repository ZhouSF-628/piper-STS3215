#!/usr/bin/env python3
"""
Piper 机械臂 — 首次校准脚本

用法：
    python scripts/calibrate.py --port /dev/ttyACM0

流程：
    1. 将所有关节移至中位 → 按 Enter
    2. 依次拨动每个关节走完全程 → 按 Enter 结束录制
    3. 校准值自动保存，后续连接不再需要重复校准
"""

import argparse
import logging

from lerobot.robots.piper_follower import PiperFollowerConfig
from lerobot.robots.utils import make_robot_from_config

logging.basicConfig(level=logging.INFO)


def main():
    parser = argparse.ArgumentParser(description="Piper 机械臂校准")
    parser.add_argument("--port", default="/dev/ttyACM0", help="舵机总线串口 (默认: /dev/ttyACM0)")
    args = parser.parse_args()

    cfg = PiperFollowerConfig(port=args.port)
    robot = make_robot_from_config(cfg)

    print(f"连接 {args.port} ...")
    robot.connect()
    print("校准完成！")
    robot.disconnect()
    print("断开连接。校准文件已保存到:", robot.calibration_fpath)


if __name__ == "__main__":
    main()
