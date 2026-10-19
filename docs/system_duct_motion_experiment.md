# DUCT 可回退运动实验：影子验证与隔离实车接近

当前状态：2026-10-19 已完成约 2.6 cm 点动及约 1.96 m 直线接近，随后恢复原驱动。接近被自动回退计时中断，**未正常达到 0.85 m 停靠阈值**；最后有效左踝位置约 `[0.920, 0.016, 0.066]` m（base_link）。用户确认停车及原功能正常。

## 阶段 B：已部署的隔离控制与回退

原驱动源码复制到独立实验目录，在副本增加命令租约/限速；不覆盖 OEM 源码、二进制或参数。实验时通过 `/run/systemd/system/robot-start.service.d/90-pose3d-motion.conf` 临时切换启动入口并重启底盘，其他原底盘节点保留。切换会重置轮式里程计原点。

- 副本仅接收 `/research/motion/motor_request`（TwistStamped），不与原 `/cmd_vel` 争抢。租约 0.25 s，最大前向 0.05 m/s，拒绝倒退/横移/转向、旧时间戳和非有限数。
- 用户同意实验模式下任意 SBUS 通道偏离采样中位超过 20 即归零锁定；中位不是独立停止。恢复原模式后摇杆功能不变。
- 左脚使用左踝索引 15，单人、置信度≥0.6、标准差≤0.10 m、横向偏差≤0.15 m。源年龄≤0.9 s；短暂缺点保持≤0.5 s，不做无限外推。
- 单次直线接近≤2.5 m / 70 s；0.05 m/s，左脚前向距离≤1.05 m 时降至 0.02 m/s，≤0.85 m 停止。该距离从车体中心算起，不是驶到人体脚上。
- 使用实测 laser→base TF 检查前向宽 0.6 m、最小 0.8 m 净空。原 `/avoidance/decision` 本轮没有发布者，因此不是原厂避障或 Nav2 验收；本轮采用研究激光门控并保留原刹车输入。
- 回退计时原为切换后 90 s，本次准备耗时使其提前中断运动；现改为 120 s，单次运动仍限 70 s。根 transient 服务缺少 HOME 导致 ROS 日志初始化失败，现 wrapper 显式配置按 EUID 隔离的绝对 ROS_LOG_DIR。新计时器完整实车周期尚未复测。

恢复命令（小车 SSH，可重复执行）：

```bash
sudo /bin/bash /home/duct/start_duct_motion_experiment.sh mode restore
python3 /home/duct/duct_motion_baseline.py verify
systemctl is-active robot-start robot-rtsp
```

实际运动准备为 wrapper 的 `mode prepare`、`sudo ... mode activate`；仅在现场确认和新鲜预检后执行。控制器 `jog --execute --approach-left-foot` 需指定 neutral-file 和 report，不设开机自启。恢复会停止实验速度服务、等待租约归零、核对中位/静止，再移除确切匹配的自有 runtime override 并启动原服务。阶段 A 的 baseline restore **不能**代替此命令。

本次人工恢复已验证：OEM 电机进程运行、override 消失、8 个原文件及有效启动配置一致。命令 watchdog 不保证电机驱动/操作系统冻结时的硬件停车。完整结果见 [当日日志](worklogs/worklog_2026-10-19.md) 和 [接近素材](../reports/demos/2026-10-19_left_foot/README.md)。

## 阶段 A 历史说明

以下保留阶段 A 时的约束及未完成项，均是当时状态，不代表阶段 B 尚未实现。

## 原功能保留边界

- 不覆盖 `/data/ductcleanrob` 的驱动、参数、启动文件，不覆盖 `robot-start.service`。
- 不停止原底盘服务，不向 `/cmd_vel`、刹车或原 SBUS 话题发布消息。
- 不更改原遥控器应用，不复用或接管其 8888/8554 端口。
- 影子节点只发布 `/research/motion/shadow_status` JSON；即使调用 shadow_arm，也没有电机输出。
- 原控制链基线保存在 `/home/duct/pose3d_motion_experiment/baseline_20261019/`，包括 8 个关键文件副本、SHA-256 清单及有效 systemd 配置。

## 已实现的逻辑门控

`motion_safety.py` 为无 ROS 副作用的纯逻辑：默认未使能，需重新显式使能；初始前向点动上限 0.02 m/s、0.10 m、5 s。命令租约 0.25 s，遥控、里程计、激光及原速度输入最大接收年龄 0.30 s。非有限数值、障碍、刹车/遥控故障、原控制非零、超时或限距均归零并锁定，不自动恢复。

这些是**单元测试覆盖的软件逻辑**，不是已安装在电机驱动内的看门狗。当前驱动仍为原版本，不能宣称断线就能实际停车。

## 可重复的检查与回退

以下命令在小车 duct 用户 SSH 中执行：

```bash
# 检查原程序/配置及备份均未变化
python3 /home/duct/duct_motion_baseline.py verify

# 启动不可驱动电机的观察节点，不设为开机启动
systemctl --user start pose3d-motion-shadow

# 结束影子实验并校验原件；不重启原底盘
python3 /home/duct/duct_motion_baseline.py restore
```

`restore` 目前只覆盖阶段 A：停止自己的影子服务，并检查原件。若发现外部修改，拒绝静默覆盖。它**不是尚未实现的真实底盘接管阶段的通用恢复器**；后续若引入实验驱动/运行时启动覆盖，必须同步扩展恢复脚本，并先完成切换、失败与恢复验收。

2026-10-19 已实测 start → 读状态 → restore：61 条影子状态、实际电机命令 0；`/cmd_vel` 唯一发布者仍是原 driving_control_node。回退后影子服务 inactive/dead，robot-start 与 robot-rtsp active，8 个原文件校验一致。

## 实车接入前未通过项

1. 用户确认所谓遥控停止仅为「摇杆回中」。自动运行时摇杆本来就在中位，不能将同一状态同时当作许可和停止。需要独立保持运行/停止信号；可采用独立实验界面按住才运行、松开即停止，不改原应用。该界面当前**未实现**。
2. 需要机器人本机唯一速度出口和原遥控优先接管，并在隔离副本的电机驱动内验证命令超时归零。还要明确驱动进程/操作系统挂起时的硬件停止边界，不能仅依赖 Python finally 发零速。
3. 影子逻辑使用全周最小激光距离，只能作保守检查，不能直接放行前进。最近约 0.14–0.15 m；用户后来说明后方有桌子。实际 TF 显示 laser_link 相对 base_link 旋转约 π，雷达约 9.5° 的近点在车体坐标约 `(-0.014, -0.024, 0.144)` m，可能涉及车体结构；不是已证明的前向障碍或已验证可忽略的点。前向通道必须在 base 坐标结合真实外形验证，不能直接按雷达 0° 判断车前。
4. 尚无已验收的路径、避障或人体目标闭环。先做不超过 10 cm 点动并验证停车/接管/回退，再讨论距脚部保留约 1 m 的接近任务；不是直接驶到脚上。

当前原底盘控制链未改动。影子实验回退后保持停止，三维可视化和原图传继续运行。
