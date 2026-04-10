# Interface Migration Summary (2026-04-10)

## 任务目标

基于 `perception` 与 `system_planner` 已完成的接口收敛文档，做项目级汇总，形成一份从当前最小闭环

`perception -> supervisor -> planner_request`

平滑迁移到后续正式系统接口的可执行说明，并判断当前感知模块是否已经可用、能否支撑 `/home/yhc/kaiti.docx` 所要求的课题主线。

本次只做项目级收口，不修改实现代码，不接入 `RTAB-Map / Nav2 / PlanSys2 / Gazebo` 真模块。

## 变更文件列表

- `docs/interface_migration_summary_2026-04-10.md`

## 指标或结构性结论

### 1. 最终推荐接口

当前项目推荐把三条 topic 视为三类正式逻辑消息，并先冻结 `schema v1`，后续再一一映射到 `kaiti_msgs`：

1. `/kaiti/perception/events`
   - 逻辑消息名：`PerceptionEvent`
   - 当前承载两类语义：
     - `event_type=perception_event`
     - `event_type=perception_status`
2. `/kaiti/system/supervisor/status`
   - 逻辑消息名：`SupervisorStatus`
3. `/kaiti/task_planner/request`
   - 逻辑消息名：`PlannerRequest`

这三条边界已经足够支撑后续接 `Nav2 / PlanSys2 / Gazebo`，前提是后续消费者只依赖冻结核心字段，不再直接解析研究态诊断字段。

### 2. 当前应冻结的字段

#### 2.1 `PerceptionEvent` 冻结字段

建议冻结为跨模块主契约的字段：

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

仅对 `perception_event` 额外冻结的运行态字段：

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

其中真正应被未来规划层长期依赖的最小核心，其实只有：

- `pipeline_state`
- `perception_available`
- `person_present`
- `stable_person_present`
- `stable_fall_detected`
- `seq_stable_fall_detected`
- `reason`

#### 2.2 `SupervisorStatus` 冻结字段

- `ts`
- `role`
- `supervisor_state`
- `planner_mode`
- `planner_action`
- `reason`

未来规划层与系统监督层长期稳定交互，应只依赖：

- `supervisor_state`
- `planner_action`
- `reason`

#### 2.3 `PlannerRequest` 冻结字段

- `ts`
- `role`
- `planner_mode`
- `requested_action`
- `reason`

这条消息当前就应被看作“最小规划意图”，不是完整计划结果。后续接 `PlanSys2` 或 LTL 自动机时，应保持这条边界不变，只在消费端做动作映射。

### 3. 当前只保留为可扩展字段的内容

以下字段当前允许继续存在，但不应冻结为长期正式契约：

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
- `planner_request_topic`
- `source_event`

项目级判断是：这些字段对当前联调有帮助，但它们不是后续 `Nav2 / PlanSys2 / Gazebo` 真正应该依赖的系统边界。

### 4. 为什么当前阶段先冻结 schema，而不是直接上自定义 msg

当前先冻结 `schema v1`，比现在立刻新建 `.msg` 更稳，原因有四个：

1. `Nav2 / PlanSys2 / Gazebo` 还没真正接入，消费者语义边界还在形成期。
2. 当前 perception payload 里仍混有研究态字段，如果现在直接固化 `.msg`，容易把诊断字段和实现细节一起锁死。
3. 当前最重要的是先把“谁能依赖什么字段”收住，而不是先把传输形式换掉。
4. 先冻结 schema，后面再做 `kaiti_msgs/msg/*.msg` 的一一映射，不会推倒重来，迁移成本最小。

因此，本阶段正确策略不是“继续随手拼 JSON”，也不是“立即全量上自定义消息”，而是：

- 继续用 `std_msgs/msg/String`
- 把负载收成稳定 schema
- 让所有后续消费者只依赖冻结核心字段
- 等消费者边界稳定后，再引入 `kaiti_msgs`

### 5. 从当前最小闭环到正式系统接口的迁移建议

推荐按下面五步推进。

#### 第一步：冻结 schema v1

马上把三条 topic 的字段、枚举、异常值、频率约定当成项目正式合同：

- `event_type`
- `pipeline_state`
- `supervisor_state`
- `planner_action`
- `requested_action`
- `reason`

从这一步开始，下游不得再自由解析诊断字段作为控制逻辑依据。

#### 第二步：感知侧补单一正式跌倒语义

当前 perception 最大问题不是字段不足，而是任务层看到两套最终跌倒语义：

- `stable_fall_detected`
- `seq_stable_fall_detected`

迁移建议是：

- 当前过渡期保留这两个字段
- 尽快在 perception 或 supervisor 层补一个单一正式 `fall_state`
- 当前默认主线应以 `LSTM` 稳定态为准
- 规则法与 `TCN` 降为诊断/对照分支

这是从“研究输出”变成“正式任务语义源”的关键一步。

#### 第三步：监督层去掉全量上游回显依赖

`source_event` 当前只适合调试，不应作为长期系统边界。迁移策略应为：

- 当前保留，方便联调
- 后续 supervisor 只保留关键摘要
- 规划层以后禁止依赖 `source_event`

#### 第四步：引入 `kaiti_msgs`

在 schema v1 稳定、消费者边界明确后，再新增：

- `ros2_ws/src/kaiti_msgs/msg/PerceptionEvent.msg`
- `ros2_ws/src/kaiti_msgs/msg/SupervisorStatus.msg`
- `ros2_ws/src/kaiti_msgs/msg/PlannerRequest.msg`

引入原则：

- 只映射冻结核心字段
- 诊断字段进入独立 `debug_*` 字段或独立调试 topic
- 不把嵌套 JSON 原样搬进正式 `.msg`

#### 第五步：真实模块接入时坚持边界不变

后续接 `Nav2 / PlanSys2 / Gazebo` 时，必须保持如下边界：

- 感知层提供稳定语义，不直接承载规划细节
- 监督层只输出状态判断和最小动作建议
- 规划层消费 `requested_action`，并将其映射到真实计划、导航或恢复动作

只要这条边界不变，后续即使替换检测器、时序模型、仿真器或规划后端，也不需要重新推翻接口。

### 6. 对照 `kaiti.docx`，当前感知模块是否可用

结论：可用，但当前层级是“研究原型可用、系统联调可用”，还不是“正式任务语义源可用”。

当前可用性的依据：

- 感知链路已经闭环，具备数据构建、训练、推理、评估、稳定化能力。
- 跌倒检测已有 benchmark，`LSTM` 是当前最佳主线，稳定帧级 `F1=0.7883`。
- 感知已经能够进入 ROS2 最小闭环，支撑 `perception -> supervisor -> planner_request`。

但当前还不够直接支撑 `kaiti.docx` 中更完整的课题主线，原因是：

1. 课题目标需要“语义状态稳定支撑任务更新与异常触发”，而当前 perception 仍在向系统暴露两套最终跌倒语义。
2. 当前 benchmark 主要来自 `UR Fall`，距离动态家居环境、遮挡、长时运行、多干扰 ADL 还有场景差距。
3. 当前对任务层仍主要提供布尔量，生命周期语义和最小可解释性还不够。
4. 当前默认主线尚未完全收口到 `LSTM`，这会影响后续接口冻结的可信度。

因此，项目级判断是：

- 当前跌倒检测模块可以继续作为课题的感知主线基础。
- 但在它成为后续正式系统接口之前，必须先完成语义收敛和场景加固，而不是继续横向扩模型。

### 7. 感知模块如何继续发展，才能更接近 `kaiti.docx` 的使用要求

当前不急着扩全系统模块时，感知侧最值得优先推进的是四件事。

#### 7.1 收口单一正式跌倒语义

先完成：

- 默认主线收口到 `LSTM`
- 增加单一正式 `fall_state`
- 上层不再同时依赖规则态和时序态两个“最终结论”

这是感知接口从研究态走向工程态的第一步。

#### 7.2 从布尔量升级到事件生命周期

面向任务层，建议把当前布尔输出发展成有限状态机式语义，例如：

- `no_person`
- `person_present`
- `fall_suspected`
- `fall_confirmed`
- `fall_cleared`
- `degraded`

这样更符合 `kaiti.docx` 中“语义状态支撑任务更新和异常触发”的要求，也更适合未来 supervisor 和规划层去重、恢复与重规划。

#### 7.3 面向家居 ADL 做误报加固

下一阶段最现实的感知提升，不是先换更复杂模型，而是补家居动态场景的负样本和 hard negative：

- 坐下
- 躺卧
- 弯腰
- 拾物
- 倚靠
- 半遮挡
- 多人交错
- 长时静止

因为对课题主线来说，误报导致的错误任务触发，往往比离线帧级精度更伤系统闭环。

#### 7.4 补最小可解释性字段

后续建议逐步补齐但不大改模型：

- `backend`
- `fall_confidence`
- `health_state`
- `transition_reason`

这些字段已经足够支撑 supervisor 做降级、去重和恢复，不需要先开放 `top_candidate` 等研究态嵌套结构。

## 未解决风险

1. 当前接口层虽然已经完成文档冻结，但代码 payload 还没有完全按“冻结字段优先、诊断字段降级”的策略收齐。
2. 当前仍是 `std_msgs/msg/String + JSON`，类型检查、工具链支持和误用防护弱于正式 `.msg`。
3. perception 侧目前还没有单一正式 `fall_state`，这是未来接规划层前必须完成的接口收口项。
4. benchmark 主要来自 `UR Fall`，还不足以证明在动态家居场景下的长期稳定性。
5. `kaiti.docx` 的完整目标还涉及建图、导航、规划、仿真和实物验证，当前系统只完成了感知主线与系统接口骨架阶段。

## 下一步命令

```bash
cd /home/yhc/kaiti_yolopose_framework
sed -n '1,260p' docs/interface_migration_summary_2026-04-10.md
```

```bash
cd /home/yhc/kaiti_yolopose_framework
git diff -- docs/interface_migration_summary_2026-04-10.md
```

```bash
cd /home/yhc/kaiti_yolopose_framework
rg -n "stable_fall_detected|seq_stable_fall_detected|fall_state|requested_action|source_event" docs ros2_ws src
```

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

```bash
source /home/yhc/kaiti_yolopose_framework/ros2_ws/install/setup.bash
ros2 topic echo /kaiti/perception/events --once
ros2 topic echo /kaiti/system/supervisor/status --once
ros2 topic echo /kaiti/task_planner/request --once
```
