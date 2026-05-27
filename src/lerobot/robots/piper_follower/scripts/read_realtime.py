#!/usr/bin/env python3
"""
Piper 外骨骼 — 实时读取舵机角度

持续读取指定舵机的当前位置并实时显示，用于遥操作调试。

用法：
    # 读取单个舵机（默认）
    python scripts/read_realtime.py --port /dev/ttyACM0 --ids 1

    # 同时读取多个舵机
    python scripts/read_realtime.py --port /dev/ttyACM0 --ids 1 2 3

    # 读取全部 7 个舵机
    python scripts/read_realtime.py --port /dev/ttyACM0 --ids 1 2 3 4 5 6 7

    # 指定刷新频率（默认 20Hz，即每秒 20 次）
    python scripts/read_realtime.py --port /dev/ttyACM0 --ids 1 --hz 50

    # 记录到文件
    python scripts/read_realtime.py --port /dev/ttyACM0 --ids 1 --log positions.csv

退出：
    按 Ctrl+C 停止
"""

import argparse
import csv
import logging
import time
from datetime import datetime

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus

logging.basicConfig(level=logging.WARNING)

# 默认关节名（ID 1-7）
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
    parser = argparse.ArgumentParser(description="Piper 外骨骼实时角度读取")
    parser.add_argument("--port", default="/dev/ttyACM0", help="串口 (默认: /dev/ttyACM0)")
    parser.add_argument("--ids", type=int, nargs="+", default=[1], help="舵机 ID 列表 (默认: 1)")
    parser.add_argument("--hz", type=float, default=20, help="刷新频率 (默认: 20)")
    parser.add_argument("--ignore-missing", action="store_true", help="跳过舵机存在检测（部分舵机不在线时使用）")
    parser.add_argument("--log", default=None, help="可选：保存到 CSV 文件路径")
    args = parser.parse_args()

    # 构建 motors dict
    motors_dict = {}
    for id_ in args.ids:
        name = DEFAULT_JOINT_NAMES.get(id_, f"motor_{id_}")
        motors_dict[name] = Motor(id_, "sts3215", MotorNormMode.DEGREES)

    # 创建总线
    bus = FeetechMotorsBus(port=args.port, motors=motors_dict)

    # 默认校准（满量程 0-4095）
    bus.calibration = {
        name: MotorCalibration(id=m.id, drive_mode=0, homing_offset=2048, range_min=0, range_max=4095)
        for name, m in motors_dict.items()
    }

    print(f"连接 {args.port} ...")
    bus.connect(handshake=not args.ignore_missing)
    if args.ignore_missing:
        print("  跳过舵机存在检测（部分舵机可能不在线）")
    print("已连接！按 Ctrl+C 停止\n")

    # CSV 日志
    csv_writer = None
    csv_file = None
    if args.log:
        csv_file = open(args.log, "w", newline="")
        fieldnames = ["timestamp"] + list(motors_dict.keys())
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        csv_writer.writeheader()

    interval = 1.0 / args.hz
    try:
        while True:
            start = time.perf_counter()

            # 同步读取所有舵机位置
            try:
                raw_positions = bus.sync_read("Present_Position")
            except Exception:
                # 供电不足时通信可能中断，跳过本轮
                time.sleep(interval)
                continue

            # 转成带关节名的 dict
            pos_dict = {}
            line_parts = []
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            for name in motors_dict:
                raw = raw_positions.get(name, 0)
                pos_dict[name] = raw
                line_parts.append(f"  {name:15s} {raw:8.1f}°")

            # 清屏并打印（使用 ANSI 上移实现原地刷新）
            print(f"\033[K[{ts}]", "".join(line_parts), end="\r")

            # CSV 记录
            if csv_writer:
                row = {"timestamp": ts}
                row.update(pos_dict)
                csv_writer.writerow(row)

            elapsed = time.perf_counter() - start
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\n停止读取。")
    finally:
        try:
            bus.disconnect(disable_torque=True)
        except Exception:
            pass  # 供电不足时断开可能报错，忽略
        if csv_file:
            csv_file.close()
            if args.log:
                print(f"数据已保存到: {args.log}")


if __name__ == "__main__":
    main()
