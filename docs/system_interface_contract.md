# System Interface Contract

本文件定义当前系统主线默认遵守的稳定接口口径。

当前阶段仍使用 `std_msgs/msg/String + JSON` 传输，但从业务语义上，已经把接口收敛成稳定逻辑消息，而不是“随手拼 JSON”。

历史快照见：

- [system_interface_contract_2026-04-10.md](system_interface_contract_2026-04-10.md)

## 1. 适用范围

当前稳定约束只覆盖三条核心系统 topic：

- `/perception/events`
- `/system/supervisor/status`
- `/task_planner/request`

`/task_planner/status` 目前仍属于任务层占位反馈，不纳入冻结核心契约。

## 2. 当前阶段决策

当前阶段先冻结字段语义和消息边界，不立即冻结自定义 `.msg`。

原因：

1. `Nav2 / PlanSys2 / Gazebo / TurtleBot4` 还未完整接入，消费者边界仍在形成期。
2. 感知层仍保留研究态诊断字段，这些字段对联调有价值，但不宜直接进入长期稳定消息。
3. 先冻结 schema 语义，再迁移到 `kaiti_msgs`，成本最低。

因此当前正式口径为：

- 传输层：暂时仍为 `std_msgs/msg/String`
- 负载层：必须是单个 JSON object
- 逻辑层：只允许下游依赖本文定义的冻结核心字段

## 3. 冻结核心逻辑消息

当前把三条 topic 视为三类核心逻辑消息：

- `PerceptionEvent`
- `SupervisorStatus`
- `PlannerRequest`

### 3.1 `PerceptionEvent`

绑定 topic：

- `/perception/events`

职责：

- 对系统层暴露任务相关的稳定感知语义
- 保留必要的 baseline/debug 字段，便于联调

冻结核心字段：

- `ts`
- `role`
- `event_type`
- `input_mode`
- `pipeline_state`
- `perception_available`
- `reason`
- `person_present`
- `stable_person_present`
- `stable_fall_detected`
- `seq_stable_fall_detected`
- `source`
- `frame_id`
- `person_count`
- `raw_person_present`
- `state_changed`
- `raw_fall_detected`
- `fall_state_changed`
- `fall_person_candidates`
- `fall_max_score`
- `seq_raw_fall_detected`
- `seq_fall_state_changed`
- `seq_fall_score`

允许存在但不建议下游长期依赖的诊断字段包括：

- 规则法启用与候选相关字段
- 时序分支启用、模型加载、track、window、skip reason、invalid reason 等诊断字段
- top candidate / active track 一类研究态字段

当前默认解释口径：

- `stable_fall_detected`：规则法稳定跌倒结果，保留为 baseline/debug
- `seq_stable_fall_detected`：时序主线稳定跌倒结果，当前系统层默认消费

### 3.2 `SupervisorStatus`

绑定 topic：

- `/system/supervisor/status`

职责：

- 将感知层事件收口成系统态判断
- 向任务层输出稳定的动作建议

冻结核心字段：

- `ts`
- `role`
- `supervisor_state`
- `planner_mode`
- `planner_action`
- `reason`

允许存在但不冻结的调试字段：

- `planner_request_topic`
- `fall_trigger_source`
- `source_event`

当前默认跌倒触发准则：

1. supervisor 默认只消费 `seq_stable_fall_detected`
2. 不再对 `stable_fall_detected` 与 `seq_stable_fall_detected` 做常态 `OR`
3. 仅当 perception event 明确给出以下任一条件时，才允许规则法最小回退：
   - `seq_fall_detector_enabled = false`
   - `seq_fall_model_loaded = false`

这意味着当前系统层默认消费的是 `LSTM` 时序主线，而不是规则法。

### 3.3 `PlannerRequest`

绑定 topic：

- `/task_planner/request`

职责：

- 向未来真实规划层输出最小动作意图

冻结核心字段：

- `ts`
- `role`
- `planner_mode`
- `requested_action`
- `reason`

## 4. 枚举与异常值约定

`event_type`：

- `perception_event`
- `perception_status`

`input_mode`：

- `mock`
- `video_file`
- `camera`
- `ros_image`

`pipeline_state`：

- `starting`
- `mock_running`
- `running`
- `completed`
- `error`
- `unavailable`

`supervisor_state`：

- `monitoring`
- `alert`
- `degraded`

`planner_action / requested_action`：

- `monitor`
- `wait_for_update`
- `trigger_safe_mode`
- `hold`

异常值约定：

- 时间戳统一使用 UTC ISO8601
- JSON 中不允许 `NaN`、`Inf`、`-Inf`
- 未知布尔量使用 `null`，不用字符串 `"unknown"`
- `reason` 优先使用 `snake_case` 原因码

## 5. 当前接口边界判断

当前系统已经形成最小闭环：

`/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status`

其中：

- `task_planner_bridge_node` 仍是 planner placeholder
- `/task_planner/status` 仍是占位反馈
- 真正的 `PlanSys2 / LTL` 消费逻辑尚未接入

因此当前契约可视为：

- 感知到任务层桥接的稳定 v1
- 而不是最终系统的完整正式消息集

## 6. 后续迁移原则

后续无论接入 `PlanSys2`、LTL 自动机还是 Gazebo 验证脚本，都应只依赖冻结核心字段。

迁移顺序建议：

1. 继续在 `String + JSON` 上稳定消费者语义
2. 在代码层对齐 schema v1 字段集合
3. 将 `PerceptionEvent / SupervisorStatus / PlannerRequest` 映射到 `kaiti_msgs`
4. 保留调试字段为 debug-only 扩展，不进入最小冻结契约
