# System Interface Contract

本文件定义当前系统主线默认遵守的稳定接口口径。

当前阶段仍使用 `std_msgs/msg/String + JSON` 传输，但从业务语义上，已经把接口收敛成稳定逻辑消息，而不是“随手拼 JSON”。

历史快照见：

- [system_interface_contract_2026-04-10.md](system_interface_contract_2026-04-10.md)

## 1. 适用范围

当前稳定约束覆盖三条核心系统 topic，并记录一个占位反馈 topic：

- `/perception/events`
- `/system/supervisor/status`
- `/task_planner/request`
- `/task_planner/status`

其中 `/task_planner/status` 目前仍属于任务层占位反馈，不等同于真实 planner 的完整执行反馈，但其占位字段和映射关系已固定。

## 2. 当前阶段决策

当前阶段先冻结字段语义和消息边界，不立即切换到新的自定义消息类型。

原因：

1. `Nav2 / PlanSys2 / Gazebo / TurtleBot4` 还未完整接入，消费者边界仍在形成期。
2. 感知层仍保留研究态诊断字段，这些字段对联调有价值，但不宜直接进入长期稳定消息。
3. 先冻结 schema 语义，再按实际集成需要收口消息定义，成本最低。

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
- `observation_state`
- `observation_reason`
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
- `observation_state`：当前观察质量语义；当前稳定取值为 `observable / no_person / low_visibility / occluded / window_not_ready / unavailable`
- `observation_reason`：观察态原因码；当前用于 `need_reobserve` 判定与联调日志

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
- `observation_state`
- `observation_reason`
- `source_event`

当前默认跌倒触发准则：

1. supervisor 默认只消费 `seq_stable_fall_detected`
2. 不再对 `stable_fall_detected` 与 `seq_stable_fall_detected` 做常态 `OR`
3. 仅当 perception event 明确给出以下任一条件时，才允许规则法最小回退：
   - `seq_fall_detector_enabled = false`
   - `seq_fall_model_loaded = false`

这意味着当前系统层默认消费的是 `LSTM` 时序主线，而不是规则法。

当前 `need_reobserve` 触发准则：

1. `need_reobserve` 不覆盖真实 `fall_detected`
2. `need_reobserve` 不替代 `no_person_present`
3. `need_reobserve` 只用于“有人但当前不可可靠判断”的中间状态
4. 当前由以下观察态作为 raw `need_reobserve` 候选：
   - `low_visibility`
   - `occluded`
   - `window_not_ready`
5. supervisor 对 raw `need_reobserve` 做最小滞回：
   - 连续 `reobserve_enter_frames=2` 帧 raw 候选才进入 `need_reobserve`
   - 连续 `reobserve_exit_frames=5` 帧非 raw 候选才退出回 `monitor`

当前允许存在但不建议下游长期依赖的 `need_reobserve` 调试字段：

- `need_reobserve_raw`
- `reobserve_enter_count`
- `reobserve_exit_count`

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

### 3.4 `TaskPlannerStatus`（占位）

绑定 topic：

- `/task_planner/status`

职责：

- 确认当前占位任务层已经消费 `/task_planner/request`
- 在真实 `PlanSys2 / LTL` 消费端接入前，提供可观察的 planner placeholder 状态

当前字段：

- `ts`
- `role`
- `planner_mode`
- `planner_state`
- `active_action`
- `reason`
- `state_reason`
- `request_reason`
- `request_supported`
- `request_topic`
- `source_request`

说明：

- `reason`：当前实际状态原因，支持动作时优先保留上游 `request_reason`
- `state_reason`：由 `active_action -> planner_state` 映射得到的占位状态原因
- `request_reason`：原始 `PlannerRequest.reason`
- `request_supported`：当前占位 planner 是否支持该 `requested_action`

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
- `need_reobserve`
- `trigger_safe_mode`
- `hold`

`PlannerRequest -> TaskPlannerStatus` 当前固定映射：

| `requested_action` | `planner_state` | `state_reason` |
|---|---|---|
| `monitor` | `idle` | `monitoring_request` |
| `wait_for_update` | `waiting` | `waiting_for_perception_update` |
| `need_reobserve` | `reobserve_pending` | `reobserve_requested` |
| `trigger_safe_mode` | `dispatching_safe_mode` | `safe_mode_requested` |
| `hold` | `holding` | `planner_hold` |
| 其他值 | `invalid_request` | `unsupported_requested_action` |

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
3. 在消费者边界稳定后，再决定是否收口为新的正式消息定义
4. 保留调试字段为 debug-only 扩展，不进入最小冻结契约

## 7. Phase 3 接口冻结与占位边界

### 7.1 当前已冻结接口清单

当前系统主线冻结以下 topic 与语义：

| Topic | 逻辑消息 | 当前用途 | 后续保留策略 |
|---|---|---|---|
| `/perception/events` | `PerceptionEvent` | 感知稳定语义事件 | 保留为感知到系统层的输入边界 |
| `/system/supervisor/status` | `SupervisorStatus` | 系统监督状态与动作建议 | 保留为调试、监控和未来 planner 的状态参考 |
| `/task_planner/request` | `PlannerRequest` | supervisor 到 planner 的最小意图 | 保留为真实 planner 的输入边界 |
| `/task_planner/status` | `TaskPlannerStatus`（占位） | planner placeholder 反馈 | topic 可保留，消费者实现可替换 |

当前冻结动作集合：

- `monitor`
- `wait_for_update`
- `need_reobserve`
- `trigger_safe_mode`
- `hold`

当前冻结 supervisor 状态集合：

- `monitoring`
- `alert`
- `degraded`

当前占位 planner 状态集合：

- `idle`
- `waiting`
- `reobserve_pending`
- `dispatching_safe_mode`
- `holding`
- `invalid_request`

### 7.2 后续真实 planner 继续保留的字段

真实 `PlanSys2 / LTL` 消费端替换 `task_planner_bridge_node` 时，应继续保留并消费：

- `PlannerRequest.ts`
- `PlannerRequest.role`
- `PlannerRequest.planner_mode`
- `PlannerRequest.requested_action`
- `PlannerRequest.reason`

真实 planner 可继续发布到 `/task_planner/status`，并至少保留：

- `ts`
- `role`
- `planner_mode`
- `planner_state`
- `active_action`
- `reason`

当前 `state_reason / request_reason / request_supported / source_request` 属于 placeholder 过渡反馈字段。真实 planner 可保留用于调试，但不应让上游依赖这些字段反向改变行为。

### 7.3 不应直接暴露给未来 planner 的字段

以下字段仍可保留在 perception event 中用于调试、分析或 OSD，但未来 planner 不应直接硬编码依赖：

- `raw_fall_detected`
- `fall_max_score`
- `fall_person_candidates`
- `seq_raw_fall_detected`
- `seq_fall_score`
- `seq_fall_threshold`
- `seq_window_ready`
- `seq_window_size`
- `seq_track_id`
- `seq_skip_reason`
- `seq_invalid_reason`
- `fall_top_candidate`
- `seq_fall_top_candidate`
- `*_active_track_ids`

未来 planner 应通过 `SupervisorStatus.planner_action` 或 `PlannerRequest.requested_action` 消费系统语义，而不是直接解释模型分数或候选细节。
