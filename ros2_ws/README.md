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

当前输入模式支持：

- `mock`：默认模式，无摄像头环境下可直接跑通
- `video_file`：显式传入视频路径后运行
- `camera`：显式传入 `camera_device` 或 `camera_index` 后运行；输入不可用时不会直接崩溃

当前接口契约草案见：

- [../docs/system_interface_contract_2026-04-10.md](../docs/system_interface_contract_2026-04-10.md)

## 3. 当前最小闭环

```text
mock / video_file / camera
        ↓
pose_stream_node
        ↓  /kaiti/perception/events
system_supervisor_node
        ↓  /kaiti/system/supervisor/status
        ↓  /kaiti/task_planner/request
future planner layer
```

当前最小闭环已经打通：

- `mock` 模式周期性发布最小 perception event
- `supervisor` 能在 perception 不可用、超时或退出时继续优雅处理
- `planner_request` 已经作为未来规划层的最小请求边界存在

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
- topic 前缀：`/kaiti/`

当前默认参数文件顶层 key 已与节点名对齐：

- `pose_stream_node`
- `system_supervisor_node`

## 7. 当前 topic 契约摘要

当前三条 topic 仍使用 `std_msgs/msg/String`，但 payload 已收敛为有约束的 JSON schema。

### `/kaiti/perception/events`

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

### `/kaiti/system/supervisor/status`

逻辑消息：

- `SupervisorStatus`

冻结核心字段：

- `ts`
- `supervisor_state`
- `planner_mode`
- `planner_action`
- `reason`

### `/kaiti/task_planner/request`

逻辑消息：

- `PlannerRequest`

冻结核心字段：

- `ts`
- `planner_mode`
- `requested_action`
- `reason`

详细字段、频率、状态枚举和异常值约定，以：

- [../docs/system_interface_contract_2026-04-10.md](../docs/system_interface_contract_2026-04-10.md)

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
ros2 topic echo /kaiti/perception/events
```

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /kaiti/system/supervisor/status
```

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /kaiti/task_planner/request
```

## 9. 下一阶段

后续系统主线应保持这个顺序：

1. 先把当前 schema v1 和实现完全对齐
2. 再引入正式接口包 `kaiti_msgs`
3. 再接 `RTAB-Map`
4. 再接 `Nav2`
5. 最后再接 `PlanSys2 / LTL / Gazebo`
