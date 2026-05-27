#!/usr/bin/env python3
"""
找零位 — 记录外骨骼各关节在"自然姿态"下的角度。

用法：
    1. 穿上外骨骼，手臂自然下垂/摆一个舒服的姿态
    2. 运行本脚本，它会记录当前所有角度
    3. 这些角度将作为遥操的"零位偏移"

遥操时：发送角度 = 当前读取角度 - 零位偏移
"""

import argparse
import json
import logging
import time

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

logging.basicConfig(level=logging.WARNING)

DEFAULT_JOINT_NAMES = {
    1: "shoulder_pan",
    2: "shoulder_lift",
    3: "elbow_flex",
    4: "forearm_roll",
    5: "wrist_flex",
    6: "wrist_roll",
    7: "gripper",
}


def main():
    parser = argparse.ArgumentParser(description="记录外骨骼零位")
    parser.add_argument("--port", default="/dev/ttyACM0", help="串口 (默认: /dev/ttyACM0)")
    parser.add_argument("--ids", type=int, nargs="+", default=list(range(1, 8)), help="舵机 ID 列表")
    parser.add_argument("--out", default=None, help="保存零位文件路径 (默认: zero_pose.json)")
    args = parser.parse_args()

    if args.out is None:
        args.out = "zero_pose.json"

    motors_dict = {}
    for id_ in args.ids:
        name = DEFAULT_JOINT_NAMES.get(id_, f"motor_{id_}")
        motors_dict[name] = Motor(id_, "sts3215", MotorNormMode.DEGREES)

    bus = FeetechMotorsBus(port=args.port, motors=motors_dict)
    bus.calibration = {
        name: MotorCalibration(id=m.id, drive_mode=0, homing_offset=2048, range_min=0, range_max=4095)
        for name, m in motors_dict.items()
    }

    bus.connect(handshake=False)
    print("已连接。请把外骨骼摆到自然姿态，按 Enter 记录零位...")
    input()

    # 连续读取取平均（自动跳过不响应的舵机）
    readings = {name: [] for name in motors_dict}
    for i in range(10):
        for retry in range(3):  # 每帧最多重试 3 次
            try:
                obs = bus.sync_read("Present_Position")
                for name in motors_dict:
                    if name in obs:
                        readings[name].append(obs[name])
                break
            except Exception:
                if retry == 2:
                    pass  # 3 次都不行就跳过这帧
                time.sleep(0.02)
        time.sleep(0.05)

    # 去掉没读到数据的舵机
    alive_motors = [name for name in motors_dict if readings[name]]
    dead_motors = [name for name in motors_dict if not readings[name]]
    if dead_motors:
        print(f"  注意：以下舵机未响应，已跳过: {', '.join(dead_motors)}")

    zero_pose = {}
    print("\n零位记录完毕：")
    for name in alive_motors:
        avg = sum(readings[name]) / len(readings[name])
        zero_pose[name] = round(avg, 1)
        print(f"  {name:15s} = {zero_pose[name]:7.1f}°")

    with open(args.out, "w") as f:
        json.dump(zero_pose, f, indent=2)
    print(f"\n已保存到 {args.out}")

    try:
        bus.disconnect(disable_torque=True)
    except Exception:
        bus.port_handler.closePort()


if __name__ == "__main__":
    main()
