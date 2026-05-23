# Piper 外骨骼遥操 — 从零配置指南

本指南帮助你从零搭建 Piper 机械臂 + 外骨骼的遥操系统。

---

## 目录

1. [系统架构](#1-系统架构)
2. [硬件清单](#2-硬件清单)
3. [软件环境](#3-软件环境)
4. [Step 1 — 查找舵机端口](#4-step-1--查找舵机端口)
5. [Step 2 — 配置舵机 ID](#5-step-2--配置舵机-id)
6. [Step 3 — 单舵机测试](#6-step-3--单舵机测试)
7. [Step 4 — 创建自定义机器人配置](#7-step-4--创建自定义机器人配置)
8. [Step 5 — 安装 Piper SDK](#8-step-5--安装-piper-sdk)
9. [Step 6 — 探测 Piper 臂关节限位](#9-step-6--探测-piper-臂关节限位)
10. [Step 7 — 记录外骨骼零位](#10-step-7--记录外骨骼零位)
11. [Step 8 — 遥操](#11-step-8--遥操)
12. [全部脚本一览](#12-全部脚本一览)
13. [排错指南](#13-排错指南)

---

## 1. 系统架构

```
外骨骼（穿在操作者身上）              Piper 机械臂
┌──────────────────────┐          ┌──────────────────┐
│ 7 × STS3215 舵机     │   USB    │ CAN 总线          │
│ 串口 → 读取角度      │ ─────→   │ JointCtrl 控制   │
│                      │          │ GripperCtrl 控制  │
└──────────────────────┘          └──────────────────┘
         ↓  角度映射  ↓
  外骨骼动多少 → 机械臂动多少
```

**核心逻辑**：外骨骼每个关节的角度变化量，经过缩放和方向取反后，直接作为 Piper 臂的目标角度发送。

---

## 2. 硬件清单

| 组件 | 数量 | 说明 |
|------|------|------|
| STS3215 舵机 | 7 | 外骨骼用（6 关节 + 1 夹爪） |
| USB 转串口控制板 | 1 | 连接外骨骼舵机总线 |
| Piper 机械臂 | 1 | 6-DOF + 夹爪（CAN 总线控制） |
| CAN 卡 | 1 | 电脑连接 Piper 臂 |
| 外接电源（6-8.4V） | 1 | 舵机总线供电（必须，USB 不够） |
| USB 线 | 若干 | |

---

## 3. 软件环境

### 3.1 Python 环境

```bash
# 推荐使用 uv 或 conda 创建 Python 3.12 环境
# 激活你的 lerobot 环境
source /home/ubuntu/uv/env/lerobot/bin/activate

# 验证
python --version  # 需要 >= 3.10
```

### 3.2 安装依赖

```bash
# LeRobot 已安装（自定义配置文件已添加）
# 安装 Piper SDK
uv pip install -e /home/ubuntu/Code/piper_sdk/
# 或
pip install -e /home/ubuntu/Code/piper_sdk/
```

验证安装：
```bash
python -c "
from piper_sdk import C_PiperInterface_V2
from lerobot.motors.feetech import FeetechMotorsBus
print('环境就绪')
"
```

### 3.3 串口权限

```bash
# 临时
sudo chmod 666 /dev/ttyACM0

# 永久（需要重新登录）
sudo usermod -a -G dialout $USER
```

---

## 4. Step 1 — 查找舵机端口

```bash
lerobot-find-port
```

输出示例：
```
Ports before disconnecting: ['/dev/ttyACM0', ...]
Remove the USB cable from your MotorsBus and press Enter when done.
The port of this MotorsBus is '/dev/ttyACM0'
```

记下端口号（如 `/dev/ttyACM0`）。

---

## 5. Step 2 — 配置舵机 ID

> 每次只连接 **一个** 舵机到控制板。

```bash
lerobot-setup-motors --robot.type=piper_follower --robot.port=/dev/ttyACM0
```

按提示操作，倒序配置 ID 7 → 1：

| 顺序 | 舵机 | ID |
|------|------|----|
| 1 | gripper (夹爪) | 7 |
| 2 | wrist_roll (腕部旋转) | 6 |
| 3 | wrist_flex (腕部俯仰) | 5 |
| 4 | forearm_roll (前臂旋转) | 4 |
| 5 | elbow_flex (肘部) | 3 |
| 6 | shoulder_lift (肩部) | 2 |
| 7 | shoulder_pan (底座) | 1 |

---

## 6. Step 3 — 单舵机测试

确认每个舵机能正常通信（无需外接电源，只需 USB）。

```bash
# 测试 ID 1
python src/lerobot/robots/piper_follower/scripts/test_single_motor.py \
    --port /dev/ttyACM0 --id 1

# 测试 ID 1 并转动 45°
python src/lerobot/robots/piper_follower/scripts/test_single_motor.py \
    --port /dev/ttyACM0 --id 1 --move 45

# 全量测试
for id in 1 2 3 4 5 6 7; do
    echo "=== ID $id ==="
    python src/lerobot/robots/piper_follower/scripts/test_single_motor.py \
        --port /dev/ttyACM0 --id $id
done
```

---

## 7. Step 4 — 创建自定义机器人配置

项目已提供 Piper 外骨骼的自定义配置，文件结构：

```
src/lerobot/robots/piper_follower/
├── __init__.py                    # 模块导出
├── config_piper_follower.py       # 配置类（端口、摄像头）
├── piper_follower.py              # 机器人实现（7 个 STS3215）
├── README.md                      # 本指南
└── scripts/
    ├── calibrate.py               # 外骨骼校准（需外接电源）
    ├── read_positions.py          # 读取一次关节位置
    ├── read_realtime.py           # 实时读取关节角度
    ├── test_single_motor.py       # 单舵机测试
    ├── test_movement.py           # 动作测试
    ├── scan_bus.py                # 扫描总线上所有舵机
    ├── diagnose_gripper.py        # 夹爪诊断
    ├── find_zero_pose.py          # 记录外骨骼零位
    ├── calibrate_piper_arm.py     # 探测 Piper 臂限位
    ├── compare_angles.py          # 外骨骼 vs Piper 角度对比
    ├── align.py                   # 角度对齐工具
    └── teleop.py                  # 遥操主程序
```

### 关节定义

| 外骨骼舵机 ID | 关节名 | 归一化模式 |
|:---:|---------|-----------|
| 1 | `shoulder_pan` | DEGREES |
| 2 | `shoulder_lift` | DEGREES |
| 3 | `elbow_flex` | DEGREES |
| 4 | `forearm_roll` | DEGREES |
| 5 | `wrist_flex` | DEGREES |
| 6 | `wrist_roll` | DEGREES |
| 7 | `gripper` | RANGE_0_100 |

如需创建其他机器人的自定义配置，参考 `config_piper_follower.py` 和 `piper_follower.py` 的模板。

---

## 8. Step 5 — 安装 Piper SDK

```bash
# 安装
pip install -e /home/ubuntu/Code/piper_sdk/

# 激活 CAN 接口
bash /home/ubuntu/Code/piper_sdk/piper_sdk/can_activate.sh can0 1000000

# 验证通信
python -c "
from piper_sdk import C_PiperInterface_V2
import time
p = C_PiperInterface_V2('can0')
p.ConnectPort()
while not p.EnablePiper():
    time.sleep(0.01)
print('连接成功')
print(p.GetArmJointMsgs().joint_state)
"
```

---

## 9. Step 6 — 探测 Piper 臂关节限位

> 将机械臂切换到手动模式（力矩关闭），可自由掰动。

```bash
python src/lerobot/robots/piper_follower/scripts/calibrate_piper_arm.py
```

操作流程：
1. 连接 Piper 臂
2. 对每个关节：
   - 🔹 掰到中位 → 按 Enter
   - ➡️ 掰到最大位置 → 按 Enter
   - ⬅️ 掰到最小位置 → 按 Enter
3. 脚本自动输出 `JOINT_LIMITS_PIPER` 配置

输出示例：
```
JOINT_LIMITS_PIPER = {
    "j0": (-155, 155),   # 底座旋转
    "j1": (-2, 195),     # 肩部抬升
    "j2": (-174, 2),     # 肘部弯曲
    "j3": (-102, 102),   # 前臂旋转
    "j4": (-74, 75),     # 腕部俯仰
    "j5": (-65, 187),    # 腕部旋转
}
```

将输出复制到 `teleop.py` 的 `JOINT_LIMITS_PIPER` 配置中。

---

## 10. Step 7 — 记录外骨骼零位

穿上外骨骼，摆到自然姿态：

```bash
python src/lerobot/robots/piper_follower/scripts/find_zero_pose.py \
    --port /dev/ttyACM0 --out zero_pose.json
```

这会记录当前各关节角度为"零位"，之后每次启动遥操时以此为基准。

---

## 11. Step 8 — 遥操

### 使用前准备

1. 激活 CAN 接口：`bash .../can_activate.sh can0 1000000`
2. 给外骨骼舵机总线上电（6-8.4V）
3. 给 Piper 机械臂上电
4. 穿戴好外骨骼，把 Piper 臂摆成**相同姿态**

### 试运行（不控制机械臂）

```bash
/home/ubuntu/uv/env/lerobot/bin/python \
    src/lerobot/robots/piper_follower/scripts/teleop.py \
    --port /dev/ttyACM0 --dry
```

### 正式遥操

```bash
/home/ubuntu/uv/env/lerobot/bin/python \
    src/lerobot/robots/piper_follower/scripts/teleop.py \
    --port /dev/ttyACM0
```

启动后：
1. 按 Enter 记录零位
2. 外骨骼角度变化会实时映射到 Piper 臂
3. 按 `q` 或 Ctrl+C 停止（机械臂保持使能，不会掉落）

### 手动调整映射

编辑 `teleop.py` 中的 `EXO_TO_PIPER_MAP`：

```python
EXO_TO_PIPER_MAP = [
    ("shoulder_pan",  1.0, True),   # (关节名, 缩放系数, 反向)
    ...
]
```

- **缩放系数**: 外骨骼转 1° → Piper 转 ?°
- **反向**: `True` 时角度方向取反

### 角度对比工具

实时对比外骨骼和 Piper 臂的角度：

```bash
/home/ubuntu/uv/env/lerobot/bin/python \
    src/lerobot/robots/piper_follower/scripts/align.py \
    --port /dev/ttyACM0 --save aligned.json
```

---

## 12. 全部脚本一览

| 脚本 | 用途 | 需外接电源 |
|------|------|:----------:|
| `test_single_motor.py` | 单舵机通信测试 | ❌ |
| `read_realtime.py` | 实时读取角度 | ❌ |
| `read_positions.py` | 读取一次角度 | ❌ |
| `scan_bus.py` | 扫描总线舵机 | ✅ |
| `diagnose_gripper.py` | 夹爪诊断 | ✅ |
| `find_zero_pose.py` | 记录外骨骼零位 | ❌(单)/✅(全) |
| `calibrate.py` | 外骨骼校准 | ✅ |
| `test_movement.py` | 动作测试 | ✅ |
| `calibrate_piper_arm.py` | 探测 Piper 臂限位 | ✅ |
| `align.py` | 外骨骼 vs Piper 角度对齐 | ✅ |
| `teleop.py` | **遥操主程序** | ✅ |
| `teleop_v1_stable.py` | 遥操 v1 稳定版备份 | ✅ |

### 遥操配置文件

编辑 `teleop.py` 顶部修改：

```python
JOINT_LIMITS_PIPER    # Piper 臂关节限位（从 calibrate_piper_arm.py 获取）
EXO_TO_PIPER_MAP      # 外骨骼→Piper 关节映射（缩放/方向）
DEADZONE = 1.0        # 防抖死区（度）
FILTER_ALPHA = 0.3    # 低通滤波系数
LOOP_HZ = 20          # 控制频率
```

---

## 13. 排错指南

### 外骨骼通信

| 现象 | 原因 | 解决 |
|------|------|------|
| `Permission denied: /dev/ttyACM0` | 无串口权限 | `sudo chmod 666 /dev/ttyACM0` |
| `Input voltage error` | 供电不足 | 使用外接电源 6-8.4V |
| `Incorrect status packet` | 夹爪接触不良 | 检查接线或临时排除夹爪 |
| 角度跳动 | 串口干扰 | 检查 USB 线/供电 |

### Piper 臂通信

| 现象 | 原因 | 解决 |
|------|------|------|
| CAN 不通 | 未激活 | `bash .../can_activate.sh can0 1000000` |
| 关节不动 | 未使能 | `EnablePiper()` 需返回 True |
| 关节掉电 | 超时保护 | 保持 10Hz+ 控制频率 |
| 反馈全 0 | 连接断开 | 重新启动 Piper |

### 遥操问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 方向反了 | 映射取反不对 | 改 `EXO_TO_PIPER_MAP` 的 `True/False` |
| 幅度不对 | 缩放系数 | 改 `scale` 参数 |
| 抖动 | 噪声 | 增大 `DEADZONE` 或减小 `FILTER_ALPHA` |
| 响应迟钝 | 频率太低 | 增大 `LOOP_HZ` |
| 启动时乱动 | 零位偏移 | 先 `--dry` 确认零位正确再正式运行 |

---

## 开发者笔记

### 文件结构

```
src/lerobot/robots/piper_follower/    ← 自定义机器人配置
src/lerobot/robots/utils.py            ← make_robot_from_config 注册
src/lerobot/scripts/lerobot_setup_motors.py  ← COMPATIBLE_DEVICES 注册
```

### CAN 单位

Piper SDK 关节角度单位：**0.001°**（millidegrees）。
- `JointCtrl` 发送时：`round(角度 * 1000)`
- `GetArmJointMsgs` 读出时：`原始值 / 1000 = 角度`

### 稳定版备份

`teleop_v1_stable.py` 是经验证可用的遥操版本，如需回退使用：

```bash
python src/lerobot/robots/piper_follower/scripts/teleop_v1_stable.py \
    --port /dev/ttyACM0
```
