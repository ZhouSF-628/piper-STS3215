#!/usr/bin/env python3
"""
Piper 机械臂 — 单舵机测试

在不接外接电源时使用。每次只连一个舵机到控制板，测试能否正常通信。

用法：
    # 测试单个舵机（比如 ID 1）
    python scripts/test_single_motor.py --port /dev/ttyACM0 --id 1

    # 测试并让它转 45 度
    python scripts/test_single_motor.py --port /dev/ttyACM0 --id 1 --move 45

    # 测试并让它回到 0 度
    python scripts/test_single_motor.py --port /dev/ttyACM0 --id 1 --move 0

全量测试（7 个舵机逐个测）：
    for id in 1 2 3 4 5 6 7; do
        echo "=== 测试舵机 ID $id ==="
        python scripts/test_single_motor.py --port /dev/ttyACM0 --id $id
    done
"""

import argparse
import logging
import time

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

logging.basicConfig(level=logging.WARNING)

MOTOR_NAME = "single_motor"


def main():
    parser = argparse.ArgumentParser(description="Piper 单舵机测试")
    parser.add_argument("--port", default="/dev/ttyACM0", help="串口 (默认: /dev/ttyACM0)")
    parser.add_argument("--id", type=int, required=True, help="舵机 ID (1-7)")
    parser.add_argument("--move", type=float, default=None, help="可选：发送目标角度并等待 N 秒后归零")
    args = parser.parse_args()

    # 创建只包含一个舵机的总线
    bus = FeetechMotorsBus(
        port=args.port,
        motors={
            MOTOR_NAME: Motor(args.id, "sts3215", MotorNormMode.DEGREES),
        },
    )

    # 设置默认校准（0-4095 满量程），不需要先跑完整校准就能测试
    bus.calibration = {
        MOTOR_NAME: MotorCalibration(
            id=args.id,
            drive_mode=0,
            homing_offset=2048,
            range_min=0,
            range_max=4095,
        ),
    }

    print(f"连接舵机 ID={args.id} ...")
    bus.connect()
    print("  已连接！")

    # 配置位置模式 + PID（力矩关闭状态下写入）
    with bus.torque_disabled():
        bus.write("Operating_Mode", MOTOR_NAME, OperatingMode.POSITION.value)
        bus.write("P_Coefficient", MOTOR_NAME, 16)
        bus.write("I_Coefficient", MOTOR_NAME, 0)
        bus.write("D_Coefficient", MOTOR_NAME, 32)

    # 读取当前位置
    pos = bus.read("Present_Position", MOTOR_NAME)
    print(f"  当前位置: {pos:.1f}°")

    # 如果需要移动
    if args.move is not None:
        print(f"  移动到 {args.move:.0f}° ...")
        bus.write("Goal_Position", MOTOR_NAME, args.move)
        time.sleep(2)
        pos_after = bus.read("Present_Position", MOTOR_NAME)
        print(f"  移动后位置: {pos_after:.1f}°")

        if args.move != 0:
            print("  归零 ...")
            bus.write("Goal_Position", MOTOR_NAME, 0)
            time.sleep(2)
            pos_zero = bus.read("Present_Position", MOTOR_NAME)
            print(f"  归零后位置: {pos_zero:.1f}°")

    try:
        bus.disconnect(disable_torque=True)
    except Exception as e:
        # USB 供电不足时断开可能报 Overload error，不影响测试结论
        print(f"  [注意] 断开时出现异常（通常因 USB 供电不足）: {e}")

    print(f"  舵机 ID={args.id} 测试完成！")


if __name__ == "__main__":
    main()
