# Architect Mock Input Summary

日期：2026-04-10

## 1. 任务目标

本轮任务目标是在不做大重构的前提下，把当前 ROS2 系统骨架收口成一个可在无摄像头机器上稳定启动、可观察、可优雅降级的最小运行闭环，具体包括：

- 将感知输入改成 `mock / video_file / camera` 三种模式，默认先保证 `mock` 模式可跑通
- 取消 `pose_stream_node` 对 `/dev/video0` 的默认强依赖
- 在 `camera` 不可用、视频路径缺失、或感知线程退出时不直接崩溃，而是显式进入可观测的降级状态
- 让 `system_stack.launch.py` 支持 `input_mode` 参数并透传到感知节点
- 在 `mock` 模式下周期性发布最小 perception event
- 让 supervisor 在 perception 不可用、超时、或退出后持续输出稳定的 status 和最小 planner request
- 修复重复 `shutdown` 路径导致的退出问题
- 同步更新 launch、config、README 与系统骨架文档

结合 [`/home/yhc/kaiti.docx`](/home/yhc/kaiti.docx) 所描述的开题目标，当前仓库的定位仍然是面向“动态家居场景中的摔倒救援、物资协同与电量补给”的 ROS2 任务系统原型，但本轮只完成了其中最前面的工程收口工作：先把感知入口和系统级 handoff 边界固定下来，为后续 `RTAB-Map / Nav2 / PlanSys2 或 LTL 规划层 / Gazebo / 实物平台` 接入留出稳定入口。

## 2. 变更文件列表

本轮实现与文档收口涉及以下文件：

- [src/yolopose/pipeline/runner.py](/home/yhc/kaiti_yolopose_framework/src/yolopose/pipeline/runner.py)
- [ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py](/home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py)
- [ros2_ws/src/yolopose_ros/yolopose_ros/system_supervisor_node.py](/home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/yolopose_ros/system_supervisor_node.py)
- [ros2_ws/src/yolopose_ros/launch/pose_stream.launch.py](/home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/launch/pose_stream.launch.py)
- [ros2_ws/src/yolopose_ros/launch/perception_bridge.launch.py](/home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/launch/perception_bridge.launch.py)
- [ros2_ws/src/yolopose_ros/launch/system_stack.launch.py](/home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/launch/system_stack.launch.py)
- [ros2_ws/src/yolopose_ros/config/perception_bridge.yaml](/home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/config/perception_bridge.yaml)
- [ros2_ws/src/yolopose_ros/config/system_stack.yaml](/home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/config/system_stack.yaml)
- [ros2_ws/README.md](/home/yhc/kaiti_yolopose_framework/ros2_ws/README.md)
- [docs/system_bringup_skeleton.md](/home/yhc/kaiti_yolopose_framework/docs/system_bringup_skeleton.md)

本次 architect 收口文档写入：

- [docs/reviews/architect_mock_input_summary_2026-04-10.md](/home/yhc/kaiti_yolopose_framework/docs/reviews/architect_mock_input_summary_2026-04-10.md)

## 3. 指标或结构性结论

### 3.1 本轮完成了什么

本轮已经把“感知入口不稳定、系统层无法优雅消费、无摄像头无法验证”的问题收成一个最小可运行闭环：

- `pose_stream_node` 默认 `input_mode=mock`，不再隐式依赖 `/dev/video0`
- `system_stack.launch.py`、`pose_stream.launch.py`、`perception_bridge.launch.py` 已支持 `input_mode` 及其相关参数透传
- `mock` 模式会周期性发布最小 perception event 到 `/kaiti/perception/events`
- `runner.py` 已提供逐帧 `event_callback`，使在线 ROS2 发布不必等整段推理结束
- `system_supervisor_node` 会持续输出 `/kaiti/system/supervisor/status` 与 `/kaiti/task_planner/request`
- perception 不可用、超时、输入缺失、runner 初始化失败、runner 退出后，系统不再静默或直接崩溃，而是进入 `unavailable / error / completed / perception_timeout` 等显式状态
- YAML 顶层 key 已对齐真实 ROS2 节点名 `pose_stream_node` 与 `system_supervisor_node`
- 重复 `shutdown` 路径已收敛为带 `rclpy.ok()` 判断的退出逻辑

### 3.2 为什么本轮定义为“最小可运行闭环”

这轮不是最终系统，而是最小可运行闭环，原因很明确：

- 当前闭环只固定了 `perception -> supervisor -> planner_request placeholder` 这条最小消息链，尚未接入真实任务规划与执行层
- `mock` 事件是最小语义占位，不代表真实摔倒检测、人物状态理解或任务决策能力已经完成
- `video_file / camera` 只是把真实输入入口和失败降级路径立住，还没有完成长期在线运行、恢复策略、结构化消息定义和完整联调
- 与 `kaiti.docx` 的终态目标相比，`RTAB-Map`、`Nav2`、`PlanSys2/LTL`、Gazebo 动态场景、多机器人协同、真实机器人硬件联调都还未落入当前运行链

因此，本轮工作的正确表述不是“系统完成”，而是“系统骨架已具备无摄像头环境下的最小运行、观测与降级能力”。

### 3.3 三种输入模式在当前阶段的意义

- `mock`：用于当前阶段的默认入口。它解决了“没有摄像头也无法推进系统联调”的问题，让系统级 topic、supervisor 行为、planner handoff 和 launch 配置可以先独立验证。
- `video_file`：用于下一阶段的离线可重复验证。它比真摄像头更利于回放、复现实验、对比稳定化和调试事件语义。
- `camera`：用于后续接入真实设备和实机联调，但当前实现先把“设备可能不存在、可能打开失败”的工程边界处理好，避免系统骨架被硬件可用性卡死。

这三种模式的组合意义不是增加功能点，而是把“算法验证、系统联调、实物部署”三个阶段的入口分离开，减少耦合。

### 3.4 mock 无摄像头验证结果

本轮已完成的无摄像头环境验证结果如下：

- `python3 -m compileall ros2_ws/src/yolopose_ros` 通过
- `colcon build --symlink-install --packages-select yolopose_ros` 通过
- `ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock` 可正常启动
- `/kaiti/perception/events`、`/kaiti/system/supervisor/status`、`/kaiti/task_planner/request` 三个 topic 在 `mock` 模式下都能收到消息
- `ros2 launch yolopose_ros system_stack.launch.py input_mode:=camera camera_device:=/dev/does_not_exist` 不会直接崩溃，`pose_stream_node` 会进入 `camera_device_not_found`，supervisor 持续输出 `unavailable`

这说明当前阶段已经具备“无摄像头机器可跑系统入口、可看到系统状态、可验证感知到任务层占位链路”的工程基础。

### 3.5 离开题目标中的完整系统还差什么

结合开题目标，当前离完整系统仍至少差以下几层：

- 空间层：`RTAB-Map` 在线建图、定位、地图增量更新，以及与动态环境的一致性处理
- 导航层：`Nav2` 的可达性、局部避障、恢复行为与底盘约束联调
- 规划层：从当前 `planner_request placeholder` 升级到真实任务建模、时序约束、恢复与重规划机制，必要时接入 `PlanSys2` 或 `LTL` 自动机方案
- 语义层：把当前 `std_msgs/String + JSON` 的研究态输出收敛成面向任务的结构化语义接口，并明确单一任务级语义状态
- 验证层：Gazebo 动态场景实验、视频回放评估、以及 TurtleBot4 或实物车平台联调

## 4. 未解决风险

- 当前消息接口仍是 `std_msgs/String + JSON`，适合最小闭环验证，不适合长期稳定接口管理
- `mock` 事件只证明系统骨架和降级路径可用，不证明真实感知精度、时序稳定性和任务触发逻辑已经满足开题目标
- `video_file / camera` 模式依然依赖现有感知链路和底层运行库，真实输入下的鲁棒性、恢复能力和长期运行表现仍待验证
- `planner_request` 目前只是最小占位输出，还没有真实连接任务规划器、导航 action 和任务执行反馈
- 从 `kaiti.docx` 的最终目标看，当前系统还没有形成“建图-导航-语义-规划-执行-评估”的完整闭环，更没有进入多机器人协同和实物验证阶段

## 5. 下一步命令

无摄像头环境下，建议先用以下命令复现本轮最小闭环：

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

另开终端观察三个关键 topic：

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

建议紧接着做的下一步，不是扩更多节点，而是先验证两个收口动作：

```bash
source /home/yhc/kaiti_yolopose_framework/ros2_ws/install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=camera \
  camera_device:=/dev/does_not_exist
```

```bash
source /home/yhc/kaiti_yolopose_framework/ros2_ws/install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=video_file \
  video_file_path:=/absolute/path/to/demo.mp4
```

前者用于确认摄像头缺失时的优雅降级仍稳定，后者用于把 `mock` 闭环推进到可复现的视频回放闭环，这是从最小系统走向真实系统的下一个合理台阶。
