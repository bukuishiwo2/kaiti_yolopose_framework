# ROS2 Planning Interface Contract

## 1. Scope

本文件定义毕业设计规划主线新增的四类 ROS2 逻辑消息：

- `/planning/semantic_state`
- `/planning/spatial_state`
- `/planning/plan`
- `/planning/execution_feedback`

传输层继续使用 `std_msgs/msg/String + JSON`，不在当前阶段引入自定义 `.msg`。

## 2. `/planning/semantic_state`

职责：

- 将 `/perception/events` 转为四状态规划语义

冻结核心字段：

- `ts`
- `role`
- `semantic_state`
- `predicate`
- `event_id`
- `event_location`
- `fall_score`
- `quality_score`
- `source_event`

合法状态：

- `normal`
- `event_uncertain`
- `event_confirmed`
- `perception_degraded`

合法谓词：

- `fall_uncertain`
- `fall_confirmed`
- `perception_degraded`
- `event_closed`

## 3. `/planning/spatial_state`

职责：

- 将任务相关区域抽象为规划层资源状态

冻结核心字段：

- `ts`
- `role`
- `region_states`
- `resource_states`
- `travel_times`
- `source`

资源状态至少支持：

- `corridor_free`
- `corridor_temporary`
- `corridor_blocked`
- `charger_available`
- `region_reachable`

## 4. `/planning/plan`

职责：

- 由离线/在线 MILP 规划器发布任务计划

冻结核心字段：

- `ts`
- `role`
- `planner_mode`
- `plan_kind`
- `current_time`
- `tasks`
- `metrics`
- `source_semantic_state`
- `source_spatial_state`

其中 `tasks` 中每项至少包含：

- `robot`
- `task`
- `start`
- `finish`
- `location`
- `resources`

## 5. `/planning/execution_feedback`

职责：

- 汇聚 `PlanSys2/Nav2` 或 placeholder 执行反馈，供后续局部修复使用

冻结核心字段：

- `ts`
- `role`
- `feedback_state`
- `active_action`
- `reason`
- `source_status`

合法反馈示例：

- `idle`
- `executing`
- `completed`
- `action_failed`
- `navigation_failed`
- `holding`

## 6. Compatibility Rules

- 不修改现有 `/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status` 语义。
- 新 planning topics 必须可独立运行，也必须允许并行订阅现有 skeleton topics。
- `PlanSys2` 不得替代 MILP 做全局分配。
- `Nav2` 不得直接消费感知调试字段。
