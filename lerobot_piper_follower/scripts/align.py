#!/usr/bin/env python3
"""
外骨骼 ←→ Piper 臂 角度对齐

显示外骨骼真实角度、Piper 实际角度，以及映射关系。

用法：
    /home/ubuntu/uv/env/lerobot/bin/python \
        src/lerobot/robots/piper_follower/scripts/align.py --port /dev/ttyACM0

按键:
    s - 保存当前对齐数据到文件
    q - 退出
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

EXO_JOINTS = [
    ("shoulder_pan", 1),
    ("shoulder_lift", 2),
    ("elbow_flex", 3),
    ("forearm_roll", 4),
    ("wrist_flex", 5),
    ("wrist_roll", 6),
]

JOINT_NAMES = ["j0 底座", "j1 肩部", "j2 肘部", "j3 前臂", "j4 腕俯仰", "j5 腕旋转"]


def main():
    parser = argparse.ArgumentParser(description="外骨骼 ↔ Piper 臂角度对齐")
    parser.add_argument("--port", default="/dev/ttyACM0", help="外骨骼串口")
    parser.add_argument("--save", default=None, help="保存对齐数据到文件")
    args = parser.parse_args()

    # ---- 连接外骨骼 ----
    motors = {}
    for name, id_ in EXO_JOINTS:
        motors[name] = Motor(id_, "sts3215", MotorNormMode.DEGREES)
    calib = {name: MotorCalibration(id=m.id, drive_mode=0, homing_offset=2048, range_min=0, range_max=4095)
             for name, m in motors.items()}
    exo_bus = FeetechMotorsBus(port=args.port, motors=motors, calibration=calib)
    print("外骨骼 ...", end="", flush=True)
    exo_bus.connect(handshake=False)
    print(" OK")

    # ---- 连接 Piper ----
    print("Piper ...", end="", flush=True)
    piper = C_PiperInterface_V2("can0")
    piper.ConnectPort()
    while not piper.EnablePiper():
        time.sleep(0.01)
    piper.MotionCtrl_2(0x01, 0x01, 30, 0x00)
    piper.GripperCtrl(0, 1000, 0x01, 0)
    time.sleep(0.5)
    print("OK\n")

    fd = sys.stdin.fileno()
    old_attr = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    saved = False

    try:
        while True:
            # 读外骨骼
            try:
                obs = exo_bus.sync_read("Present_Position")
            except Exception:
                obs = {}
            exo_raw = []
            for name, _ in EXO_JOINTS:
                exo_raw.append(obs.get(name, 0))

            # 读 Piper
            try:
                js = piper.GetArmJointMsgs().joint_state
                piper_raw = [js.joint_1, js.joint_2, js.joint_3, js.joint_4, js.joint_5, js.joint_6]
            except Exception:
                piper_raw = [0] * 6
            piper_deg = [round(v / MILLI_DEG, 1) for v in piper_raw]

            # 显示
            lines = []
            lines.append("=" * 70)
            lines.append("  关节   外骨骼实际(°)   Piper实际(°)    映射:外骨骼→Piper   误差")
            lines.append("-" * 70)
            for j in range(6):
                exo = round(exo_raw[j], 1)
                pip = piper_deg[j]
                # 简单的映射: 把外骨骼角度映射到 Piper 范围
                # 暂用 1:1 映射 + 偏移
                mapped = round(exo - (exo - pip), 1)  # place holder
                err = round(pip - exo, 1)
                lines.append(f"  {JOINT_NAMES[j]:8s}  {exo:+8.1f}        {pip:+8.1f}        {exo:+7.1f}→{pip:+6.1f}       {err:+5.1f}")

            lines.append("=" * 70)
            lines.append("  [s]保存对齐数据  [q]退出")

            print("\033[2J\033[H" + "\n".join(lines), end="", flush=True)

            if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                key = sys.stdin.read(1)
                if key == "q":
                    break
                elif key == "s" and args.save:
                    data = {}
                    for j, (name, _) in enumerate(EXO_JOINTS):
                        data[name] = round(exo_raw[j], 1)
                        data[f"piper_j{j}"] = piper_deg[j]
                    with open(args.save, "w") as f:
                        json.dump(data, f, indent=2)
                    saved = True
                    print(f"\n  ✅ 已保存到 {args.save}")
                    time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
        exo_bus.disconnect(disable_torque=False)
        piper.DisconnectPort()
        print(f"\n退出。{'已保存' if saved else ''}")

if __name__ == "__main__":
    main()
