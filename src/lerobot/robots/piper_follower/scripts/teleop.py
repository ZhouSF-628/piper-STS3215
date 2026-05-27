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
import json
import os
import select
import sys
import termios
import tty
import time

# 使用仓库自带的 _vendor 电机控制库（避免依赖完整的 LeRobot 安装）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

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

DEADZONE = 1.0               # 死区（度）：小于此值的变化忽略
FILTER_ALPHA = 0.5            # 低通滤波系数（0-1）。结合 RATE_LIMIT 防尖峰，不需要过重平滑
RATE_LIMIT = 5.0              # 滑率限制（度/帧）：每周期最大角度变化
LOOP_HZ = 80                  # 控制循环频率（Hz）
MILLI_DEG = 1000
DISPLAY_EVERY = 8            # 每 N 帧刷新一次显示（控制频率 80Hz 时显示 10Hz）

# 夹爪映射: 外骨骼 x% → Piper 闭合, y% → Piper 张开
GRIP_CLOSE_PCT = 42   # 握拳时外骨骼舵机百分比
GRIP_OPEN_PCT = 30    # 张开时外骨骼舵机百分比

EXO_JOINTS = [
    ("shoulder_pan", 1), ("shoulder_lift", 2), ("elbow_flex", 3),
    ("forearm_roll", 4), ("wrist_flex", 5), ("wrist_roll", 6),
]
# ======================================

CALIB_DIR = os.path.expanduser("~/.config/piper_teleop")
CALIB_FILE = os.path.join(CALIB_DIR, "calibration.json")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--calibrate", action="store_true",
                        help="一次初始化校准：记录外骨骼与机械臂的同步姿态并保存")
    parser.add_argument("--no-display", action="store_true",
                        help="关闭实时显示，减少终端输出开销")
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

    # ---- Piper 连接 ----
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
        print(" OK")
    else:
        print("【试运行模式】\n")

    # ---- 初始化校准（--calibrate） ----
    if args.calibrate:
        if args.dry:
            print("错误：校准需要连接真实机械臂，不能与 --dry 同时使用")
            return
        print("校准模式：请将外骨骼和机械臂摆成同一姿态...")
        input("摆好后按 Enter...\n")
        try:
            obs = exo.sync_read("Present_Position")
        except Exception:
            obs = {}
        exo_calib = [obs.get(name, 0) for name, _ in EXO_JOINTS]
        grip_calib = obs.get("gripper", 50.0)
        js = piper_handle.GetArmJointMsgs().joint_state
        piper_calib = [js.joint_1, js.joint_2, js.joint_3, js.joint_4, js.joint_5, js.joint_6]
        os.makedirs(CALIB_DIR, exist_ok=True)
        with open(CALIB_FILE, "w") as f:
            json.dump({"exo": exo_calib, "piper": piper_calib, "gripper": grip_calib}, f)
        print(f"校准完成 → {CALIB_FILE}")
        print(f"外骨骼零位: {[f'{v:.1f}' for v in exo_calib]}")
        print(f"机械臂零位: {[f'{v // 1000}.{v % 1000:03d}' for v in piper_calib]}")
        print(f"夹爪零位: {grip_calib:.0f}%")
        piper_handle.DisconnectPort()
        return

    # ---- 加载校准 ----
    if args.dry:
        exo_zero = [0.0] * 6
        piper_zero = [0] * 6
        grip_zero = 50.0
    elif os.path.exists(CALIB_FILE):
        with open(CALIB_FILE) as f:
            calib = json.load(f)
        exo_zero = calib.get("exo", [0.0] * 6)
        piper_zero = calib.get("piper", [0] * 6)
        grip_zero = calib.get("gripper", 50.0)
        print(f"已加载校准 ({CALIB_FILE})  夹爪零位: {grip_zero:.0f}%")
    else:
        print("未找到校准文件，请先运行 --calibrate")
        if piper_handle:
            piper_handle.DisconnectPort()
        return

    # ---- 自动追踪：机械臂跟随外骨骼当前姿态 ----
    if not args.dry:
        print("自动追踪外骨骼姿态...", end="", flush=True)
        try:
            obs = exo.sync_read("Present_Position")
        except Exception:
            obs = {}
        targets = [0] * 6
        for j, (name, scale, invert) in enumerate(EXO_TO_PIPER_MAP):
            raw = obs.get(name, exo_zero[j])
            delta = raw - exo_zero[j]
            direction = -1 if invert else 1
            pip_delta = delta * scale * direction
            pip_target_deg = piper_zero[j] / MILLI_DEG + pip_delta
            lim = JOINT_LIMITS_PIPER.get(f"j{j}")
            if lim:
                pip_target_deg = clamp(pip_target_deg, lim[0], lim[1])
            targets[j] = round(pip_target_deg * MILLI_DEG)
        piper_handle.JointCtrl(*targets)
        if "gripper" in obs:
            g = obs["gripper"]
            grip_target = int(clamp(
                (GRIP_CLOSE_PCT - g) * 100000 / (GRIP_CLOSE_PCT - GRIP_OPEN_PCT), 0, 100000
            ))
            piper_handle.GripperCtrl(grip_target, 1000, 0x01, 0)
        time.sleep(0.5)
        print(" OK\n")

    # ---- 外骨骼扭矩使能 ----
    if not args.dry:
        ok = 0
        fail = 0
        for name, _ in EXO_JOINTS:
            try:
                exo.enable_torque(motors=name, num_retry=2)
                ok += 1
            except Exception:
                fail += 1
        try:
            exo.enable_torque(motors="gripper", num_retry=2)
            ok += 1
        except Exception:
            fail += 1
        if fail == 0:
            print(f"外骨骼使能 OK（{ok} 舵机，扭矩常开，松手保持位置）\n")
        else:
            print(f"外骨骼使能: {ok} OK, {fail} 失败（检查供电电压）\n")

    # ---- 键盘设置 ----
    fd = sys.stdin.fileno()
    old_attr = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    # ---- 状态变量 ----
    prev_delta = [0.0] * 6
    interval = 1.0 / LOOP_HZ
    frame = 0

    display_hz = LOOP_HZ // DISPLAY_EVERY if not args.no_display else 0
    print(f"开始遥操 ({LOOP_HZ}Hz 控制, {display_hz}Hz 显示)  按 q 退出{' [试运行]' if args.dry else ''}")
    header = " 关节  | 外骨骼(°) | 变化量(°) | Piper目标(°) | Piper实际(°)"
    sep = "-" * 55

    try:
        while True:
            t0 = time.perf_counter()

            # 读外骨骼（包括夹爪）
            try:
                obs = exo.sync_read("Present_Position")
            except Exception:
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
                # 滑率限制：每周期变化不超过 RATE_LIMIT°，防止噪声尖峰
                delta = clamp(delta, prev_delta[j] - RATE_LIMIT, prev_delta[j] + RATE_LIMIT)
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

            # 发送关节（每帧发送，降低延迟）
            if piper_handle:
                try:
                    piper_handle.JointCtrl(*targets)
                except Exception:
                    pass

            # 夹爪控制（每帧发送）
            grip_piper = None
            if "gripper" in obs:
                g = obs["gripper"]
                grip_piper = int(clamp(
                    (GRIP_CLOSE_PCT - g) * 100000 / (GRIP_CLOSE_PCT - GRIP_OPEN_PCT), 0, 100000
                ))
                lines.append(f"  夹爪: {g:.0f}% → Piper {grip_piper//1000}%")
                if piper_handle:
                    try:
                        piper_handle.GripperCtrl(grip_piper, 1000, 0x01, 0)
                    except Exception:
                        pass
            else:
                lines.append(f"  夹爪: N/A")

            # 外骨骼扭矩保持：把当前位置回写 Goal_Position，松手即停
            if not args.dry and frame % 2 == 0:
                try:
                    hold = {}
                    for name, _ in EXO_JOINTS:
                        if name in obs:
                            hold[name] = obs[name]
                    if "gripper" in obs:
                        hold["gripper"] = obs["gripper"]
                    if hold:
                        exo.sync_write("Goal_Position", hold)
                except Exception:
                    pass

            # 显示（降低频率减少终端输出对控制循环的影响）
            if not args.no_display and frame % DISPLAY_EVERY == 0:
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
