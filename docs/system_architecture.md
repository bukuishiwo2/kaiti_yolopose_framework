# System Architecture

本文件描述的是开题目标中的**系统层**，不是当前 `YOLOPose` 感知实验本身。

当前仓库已经把感知子系统做成可训练、可评估、可切换模型的原型；下一步要把它收敛成 ROS2 系统里的一个稳定语义源，再向建图、导航、任务规划层扩展。

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

建议输出：
- `/kaiti/perception/events`
- `/kaiti/perception/person_state`

建议消息格式：
- 当前先用 `std_msgs/String` 携带 JSON
- 后续再升级为自定义消息

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
- `/kaiti/task_planner/request`
- `/kaiti/task_planner/plan`
- `/kaiti/task_planner/status`

当前状态：
- 未接入
- 仅有规划位点定义

### 2.5 系统监督层

建议节点名：
- `system_supervisor_node`

职责：
- 订阅感知事件
- 将事件标准化
- 根据状态决定是否触发规划层
- 作为感知层与任务层之间的稳定缓冲

建议接口：
- 输入：`/kaiti/perception/events`
- 输出：`/kaiti/system/supervisor/status`
- 输出：`/kaiti/task_planner/request`

当前状态：
- 已有最小占位节点
- 主要用于打通消息边界和后续接入点

## 3. 事件与接口约定

### 3.1 感知事件

感知桥接节点建议输出统一事件对象，最少包含：

- `timestamp`
- `source`
- `person_present`
- `person_count`
- `fall_detected`
- `fall_score`
- `stable_fall_detected`
- `frame_id`

如果是学习型模型，也可以附带：
- `seq_fall_score`
- `seq_raw_fall_detected`
- `seq_stable_fall_detected`

### 3.2 规划事件

任务规划层建议使用事件标签而不是直接耦合原始帧信息，例如：

- `fall_detected`
- `person_lost`
- `map_ready`
- `goal_reached`
- `battery_low`
- `replan_required`

### 3.3 任务动作

任务层输出不应直接等于“感知结果”，而应是可执行动作，例如：

- `navigate_to_pose`
- `switch_to_safe_mode`
- `notify_operator`
- `request_relocalization`

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
- 系统级 launch / config 骨架

### 5.2 下一阶段

- 接入 `RTAB-Map`
- 接入 `Nav2`
- 定义自定义消息或服务
- 引入 `PlanSys2` 或等价规划层
- 建立 LTL 到自动机的映射
- 完成 Gazebo / TurtleBot4 骨架联调

## 6. 最终工程定位

当前仓库的准确定位不是“单纯的视频摔倒检测仓库”，而是：

`面向动态家居场景移动机器人任务系统的感知子系统与系统层骨架研究框架`

后续系统层工作应围绕这个定位持续展开。
