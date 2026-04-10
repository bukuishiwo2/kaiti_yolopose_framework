# System Audit 2026-04-10

## 1. 任务目标

检查 `ros2_ws/` 系统骨架是否与仓库当前系统主线一致，重点核对：

- `launch / config / node / package` 骨架是否自洽
- 是否已经支撑“感知到任务层桥接”的当前阶段目标
- topic、参数、节点职责、启动入口与文档是否一致
- `RTAB-Map / Nav2 / PlanSys2 / LTL` 的预留是否已经形成稳定接口边界
- 哪些结构性风险会阻碍后续接入或联调

## 2. 检查范围

- `ros2_ws/README.md`
- `ros2_ws/src/yolopose_ros/package.xml`
- `ros2_ws/src/yolopose_ros/setup.py`
- `ros2_ws/src/yolopose_ros/setup.cfg`
- `ros2_ws/src/yolopose_ros/config/perception_bridge.yaml`
- `ros2_ws/src/yolopose_ros/config/system_stack.yaml`
- `ros2_ws/src/yolopose_ros/launch/pose_stream.launch.py`
- `ros2_ws/src/yolopose_ros/launch/perception_bridge.launch.py`
- `ros2_ws/src/yolopose_ros/launch/system_stack.launch.py`
- `ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py`
- `ros2_ws/src/yolopose_ros/yolopose_ros/system_supervisor_node.py`
- `docs/system_architecture.md`
- `docs/system_bringup_skeleton.md`
- `docs/kaiti_alignment.md`
- 参考：`README.md`
- 参考：`docs/worklogs/worklog_2026-04-10.md`
- 参考：`src/yolopose/pipeline/runner.py`
- 参考：`configs/infer_pose_stream.yaml`

## 3. 检查方法

- 静态阅读系统文档与 `ros2_ws` 骨架实现
- 交叉核对默认 topic、参数、节点职责和启动入口
- 结合感知运行器 `PoseRunner` 判断系统桥接是否真实闭环
- 进行了轻量语法校验：`python3 -m compileall ros2_ws/src/yolopose_ros` 通过

## 4. 关键发现

### 4.1 当前骨架“能启动包结构”，但还不能稳定支撑真正的感知到任务层桥接

结论：**当前 `ros2_ws` 更接近“系统边界占位骨架”，还不是可联调的在线桥接骨架。**

依据：

- `pose_stream_node.py` 中 `run()` 直接同步执行 `self.runner.run()`，只有在整个推理流程结束后才发布一次 `{"status": "finished"}` 到事件 topic。
- `src/yolopose/pipeline/runner.py` 实际已经逐帧生成 `record`，但这些记录只写 `jsonl` 和打印日志，没有回调给 ROS2 发布器。
- 对于摄像头 / RTSP / 长视频输入，`system_supervisor_node` 在运行期间大概率收不到持续语义事件，因此“感知到任务层桥接”在运行时并未打通。

判断：

- 这套骨架足以表达“未来节点边界长什么样”。
- 但它还不足以支撑当前阶段目标中所说的“把感知结果作为任务层可消费的稳定语义源”。

### 4.2 参数文件与节点名不一致，YAML 很可能没有真正生效

`perception_bridge.yaml` 与 `system_stack.yaml` 的顶层键都是 `yolopose_ros`，但 launch 中实际节点名分别是 `pose_stream_node` 和 `system_supervisor_node`。

这意味着：

- `ros2_ws/src/yolopose_ros/config/perception_bridge.yaml`
- `ros2_ws/src/yolopose_ros/config/system_stack.yaml`

很可能不会按预期把参数注入到对应节点，除非改成节点名或通配写法。当前 launch 中真正确定会生效的只有内联传入的：

- `project_root` in `pose_stream.launch.py`
- `project_root` in `perception_bridge.launch.py`
- `project_root` in `system_stack.launch.py`

影响：

- `infer_config`
- `event_topic`
- `perception_event_topic`
- `supervisor_status_topic`
- `planner_request_topic`
- `planner_mode`

这些参数大概率都在依赖节点内默认值，而不是 YAML。

这属于当前骨架最重要的自洽性问题之一，因为它会直接影响后续多机、多实例和环境迁移。

### 4.3 文档声称已形成的 topic / 节点职责，有多处仍停留在占位

对照文档和代码后，存在以下错位：

- `docs/system_architecture.md` 建议感知桥接输出 `/kaiti/perception/events` 与 `/kaiti/perception/person_state`，但代码只创建了一个事件 publisher，没有 `person_state` publisher，也没有相应参数。
- `docs/system_architecture.md` 与 `docs/system_bringup_skeleton.md` 都把 `/kaiti/task_planner/request` 描述为监督层输出，但 `system_supervisor_node.py` 只发布 `/kaiti/system/supervisor/status`，并没有创建 planner request publisher。
- `system_stack.yaml` 里有 `map_topic`、`localization_topic`、`nav_goal_action`，但 `system_supervisor_node.py` 没有声明、读取或使用这 3 个参数。
- `docs/system_bringup_skeleton.md` 把 `pose_stream.launch.py` 和 `perception_bridge.launch.py` 区分为两种用途，但两份 launch 目前几乎等价，只是变量名不同。

判断：

- topic 命名方向是清楚的。
- 但 topic 的“实际写入方”和“实际消费方”仍未全部存在，当前接口边界还没有落到可验证状态。

### 4.4 当前默认系统入口与仓库主学习模型结论不一致

仓库当前主线结论明确为：

- `README.md`：`LSTM` 是综合主模型，`TCN` 是低误报候选
- `docs/worklogs/worklog_2026-04-10.md`：默认推理模型已切回 `models/fall_sequence_lstm.pt`

但 `configs/infer_pose_stream.yaml` 当前仍写的是：

- `sequence_fall_detector.model_path: models/fall_sequence_tcn.pt`

而 `pose_stream_node.py` 默认就是读取这份 `infer_pose_stream.yaml`。

影响：

- 即使 ROS2 骨架运行起来，系统默认接入的也不是仓库当前声明的主学习模型。
- 这会让系统层联调结论和感知主线 benchmark 结论出现偏差。

这是“系统主线是否与仓库当前默认一致”的直接错位。

### 4.5 事件字段边界已经有雏形，但还不是稳定接口

正面结论：

- `runner.py` 逐帧 `record` 已包含 `frame_id`、`source`、`person_count`、`stable_person_present`、`stable_fall_detected`、`seq_stable_fall_detected` 等字段。
- `system_supervisor_node.py` 也已经在 `_build_status()` 中做了第一层语义归一化，能产出 `planner_action` 和 `reason`。

但接口仍不稳定，原因是：

- 文档建议字段名包含 `timestamp`、`person_present`，当前运行器实际输出是 `ts`、`stable_person_present`。
- 监督节点对字段名做了兼容分支，说明上游 schema 仍在漂移。
- 传输格式仍是 `std_msgs/String + JSON`，还没有形成明确的消息定义、版本约束和扩展策略。

结论：

- 边界已经开始收敛。
- 但目前仍属于“概念稳定、协议未稳定”。

## 5. 对题目 1-5 的直接回答

### 5.1 `ros2_ws` 当前 launch/config/node/package 骨架是否自洽，能否支撑当前阶段目标

部分自洽。

自洽的部分：

- `package.xml / setup.py / setup.cfg / launch / config / console_scripts` 组织关系完整。
- `system_stack.launch.py` 作为系统入口的意图明确。
- 语法层面，现有 Python 文件可被 `compileall` 通过。

不自洽的部分：

- 参数 YAML 与节点名不匹配，配置生效路径不可靠。
- `pose_stream_node` 不是在线事件桥，而是“一次性跑完推理后发结束消息”。
- `system_supervisor_node` 没有真正向 planner request topic 发消息。

因此结论是：

- **它能支撑“系统骨架展示”和“接口命名收敛”这个阶段目标。**
- **它还不能支撑“感知到任务层桥接已基本打通”这个更强目标。**

### 5.2 topic、参数、节点职责、启动入口是否一致；文档和代码有无错位

不完全一致，存在明确错位。

主要错位：

- 参数文件顶层键错误，topic / 参数配置可能未实际注入节点。
- 文档描述有 `/kaiti/perception/person_state` 与 `/kaiti/task_planner/request` 输出，代码未实现对应 publisher。
- `system_stack.yaml` 中部分未来参数没有被节点使用。
- `pose_stream.launch.py` 与 `perception_bridge.launch.py` 的职责差异主要停留在文档说明。
- 文档主线默认模型为 `LSTM`，系统默认推理配置实际指向 `TCN`。

### 5.3 对 `RTAB-Map / Nav2 / PlanSys2 / LTL` 的预留是否清楚，哪些是文档占位，哪些已形成稳定接口边界

预留是清楚的，但大部分仍是文档占位。

仅文档占位：

- `RTAB-Map`：当前只有 `docs/system_architecture.md` 中的输入输出建议，以及 `system_stack.launch.py` 中的 `LogInfo`
- `Nav2`：当前只有 action/topic 命名建议和日志提示
- `PlanSys2 / LTL`：当前只有 topic 命名、planner_mode 字符串和架构说明

已开始形成边界但仍未稳定：

- `/kaiti/perception/events`
- `/kaiti/system/supervisor/status`
- `system_supervisor_node.py` 中的事件归一化逻辑

尚未形成稳定接口的原因：

- 仍使用字符串 JSON
- 没有 planner request publisher
- 没有自定义消息 / service / action
- 没有关于地图、导航、规划层的真实订阅或依赖声明

### 5.4 有哪些结构性风险会阻碍后续接入或联调

高优先级风险如下：

1. 参数文件不生效风险  
会直接破坏环境迁移、topic 重映射、多实例运行和后续分层调参。

2. 感知桥接不是在线流式发布  
会使监督层、规划层、导航层无法在运行中消费感知事件，导致系统联调停留在“启动了两个节点但没有消息闭环”。

3. 默认模型配置与主线结论不一致  
会让系统层验证和感知 benchmark 指向不同模型，影响后续结论可信度。

4. planner 接口只有名字没有 publisher  
后续接入 `PlanSys2` 时，当前监督层无法作为稳定 handoff 点复用。

5. 事件 schema 未冻结  
后续一旦引入自定义消息或第三方规划层，现有 `String + JSON` 的字段漂移会导致兼容层不断增加。

### 5.5 当前系统骨架最重要的结构性结论

最重要的结构性结论有 3 条：

1. 当前 `ros2_ws` 已经把“感知桥接节点 + 监督节点 + 系统入口 launch”这条主骨架立住了，方向是对的。
2. 这套骨架目前仍然是“文档先行、运行时接口未闭环”的阶段，尚不能作为稳定的感知到任务层桥接实现。
3. 真正需要优先收敛的不是再加更多占位文档，而是先把参数注入、在线事件发布、planner request 输出这三条运行时边界做实。

## 6. 结构性结论

- 当前系统主线与仓库整体定位是一致的：仓库确实正在从“感知实验仓库”向“感知 + 系统骨架研究框架”过渡。
- `ros2_ws` 的价值主要在于先固定节点边界、topic 命名和系统入口，这一点已经初步完成。
- 但从工程完成度看，当前阶段应把它定义为“系统骨架 v0”，而不是“系统桥接已可用”。
- 对后续 `RTAB-Map / Nav2 / PlanSys2 / LTL` 接入而言，现阶段最可复用的资产是命名约定与监督节点职责定义，不是现有运行时实现。

## 7. 未解决风险

- 未在本次审计中执行 `colcon build` 和真实 `ros2 launch`，因此没有覆盖环境依赖、安装路径和 ROS2 运行时行为。
- `std_msgs/String` 承载 JSON 的方案仍然脆弱，若后续多个节点并行消费，schema 漂移会放大。
- `system_supervisor_node.py` 当前更像状态解释器，不是任务层适配器；若不尽快补实际 request publisher，后续规划层接入会重新改节点职责。
- `perception_bridge.yaml` 仍写死绝对路径 `/home/yhc/kaiti_yolopose_framework`，即使已有环境变量兜底，也不利于跨机器复用。

## 8. Changed Files

本次审计未改其他文件。

changed files:

- `docs/reviews/system_audit_2026-04-10.md`

## 9. 下一步命令

建议先做最小复核：

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py
```

如果要验证当前桥接是否真的在线打通，继续执行：

```bash
ros2 topic echo /kaiti/perception/events
ros2 topic echo /kaiti/system/supervisor/status
```

如果要先修最关键的自洽性问题，优先检查：

```bash
sed -n '1,120p' /home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/config/perception_bridge.yaml
sed -n '1,120p' /home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/config/system_stack.yaml
sed -n '1,220p' /home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py
sed -n '1,220p' /home/yhc/kaiti_yolopose_framework/ros2_ws/src/yolopose_ros/yolopose_ros/system_supervisor_node.py
```
