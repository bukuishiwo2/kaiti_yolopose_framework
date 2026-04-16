# ROS2 Workspace

`ros2_ws/` 是本项目的系统层骨架工作区，当前只包含 `yolopose_ros` 一个最小包。

当前阶段的职责不是完整系统集成，而是先把感知到任务层的最小 ROS2 边界立住。

## 1. 结构

```text
ros2_ws/
└── src/yolopose_ros/
    ├── config/
    ├── launch/
    ├── resource/
    └── yolopose_ros/
```

## 2. 当前职责

当前这个 workspace 只做三件事：

1. 把当前感知管线封装成 ROS2 节点入口
2. 输出最小系统桥接 topic
3. 为后续 `RTAB-Map / Nav2 / PlanSys2 / Gazebo` 预留清晰边界

当前默认感知主线直接复用：

- `configs/infer_pose_stream.yaml`
- `models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`
- `score_threshold=0.6`
- `min_true_frames=3`
- `min_false_frames=5`

当前输入模式支持：

- `mock`：默认模式，无摄像头环境下可直接跑通
- `video_file`：显式传入视频路径后运行
- `camera`：显式传入 `camera_device` 或 `camera_index` 后运行；输入不可用时不会直接崩溃
- `ros_image`：订阅 `/camera/image_raw` 等 ROS2 图像 topic 做在线推理

当前稳定接口契约见：

- [../docs/system_interface_contract.md](../docs/system_interface_contract.md)

## 3. 当前最小闭环

```text
mock / video_file / camera / ros_image
        ↓
camera_stream_node (optional for laptop webcam)
        ↓  /camera/image_raw
pose_stream_node
        ↓  /perception/events
system_supervisor_node
        ↓  /system/supervisor/status
        ↓  /task_planner/request
task_planner_bridge_node
        ↓  /task_planner/status
future planner layer
```

当前最小闭环已经打通：

- `mock` 模式周期性发布最小 perception event
- `supervisor` 能在 perception 不可用、超时或退出时继续优雅处理
- `planner_request` 已经被最小任务层占位节点消费
- `planner_status` 已经作为未来规划层替换前的过渡反馈边界存在
- `ros_image` 模式可用 `camera_stream_node` 把电脑摄像头接成 ROS2 真图像流
- 可选发布 `/perception/debug_image`，可直接用 `rqt_image_view` 观察骨架和状态叠加

## 4. 启动方式

先构建：

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
```

只启动感知桥接：

```bash
ros2 launch yolopose_ros pose_stream.launch.py input_mode:=mock
```

启动系统级骨架：

```bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

视频文件模式：

```bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=video_file \
  video_file_path:=/absolute/path/to/demo.mp4
```

摄像头模式：

```bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=camera \
  camera_device:=/dev/video0
```

电脑摄像头 + ROS2 图像流模式：

```bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=ros_image \
  camera_stream_enabled:=true \
  camera_index:=0 \
  visualization_enabled:=true
```

如果摄像头不存在，`pose_stream_node` 不会直接崩溃，而是进入 `unavailable` 状态并继续发布状态事件。

## 5. 环境变量

建议设置：

```bash
export KAITI_PROJECT_ROOT=/absolute/path/to/kaiti_yolopose_framework
```

这样 launch 文件和节点脚本可以通过环境变量读取项目根目录，而不是把宿主机绝对路径写进配置。

## 6. 命名规则

- launch 文件：`snake_case.launch.py`
- YAML 配置：`snake_case.yaml`
- 节点文件：`snake_case_node.py`
- topic 推荐命名：`/<layer>/<name>`

当前默认参数文件顶层 key 已与节点名对齐：

- `camera_stream_node`
- `pose_stream_node`
- `system_supervisor_node`
- `task_planner_bridge_node`

`system_supervisor_node` 当前提供 `need_reobserve` 边界稳定化参数：

- `reobserve_enter_frames: 2`
- `reobserve_exit_frames: 5`

## 7. 当前 topic 契约摘要

当前三条 topic 仍使用 `std_msgs/msg/String`，但 payload 已收敛为有约束的 JSON schema。

### `/perception/events`

逻辑消息：

- `PerceptionEvent`

核心字段：

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

补充说明：

- 当 `input_mode=ros_image` 时，`source` 会标记为 `ros:///camera/image_raw`
- 诊断字段里会额外带 `ros_image_topic` 与 `ros_header_frame_id`
- supervisor 默认以 `seq_stable_fall_detected` 作为任务层跌倒触发输入
- 当前额外输出 `observation_state / observation_reason`，用于表达“有人但当前不可可靠判断”的观察态
- `stable_fall_detected / raw_fall_detected` 继续保留在事件与调试图像中，仅用于 baseline/debug 与显式失效回退
- sequence 在线诊断字段已补齐，当前可直接从 `PerceptionEvent` 观察：
  `seq_model_loaded`
  `seq_detector_enabled`
  `seq_sequence_len`
  `seq_window_ready`
  `seq_window_size`
  `seq_track_id`
  `seq_fall_score`
  `seq_raw_fall_detected`
  `seq_stable_fall_detected`
  `seq_skip_reason`
  `seq_invalid_reason`

### `/camera/image_raw`

逻辑消息：

- `sensor_msgs/msg/Image`

当前用途：

- 由 `camera_stream_node` 从电脑摄像头发布真实图像流
- 供 `pose_stream_node(input_mode=ros_image)` 订阅

### `/perception/debug_image`

逻辑消息：

- `sensor_msgs/msg/Image`

当前用途：

- 由 `pose_stream_node` 可选发布调试图像
- 图像中叠加关键点骨架、人体框、track id、fall score、raw/stable state、supervisor action/reason
- sequence 调试信息会额外显示 `loaded / ready / win / mode / track / valid / kpts / skip / invalid`
- 可直接用 `rqt_image_view` 观察

### `/system/supervisor/status`

逻辑消息：

- `SupervisorStatus`

冻结核心字段：

- `ts`
- `supervisor_state`
- `planner_mode`
- `planner_action`
- `reason`

当前决策补充：

- 正常情况下只消费时序主线 `seq_stable_fall_detected`
- 仅当 perception event 明确给出 `seq_fall_detector_enabled=false` 或 `seq_fall_model_loaded=false` 时，才允许规则法 `stable_fall_detected` 回退接管
- `need_reobserve` 当前只用于“有人但当前不可可靠判断”的中间状态
- `need_reobserve` 不覆盖真实 `fall_detected`，也不替代 `no_person_present`
- `need_reobserve` 采用最小滞回：连续 2 帧进入，连续 5 帧退出，减少 `low_visibility <-> stable` 抖动

### `/task_planner/request`

逻辑消息：

- `PlannerRequest`

冻结核心字段：

- `ts`
- `planner_mode`
- `requested_action`
- `reason`

### `/task_planner/status`

当前用途：

- 由 `task_planner_bridge_node` 发布占位反馈
- 用于确认任务层最小消费者已经接到 supervisor request
- 暂不作为冻结核心契约

当前字段会区分：

- `reason`：当前实际状态原因
- `state_reason`：由动作映射得到的占位状态原因
- `request_reason`：原始请求原因
- `request_supported`：占位 planner 是否支持该动作

当前最小占位状态集合：

- `idle`
- `waiting`
- `reobserve_pending`
- `dispatching_safe_mode`
- `holding`

当前固定映射：

- `monitor -> idle / monitoring_request`
- `wait_for_update -> waiting / waiting_for_perception_update`
- `need_reobserve -> reobserve_pending / reobserve_requested`
- `trigger_safe_mode -> dispatching_safe_mode / safe_mode_requested`
- `hold -> holding / planner_hold`

详细字段、频率、状态枚举和异常值约定，以：

- [../docs/system_interface_contract.md](../docs/system_interface_contract.md)

为准。

## 8. 无摄像头环境验证

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

另开终端观察：

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /perception/events
```

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /camera/image_raw
```

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /system/supervisor/status
```

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /task_planner/request
```

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /task_planner/status
```

```bash
source ros2_ws/install/setup.bash
rqt_image_view /perception/debug_image
```

## 9. Phase 4a TurtleBot4 + RTAB-Map 最小接入

Phase 4a 提供一个专用入口，用于把 TurtleBot4 仿真相机接到现有 `pose_stream_node(input_mode=ros_image)`，同时让 RTAB-Map 消费同一组仿真传感器流。

先安装外部运行依赖：

```bash
sudo apt install ros-humble-turtlebot4-simulator ros-humble-irobot-create-nodes ros-humble-rtabmap-ros
```

构建并启动：

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros phase4a_turtlebot4_rtabmap.launch.py
```

默认逻辑 topic：

- RGB：`/oakd/rgb/preview/image_raw`
- Depth：`/oakd/rgb/preview/depth`
- Camera info：`/oakd/rgb/preview/camera_info`
- Laser scan：`/scan`
- Odometry：`/odom`
- TF：`/tf`、`/tf_static`

当前默认禁用 RTAB-Map visual odometry：

- `visual_odometry:=false`
- `publish_tf_odom:=false`

因此 `/odom` 应只由 TurtleBot4 底盘侧发布，不能再出现 `/rgbd_odometry` 同时发布 `/odom`。

如果 TurtleBot4 仿真实际 topic 名不同，启动时覆盖：

```bash
ros2 launch yolopose_ros phase4a_turtlebot4_rtabmap.launch.py \
  rgb_topic:=/actual/rgb/image \
  depth_topic:=/actual/depth/image \
  camera_info_topic:=/actual/camera_info
```

验证最小输出：

```bash
ros2 topic echo /perception/events
ros2 topic echo /task_planner/status
ros2 topic echo --once /map
ros2 topic echo --once /localization_pose
ros2 run tf2_ros tf2_echo odom base_link
```

该入口不启动 Nav2 完整闭环，不接 PlanSys2 / LTL，不新增消息类型，也不让 planner placeholder 消费地图或定位输出。

## 10. 下一阶段

后续系统主线应保持这个顺序：

1. 先把当前 schema v1 和实现完全对齐
2. 验证 Phase 4a `RTAB-Map` 最小挂载
3. 再接 `Nav2`
4. 用真实 `PlanSys2 / LTL` 替换当前占位任务层，再推进 Gazebo
