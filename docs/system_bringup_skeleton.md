# ROS2 Skeleton

本文件说明 `ros2_ws/` 里当前已经准备好的系统级骨架，以及下一步如何往 `RTAB-Map`、`Nav2`、`PlanSys2` 对接。

接口字段级约定统一见：
- [docs/system_interface_contract_2026-04-10.md](/home/yhc/kaiti_yolopose_framework/docs/system_interface_contract_2026-04-10.md)

## 1. 目录结构

```text
ros2_ws/
├── README.md
└── src/
    └── yolopose_ros/
        ├── config/
        │   ├── perception_bridge.yaml
        │   └── system_stack.yaml
        ├── launch/
        │   ├── perception_bridge.launch.py
        │   ├── pose_stream.launch.py
        │   └── system_stack.launch.py
        ├── resource/
        ├── yolopose_ros/
        │   ├── pose_stream_node.py
        │   └── system_supervisor_node.py
        ├── package.xml
        ├── setup.py
        └── setup.cfg
```

## 2. 文件职责

### 2.1 `launch/pose_stream.launch.py`

作用：
- 只启动感知桥接节点
- 支持 `mock / video_file / camera` 三种输入模式
- 当前默认是 `mock`，适合无摄像头机器直接验证

### 2.2 `launch/perception_bridge.launch.py`

作用：
- 和 `pose_stream.launch.py` 对应，但参数来源更适合 ROS2 工作区安装后的调用
- 便于后续被更大的系统级 launch 引入

### 2.3 `launch/system_stack.launch.py`

作用：
- 当前系统级入口
- 同时拉起感知桥接节点和系统监督节点
- 支持 `input_mode` 启动参数，并把输入模式透传给感知桥接节点
- 用日志说明 `RTAB-Map`、`Nav2`、`PlanSys2` 的未来挂载点

### 2.4 `config/perception_bridge.yaml`

作用：
- 给感知桥接节点提供参数默认值
- 包含项目根目录、推理配置路径、事件话题
- 当前默认 `input_mode: mock`
- 显式保留 `video_file_path`、`camera_device`、`camera_index` 三类输入参数

### 2.5 `config/system_stack.yaml`

作用：
- 给系统监督节点提供参数默认值
- 定义感知输入、监督输出、规划请求的 topic 约定
- 定义感知超时和周期性状态发布参数

### 2.6 `yolopose_ros/system_supervisor_node.py`

作用：
- 订阅感知事件
- 将事件标准化
- 在感知超时、不可用、或退出后继续发布 supervisor status
- 同步输出最小 planner request，维持 perception-to-planner handoff 边界

当前它不负责真正规划，只负责把系统边界先打通。

## 3. 当前可执行方式

### 3.1 构建

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
```

### 3.2 只启动感知桥接

```bash
ros2 launch yolopose_ros pose_stream.launch.py input_mode:=mock
```

### 3.3 启动系统级骨架

```bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

### 3.4 视频文件模式

```bash
ros2 launch yolopose_ros pose_stream.launch.py \
  input_mode:=video_file \
  video_file_path:=/absolute/path/to/demo.mp4
```

### 3.5 摄像头模式

```bash
ros2 launch yolopose_ros pose_stream.launch.py \
  input_mode:=camera \
  camera_device:=/dev/video0
```

如果摄像头设备不存在，`pose_stream_node` 不会直接崩溃，而是进入 `unavailable` 状态并持续向 `/kaiti/perception/events` 发布状态事件。

## 4. 当前消息流

当前系统骨架中，消息流建议按如下方式理解：

```text
mock / camera / video_file
        ↓
pose_stream_node
        ↓  /kaiti/perception/events
system_supervisor_node
        ↓  /kaiti/system/supervisor/status
        ↓  /kaiti/task_planner/request
planner layer (future)
        ↓
nav2 / rtabmap / task execution
```

当前最小闭环约定：

- `mock` 模式周期性发布最小 perception event
- `video_file` 或 `camera` 模式在输入缺失、runner 初始化失败、或 runner 退出后，转为 `unavailable / error / completed` 状态事件
- `system_supervisor_node` 会在感知无消息超过 `perception_timeout_sec` 后发布 `perception_timeout` 状态，不会静默

## 5. 当前三条 topic 的正式收敛方式

当前仍使用 `std_msgs/msg/String`，但不再把 payload 当成无约束 JSON。后续联调时应把三条 topic 分别视为三类正式逻辑消息：

### 5.1 `/kaiti/perception/events`

逻辑消息名：
- `PerceptionEvent`

当前负载包含两种 `event_type`：
- `perception_event`
- `perception_status`

系统层只允许稳定依赖以下核心字段：
- `ts`
- `event_type`
- `input_mode`
- `pipeline_state`
- `perception_available`
- `reason`
- `person_present`
- `stable_person_present`
- `stable_fall_detected`
- `seq_stable_fall_detected`

运行态帧事件额外依赖：
- `frame_id`
- `source`
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

频率约定：
- `mock` 默认 `1 Hz`
- `video_file / camera` 跟随处理帧率
- 终止态 heartbeat 默认 `0.5 Hz`

### 5.2 `/kaiti/system/supervisor/status`

逻辑消息名：
- `SupervisorStatus`

冻结核心字段：
- `ts`
- `supervisor_state`
- `planner_mode`
- `planner_action`
- `reason`

当前会附带：
- `planner_request_topic`
- `source_event`

这两个字段只用于过渡期调试，后续真正接规划层时不应作为稳定依赖。

频率约定：
- 正常时随 perception 事件同步发布
- 等待 perception 或 perception 超时时，按 `status_publish_period_sec` 周期发布，默认 `1 Hz`

### 5.3 `/kaiti/task_planner/request`

逻辑消息名：
- `PlannerRequest`

冻结核心字段：
- `ts`
- `planner_mode`
- `requested_action`
- `reason`

当前这不是完整任务计划，只是监督层给未来规划层的最小意图请求。后续接 `PlanSys2` 或 LTL 自动机时，应保留这条边界，只在消费端把 `requested_action` 映射成真实计划更新或动作分发。

## 6. 命名规则

建议统一使用以下规则：

- ROS2 包名：`snake_case`
- launch 文件：`snake_case.launch.py`
- config 文件：`snake_case.yaml`
- 节点名：`snake_case`
- topic：`/kaiti/<layer>/<name>`

推荐命名示例：
- `pose_stream_node`
- `system_supervisor_node`
- `/kaiti/perception/events`
- `/kaiti/system/supervisor/status`
- `/kaiti/task_planner/request`

## 7. 当前已实现与下一阶段

### 7.1 当前已实现

- 感知桥接包 `yolopose_ros`
- 只启动感知的本地 launch
- 系统级 skeleton launch
- 系统监督占位节点
- 参数化 YAML 配置
- `mock / video_file / camera` 三种输入模式骨架
- 无摄像头环境下可跑通的最小闭环

### 7.2 下一阶段

- 先把当前 JSON schema v1 对齐到实现
- 再引入 `kaiti_msgs` 包承接冻结核心字段
- 引入 `RTAB-Map`
- 引入 `Nav2`
- 引入 `PlanSys2` 或同类规划层
- 用真实任务流替代当前日志占位

## 8. 说明

这个骨架的目标不是一次性把所有模块都接完，而是先把工程边界和启动入口固定下来，避免后续把感知、建图、规划混成一个难以维护的文件堆。当前版本先优先保证 `mock` 默认可运行，再为真实视频和摄像头输入留出兼容入口。
