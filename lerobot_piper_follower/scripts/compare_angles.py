#!/usr/bin/env python3
"""
外骨骼 ↔ Piper 臂 角度对比

同时读取外骨骼（串口）和 Piper 臂（CAN）的角度并排显示。
手动掰其中一个，看两者的角度变化方向和幅度是否一致。

用法：
    /home/ubuntu/uv/env/lerobot/bin/python \
        src/lerobot/robots/piper_follower/scripts/compare_angles.py \
        --port /dev/ttyACM0 --zero zero_pose.json
"""

import argparse
import json
import sys
import select
import termios
import tty
import time

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus
from piper_sdk import C_PiperInterface_V2

MILLI_DEG = 1000

JOINT_LABELS = ["j0 底座", "j1 肩部", "j2 肘部", "j3 前臂", "j4 腕俯仰", "j5 腕旋转"]


def main():
    parser = argparse.ArgumentParser(description="外骨骼 ↔ Piper 臂角度对比")
    parser.add_argument("--port", default="/dev/ttyACM0", help="外骨骼串口")
    parser.add_argument("--zero", default="zero_pose.json", help="零位文件")
    args = parser.parse_args()

    # 加载零位
    with open(args.zero) as f:
        zero_offset = json.load(f)
    # ---- 连接外骨骼（只读 6 个关节，排除 gripper 避免通信干扰） ----
    motors_dict = {}
    exo_joints = [
        ("shoulder_pan", 1),
        ("shoulder_lift", 2),
        ("elbow_flex", 3),
        ("forearm_roll", 4),
        ("wrist_flex", 5),
        ("wrist_roll", 6),
    ]
    for name, id_ in exo_joints:
        motors_dict[name] = Motor(id_, "sts3215", MotorNormMode.DEGREES)

    calib = {
        name: MotorCalibration(id=m.id, drive_mode=0, homing_offset=2048, range_min=0, range_max=4095)
        for name, m in motors_dict.items()
    }

    gripper_included = False

    print("连接外骨骼 ...", end="", flush=True)
    exo_bus = FeetechMotorsBus(port=args.port, motors=motors_dict, calibration=calib)
    exo_bus.connect(handshake=False)
    print(" ✅")

    # ---- 连接 Piper 臂 ----
    print("连接 Piper 臂 ...", end="", flush=True)
    piper = C_PiperInterface_V2("can0")
    piper.ConnectPort()
    print(" ✅")

    print("掰动外骨骼或 Piper 臂，角度实时对比。按 Ctrl+C 退出")
    print()

    # 终端设置（非阻塞键盘）
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    try:
        while True:
            # 读外骨骼（自动重试 3 次）
            obs = {}
            for retry in range(3):
                try:
                    obs = exo_bus.sync_read("Present_Position")
                    break
                except Exception:
                    time.sleep(0.05)
            exo_deg = []
            for name in motors_dict:
                raw = obs.get(name, 0)
                exo_deg.append(raw - zero_offset.get(name, 0))

            # 夹爪跳过（需要单独总线，避免干扰 6 个关节的 sync_read）
            exo_grip = "--"

            # 读 Piper 臂
            try:
                js = piper.GetArmJointMsgs().joint_state
                piper_raw = [js.joint_1, js.joint_2, js.joint_3,
                             js.joint_4, js.joint_5, js.joint_6]
            except Exception:
                piper_raw = [0] * 6
            piper_deg = [round(r / MILLI_DEG, 1) for r in piper_raw]

            piper_grip = "--"

            # 显示
            lines = [f"[{time.strftime('%H:%M:%S')}]"]
            lines.append(f"  {'─'*50}")
            lines.append(f"  关节      外骨骼(°)    Piper臂(°)    方向一致?")
            lines.append(f"  {'─'*50}")
            for j in range(6):
                diff = round(exo_deg[j] - piper_deg[j], 1)
                same = "✓" if abs(diff) < 180 else "?"
                lines.append(f"  {JOINT_LABELS[j]:8s}  {exo_deg[j]:+8.1f}    {piper_deg[j]:+8.1f}     {same}")
            lines.append(f"  {'─'*50}")
            lines.append(f"  Ctrl+C 退出")

            # 刷新显示
            text = "\n".join(lines)
            print("\033[2J\033[H" + text, end="", flush=True)

            # 检查退出
            if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                sys.stdin.read(1)
                break

    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        exo_bus.disconnect(disable_torque=False)
        piper.DisconnectPort()
        print("\n退出。")


if __name__ == "__main__":
    main()
