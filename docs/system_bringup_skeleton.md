# ROS2 Skeleton

本文件说明 `ros2_ws/` 里当前已经准备好的系统级骨架，以及下一步如何往 `RTAB-Map`、`Nav2`、`PlanSys2` 对接。

接口字段级约定统一见：
- [system_interface_contract.md](system_interface_contract.md)

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
        │   ├── camera_stream_node.py
        │   ├── pose_stream_node.py
        │   ├── task_planner_bridge_node.py
        │   └── system_supervisor_node.py
        ├── package.xml
        ├── setup.py
        └── setup.cfg
```

## 2. 文件职责

### 2.1 `launch/pose_stream.launch.py`

作用：
- 只启动感知桥接节点
- 支持 `mock / video_file / camera / ros_image` 四种输入模式
- 当前默认是 `mock`，适合无摄像头机器直接验证

### 2.2 `launch/perception_bridge.launch.py`

作用：
- 和 `pose_stream.launch.py` 对应，但参数来源更适合 ROS2 工作区安装后的调用
- 便于后续被更大的系统级 launch 引入

### 2.3 `launch/system_stack.launch.py`

作用：
- 当前系统级入口
- 可选拉起电脑摄像头发布节点，并同时拉起感知桥接节点、系统监督节点和任务层占位节点
- 支持 `input_mode` 启动参数，并把输入模式透传给感知桥接节点
- 用日志说明 `RTAB-Map`、`Nav2`、`PlanSys2` 的未来挂载点

### 2.4 `config/perception_bridge.yaml`

作用：
- 给感知桥接节点提供参数默认值
- 包含项目根目录、推理配置路径、事件话题
- 当前默认 `input_mode: mock`
- 显式保留 `video_file_path`、`camera_device`、`camera_index`、`ros_image_topic` 等输入参数
- 可选保留 `visualization_enabled`、`visualization_topic`、`supervisor_status_topic` 等调试参数

### 2.5 `config/system_stack.yaml`

作用：
- 给相机节点、系统监督节点和任务层占位节点提供参数默认值
- 定义图像输入、感知输入、监督输出、规划请求、规划状态的 topic 约定
- 定义感知超时、请求超时和周期性状态发布参数
- 定义 `need_reobserve` 的最小进入 / 退出滞回参数

### 2.6 `yolopose_ros/system_supervisor_node.py`

作用：
- 订阅感知事件
- 将事件标准化
- 在感知超时、不可用、或退出后继续发布 supervisor status
- 同步输出最小 planner request，维持 perception-to-planner handoff 边界

当前它不负责真正规划，只负责把系统边界先打通。

### 2.6 `yolopose_ros/camera_stream_node.py`

作用：
- 从电脑摄像头读取实时图像
- 发布 `/camera/image_raw`
- 作为 `ros_image` 在线推理模式的最小图像源

当前它只负责最小图像发布，不负责 `camera_info`、标定或图像压缩。

### 2.7 `yolopose_ros/pose_stream_node.py` 可视化调试能力

当前额外支持：
- 可选发布调试图像 topic
- 图像中叠加关键点骨架、人体框、track id
- 图像中叠加 `fall score / raw state / stable state`
- 图像中叠加 `observation_state / observation_reason`
- 通过订阅 supervisor status 叠加 `planner_action / reason`

### 2.8 `yolopose_ros/task_planner_bridge_node.py`

作用：
- 订阅 `/task_planner/request`
- 将 `monitor / wait_for_update / need_reobserve / trigger_safe_mode / hold` 映射成最小任务层状态
- 发布 `/task_planner/status`
- 作为未来 `PlanSys2 / LTL` 消费端的占位替身

当前它不生成真实任务计划，只负责把 `planner_request` 后面的最小任务层接入补齐。

## 3. 当前可执行方式

### 3.1 构建

```bash
cd ros2_ws
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

如果摄像头设备不存在，`pose_stream_node` 不会直接崩溃，而是进入 `unavailable` 状态并持续向 `/perception/events` 发布状态事件。

### 3.6 电脑摄像头 + ROS2 图像流模式

```bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=ros_image \
  camera_stream_enabled:=true \
  camera_index:=0 \
  visualization_enabled:=true
```

该模式的最小链路为：
1. `camera_stream_node` 发布 `/camera/image_raw`
2. `pose_stream_node(input_mode=ros_image)` 订阅真实图像流并做在线推理
3. `pose_stream_node` 可选发布 `/perception/debug_image`
4. `system_supervisor_node` 输出 `/task_planner/request`
5. `task_planner_bridge_node` 输出 `/task_planner/status`

## 4. 当前消息流

当前系统骨架中，消息流建议按如下方式理解：

```text
mock / camera / video_file / ros_image
        ↓
camera_stream_node (optional)
        ↓  /camera/image_raw
        ↓
pose_stream_node
        ↓  /perception/events
        ↓  /perception/debug_image (optional)
system_supervisor_node
        ↓  /system/supervisor/status
        ↓  /task_planner/request
task_planner_bridge_node
        ↓  /task_planner/status
planner layer (future replacement)
        ↓
nav2 / rtabmap / task execution
```

当前最小闭环约定：

- `mock` 模式周期性发布最小 perception event
- `video_file` 或 `camera` 模式在输入缺失、runner 初始化失败、或 runner 退出后，转为 `unavailable / error / completed` 状态事件
- `ros_image` 模式在图像流未到达或中断时，发布 `waiting_for_ros_image / ros_image_timeout` 状态事件
- `system_supervisor_node` 会在感知无消息超过 `perception_timeout_sec` 后发布 `perception_timeout` 状态，不会静默
- `need_reobserve` 需要连续 `reobserve_enter_frames` 帧 raw 候选才进入，并连续 `reobserve_exit_frames` 帧稳定可观测才退出
- `task_planner_bridge_node` 会消费监督层请求并持续发布占位 `planner_status`
- `visualization_enabled=true` 时，`pose_stream_node` 会额外发布调试图像 topic

## 5. 当前核心三条 topic 的正式收敛方式

当前仍使用 `std_msgs/msg/String`，但不再把 payload 当成无约束 JSON。后续联调时应把三条 topic 分别视为三类正式逻辑消息：

### 5.1 `/perception/events`

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
- `observation_state`
- `observation_reason`

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
- `video_file / camera / ros_image` 跟随处理帧率或图像流频率
- 终止态或等待态 heartbeat 默认 `0.5 Hz`

### 5.2 `/system/supervisor/status`

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
- `observation_state`
- `observation_reason`
- `source_event`

这些字段只用于过渡期调试，后续真正接规划层时不应作为稳定依赖。

频率约定：
- 正常时随 perception 事件同步发布
- 等待 perception 或 perception 超时时，按 `status_publish_period_sec` 周期发布，默认 `1 Hz`

### 5.3 `/task_planner/request`

逻辑消息名：
- `PlannerRequest`

冻结核心字段：
- `ts`
- `planner_mode`
- `requested_action`
- `reason`

当前这不是完整任务计划，只是监督层给未来规划层的最小意图请求。后续接 `PlanSys2` 或 LTL 自动机时，应保留这条边界，只在消费端把 `requested_action` 映射成真实计划更新或动作分发。

### 5.4 `/task_planner/status`

逻辑消息名：
- `TaskPlannerStatus`（占位）

当前用途：
- 由 `task_planner_bridge_node` 发布
- 用于确认 `/task_planner/request` 已被系统层最小消费者接收
- 作为后续真实规划层替换前的过渡状态 topic

当前常见字段：
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

当前最小占位状态集合：
- `idle`
- `waiting`
- `reobserve_pending`
- `dispatching_safe_mode`
- `holding`

当前 request/status 固定映射：

| `requested_action` | `planner_state` | `state_reason` |
|---|---|---|
| `monitor` | `idle` | `monitoring_request` |
| `wait_for_update` | `waiting` | `waiting_for_perception_update` |
| `need_reobserve` | `reobserve_pending` | `reobserve_requested` |
| `trigger_safe_mode` | `dispatching_safe_mode` | `safe_mode_requested` |
| `hold` | `holding` | `planner_hold` |

说明：
- 该 topic 当前不属于冻结核心契约
- 后续接入真实规划层时，可以保留 topic 名并替换消费者实现

### 5.5 `/perception/debug_image`

逻辑消息名：
- `DebugPerceptionImage`（调试）

当前用途：
- 发布带关键点骨架、人体框、track id 的调试图像
- 叠加 `fall score / raw / stable / supervisor action / reason`
- 供 `rqt_image_view` 直接查看

说明：
- 该 topic 不属于核心接口契约
- 默认关闭，需显式设置 `visualization_enabled:=true`

## 6. 命名规则

建议统一使用以下规则：

- ROS2 包名：`snake_case`
- launch 文件：`snake_case.launch.py`
- config 文件：`snake_case.yaml`
- 节点名：`snake_case`
- topic：`/<layer>/<name>`

推荐命名示例：
- `pose_stream_node`
- `camera_stream_node`
- `system_supervisor_node`
- `task_planner_bridge_node`
- `/camera/image_raw`
- `/perception/events`
- `/perception/debug_image`
- `/system/supervisor/status`
- `/task_planner/request`
- `/task_planner/status`

## 7. 当前已实现与下一阶段

### 7.1 当前已实现

- 感知桥接包 `yolopose_ros`
- 只启动感知的本地 launch
- 系统级 skeleton launch
- 电脑摄像头 ROS2 图像发布节点
- 在线可视化调试图像 topic
- 系统监督占位节点
- 任务层占位节点
- 参数化 YAML 配置
- `mock / video_file / camera / ros_image` 四种输入模式骨架
- 无摄像头环境下可跑通的最小闭环

### 7.2 下一阶段

- 保持当前 perception / supervisor / planner request / planner status 语义不回改
- 按挂载边界引入 `RTAB-Map`
- 按挂载边界引入 `Nav2`
- 用真实 `PlanSys2 / LTL` 任务流替代当前 `task_planner_bridge_node`

## 8. 后续系统挂载边界

### 8.1 `RTAB-Map / 建图定位层`

当前不接入真实 `RTAB-Map` 节点，只冻结未来挂载点：

- 未来输入：`/camera/image_raw`、`/camera/camera_info`、`/scan`、`/odom`、`/tf`
- 未来输出：`/map`、`/rtabmap/localization_pose`、`/tf`
- 当前关系：不改变 `/perception/events -> /system/supervisor/status -> /task_planner/request` 语义
- 后续职责：向真实 planner 提供地图、定位和可达性信息

### 8.2 `Nav2 / 导航执行层`

当前不接入 `/navigate_to_pose` action，只冻结未来挂载点：

- 未来输入：真实 planner 发出的导航目标或恢复动作
- 未来输出：导航状态、到达结果、失败原因
- 当前关系：`task_planner_bridge_node` 不调用 Nav2，只作为 planner placeholder
- 后续职责：执行由真实 planner 产生的空间动作

### 8.3 `PlanSys2 / LTL / 任务规划层`

当前不接入真实 `PlanSys2` 或 LTL 自动机，只冻结替换边界：

- 替换对象：`task_planner_bridge_node`
- 保留输入：`/task_planner/request`
- 保留输出：`/task_planner/status`
- 允许新增：内部 plan、action dispatch、execution feedback topic
- 不允许要求：上游 `pose_stream_node` 或 `system_supervisor_node` 为真实 planner 回改现有语义

### 8.4 当前明确不做

- 不接真实 `RTAB-Map`
- 不接真实 `Nav2`
- 不接真实 `PlanSys2 / LTL`
- 不新增 action/service 调用
- 不新增消息类型体系
- 不改 `models/*.pt`
- 不训练
- 不扩外部数据集
- 不让 planner 直接依赖感知研究态字段

## 9. 说明

这个骨架的目标不是一次性把所有模块都接完，而是先把工程边界和启动入口固定下来，避免后续把感知、建图、规划混成一个难以维护的文件堆。当前版本先优先保证 `mock` 默认可运行，再为真实视频和摄像头输入留出兼容入口。
