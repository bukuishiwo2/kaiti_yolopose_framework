# Phase 5 Planner Nav2 Dispatch 2026-04-17

## 1. 任务目标

本阶段只实现 `/task_planner/request` 到 Nav2 `/navigate_to_pose` 之间的受控派发边界。

本阶段不进入：

- 完整任务规划闭环
- 真实 `PlanSys2 / LTL`
- `/task_planner/request` 到 `/navigate_to_pose` 的直通
- 新消息类型体系
- 感知模型训练、模型替换或外部数据集扩展

## 2. 三角色状态判断

`architect`：

- Phase 4a/4b 已冻结，Phase 5 只收口“谁能触发导航、如何触发、默认如何禁止”。
- 当前结论不能扩大为完整导航闭环或任务系统闭环。
- 新增派发节点必须默认不产生运动。

`system_planner`：

- Nav2 action server 已在 Phase 4b 验证可用。
- `/task_planner/request` 不能直接接入 `/navigate_to_pose`。
- 新增 `planner_nav2_dispatcher_node` 作为受控中间层，负责动作白名单、目标映射、reason 校验、冷却、单 active goal 和 `hold` cancel。

`perception`：

- 本阶段不改模型、不训练、不扩数据集。
- `seq_stable_fall_detected`、`need_reobserve`、`trigger_safe_mode` 等上游语义保持不变。
- perception 与 supervisor 仍只输出稳定语义，不携带导航目标坐标。

## 3. 允许与不允许触发导航的动作边界

| `requested_action` | 是否允许触发导航 | Phase 5 规则 |
|---|---:|---|
| `monitor` | 不允许 | 只表示稳定监控，不发 goal，不取消既有 goal。 |
| `wait_for_update` | 不允许 | 只表示等待感知更新或无人，不发 goal。 |
| `need_reobserve` | 有条件允许 | 仅在 `dispatch_enabled=true`、动作被加入 `allowed_actions`、`reason` 属于遮挡/低可见度类、且存在 `reobserve_vantage` 命名 goal 时派发。`temporal_window_not_ready` 默认禁止移动。 |
| `trigger_safe_mode` | 有条件允许 | 仅在 `dispatch_enabled=true`、动作被加入 `allowed_actions`、`reason in {fall_detected, fall_detected_rule_fallback}`、且存在 `safe_mode_staging` 命名 goal 时派发。 |
| `hold` | 不允许触发 | 不发新 goal；若 dispatcher 自己有 active goal，则请求 cancel。 |
| 其他值 | 不允许 | 记录 reject，不发送 Nav2 goal。 |

核心约束：

- `/task_planner/request` 永远不直接变成 Nav2 goal。
- 不向 `PlannerRequest` 增加 goal 字段。
- 不新增 `.msg / .action / .srv`。
- 所有可导航目标只来自 Phase 5 YAML 中的命名 goal registry。
- 默认 `dispatch_enabled=false`，新增节点默认只观察和拒绝，不产生机器人运动。

## 4. 实现内容

新增文件：

- `ros2_ws/src/yolopose_ros/yolopose_ros/planner_nav2_dispatcher_logic.py`
- `ros2_ws/src/yolopose_ros/yolopose_ros/planner_nav2_dispatcher_node.py`
- `ros2_ws/src/yolopose_ros/config/phase5_nav2_dispatcher.yaml`
- `ros2_ws/src/yolopose_ros/launch/phase5_nav2_dispatcher.launch.py`
- `scripts/verify_planner_nav2_dispatcher.py`
- `scripts/phase5_nav2_dispatch_smoke.py`

更新文件：

- `ros2_ws/src/yolopose_ros/setup.py`
- `ros2_ws/src/yolopose_ros/package.xml`
- `docs/system_bringup_skeleton.md`
- `ros2_ws/README.md`
- `docs/reviews/README.md`
- `docs/worklogs/worklog_2026-04-17.md`

派发策略：

- `planner_nav2_dispatcher_node` 订阅 `/task_planner/request`。
- 只有该节点可以调用 `/navigate_to_pose`。
- `task_planner_bridge_node` 保持 placeholder，只发布 `/task_planner/status`。
- Phase 5 使用单 active goal 策略：已有 dispatcher goal 时拒绝新 goal。
- 重复的 `(action, reason, goal)` 在 `cooldown_sec` 内不会重复派发。
- `hold` 只取消 dispatcher 自己派发的 active goal。
- 不新增项目级反馈 topic；验收通过日志、Nav2 action feedback/result、`/plan`、`/cmd_vel` 观察。

## 5. 验证

已执行：

```bash
python3 scripts/verify_planner_nav2_dispatcher.py
source /opt/ros/humble/setup.bash
python3 -m py_compile \
  ros2_ws/src/yolopose_ros/yolopose_ros/planner_nav2_dispatcher_node.py \
  ros2_ws/src/yolopose_ros/yolopose_ros/planner_nav2_dispatcher_logic.py \
  scripts/verify_planner_nav2_dispatcher.py
cd ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
timeout 5s ros2 launch yolopose_ros phase5_nav2_dispatcher.launch.py \
  launch_phase4b:=false \
  dispatch_enabled:=false
timeout 5s ros2 launch yolopose_ros phase5_nav2_dispatcher.launch.py \
  launch_phase4b:=false \
  dispatch_enabled:=true \
  allowed_actions:='[trigger_safe_mode]'
```

验证覆盖：

- 默认禁用时拒绝派发
- 缺失 `planner_mode` 时拒绝请求
- `monitor / wait_for_update / unsupported` 不触发导航
- `need_reobserve + temporal_window_not_ready` 不触发导航
- `need_reobserve + low_visibility` 在显式开启和白名单下允许派发
- `trigger_safe_mode + fall_detected` 在显式开启和白名单下允许派发
- 缺失命名 goal 时拒绝派发
- 重复请求在冷却期内拒绝
- active goal 期间 `hold` 进入 cancel 分支
- Phase 5 dispatcher 单独启动成功，默认禁用和显式白名单两种参数形式均可解析

运行态 smoke 结论：

- `trigger_safe_mode -> safe_mode_staging` 运行态通过，dispatcher 可将合规 `/task_planner/request` 映射为 Nav2 `/navigate_to_pose` goal。
- `hold` cancel 运行态通过，已观察到 `cancel requested`、`goals_canceling=1` 与 `goal finished status=5`。
- 手工 `ros2 topic pub --once /task_planner/request` 存在时序噪声，可能因 DDS discovery、dispatcher/Nav2 readiness 或 active goal 尚未建立，导致需要重复发布 `trigger_safe_mode` 或 `hold`。
- 后续标准 Phase 5 运行态测试推荐使用 `scripts/phase5_nav2_dispatch_smoke.py`，由脚本等待 request subscriber、Nav2 action server 和 active goal 状态后再发送 `hold`。

## 6. 风险

- Phase 5 不解决 RTAB-Map 长时漂移、地图质量或动态家居导航稳定性。
- 当前 request 不携带目标位置，因此不能声称机器人会自动去往摔倒人员位置。
- 命名 goal 当前只是短距离预设 map pose，需要后续在可复现实验中重新标定。
- 同时运行 Gazebo、RTAB-Map、YOLOPose、Nav2 和 dispatcher 仍有实时性压力。
- 若误把 `need_reobserve` 的 `temporal_window_not_ready` 加入白名单，可能导致启动初期无意义移动；当前默认禁止。

## 7. 下一步命令

默认只观察、不派发：

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros phase5_nav2_dispatcher.launch.py dispatch_enabled:=false
```

显式开启单动作 smoke test：

```bash
ros2 launch yolopose_ros phase5_nav2_dispatcher.launch.py \
  launch_phase4b:=false \
  dispatch_enabled:=true \
  allowed_actions:='[trigger_safe_mode]'
```

标准运行态 smoke test：

```bash
cd /home/yhc/kaiti_yolopose_framework
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
python3 scripts/phase5_nav2_dispatch_smoke.py
```

观察 Nav2：

```bash
ros2 action info /navigate_to_pose
ros2 topic echo --once /plan
ros2 topic echo /cmd_vel
```

## 8. 冻结结论

Phase 5 受控派发边界可以冻结为“planner request 到 Nav2 的显式授权派发层”，不扩大为完整任务规划闭环。

已确认：

- `scripts/phase5_nav2_dispatch_smoke.py` 运行态通过。
- `trigger_safe_mode / fall_detected -> safe_mode_staging` 运行态通过，机器人可响应受控请求并进入 Nav2 目标点导航。
- `hold` cancel 运行态通过，可取消 dispatcher 自己派发的 active Nav2 goal。
- 手工 `ros2 topic pub --once /task_planner/request` 存在时序噪声，不作为后续标准验收方式。

冻结边界：

- `/task_planner/request` 不直通 `/navigate_to_pose`。
- dispatcher 仍由 `dispatch_enabled` 和 `allowed_actions` 显式开启，默认不产生机器人运动。
- `task_planner_bridge_node` 继续保持 placeholder 语义。
- 不接 PlanSys2 / LTL。
- 不扩展 `PlannerRequest` schema。
- 不修改 perception / supervisor 语义。
