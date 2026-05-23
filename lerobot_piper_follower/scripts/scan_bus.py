#!/usr/bin/env python3
"""
扫描舵机总线，列出所有能响应 ID。

用法：
    python scripts/scan_bus.py --port /dev/ttyACM0

用于排查哪些舵机在线、哪些没响应。
"""

import argparse
import logging

from lerobot.motors.feetech import FeetechMotorsBus

logging.basicConfig(level=logging.WARNING)


def main():
    parser = argparse.ArgumentParser(description="Piper 舵机总线扫描")
    parser.add_argument("--port", default="/dev/ttyACM0", help="串口 (默认: /dev/ttyACM0)")
    args = parser.parse_args()

    print(f"扫描 {args.port} ...")
    bus = FeetechMotorsBus(port=args.port, motors={})
    try:
        bus.connect(handshake=False)
    except Exception as e:
        print(f"连接失败: {e}")
        return

    print("\n扫描 ID 1~253 中，请稍候...")
    found = []
    for id_ in range(1, 254):
        try:
            model = bus.ping(id_)
            if model is not None:
                found.append((id_, model))
                print(f"  ID {id_:3d} → 型号 {model}")
        except Exception:
            pass

    print(f"\n找到 {len(found)} 个舵机。")
    if found:
        ids = [str(id_) for id_, _ in found]
        print("在线 ID:", ", ".join(ids))
    else:
        print("没有找到任何舵机。请检查接线和电源。")

    try:
        bus.disconnect(disable_torque=True)
    except Exception:
        bus.port_handler.closePort()


if __name__ == "__main__":
    main()
