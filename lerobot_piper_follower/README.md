# Piper 外骨骼遥操 — 从零配置指南

本指南帮助你从零搭建 Piper 机械臂 + 外骨骼的遥操系统。

---

## 目录

1. [系统架构](#1-系统架构)
2. [硬件清单](#2-硬件清单)
3. [软件环境](#3-软件环境)
4. [外骨骼舵机配置](#4-外骨骼舵机配置)
   - 4.1 [查找舵机端口](#41-查找舵机端口)
   - 4.2 [配置舵机 ID](#42-配置舵机-id)
   - 4.3 [测试舵机通信](#43-测试舵机通信)
   - 4.4 [创建自定义机器人配置](#44-创建自定义机器人配置)
5. [Piper 机械臂配置](#5-piper-机械臂配置)
   - 5.1 [安装 Piper SDK](#51-安装-piper-sdk)
   - 5.2 [Piper 臂关节限位探测](#52-piper-臂关节限位探测)
6. [遥操](#6-遥操)
   - 6.1 [记录外骨骼零位](#61-记录外骨骼零位)
   - 6.2 [试运行](#62-试运行)
   - 6.3 [正式遥操](#63-正式遥操)
   - 6.4 [手动调整映射](#64-手动调整映射)
7. [全部脚本一览](#7-全部脚本一览)
8. [排错指南](#8-排错指南)

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

参考 [LeRobot SO-101 教程](https://huggingface.co/docs/lerobot/so101) 搭建 LeRobot 开发环境。

```bash
# 激活你的 Python 环境
source path_to_your_env/bin/activate

# 验证
python --version  # 需要 >= 3.10
```

### 3.2 安装 Piper SDK

参考 [Piper SDK GitHub](https://github.com/agilexrobotics/piper_sdk/tree/master) 安装。

```bash
# 从本地源码安装
pip install -e path_to_piper_sdk/

# 验证
python -c "from piper_sdk import C_PiperInterface_V2; print('Piper SDK OK')"
```

### 3.3 串口权限

```bash
# 临时
sudo chmod 666 /dev/ttyACM0

# 永久（需要重新登录）
sudo usermod -a -G dialout $USER
```

### 3.4 验证全部依赖

```bash
python -c "
from piper_sdk import C_PiperInterface_V2
from lerobot.motors.feetech import FeetechMotorsBus
print('环境就绪')
"
```

---

## 4. 外骨骼舵机配置

### 4.1 查找舵机端口

```bash
lerobot-find-port
```

输出示例：
```
Ports before disconnecting: ['/dev/ttyACM0', ...]
Remove the USB cable from your MotorsBus and press Enter when done.
The port of this MotorsBus is '/dev/ttyACM0'
```

记下端口号（如 `/dev/ttyACM0`），后续步骤中统一称为 `YOUR_PORT`。

---

### 4.2 配置舵机 ID

新舵机默认 ID 通常都是 1。需要给每个舵机分配唯一的 ID（1–7）。

> ⚠️ **每次只能连接一个舵机**，多个舵机同时在线会冲突。

使用 `lerobot-setup-motors` 命令，逐个连接舵机进行配置：

```bash
lerobot-setup-motors \
    --robot.type=piper_follower \
    --robot.port=YOUR_PORT
```

> 如果遇到 `PermissionError`，先执行 `sudo chmod 666 YOUR_PORT`。

程序从 gripper 开始倒序配置，每次只连一个舵机，按 Enter 确认：

| 顺序 | 舵机 | 分配 ID |
|------|------|:-------:|
| 1 | gripper（夹爪） | 7 |
| 2 | wrist_roll（腕部旋转） | 6 |
| 3 | wrist_flex（腕部俯仰） | 5 |
| 4 | forearm_roll（前臂旋转） | 4 |
| 5 | elbow_flex（肘部） | 3 |
| 6 | shoulder_lift（肩部） | 2 |
| 7 | shoulder_pan（底座） | 1 |

实际运行效果：
```
Connect the controller board to the 'gripper' motor only and press enter.
'gripper' motor id set to 7
Connect the controller board to the 'wrist_roll' motor only and press enter.
'wrist_roll' motor id set to 6
...
'shoulder_pan' motor id set to 1
```

---

### 4.3 测试舵机通信

#### 单舵机测试（无需外接电源）

```bash
# 测试单个舵机（如 ID 1）
python path_to_scripts/test_single_motor.py --port YOUR_PORT --id 1

# 测试并转动 45°
python path_to_scripts/test_single_motor.py --port YOUR_PORT --id 1 --move 45

# 逐个测试全部 7 个舵机
for id in 1 2 3 4 5 6 7; do
    echo "=== ID $id ==="
    python path_to_scripts/test_single_motor.py --port YOUR_PORT --id $id
done
```

#### 多舵机串联测试（需外接电源）

```bash
# 实时读取全部 7 个舵机角度
python path_to_scripts/read_realtime.py \
    --port YOUR_PORT --ids 1 2 3 4 5 6 7
```

---

### 4.4 创建自定义机器人配置

本项目已提供 Piper 外骨骼的自定义 LeRobot 配置，文件结构：

```
path_to_lerobot/src/lerobot/robots/piper_follower/
├── __init__.py                    # 模块导出
├── config_piper_follower.py       # 配置类（端口、摄像头等）
├── piper_follower.py              # 机器人实现（7 个 STS3215）
├── README.md                      # 本指南
└── scripts/                       # 全部脚本
    ├── test_single_motor.py       # 单舵机测试
    ├── read_realtime.py           # 实时读取角度
    ├── calibrate.py               # 外骨骼校准
    ├── test_movement.py           # 动作测试
    ├── scan_bus.py                # 扫描总线舵机
    ├── diagnose_gripper.py        # 夹爪诊断
    ├── find_zero_pose.py          # 记录外骨骼零位
    ├── calibrate_piper_arm.py     # 探测 Piper 臂限位
    ├── align.py                   # 角度对齐工具
    ├── teleop.py                  # 遥操主程序
    ├── teleop_v1_stable.py        # 稳定版备份
    ├── compare_angles.py          # 角度对比
    └── read_positions.py          # 读取一次位置
```

#### 关节定义

| 外骨骼舵机 ID | 关节名 | 归一化模式 |
|:---:|---------|-----------|
| 1 | `shoulder_pan`（底座旋转）| DEGREES |
| 2 | `shoulder_lift`（肩部抬升）| DEGREES |
| 3 | `elbow_flex`（肘部弯曲）| DEGREES |
| 4 | `forearm_roll`（前臂旋转）| DEGREES |
| 5 | `wrist_flex`（腕部俯仰）| DEGREES |
| 6 | `wrist_roll`（腕部旋转）| DEGREES |
| 7 | `gripper`（夹爪）| RANGE_0_100 |

#### 如需创建其他机器人

参考 `config_piper_follower.py` 和 `piper_follower.py` 作为模板，同时需在以下两处注册：

- `path_to_lerobot/src/lerobot/robots/utils.py` → `make_robot_from_config()`
- `path_to_lerobot/src/lerobot/scripts/lerobot_setup_motors.py` → `COMPATIBLE_DEVICES`

---

## 5. Piper 机械臂配置

### 5.1 安装 Piper SDK

参考 [Piper SDK GitHub](https://github.com/agilexrobotics/piper_sdk/tree/master) 完成安装。

```bash
# 安装
pip install -e path_to_piper_sdk/

# 激活 CAN 接口
bash path_to_piper_sdk/piper_sdk/can_activate.sh can0 1000000

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

### 5.2 Piper 臂关节限位探测

> 将机械臂切换到手动模式（力矩关闭），可自由掰动。

```bash
python path_to_scripts/calibrate_piper_arm.py
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

## 6. 遥操

### 6.1 记录外骨骼零位

穿上外骨骼，摆到自然姿态：

```bash
python path_to_scripts/find_zero_pose.py \
    --port /dev/ttyACM0 --out zero_pose.json
```

### 6.2 试运行

先试运行确认映射方向正确（不控制机械臂）：

```bash
python path_to_scripts/teleop.py --port YOUR_PORT --dry
```

### 6.3 正式遥操

```bash
python path_to_scripts/teleop.py --port YOUR_PORT
```

**启动前准备：**
1. 激活 CAN 接口：`bash path_to_piper_sdk/piper_sdk/can_activate.sh can0 1000000`
2. 给外骨骼舵机总线上电（6-8.4V）
3. 给 Piper 机械臂上电
4. 穿戴好外骨骼，把 Piper 臂摆成**相同姿态**

**启动后：**
1. 按 Enter 记录零位
2. 外骨骼角度变化实时映射到 Piper 臂
3. 按 `q` 或 `Ctrl+C` 停止（机械臂保持使能，不会掉落）

### 6.4 手动调整映射

编辑 `teleop.py` 中的 `EXO_TO_PIPER_MAP`：

```python
EXO_TO_PIPER_MAP = [
    ("shoulder_pan",  1.0, True),   # (关节名, 缩放系数, 反向)
    ...
]
```

- **缩放系数**：外骨骼转 1° → Piper 转 ?°
- **反向**：`True` 时角度方向取反

其他可调参数：

```python
JOINT_LIMITS_PIPER    # Piper 臂关节限位
DEADZONE = 1.0        # 防抖死区（度）
FILTER_ALPHA = 0.3    # 低通滤波系数
LOOP_HZ = 20          # 控制频率
```

---

## 7. 全部脚本一览

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

---

## 8. 排错指南

### 外骨骼通信

| 现象 | 原因 | 解决 |
|------|------|------|
| `Permission denied:` | 无串口权限 | `sudo chmod 666 YOUR_PORT` |
| `Input voltage error` | 供电不足 | 使用外接电源 6-8.4V |
| `Incorrect status packet` | 夹爪接触不良 | 检查接线 |
| 角度跳动 | 串口干扰 | 检查 USB 线/供电 |

### Piper 臂通信

| 现象 | 原因 | 解决 |
|------|------|------|
| CAN 不通 | 未激活 | `bash can_activate.sh can0 1000000` |
| 关节不动 | 未使能 | `EnablePiper()` 需返回 True |
| 反馈全 0 | 连接断开 | 重新启动 Piper |

### 遥操问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 方向反了 | 映射取反不对 | 改 `EXO_TO_PIPER_MAP` 的 `True/False` |
| 幅度不对 | 缩放系数 | 改 `scale` 参数 |
| 抖动 | 噪声 | 增大 `DEADZONE`/减小 `FILTER_ALPHA` |
| 启动时乱动 | 零位偏移 | 先 `--dry` 确认零位正确 |
