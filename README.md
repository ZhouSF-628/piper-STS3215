# Piper 外骨骼遥操 — piper-STS3215

基于 Piper SDK 的外骨骼遥操系统。

- 外骨骼：7 × STS3215 舵机（6-DOF + 夹爪）
- 机械臂：Piper 6-DOF + 夹爪（CAN 总线）
- 详细指南见 `lerobot_piper_follower/README.md`

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 Piper SDK
pip install -e path/to/piper_sdk/

# 3. 激活 CAN 接口
bash path/to/piper_sdk/piper_sdk/can_activate.sh can0 1000000

# 4. 一次性初始化校准（首次使用）
python lerobot_piper_follower/scripts/teleop.py --port /dev/ttyACM0 --calibrate

# 5. 开始遥操
python lerobot_piper_follower/scripts/teleop.py --port /dev/ttyACM0
```
