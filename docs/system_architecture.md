# System Architecture

本文件描述的是开题目标中的**系统层**，不是当前 `YOLOPose` 感知实验本身。

当前仓库已经把感知子系统做成可训练、可评估、可切换模型的原型；下一步要把它收敛成 ROS2 系统里的一个稳定语义源，再向建图、导航、任务规划层扩展。

当前接口收敛基线见：
- [system_interface_contract_2026-04-10.md](system_interface_contract_2026-04-10.md)

## 1. 系统目标

对齐 `kaiti.docx` 的最终目标，完整系统应覆盖四层：

1. 感知层
2. 建图与定位层
3. 任务规划层
4. 系统验证层

当前仓库已经完成的是感知层的核心部分：
- 预训练人体姿态估计
- 跌倒检测规则法基线
- 学习型时序模型 `LSTM` / `TCN`
- 事件稳定化输出

系统层当前还处于骨架阶段，但接口已经开始收敛。

## 2. ROS2 节点边界

建议将系统拆成 5 个长期边界清晰的节点域。

### 2.1 感知桥接节点

建议节点名：
- `pose_stream_node`

职责：
- 读取视频流、摄像头或 RTSP
- 调用当前感知管线
- 输出稳定语义事件

当前状态：
- 已有最小实现
- 仍是单机桥接原型
- 默认直接复用 `configs/infer_pose_stream.yaml`
- 当前默认学习型主线为 `models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`
- 当前默认时序阈值为 `score_threshold=0.6`、`min_true_frames=3`、`min_false_frames=5`

当前输出：
- `/perception/events`
- `/perception/debug_image`（可选调试）

接口策略：
- 当前继续使用 `std_msgs/msg/String` 承载 JSON object
- 先冻结 schema v1，再升级为 `kaiti_msgs/msg/PerceptionEvent`
- 当前不再额外定义 `/perception/person_state`，避免在系统层形成第二条并行语义边界

### 2.2 建图与定位层

建议依赖：
- `RTAB-Map`
- 里程计
- 深度 / 激光 / RGB-D 传感器
- `tf` / `tf_static`

职责：
- 在线建图
- 位姿估计
- 增量地图更新
- 动态场景下的可达性支持

建议接口：
- 输入：`/camera/image_raw`、`/camera/camera_info`、`/scan`、`/odom`
- 输出：`/map`、`/rtabmap/localization_pose`、`/tf`

当前状态：
- 仅在文档中定义
- 尚未接入真实节点

### 2.3 导航层

建议依赖：
- `Nav2`

职责：
- 全局规划
- 局部避障
- 目标点导航
- 导航失败恢复

建议接口：
- Action：`/navigate_to_pose`
- Topics：`/cmd_vel`、`/plan`

当前状态：
- 未接入
- 只保留接口占位

### 2.4 任务规划层

建议依赖：
- `PlanSys2`
- LTL 到自动机映射

职责：
- 将自然任务或 LTL 公式转成自动机
- 根据当前世界状态驱动任务状态迁移
- 决定是否调用导航、重规划、恢复或告警动作

建议输入：
- 感知事件
- 地图状态
- 机器人状态
- 电量状态

建议输出：
- 任务请求
- 规划结果
- 执行动作列表

建议接口：
- `/task_planner/request`
- `/task_planner/plan`
- `/task_planner/status`

当前状态：
- 已接入最小占位任务层节点
- 当前由 `task_planner_bridge_node` 消费 `/task_planner/request`
- 当前输出 `/task_planner/status` 作为任务层占位状态
- 仍未接入真实 `PlanSys2 / LTL` 规划逻辑

### 2.5 系统监督层

建议节点名：
- `system_supervisor_node`

职责：
- 订阅感知事件
- 将事件标准化
- 根据状态决定是否触发规划层
- 作为感知层与任务层之间的稳定缓冲

当前接口：
- 输入：`/perception/events`
- 输出：`/system/supervisor/status`
- 输出：`/task_planner/request`

当前状态：
- 已有最小占位节点
- 当前已经和占位任务层形成 `perception -> supervisor -> planner_request -> planner_status` 最小链路
- 主要用于打通消息边界和后续接入点

## 3. 事件与接口约定

### 3.1 当前阶段的接口收敛原则

本阶段先不新增真实规划模块，也不直接冻结自定义 `.msg`，而是先把三条 topic 的业务语义固定住。

原因：
- `Nav2 / PlanSys2 / Gazebo` 消费边界还没完全落地
- 当前感知 payload 仍包含研究态诊断字段
- 先冻结字段名、状态枚举、空值和频率约定，更利于平滑迁移

### 3.2 当前冻结的三个逻辑消息

当前把三条 topic 视为三类正式逻辑消息：

- `PerceptionEvent`
- `SupervisorStatus`
- `PlannerRequest`

其中：
- `PerceptionEvent` 负责表达感知层对任务层有意义的稳定语义
- `SupervisorStatus` 负责把上游事件收敛成系统态判断
- `PlannerRequest` 负责向未来规划层输出最小意图

当前 `task_planner_bridge_node` 还会发布 `/task_planner/status`，但该消息目前仅作为系统层占位反馈，不纳入本轮冻结核心契约。

详细字段、频率、枚举、异常值约定，统一以 [system_interface_contract_2026-04-10.md](system_interface_contract_2026-04-10.md) 为准。

### 3.3 对未来规划层的边界要求

后续无论接 `PlanSys2`、LTL 自动机还是 Gazebo 验证脚本，都不应直接消费研究态感知细节，而应只依赖冻结核心字段：

- 从感知层读取：
  - `person_present`
  - `stable_person_present`
  - `stable_fall_detected`
  - `seq_stable_fall_detected`
  - `pipeline_state`
  - `perception_available`
- 从监督层读取：
  - `supervisor_state`
  - `planner_action`
  - `reason`
- 从规划请求读取：
  - `requested_action`
  - `reason`

这能保证未来替换 YOLO 检测器、时序模型甚至 perception 内部实现时，不会把规划层一起拖垮。

当前默认消费策略补充：

- supervisor 对任务层暴露的默认跌倒语义，已经收口为 `seq_stable_fall_detected`
- 规则法 `stable_fall_detected` 继续保留在 `PerceptionEvent` 中，但默认只承担 baseline/debug 职责
- 仅当时序分支在事件中显式报告 `disabled` 或 `model_not_loaded` 时，才允许规则法作为最小回退

## 4. LTL 与自动机映射

开题目标里的 `LTL + 自动机`，在工程上建议这样落地：

1. 将感知与地图中的关键状态抽象成原子命题
2. 用 LTL 描述任务约束
3. 编译成自动机
4. 将自动机状态迁移结果映射为 ROS2 任务动作

例如：
- `fall_detected -> safe_mode`
- `goal_reached -> next_task`
- `battery_low -> dock`

当前仓库还没有实现这部分逻辑，但系统架构已经为它预留了消息边界。

## 5. 当前已实现与下一阶段

### 5.1 当前已实现

- `YOLOPose` 感知主链路
- 规则法跌倒检测 baseline
- `LSTM` / `TCN` 学习型时序模型
- 批量评估与调参
- ROS2 站点级最小桥接包 `yolopose_ros`
- 系统监督占位节点
- 任务层占位节点 `task_planner_bridge_node`
- 系统级 launch / config 骨架

### 5.2 下一阶段

- 在现有 JSON schema v1 上冻结字段并做一次代码对齐
- 用真实 `PlanSys2 / LTL` 消费端替换当前 `task_planner_bridge_node`
- 接入 `RTAB-Map`
- 接入 `Nav2`
- 建立 LTL 到自动机的映射
- 在消费者语义稳定后，把三类逻辑消息迁移到 `kaiti_msgs`
- 完成 Gazebo / TurtleBot4 骨架联调

## 6. 最终工程定位

当前仓库的准确定位不是“单纯的视频摔倒检测仓库”，而是：

`面向动态家居场景移动机器人任务系统的感知子系统与系统层骨架研究框架`

后续系统层工作应围绕这个定位持续展开。
