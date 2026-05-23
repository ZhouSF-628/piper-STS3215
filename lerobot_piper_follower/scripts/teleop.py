#!/usr/bin/env python3
"""
Piper 外骨骼 → Piper 机械臂 遥操

用法：
    # 试运行
    /home/ubuntu/uv/env/lerobot/bin/python \
        src/lerobot/robots/piper_follower/scripts/teleop.py \
        --port /dev/ttyACM0 --dry

    # 正式遥操
    /home/ubuntu/uv/env/lerobot/bin/python \
        src/lerobot/robots/piper_follower/scripts/teleop.py \
        --port /dev/ttyACM0
"""

import argparse
import select
import sys
import termios
import tty
import time

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus
from piper_sdk import C_PiperInterface_V2

# ============== 可调参数 ==============
JOINT_LIMITS_PIPER = {
    "j0": (-155, 155), "j1": (-2, 195), "j2": (-174, 2),
    "j3": (-102, 102), "j4": (-74, 75), "j5": (-65, 187),
}

EXO_TO_PIPER_MAP = [
    ("shoulder_pan",  1.0, True),   # j0
    ("shoulder_lift", 1.0, True),   # j1
    ("elbow_flex",    1.0, True),   # j2
    ("forearm_roll",  1.0, True),   # j3
    ("wrist_flex",    1.0, True),   # j4
    ("wrist_roll",    1.0, True),   # j5
]

DEADZONE = 1.0
FILTER_ALPHA = 0.3
LOOP_HZ = 20
MILLI_DEG = 1000

# 夹爪映射: 外骨骼 x% → Piper 闭合, y% → Piper 张开
GRIP_CLOSE_PCT = 42   # 握拳时外骨骼舵机百分比
GRIP_OPEN_PCT = 30    # 张开时外骨骼舵机百分比

EXO_JOINTS = [
    ("shoulder_pan", 1), ("shoulder_lift", 2), ("elbow_flex", 3),
    ("forearm_roll", 4), ("wrist_flex", 5), ("wrist_roll", 6),
]
# ======================================


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args()

    # ---- 外骨骼（6 关节 + 夹爪） ----
    motors = {}
    for name, id_ in EXO_JOINTS:
        motors[name] = Motor(id_, "sts3215", MotorNormMode.DEGREES)
    motors["gripper"] = Motor(7, "sts3215", MotorNormMode.RANGE_0_100)
    calib = {n: MotorCalibration(id=m.id, drive_mode=0, homing_offset=2048, range_min=0, range_max=4095)
             for n, m in motors.items()}
    exo = FeetechMotorsBus(port=args.port, motors=motors, calibration=calib)
    print("外骨骼 ...", end="", flush=True)
    exo.connect(handshake=False)
    print(" OK")

    input("请将外骨骼和机械臂摆成同一姿态，然后按 Enter...\n")

    # ---- 记录外骨骼零位（含夹爪） ----
    try:
        obs0 = exo.sync_read("Present_Position")
    except Exception:
        obs0 = {}
    exo_zero = [obs0.get(name, 0) for name, _ in EXO_JOINTS]
    grip_zero = obs0.get("gripper", 50.0)
    print(f"外骨骼零位已记录  (夹爪: {grip_zero:.0f}%)")

    # ---- Piper ----
    piper_handle = None
    piper_zero = [0] * 6
    if not args.dry:
        print("Piper ...", end="", flush=True)
        piper_handle = C_PiperInterface_V2("can0")
        piper_handle.ConnectPort()
        while not piper_handle.EnablePiper():
            time.sleep(0.01)
        piper_handle.MotionCtrl_2(0x01, 0x01, 30, 0x00)
        piper_handle.GripperCtrl(0, 1000, 0x01, 0)
        time.sleep(1.0)
        js = piper_handle.GetArmJointMsgs().joint_state
        piper_zero = [js.joint_1, js.joint_2, js.joint_3, js.joint_4, js.joint_5, js.joint_6]
        piper_handle.JointCtrl(*piper_zero)
        time.sleep(0.3)
        print(" OK")
    else:
        print("【试运行模式】\n")

    # ---- 重新锁定零位 ----
    print("锁定零位...", end="", flush=True)
    try:
        obs_final = exo.sync_read("Present_Position")
    except Exception:
        obs_final = {}
    exo_zero = [obs_final.get(name, 0) for name, _ in EXO_JOINTS]
    grip_zero = obs_final.get("gripper", grip_zero)
    if piper_handle:
        try:
            js = piper_handle.GetArmJointMsgs().joint_state
            piper_zero = [js.joint_1, js.joint_2, js.joint_3, js.joint_4, js.joint_5, js.joint_6]
            piper_handle.JointCtrl(*piper_zero)
        except Exception:
            pass
    print(" OK\n")

    # ---- 键盘设置 ----
    fd = sys.stdin.fileno()
    old_attr = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    # ---- 状态变量 ----
    prev_delta = [0.0] * 6
    interval = 1.0 / LOOP_HZ
    frame = 0

    print(f"开始遥操 ({LOOP_HZ}Hz)  按 q 退出{' [试运行]' if args.dry else ''}")
    header = " 关节  | 外骨骼(°) | 变化量(°) | Piper目标(°) | Piper实际(°)"
    sep = "-" * 55

    try:
        while True:
            t0 = time.perf_counter()

            # 读外骨骼
            # 读外骨骼（包括夹爪）
            try:
                obs = exo.sync_read("Present_Position")
            except Exception:
                # sync_read 失败时，单独读 6 个关节，跳过夹爪
                obs = {}
                for n, _ in EXO_JOINTS:
                    try:
                        obs[n] = exo.read("Present_Position", n)
                    except Exception:
                        pass

            # 读 Piper 反馈
            fb_deg = [None] * 6
            if piper_handle:
                try:
                    js = piper_handle.GetArmJointMsgs().joint_state
                    fb_raw = [js.joint_1, js.joint_2, js.joint_3, js.joint_4, js.joint_5, js.joint_6]
                    fb_deg = [round(v / MILLI_DEG, 1) for v in fb_raw]
                except Exception:
                    pass

            # 计算目标
            targets = [0] * 6
            lines = [header, sep]
            for j, (name, scale, invert) in enumerate(EXO_TO_PIPER_MAP):
                raw = obs.get(name, exo_zero[j])
                delta = raw - exo_zero[j]
                if abs(delta) < DEADZONE:
                    delta = 0.0
                delta = FILTER_ALPHA * delta + (1 - FILTER_ALPHA) * prev_delta[j]
                prev_delta[j] = delta
                direction = -1 if invert else 1
                pip_delta = delta * scale * direction
                pip_target_deg = piper_zero[j] / MILLI_DEG + pip_delta
                lim = JOINT_LIMITS_PIPER.get(f"j{j}")
                if lim:
                    pip_target_deg = clamp(pip_target_deg, lim[0], lim[1])
                targets[j] = round(pip_target_deg * MILLI_DEG)
                fb_str = f"{fb_deg[j]:+8.1f}" if fb_deg[j] is not None else "      N/A"
                lines.append(f"  j{j}  |  {raw:+8.1f}   |  {delta:+8.1f}   |  {pip_target_deg:+8.1f}     |  {fb_str}")

            # 夹爪控制
            grip_piper = None
            if "gripper" in obs:
                g = obs["gripper"]
                grip_piper = int(clamp(
                    (GRIP_CLOSE_PCT - g) * 100000 / (GRIP_CLOSE_PCT - GRIP_OPEN_PCT), 0, 100000
                ))
                lines.append(f"  夹爪: {g:.0f}% → Piper {grip_piper//1000}%")
                if piper_handle and frame % 3 == 0:
                    try:
                        piper_handle.GripperCtrl(grip_piper, 1000, 0x01, 0)
                    except Exception:
                        pass
            else:
                lines.append(f"  夹爪: N/A")

            # 发送关节
            if piper_handle and frame % 2 == 0:
                try:
                    piper_handle.JointCtrl(*targets)
                except Exception:
                    pass

            # 显示
            print("\033[2J\033[H" + "\n".join(lines), end="", flush=True)

            # 按键
            if sys.stdin in select.select([sys.stdin], [], [], 0):
                if sys.stdin.read(1) == "q":
                    break

            frame += 1
            time.sleep(max(0, interval - (time.perf_counter() - t0)))

    except KeyboardInterrupt:
        print("\n\n停止遥操。")
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
        except Exception:
            pass
        try:
            exo.disconnect(disable_torque=False)
        except Exception:
            pass
        if piper_handle:
            piper_handle.DisconnectPort()
        print("已断开（机械臂保持使能）。")


if __name__ == "__main__":
    main()
