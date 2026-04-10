# ROS2 Workspace

这个目录是系统层骨架，当前只包含 `yolopose_ros` 一个最小包。

## 1. 结构

```text
ros2_ws/
└── src/yolopose_ros/
    ├── launch/
    ├── config/
    ├── resource/
    └── yolopose_ros/
```

## 2. 当前职责

当前这个 workspace 只做两件事：

1. 把当前感知管线封装成 ROS2 节点入口
2. 为后续的 `RTAB-Map`、`Nav2`、`PlanSys2` 提供系统级骨架

当前输入模式支持：

- `mock`：默认模式，无摄像头环境下可直接跑通
- `video_file`：显式传入视频路径后运行
- `camera`：显式传入 `camera_device` 或 `camera_index` 后运行；输入不可用时不会直接崩溃，会持续发布不可用状态

当前接口契约文档见：
- [docs/system_interface_contract_2026-04-10.md](/home/yhc/kaiti_yolopose_framework/docs/system_interface_contract_2026-04-10.md)

## 3. 启动顺序

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros pose_stream.launch.py input_mode:=mock
```

系统级骨架入口：

```bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

视频文件模式：

```bash
ros2 launch yolopose_ros pose_stream.launch.py \
  input_mode:=video_file \
  video_file_path:=/absolute/path/to/demo.mp4
```

摄像头模式：

```bash
ros2 launch yolopose_ros pose_stream.launch.py \
  input_mode:=camera \
  camera_device:=/dev/video0
```

如果不传 `camera_device` 且 `camera_index` 仍为 `-1`，节点不会强行退回到 `/dev/video0`，而是进入 `unavailable` 状态并继续输出状态事件。

## 4. 环境变量

建议设置：

```bash
export KAITI_PROJECT_ROOT=/home/yhc/kaiti_yolopose_framework
```

这样 launch 文件和节点脚本都可以从环境变量读取项目根目录，而不是把绝对路径写死在配置里。

## 5. 命名规则

- launch 文件统一使用 `snake_case.launch.py`
- YAML 配置统一使用 `snake_case.yaml`
- 节点统一使用 `snake_case_node.py`
- topic 建议统一以 `/kaiti/` 作为前缀

当前默认参数文件的顶层 key 已与节点名对齐：

- `pose_stream_node`
- `system_supervisor_node`

## 6. 当前 topic 契约摘要

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

运行态帧事件还包含：
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

### `/kaiti/system/supervisor/status`

逻辑消息：
- `SupervisorStatus`

冻结核心字段：
- `ts`
- `supervisor_state`
- `planner_mode`
- `planner_action`
- `reason`

当前实现中的 `source_event` 只用于调试，不建议未来消费者继续依赖。

### `/kaiti/task_planner/request`

逻辑消息：
- `PlannerRequest`

冻结核心字段：
- `ts`
- `planner_mode`
- `requested_action`
- `reason`

当前阶段它表达的是最小规划意图，不是完整计划结果。

推荐下游做法：
- 规划层只依赖冻结核心字段
- 不直接解析 perception 诊断字段或 `source_event`
- 等 `Nav2 / PlanSys2 / Gazebo` 消费边界稳定后，再迁移到 `kaiti_msgs`

## 7. 无摄像头环境验证

建议至少验证下面三条：

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

另开终端观察 topic：

```bash
source /home/yhc/kaiti_yolopose_framework/ros2_ws/install/setup.bash
ros2 topic echo /kaiti/perception/events
```

```bash
source /home/yhc/kaiti_yolopose_framework/ros2_ws/install/setup.bash
ros2 topic echo /kaiti/system/supervisor/status
```

```bash
source /home/yhc/kaiti_yolopose_framework/ros2_ws/install/setup.bash
ros2 topic echo /kaiti/task_planner/request
```

## 8. 下一阶段

后续这里会继续扩展：
- 先把当前 schema v1 和实现完全对齐
- 再引入正式接口包 `kaiti_msgs`
- 传感器/建图节点
- 导航节点
- 任务规划节点
- 监督与恢复节点
