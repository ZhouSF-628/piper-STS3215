#!/usr/bin/env python3
"""
Piper 机械臂 — 手动关节限位探测（实时角度显示）

用法：
    1. 把机械臂切换到手动模式（力矩关闭）
    2. 运行本脚本
    3. 掰关节时数字实时跳动，按 Enter 锁定当前值
    4. 输出安全限位，可直接复制到 teleop.py

运行：
    cd ~/Code/lerobot
    /home/ubuntu/uv/env/lerobot/bin/python \
        src/lerobot/robots/piper_follower/scripts/calibrate_piper_arm.py
"""

import sys
import select
import termios
import tty
import time
from piper_sdk import C_PiperInterface_V2

# joint_1..6 单位是 0.001°，除以 1000 得到度
# 参考: piper_sdk/piper_msgs/msg_v2/feedback/arm_feedback_joint_states.py
MILLI_DEG = 1000

JOINT_NAMES = [
    "j0 (底座旋转)",
    "j1 (肩部抬升)",
    "j2 (肘部弯曲)",
    "j3 (前臂旋转)",
    "j4 (腕部俯仰)",
    "j5 (腕部旋转)",
]


def piper_to_deg(raw):
    return round(raw / MILLI_DEG, 1)


def live_read(piper, joint_idx, label, joint_names=JOINT_NAMES):
    """
    实时显示指定关节的角度，按 Enter 锁定当前值并返回。

    参数:
        piper: Piper 接口
        joint_idx: 要监视的关节索引 (0-5)
        label: 显示标签（如 "中位"、"最大"）
        joint_names: 关节名列表（用于全关节显示）
    """
    # 把终端设为 cbreak 模式（输入不回显，不用等 Enter）
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    try:
        while True:
            js_msg = piper.GetArmJointMsgs().joint_state
            all_raw = [
                js_msg.joint_1, js_msg.joint_2, js_msg.joint_3,
                js_msg.joint_4, js_msg.joint_5, js_msg.joint_6,
            ]
            current = round(all_raw[joint_idx] / MILLI_DEG, 1)

            # 显示所有关节状态，高亮当前关节
            parts = []
            for j in range(6):
                val_str = f"{round(all_raw[j] / MILLI_DEG, 1):6.1f}"
                if j == joint_idx:
                    parts.append(f">>> j{j} {val_str}° <<<")  # 当前关节高亮
                else:
                    parts.append(f"j{j} {val_str}")
            status = " | ".join(parts)

            print(f"\r  {label:6s}  {status}  [Enter 记录]", end="", flush=True)

            # 非阻塞检查 Enter
            if sys.stdin in select.select([sys.stdin], [], [], 0.05)[0]:
                sys.stdin.read(1)  # 消费 Enter
                print()
                return current, all_raw

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    print("=" * 60)
    print("Piper 机械臂 — 手动关节限位探测（实时角度）")
    print("=" * 60)
    print("\n步骤：")
    print("  1. 将机械臂切换到手动模式（力矩关闭）")
    print("  2. 运行本脚本")
    print("  3. 掰关节，数字实时跳动，按 Enter 锁定")
    print("  4. 每关节记录 3 个位置：中位 → 最大 → 最小")
    print("  5. 最后输出限位配置\n")

    input("准备好后按 Enter 开始连接...\n")

    print("连接 Piper 臂 ...")
    piper = C_PiperInterface_V2("can0")
    piper.ConnectPort()
    print("已连接。\n")

    print("请确保机械臂处于手动模式，按 Enter 开始探测...")
    input()

    limits = {}

    for joint_idx in range(6):
        name = JOINT_NAMES[joint_idx]
        print(f"\n{'='*55}")
        print(f"  关节 {name}")
        print(f"{'='*55}")

        print("  （掰动关节，数字实时变化，按 Enter 锁定）\n")

        # 中位
        mid_deg, _ = live_read(piper, joint_idx, "🔹中位")
        print(f"  📍 中位已记录: {mid_deg}°\n")

        # 最大
        max_deg, _ = live_read(piper, joint_idx, "➡️最大")
        print(f"  ✅ 最大已记录: {max_deg}°\n")

        # 最小
        min_deg, _ = live_read(piper, joint_idx, "⬅️最小")
        print(f"  ✅ 最小已记录: {min_deg}°\n")

        # 自动纠正顺序
        bounds = sorted([min_deg, max_deg])
        limits[f"j{joint_idx}"] = {
            "name": name,
            "mid": mid_deg,
            "min": bounds[0],
            "max": bounds[1],
        }
        print(f"  📊 范围: {bounds[0]}°  ~  {bounds[1]}°（中位: {mid_deg}°）")

    # 输出结果
    print("\n\n" + "=" * 60)
    print("  探测结果 — 复制到 teleop.py 的 JOINT_LIMITS_PIPER")
    print("=" * 60)
    print()
    print("JOINT_LIMITS_PIPER = {")
    for j in range(6):
        l = limits.get(f"j{j}", {"min": "?", "max": "?", "mid": "?"})
        print(f'    "j{j}": ({l["min"]}, {l["max"]}),  # {l["mid"]}° 中位')
    print("}")
    print()

    piper.DisconnectPort()
    print("已断开。")


if __name__ == "__main__":
    main()
