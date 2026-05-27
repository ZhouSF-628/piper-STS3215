#!/usr/bin/env python3
"""
Piper 机械臂 — 动作测试脚本

用法：
    python scripts/test_movement.py --port /dev/ttyACM0

安全提示：
    - 首次运行时把机械臂放在开阔区域
    - 手放在急停开关或 USB 线附近
    - 如需调整关节角度，修改下方 ACTIONS 列表
"""

import argparse
import logging
import time

from lerobot.robots.piper_follower import PiperFollowerConfig
from lerobot.robots.utils import make_robot_from_config

logging.basicConfig(level=logging.INFO)

# 动作序列：每个动作是一个 dict {关节名: 目标角度}
# 角度制：正负号取决于舵机安装方向，根据实际情况调整
ACTIONS = [
    {"name": "回零", "pos": {
        "shoulder_pan": 0, "shoulder_lift": 0, "elbow_flex": 0,
        "forearm_roll": 0, "wrist_flex": 0, "wrist_roll": 0, "gripper": 100,
    }},
    {"name": "肩部旋转 10°", "pos": {
        "shoulder_pan": 10, "shoulder_lift": 0, "elbow_flex": 0,
        "forearm_roll": 0, "wrist_flex": 0, "wrist_roll": 0, "gripper": 50,
    }},
    {"name": "回零", "pos": {
        "shoulder_pan": 0, "shoulder_lift": 0, "elbow_flex": 0,
        "forearm_roll": 0, "wrist_flex": 0, "wrist_roll": 0, "gripper": 100,
    }},
    {"name": "肘部弯曲 20°", "pos": {
        "shoulder_pan": 0, "shoulder_lift": 10, "elbow_flex": 20,
        "forearm_roll": 0, "wrist_flex": 0, "wrist_roll": 0, "gripper": 50,
    }},
    {"name": "回零", "pos": {
        "shoulder_pan": 0, "shoulder_lift": 0, "elbow_flex": 0,
        "forearm_roll": 0, "wrist_flex": 0, "wrist_roll": 0, "gripper": 100,
    }},
    {"name": "夹爪开合", "pos": {
        "shoulder_pan": 0, "shoulder_lift": 0, "elbow_flex": 0,
        "forearm_roll": 0, "wrist_flex": 0, "wrist_roll": 0, "gripper": 0,
    }},
    {"name": "夹爪松开", "pos": {
        "shoulder_pan": 0, "shoulder_lift": 0, "elbow_flex": 0,
        "forearm_roll": 0, "wrist_flex": 0, "wrist_roll": 0, "gripper": 100,
    }},
]


def main():
    parser = argparse.ArgumentParser(description="Piper 机械臂动作测试")
    parser.add_argument("--port", default="/dev/ttyACM0", help="舵机总线串口 (默认: /dev/ttyACM0)")
    parser.add_argument("--delay", type=float, default=2.0, help="动作间隔秒数 (默认: 2.0)")
    args = parser.parse_args()

    cfg = PiperFollowerConfig(port=args.port)
    robot = make_robot_from_config(cfg)
    robot.connect()
    print(f"\nPiper 机械臂已连接 ({args.port})，开始动作测试...\n")

    try:
        for action in ACTIONS:
            print(f"[{action['name']}]")
            # 转换格式：{关节名} → {关节名.pos}
            goal = {f"{k}.pos": v for k, v in action["pos"].items()}
            robot.send_action(goal)
            time.sleep(args.delay)

        print("\n动作测试完成！")
    finally:
        robot.disconnect()
        print("已断开连接。")


if __name__ == "__main__":
    main()
