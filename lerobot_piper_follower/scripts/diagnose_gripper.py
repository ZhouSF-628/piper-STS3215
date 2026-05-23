#!/usr/bin/env python3
"""
Gripper 诊断 — 检查 gripper 舵机的原始通信状态

用法：
    python scripts/diagnose_gripper.py --port /dev/ttyACM0
"""

import argparse
import logging
import time

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

logging.basicConfig(level=logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="Gripper 诊断")
    parser.add_argument("--port", default="/dev/ttyACM0", help="串口 (默认: /dev/ttyACM0)")
    args = parser.parse_args()

    # 用 DEGREES 模式创建 bus，只含 gripper
    bus = FeetechMotorsBus(
        port=args.port,
        motors={"gripper": Motor(7, "sts3215", MotorNormMode.DEGREES)},
    )
    bus.calibration = {
        "gripper": MotorCalibration(id=7, drive_mode=0, homing_offset=2048, range_min=0, range_max=4095),
    }

    print(f"连接 {args.port} ...")
    try:
        bus.connect(handshake=False)
    except Exception as e:
        print(f"连接失败: {e}")
        return
    print("已连接\n")

    # 1. Ping 测试
    print("1. Ping ID 7 ...")
    model = bus.ping(7)
    if model is None:
        print("   ❌ 没有响应！检查接线")
        try:
            bus.disconnect(disable_torque=True)
        except Exception:
            bus.port_handler.closePort()
        return
    print(f"   ✅ 型号 {model}\n")

    # 2. 读原始值
    print("2. 读取 Present_Position（原始值）...")
    for i in range(5):
        try:
            raw = bus.read("Present_Position", "gripper")
        except Exception:
            raw = None
        print(f"   第 {i+1} 次: 原始值 = {raw}")
        time.sleep(0.2)

    # 3. 如果原始值是 0，写入一个位置看看能不能动
    if raw is not None and raw < 100:
        print(f"\n3. 当前原始值 ≈ {raw}（接近 0），尝试写入 Goal_Position...")
        with bus.torque_disabled():
            bus.write("Operating_Mode", "gripper", 0)  # POSITION mode
            bus.write("P_Coefficient", "gripper", 16)
            bus.write("I_Coefficient", "gripper", 0)
            bus.write("D_Coefficient", "gripper", 32)

        print("   发送目标值 2048（中位）...")
        bus.write("Goal_Position", "gripper", 2048)
        time.sleep(1)
        raw_after = bus.read("Present_Position", "gripper")
        print(f"   移动后原始值 = {raw_after}")
        bus.write("Goal_Position", "gripper", 0)
        time.sleep(1)
    else:
        print(f"\n3. 原始值 {raw}，正常")

    # 4. 尝试读 RANGE_0_100（归一化后）
    print("\n4. 改用 RANGE_0_100 模式读取：")
    bus.motors["gripper"].norm_mode = MotorNormMode.RANGE_0_100
    for i in range(3):
        val = bus.read("Present_Position", "gripper")
        print(f"   第 {i+1} 次: {val:.1f}%")
        time.sleep(0.2)

    try:
        bus.disconnect(disable_torque=True)
    except Exception:
        bus.port_handler.closePort()
    print("\n诊断完成。")


if __name__ == "__main__":
    main()
