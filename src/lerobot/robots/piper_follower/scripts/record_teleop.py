#!/usr/bin/env python3
"""
遥操数据采集 — 先遥操，按 Enter 开始记录轨迹，再按 Enter 停止并保存。

用法：
    # 首次校准（只需一次）
    python src/lerobot/robots/piper_follower/scripts/record_teleop.py \\
        --port /dev/ttyACM0 --calibrate

    # 采集数据
    python src/lerobot/robots/piper_follower/scripts/record_teleop.py \\
        --port /dev/ttyACM0 --save-dir ./teleop_data

操作：
    启动后进入遥操模式，按 Enter 开始/停止采集
    按 q 退出
"""

import argparse
import json
import os
import select
import sys
import termios
import tty
import time

# 使用仓库自带的电机控制库
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

import numpy as np
import h5py
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
FILTER_ALPHA = 0.5
RATE_LIMIT = 5.0
LOOP_HZ = 100
MILLI_DEG = 1000

GRIP_CLOSE_PCT = 42
GRIP_OPEN_PCT = 30

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
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--save-dir", default="./teleop_data")
    parser.add_argument("--start-idx", type=int, default=1)
    parser.add_argument("--record-fps", type=float, default=0,
                        help="采集帧率（0=跟随控制循环实际帧率，如 50）")
    parser.add_argument("--cam-exposure", type=float, default=None,
                        help="可选：偏振相机曝光时间（如 200000.0）")
    parser.add_argument("--cam-gain", type=float, default=None)
    args = parser.parse_args()

    # ---- 可选偏振相机 ----
    wrist_cam = None
    if args.cam_exposure is not None:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                        '..', '..', '..', '..', '..', '..', '..',
                        'data_collect', 'src'))
        from arena_camera_interface import ArenaCameraAgent
        wrist_cam = ArenaCameraAgent(exposure_time=args.cam_exposure, gain=args.cam_gain)
        print(f"偏振相机: OK (曝光={args.cam_exposure}, gain={args.cam_gain})")

    # ---- 外骨骼 ----
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
        print(" OK")
    else:
        print("【试运行模式】\n")

    # ---- 校准 ----
    if args.calibrate:
        if args.dry:
            print("错误：校准时不能使用 --dry")
            return
        print("校准模式：请将外骨骼和机械臂摆成同一姿态...")
        input("摆好后按 Enter...\n")
        obs = exo.sync_read("Present_Position")
        exo_calib = [obs.get(name, 0) for name, _ in EXO_JOINTS]
        grip_calib = obs.get("gripper", 50.0)
        js = piper_handle.GetArmJointMsgs().joint_state
        piper_calib = [js.joint_1, js.joint_2, js.joint_3, js.joint_4, js.joint_5, js.joint_6]
        os.makedirs(CALIB_DIR, exist_ok=True)
        with open(CALIB_FILE, "w") as f:
            json.dump({"exo": exo_calib, "piper": piper_calib, "gripper": grip_calib}, f)
        print(f"校准完成 → {CALIB_FILE}")
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

    # ---- 自动追踪 ----
    if not args.dry:
        print("自动追踪外骨骼姿态...", end="", flush=True)
        obs = exo.sync_read("Present_Position")
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

    # ---- 外骨骼使能 ----
    if not args.dry:
        for name, _ in EXO_JOINTS:
            try:
                exo.enable_torque(motors=name, num_retry=2)
            except Exception:
                pass
        try:
            exo.enable_torque(motors="gripper", num_retry=2)
        except Exception:
            pass
        print("外骨骼使能 OK\n")

    # ---- 键盘设置 ----
    fd = sys.stdin.fileno()
    old_attr = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    # ---- 状态变量 ----
    prev_delta = [0.0] * 6
    interval = 1.0 / LOOP_HZ
    frame = 0
    episode = args.start_idx

    # ---- 录制状态 ----
    recording = False
    rec_buf = []            # [(timestamp, exo_state_7, piper_action_7), ...]
    rec_img_buf = []        # 可选图像

    os.makedirs(args.save_dir, exist_ok=True)

    print(f"开始遥操 ({LOOP_HZ}Hz)")
    print("操作: 按 Enter 开始/停止采集  按 q 退出\n")

    try:
        while True:
            t0 = time.perf_counter()

            # 读外骨骼
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
            exo_angles = [0.0] * 7  # 6 joints + gripper, 用于记录
            for j, (name, scale, invert) in enumerate(EXO_TO_PIPER_MAP):
                raw = obs.get(name, exo_zero[j])
                delta = raw - exo_zero[j]
                if abs(delta) < DEADZONE:
                    delta = 0.0
                delta = FILTER_ALPHA * delta + (1 - FILTER_ALPHA) * prev_delta[j]
                delta = clamp(delta, prev_delta[j] - RATE_LIMIT, prev_delta[j] + RATE_LIMIT)
                prev_delta[j] = delta
                direction = -1 if invert else 1
                pip_delta = delta * scale * direction
                pip_target_deg = piper_zero[j] / MILLI_DEG + pip_delta
                lim = JOINT_LIMITS_PIPER.get(f"j{j}")
                if lim:
                    pip_target_deg = clamp(pip_target_deg, lim[0], lim[1])
                targets[j] = round(pip_target_deg * MILLI_DEG)
                exo_angles[j] = raw

            # 夹爪
            grip_cmd = 0
            if "gripper" in obs:
                g = obs["gripper"]
                grip_cmd = int(clamp(
                    (GRIP_CLOSE_PCT - g) * 100000 / (GRIP_CLOSE_PCT - GRIP_OPEN_PCT), 0, 100000
                ))
                exo_angles[6] = g
            else:
                exo_angles[6] = 50.0

            # 发送关节
            if piper_handle:
                try:
                    piper_handle.JointCtrl(*targets)
                except Exception:
                    pass

            # 夹爪控制（每帧发送）
            if piper_handle and "gripper" in obs:
                try:
                    piper_handle.GripperCtrl(grip_cmd, 1000, 0x01, 0)
                except Exception:
                    pass

            # ---- 录制 ----
            now = time.time()
            if recording:
                action = np.array(targets + [grip_cmd / 100000.0], dtype=np.float32)
                state = np.array(exo_angles, dtype=np.float32)
                rec_buf.append((now, state, action))

                if wrist_cam:
                    raw = wrist_cam.get_raw_frame()
                    if raw is not None:
                        rec_img_buf.append(raw)

            # ---- 按键处理 ----
            if select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1)
                if key == "q":
                    if recording:
                        # 停止并保存
                        _save_segment(rec_buf, rec_img_buf, episode, args.save_dir, wrist_cam)
                        episode += 1
                        recording = False
                        rec_buf = []
                        rec_img_buf = []
                    break
                elif key in ("\r", "\n"):
                    if not recording:
                        recording = True
                        rec_buf = []
                        rec_img_buf = []
                        rec_start = time.time()
                        print(f"\n{'='*50}")
                        print(f"  >>> [{episode}] \u25cf 采集中 \u25cf  (Enter 停止, q 退出)")
                        print(f"{'='*50}")
                    else:
                        elapsed = time.time() - rec_start
                        recording = False
                        print(f"\n  >>> [{episode}] 停止, 保存中... ({len(rec_buf)} 帧, {elapsed:.0f}s)")
                        _save_segment(rec_buf, rec_img_buf, episode, args.save_dir, wrist_cam)
                        episode += 1
                        rec_buf = []
                        rec_img_buf = []
                        print(f"  >>> 准备就绪, 按 Enter 开始下一段\n")

            # 状态提示（每帧更新计时器）
            if recording:
                rec_elapsed = time.time() - rec_start
                rec_m, rec_s = divmod(int(rec_elapsed), 60)
                print(f"\r  \u25cf REC [{episode}]  {rec_m:02d}:{rec_s:02d}  |  {len(rec_buf)} 帧  |  Enter=停止  q=退出  ", end="", flush=True)
            elif frame == 0 or frame % (LOOP_HZ * 2) == 0:
                print(f"\r  \u25cb 待机  按 Enter 开始采集  按 q 退出{' [试运行]' if args.dry else ''}  ", end="", flush=True)

            frame += 1
            time.sleep(max(0, interval - (time.perf_counter() - t0)))

    except KeyboardInterrupt:
        print("\n\n停止遥操。")
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
        except Exception:
            pass
        if recording:
            _save_segment(rec_buf, rec_img_buf, episode, args.save_dir, wrist_cam)
            episode += 1
        try:
            exo.disconnect(disable_torque=False)
        except Exception:
            pass
        if piper_handle:
            piper_handle.DisconnectPort()
        if wrist_cam:
            wrist_cam.close()
        print(f"数据保存至: {args.save_dir}/")
        print("已断开。")


def _save_segment(rec_buf, rec_img_buf, episode, save_dir, wrist_cam):
    """将一段录制数据保存为 HDF5 文件."""
    if not rec_buf:
        print("    [跳过] 无数据")
        return

    ts = np.array([r[0] for r in rec_buf], dtype=np.float64)
    states = np.stack([r[1] for r in rec_buf], axis=0)   # (N, 7)
    actions = np.stack([r[2] for r in rec_buf], axis=0)  # (N, 7)

    # 计算帧率
    duration = ts[-1] - ts[0]
    fps = len(rec_buf) / duration if duration > 0 else 0

    fname = f"teleop_{episode:03d}.h5"
    fpath = os.path.join(save_dir, fname)
    with h5py.File(fpath, "w") as f:
        f.create_dataset("state", data=states, dtype=np.float32, compression="gzip", chunks=True)
        f.create_dataset("action", data=actions, dtype=np.float32, compression="gzip", chunks=True)
        f.create_dataset("timestamp", data=ts, dtype=np.float64)
        f.attrs["num_frames"] = len(rec_buf)
        f.attrs["fps"] = fps
        f.attrs["episode"] = episode
        # 保存可选的图像
        if rec_img_buf and wrist_cam:
            # 计算偏振
            from utils import compute_aop_dop_from_raw
            s0_list, aop_list, dop_list = [], [], []
            for raw in rec_img_buf:
                s, a, d = compute_aop_dop_from_raw(raw)
                s0_list.append(s.astype(np.float32))
                aop_list.append(a.astype(np.float32))
                dop_list.append(d.astype(np.float32))
            f.create_dataset("s0", data=np.stack(s0_list, axis=0), compression="gzip", chunks=True)
            f.create_dataset("aop", data=np.stack(aop_list, axis=0), dtype=np.float32)
            f.create_dataset("dop", data=np.stack(dop_list, axis=0), dtype=np.float32)
            f.attrs["has_image"] = True
        else:
            f.attrs["has_image"] = False

    print(f"    ✓ {fname}  ({len(rec_buf)} 帧, {fps:.1f} Hz)")


if __name__ == "__main__":
    main()
