# System Interface Contract 2026-04-10

本文件用于把当前 `ros2_ws` 中基于 `std_msgs/msg/String + JSON` 的临时 topic，收敛成后续可平滑迁移到正式 ROS2 message 的接口契约。

当前约束范围只覆盖：

- `/perception/events`
- `/system/supervisor/status`
- `/task_planner/request`

## 1. 当前阶段决策

当前阶段**先冻结字段语义与 JSON schema，不立即落自定义 `.msg`**。

原因：

1. `Nav2 / PlanSys2 / Gazebo` 还没有真正接入，消费者接口仍在形成期，现在直接固化 `.msg` 容易把研究态字段一起锁死。
2. 当前感知侧仍携带较多诊断字段，例如 `fall_top_candidate`、`seq_fall_top_candidate`、`source_event`，这些字段对联调有帮助，但不适合作为长期稳定主契约。
3. 先在 `String + JSON` 上冻结字段集合和枚举，后续可以一一映射到 `kaiti_msgs/msg/*.msg`，不需要推倒重来。

因此本次输出的正式结论是：

- 传输层暂时不变，仍为 `std_msgs/msg/String`
- 负载层从“随手拼 JSON”收敛为“有版本边界的 schema”
- 下游从现在开始只允许依赖本文定义的**冻结核心字段**

## 2. 基于当前代码的字段盘点

字段盘点基于以下实现：

- `ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py`
- `ros2_ws/src/yolopose_ros/yolopose_ros/system_supervisor_node.py`
- `src/yolopose/pipeline/runner.py`
- `src/yolopose/pipeline/fall_detector.py`
- `src/yolopose/temporal/sequence_fall_detector.py`

### 2.1 `/perception/events` 当前实际字段

当前这个 topic 实际承载了两类消息：

1. `event_type=perception_event`
2. `event_type=perception_status`

当前稳定出现的公共字段：

| 字段 | 类型 | 当前来源 | 说明 |
| --- | --- | --- | --- |
| `ts` | `string` | mock / runner / terminal heartbeat | UTC ISO8601 时间戳 |
| `role` | `string` | `pose_stream_node` | 当前固定为感知桥接节点身份 |
| `event_type` | `string` | 节点包装层 | `perception_event` 或 `perception_status` |
| `input_mode` | `string` | 节点参数 | `mock` / `video_file` / `camera` / `ros_image` |
| `pipeline_state` | `string` | 节点状态机 | `starting` / `mock_running` / `running` / `completed` / `error` / `unavailable` |
| `perception_available` | `bool` | 节点状态机 | 感知当前是否可用 |
| `reason` | `string` | 节点状态机 | 原因码或原因码附带细节 |

仅在 `perception_event` 中稳定出现的核心字段：

| 字段 | 类型 | 当前来源 | 说明 |
| --- | --- | --- | --- |
| `frame_id` | `int` | `PoseRunner.run()` 或 mock | 当前进程内单调递增帧号 |
| `source` | `string` | runner 结果或 mock | 视频文件路径、相机源或 `mock://perception` |
| `person_count` | `int` | `PoseRunner.run()` 或 mock | 当前帧人体数量 |
| `person_present` | `bool` | 节点包装层 | 当前由 `stable_person_present` 派生 |
| `raw_person_present` | `bool` | `PoseRunner.run()` 或 mock | 原始人数阈值判断 |
| `stable_person_present` | `bool` | `BooleanStabilizer` | 稳定化后的人存在状态 |
| `state_changed` | `bool` | `BooleanStabilizer` | `stable_person_present` 是否翻转 |
| `raw_fall_detected` | `bool` | `FallDetector` 或 mock | 规则法原始跌倒判定 |
| `stable_fall_detected` | `bool` | `FallDetector` 或 mock | 规则法稳定化跌倒判定 |
| `fall_state_changed` | `bool` | `FallDetector` 或 mock | 规则法稳定状态是否翻转 |
| `fall_person_candidates` | `int` | `FallDetector` 或 mock | 候选跌倒目标数量 |
| `fall_max_score` | `float` | `FallDetector` 或 mock | 规则法最高候选分数 |
| `seq_raw_fall_detected` | `bool` | `SequenceFallDetector` 或 mock | 时序模型原始跌倒判定 |
| `seq_stable_fall_detected` | `bool` | `SequenceFallDetector` 或 mock | 时序模型稳定化跌倒判定 |
| `seq_fall_state_changed` | `bool` | `SequenceFallDetector` 或 mock | 时序模型稳定状态是否翻转 |
| `seq_fall_score` | `float` | `SequenceFallDetector` 或 mock | 时序模型最高分数 |

当前代码还会附带的诊断字段：

| 字段 | 类型 | 当前来源 | 说明 |
| --- | --- | --- | --- |
| `fall_detector_enabled` | `bool` | `FallDetector` | 规则法是否启用 |
| `fall_track_mode_used` | `bool` | `FallDetector` | 是否走 track 级稳定化 |
| `fall_top_candidate` | `object \| null` | `FallDetector` | 当前最强候选，结构仍属研究态 |
| `fall_active_track_ids` | `int[]` | `FallDetector` | 当前稳定为跌倒的 track 集合 |
| `fall_active_track_count` | `int` | `FallDetector` | 当前稳定跌倒 track 数量 |
| `seq_fall_detector_enabled` | `bool` | `SequenceFallDetector` | 时序检测器是否启用 |
| `seq_fall_model_loaded` | `bool` | `SequenceFallDetector` | 时序模型是否成功加载 |
| `seq_fall_track_mode_used` | `bool` | `SequenceFallDetector` | 是否走 track 级序列判定 |
| `seq_fall_threshold` | `float` | `SequenceFallDetector` | 当前使用阈值 |
| `seq_fall_person_candidates` | `int` | `SequenceFallDetector` | 有效序列候选人数 |
| `seq_fall_top_candidate` | `object \| null` | `SequenceFallDetector` | 当前最强时序候选 |
| `seq_active_track_ids` | `int[]` | `SequenceFallDetector` | 当前稳定为跌倒的序列 track |
| `seq_active_track_count` | `int` | `SequenceFallDetector` | 当前稳定序列跌倒 track 数量 |

仅在 `perception_status` 中出现的状态字段：

| 字段 | 类型 | 当前来源 | 说明 |
| --- | --- | --- | --- |
| `source` | `string \| int \| null` | 节点状态机 | 当前输入源；不可解析时可能为 `null` |
| `person_present` | `bool \| null` | 节点状态机 | 当前不可用时为 `null` |
| `stable_person_present` | `bool \| null` | 节点状态机 | 当前不可用时为 `null` |
| `stable_fall_detected` | `bool` | 节点状态机 | 当前不可用时固定为 `false` |
| `seq_stable_fall_detected` | `bool` | 节点状态机 | 当前不可用时固定为 `false` |

### 2.2 `/system/supervisor/status` 当前实际字段

| 字段 | 类型 | 当前来源 | 说明 |
| --- | --- | --- | --- |
| `ts` | `string` | `SystemSupervisorNode` | UTC ISO8601 时间戳 |
| `role` | `string` | `system_supervisor` | 当前固定值 |
| `supervisor_state` | `string` | 监督状态机 | `monitoring` / `alert` / `degraded` |
| `planner_mode` | `string` | 参数 | 当前默认 `plansys2_placeholder` |
| `planner_request_topic` | `string` | 参数 | 当前规划请求输出 topic |
| `planner_action` | `string` | 监督状态机 | `monitor` / `wait_for_update` / `trigger_safe_mode` / `hold` |
| `reason` | `string` | 监督状态机 | 当前决策原因 |
| `source_event` | `object` | 透传 perception 事件 | 当前完整回显上游事件，属于调试态字段 |

### 2.3 `/task_planner/request` 当前实际字段

| 字段 | 类型 | 当前来源 | 说明 |
| --- | --- | --- | --- |
| `ts` | `string` | `SystemSupervisorNode` | 直接复用 supervisor status 时间戳 |
| `role` | `string` | `system_supervisor` | 当前固定值 |
| `planner_mode` | `string` | 参数 | 当前默认 `plansys2_placeholder` |
| `requested_action` | `string` | 由 `planner_action` 映射 | `monitor` / `wait_for_update` / `trigger_safe_mode` / `hold` |
| `reason` | `string` | 由 supervisor 透传 | 当前请求原因 |

## 3. 最小正式接口方案

### 3.1 统一传输约束

当前三条 topic 统一遵守以下约束：

- ROS2 消息类型暂时为 `std_msgs/msg/String`
- `msg.data` 必须是单个 JSON object，不能是数组、数字或任意拼接字符串
- 时间字段统一使用 UTC ISO8601，例如 `2026-04-10T12:34:56.123456+00:00`
- JSON 中不允许 `NaN`、`Inf`、`-Inf`
- 布尔状态未知时使用 `null`，不要用字符串 `"unknown"`
- 枚举字段使用 `snake_case`
- `reason` 字段优先使用 `snake_case` 原因码；若必须带调试细节，格式为 `reason_code:detail`

建议从现在开始把这一层视为**schema v1**，即使代码里还没有显式 `schema_version` 字段。

### 3.2 `PerceptionEvent`

绑定 topic：

- `/perception/events`

当前建议的长期消息名：

- `kaiti_msgs/msg/PerceptionEvent`

冻结核心字段如下。

| 字段 | 类型 | 必填 | 语义 |
| --- | --- | --- | --- |
| `ts` | `string` | 是 | 事件生成时间 |
| `role` | `string` | 是 | 当前固定为 `pose_stream_node` |
| `event_type` | `string` | 是 | `perception_event` 或 `perception_status` |
| `input_mode` | `string` | 是 | `mock` / `video_file` / `camera` / `ros_image` |
| `pipeline_state` | `string` | 是 | 当前输入链路状态 |
| `perception_available` | `bool` | 是 | 当前感知是否可用 |
| `reason` | `string` | 是 | 当前状态或事件原因 |
| `person_present` | `bool \| null` | 是 | 对系统层暴露的“是否存在人”最终布尔量 |
| `stable_person_present` | `bool \| null` | 是 | 感知稳定化结果 |
| `stable_fall_detected` | `bool` | 是 | 规则法稳定跌倒结果 |
| `seq_stable_fall_detected` | `bool` | 是 | 时序模型稳定跌倒结果 |
| `source` | `string \| null` | 条件必填 | `perception_event` 必填；`perception_status` 可为 `null` |
| `frame_id` | `int` | 条件必填 | `perception_event` 必填；`perception_status` 不填 |
| `person_count` | `int` | 条件必填 | `perception_event` 必填；最小值为 `0` |
| `raw_person_present` | `bool` | 条件必填 | `perception_event` 必填 |
| `state_changed` | `bool` | 条件必填 | `perception_event` 必填 |
| `raw_fall_detected` | `bool` | 条件必填 | `perception_event` 必填 |
| `fall_state_changed` | `bool` | 条件必填 | `perception_event` 必填 |
| `fall_person_candidates` | `int` | 条件必填 | `perception_event` 必填；最小值为 `0` |
| `fall_max_score` | `float` | 条件必填 | `perception_event` 必填；范围 `[0.0, 1.0]` |
| `seq_raw_fall_detected` | `bool` | 条件必填 | `perception_event` 必填 |
| `seq_fall_state_changed` | `bool` | 条件必填 | `perception_event` 必填 |
| `seq_fall_score` | `float` | 条件必填 | `perception_event` 必填；范围 `[0.0, 1.0]` |

允许保留但不建议下游依赖的诊断字段：

- `fall_detector_enabled`
- `fall_track_mode_used`
- `fall_top_candidate`
- `fall_active_track_ids`
- `fall_active_track_count`
- `seq_fall_detector_enabled`
- `seq_fall_model_loaded`
- `seq_fall_track_mode_used`
- `seq_fall_threshold`
- `seq_fall_person_candidates`
- `seq_fall_top_candidate`
- `seq_active_track_ids`
- `seq_active_track_count`

#### 枚举约定

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

#### 频率约定

- `mock` 模式：按 `mock_publish_period_sec` 周期发布，当前默认 `1.0 Hz`
- `video_file / camera` 正常运行：按处理帧率发布 `perception_event`
- `completed / error / unavailable`：按 `heartbeat_interval_sec` 发送 `perception_status`，当前默认 `0.5 Hz`

#### 异常值约定

- 感知不可用时：`perception_available=false`
- 感知不可用或退出时：`person_present=null`、`stable_person_present=null`
- 感知不可用或退出时：`stable_fall_detected=false`、`seq_stable_fall_detected=false`
- `source` 无法解析时允许为 `null`
- `frame_id` 只在当前节点生命周期内单调递增，不作为全局唯一 ID

### 3.3 `SupervisorStatus`

绑定 topic：

- `/system/supervisor/status`

当前建议的长期消息名：

- `kaiti_msgs/msg/SupervisorStatus`

冻结核心字段如下。

| 字段 | 类型 | 必填 | 语义 |
| --- | --- | --- | --- |
| `ts` | `string` | 是 | 状态生成时间 |
| `role` | `string` | 是 | 当前固定为 `system_supervisor` |
| `supervisor_state` | `string` | 是 | 系统监督状态 |
| `planner_mode` | `string` | 是 | 当前规划后端模式 |
| `planner_action` | `string` | 是 | 对规划层的当前建议动作 |
| `reason` | `string` | 是 | 监督状态原因 |

当前实现中存在但不冻结为核心契约的字段：

- `planner_request_topic`
- `source_event`

理由：

- `planner_request_topic` 属于配置态信息，不应长期进入业务消息
- `source_event` 是整个 perception JSON 的嵌套回显，不适合作为长期稳定字段

#### 枚举约定

`supervisor_state`：

- `monitoring`
- `alert`
- `degraded`

`planner_action`：

- `monitor`
- `wait_for_update`
- `trigger_safe_mode`
- `hold`

#### 决策语义

- `degraded + hold`：上游感知不可用、已退出、或长时间超时
- `alert + trigger_safe_mode`：检测到稳定跌倒事件
- `monitoring + wait_for_update`：当前无人或暂不满足触发条件
- `monitoring + monitor`：感知正常且未触发告警

#### 频率约定

- 正常情况下：每收到一个 perception event/status 就同步发布一次
- 上游未启动或超时：按 `status_publish_period_sec` 周期发布，当前默认 `1.0 Hz`

#### 异常值约定

- 不允许把上游原始异常堆叠成自由文本状态；状态判断必须只依赖 `supervisor_state` + `planner_action`
- `reason` 可带调试细节，但下游状态机不得只靠完整字符串精确匹配

### 3.4 `PlannerRequest`

绑定 topic：

- `/task_planner/request`

当前建议的长期消息名：

- `kaiti_msgs/msg/PlannerRequest`

冻结核心字段如下。

| 字段 | 类型 | 必填 | 语义 |
| --- | --- | --- | --- |
| `ts` | `string` | 是 | 请求生成时间 |
| `role` | `string` | 是 | 当前固定为 `system_supervisor` |
| `planner_mode` | `string` | 是 | 请求面向的规划后端 |
| `requested_action` | `string` | 是 | 当前最小规划请求 |
| `reason` | `string` | 是 | 请求原因 |

#### 枚举约定

`requested_action`：

- `monitor`
- `wait_for_update`
- `trigger_safe_mode`
- `hold`

#### 当前阶段语义

当前 `PlannerRequest` 不是完整任务规划命令，而是**从系统监督层发向未来规划层的最小意图消息**。后续接 `PlanSys2` 或 LTL 自动机时，应保持这条边界不变，只把 `requested_action` 映射成更具体的计划更新、goal dispatch 或恢复动作。

#### 频率约定

- 与 `/system/supervisor/status` 同步发布

#### 异常值约定

- 当前阶段不允许空请求；即使是等待态，也应显式发布 `requested_action=hold` 或 `wait_for_update`

## 4. 推荐的后续 ROS2 message 映射

在 schema v1 稳定后，再引入独立接口包，例如：

- `ros2_ws/src/kaiti_msgs/msg/PerceptionEvent.msg`
- `ros2_ws/src/kaiti_msgs/msg/SupervisorStatus.msg`
- `ros2_ws/src/kaiti_msgs/msg/PlannerRequest.msg`

推荐原则：

1. 先只映射**冻结核心字段**
2. 诊断字段单独放入 `debug_*` 区域，或改成独立调试 topic
3. 不要把 `source_event` 这种嵌套 JSON 原样搬进正式 `.msg`

## 5. 从当前最小闭环到正式接口的迁移步骤

1. 当前阶段先把三个 topic 的字段名、枚举和空值约定固定下来，继续使用 `String + JSON`
2. 感知侧后续补一个“任务级最终语义字段”，但不删除现有诊断字段
3. 监督层后续去掉 `source_event` 全量回显，只保留上游关键摘要
4. 新增 `kaiti_msgs` 包时，只实现本文冻结核心字段的一一映射
5. 接 `Nav2 / PlanSys2 / Gazebo` 时，统一只消费正式 message 或本文定义的核心字段，不再直接解析研究态诊断字段

## 6. 本轮接口层最高优先级结论

1. 三个 topic 现在已经有足够清晰的语义边界，可以先冻结 schema，再升级 `.msg`
2. `/perception/events` 需要区分 `perception_event` 与 `perception_status`，下游不能把两者当同一类帧事件使用
3. `/system/supervisor/status` 的核心契约应该只有 `state + action + reason`，`source_event` 只保留为过渡期调试字段
4. `/task_planner/request` 当前是“最小意图请求”，不是完整计划结果，这个边界应保持到接入真实规划层
5. 先冻结核心字段、后引入 `kaiti_msgs`，可以避免未来接 `Nav2 / PlanSys2 / Gazebo` 时重新推翻接口
