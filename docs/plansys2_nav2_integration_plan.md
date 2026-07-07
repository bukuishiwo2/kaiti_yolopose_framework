# PlanSys2 And Nav2 Integration Plan

## 1. Scope

本文件定义下一阶段如何把：

- `/planning/semantic_state`
- `/planning/spatial_state`
- `/planning/plan`
- `/planning/execution_feedback`

挂到：

- `Nav2`
- `PlanSys2`
- Gazebo 仿真环境

同时保持冻结版边界不变：

- `MILP` 负责全局分配、排程和重规划
- `PlanSys2` 只负责动作生命周期
- `Nav2` 只负责导航执行

## 2. Integration Principle

### 2.1 MILP Role

`MILP` 输出的是任务层计划，而不是底盘速度控制。

它负责：

- 任务分配
- 开始时间与完成时间
- 资源时间窗
- 事件触发完整重规划
- 局部修复

### 2.2 PlanSys2 Role

`PlanSys2` 后续只承担：

- 动作实例执行
- 动作状态跟踪
- 执行失败回传

它不应承担：

- 多机器人全局任务分配
- 资源时间窗求解
- 动态重规划主逻辑

### 2.3 Nav2 Role

`Nav2` 只承担：

- 路径规划
- 局部避障
- 到点导航
- 导航失败回报

## 3. Action Mapping

建议把当前任务映射成以下执行动作：

- `T1 patrol@A`
  - 动作：`navigate(A) -> observe(A)`
- `T2 patrol@C`
  - 动作：`navigate(C) -> observe(C)`
- `T3 verify_fall@B`
  - 动作：`navigate(B) -> verify_event(B)`
- `T4 deliver_supply(S->B)`
  - 动作：`navigate(S) -> pickup_supply -> navigate(B) -> drop_supply`
- `T5 charge@D`
  - 动作：`navigate(D) -> dock_or_hold_charge`

这里：

- `navigate(*)` 由 `Nav2` 执行
- 其余动作由 `PlanSys2` 生命周期管理

## 4. Feedback Mapping

建议统一把执行反馈写回 `/planning/execution_feedback`：

- `idle`
- `executing`
- `completed`
- `action_failed`
- `navigation_failed`
- `holding`

局部修复消费的关键字段至少包括：

- 当前活动任务
- 失败动作
- 失败原因
- 时间戳

## 5. Recommended Stages

### Stage I

单机器人 world + `Nav2`

目标：

- 验证 `navigate_to_pose`
- 验证 custom world
- 不接 `PlanSys2`

当前对应入口：

- `ros2 launch yolopose_ros kaiti_house_nav2_precheck.launch.py`

### Stage II

单机器人 + `/planning/*`

目标：

- `semantic_state_node`
- `spatial_state_node`
- `milp_planner_node`
- `execution_feedback_bridge_node`

全部在线联调

当前建议基座：

- `ros2 launch yolopose_ros kaiti_house_turtlebot4_rtabmap.launch.py`
- `ros2 launch yolopose_ros planning_stack.launch.py`

当前基座已补两项启动约束：

- `controller_ready_node` 负责确认 `ros2_control` 最终 active，不再把上游 `spawner` 的瞬态失败当成系统失败。
- `kaiti_house_turtlebot4_rtabmap.launch.py` 对 `RTAB-Map` sidecar 增加启动延迟，优先等 RGBD / LiDAR 稳定后再挂建图。
- `robot_ready_gate_node` 在 `kaiti_house_nav2_precheck.launch.py` 中等待 `joint_states`、`/odom`、`odom -> base_link`，并在家居预检查场景中额外等待 `/map` 与 `map -> base_link`，满足后才放行 `Nav2`。

当前建议直接使用的联调入口：

- `ros2 launch yolopose_ros kaiti_house_planning_precheck.launch.py`

这个入口当前负责：

- 拉起 custom house + TurtleBot4 + RTAB-Map + Nav2
- 拉起 `semantic_state_node`、`spatial_state_node`、`milp_planner_node`、`execution_feedback_bridge_node`
- 可选拉起 `planner_nav2_dispatcher_node`

默认仍保持：

- `dispatch_enabled=false`
- `allowed_actions=""`

即默认只验证接口，不自动下发导航目标。

另外，`nav2_start_delay` 当前只作为 gate 最大等待时间保留，不再表示固定延时启动。

### Stage III

单机器人 + `PlanSys2`

目标：

- `PlanSys2` 消费 MILP 输出动作
- 回传动作完成/失败

### Stage IV

多机器人 `3` namespace bringup

目标：

- 对齐 `R1/R2/R3`
- 对齐区域 `A/C/B/D/S`
- 验证局部修复回路

## 6. Immediate Next Deliverables

下一阶段优先新增：

- `PlanSys2 action adapter`
- `plan -> Nav2 goal dispatcher`
- `execution feedback -> local repair trigger`
- `multi-robot namespace scene bringup`
