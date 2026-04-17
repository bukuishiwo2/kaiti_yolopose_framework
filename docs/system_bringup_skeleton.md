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
        │   ├── phase5_nav2_dispatcher.yaml
        │   ├── phase4b_nav2_precheck.yaml
        │   ├── phase4a_turtlebot4_rtabmap.yaml
        │   └── system_stack.yaml
        ├── launch/
        │   ├── perception_bridge.launch.py
        │   ├── phase5_nav2_dispatcher.launch.py
        │   ├── phase4b_nav2_precheck.launch.py
        │   ├── phase4a_turtlebot4_rtabmap.launch.py
        │   ├── pose_stream.launch.py
        │   └── system_stack.launch.py
        ├── resource/
        ├── yolopose_ros/
        │   ├── camera_stream_node.py
        │   ├── planner_nav2_dispatcher_logic.py
        │   ├── planner_nav2_dispatcher_node.py
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

### 2.4 `launch/phase4a_turtlebot4_rtabmap.launch.py`

作用：
- Phase 4a 专用系统入口
- 组合 TurtleBot4 仿真、当前 `system_stack.launch.py` 和 `rtabmap_launch`
- 默认让 TurtleBot4 自带 `slam/nav2` 保持关闭，由本项目单独拉起 RTAB-Map
- 将仿真 RGB 图像通过 `input_mode=ros_image` 接到 `pose_stream_node`
- RTAB-Map 作为建图定位 sidecar 输出 `/map`、`/localization_pose` 和 `/tf`
- 默认禁用 RTAB-Map visual odometry，只使用 TurtleBot4 `/odom`
- 不改变 `/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status` 语义

### 2.5 `launch/phase4b_nav2_precheck.launch.py`

作用：
- Phase 4b 专用最小 Nav2 precheck 入口
- 默认先拉起 Phase 4a TurtleBot4 + RTAB-Map 基线
- 再通过 `nav2_bringup` 的 `navigation_launch.py` 启动 Nav2 navigation servers
- 不启动 Nav2 `localization_launch.py`，不额外启动 `map_server / AMCL`
- 继续使用 RTAB-Map 输出的 `/map` 与 `map -> odom`
- 默认关闭 TurtleBot4 simulator 自带 `nav2`
- 只允许人工向 `/navigate_to_pose` 发送短距离固定 goal
- 不从 `/task_planner/request` 自动派发 goal
- 不改变 perception / supervisor / planner placeholder 语义

### 2.6 `config/perception_bridge.yaml`

作用：
- 给感知桥接节点提供参数默认值
- 包含项目根目录、推理配置路径、事件话题
- 当前默认 `input_mode: mock`
- 显式保留 `video_file_path`、`camera_device`、`camera_index`、`ros_image_topic` 等输入参数
- 可选保留 `visualization_enabled`、`visualization_topic`、`supervisor_status_topic` 等调试参数

### 2.7 `config/phase5_nav2_dispatcher.yaml`

作用：
- Phase 5 planner 到 Nav2 受控派发参数文件
- 默认 `dispatch_enabled=false`，不会产生机器人运动
- 默认 `allowed_actions=""`，需要显式开启动作白名单
- 定义 `trigger_safe_mode -> safe_mode_staging` 与 `need_reobserve -> reobserve_vantage` 的命名 goal registry
- goal pose 只来自该 YAML，当前 pose 数组格式为 `[x, y, z, qx, qy, qz, qw]`
- 默认 frame 固定为 `map`

### 2.8 `config/system_stack.yaml`

作用：
- 给相机节点、系统监督节点和任务层占位节点提供参数默认值
- 定义图像输入、感知输入、监督输出、规划请求、规划状态的 topic 约定
- 定义感知超时、请求超时和周期性状态发布参数
- 定义 `need_reobserve` 的最小进入 / 退出滞回参数

### 2.9 `config/phase4a_turtlebot4_rtabmap.yaml`

作用：
- 记录 Phase 4a 默认仿真和 RTAB-Map topic 口径
- 默认机器人为 `TurtleBot4 standard`
- 默认世界为 `warehouse`
- 默认 RTAB-Map 输入为 `/oakd/rgb/preview/image_raw`、`/oakd/rgb/preview/depth`、`/oakd/rgb/preview/camera_info`、`/scan`、`/odom`、`/tf`
- 默认 `visual_odometry=false`、`publish_tf_odom=false`，避免 `rgbd_odometry` 与 TurtleBot4 底盘同时发布 `/odom`
- 默认 perception 输入为 `ros_image`
- 该文件作为人工维护的集成配置说明，具体 launch 参数仍可在命令行覆盖

### 2.10 `config/phase4b_nav2_precheck.yaml`

作用：
- Phase 4b Nav2 最小参数文件
- 面向 TurtleBot4 standard + 简单静态短距离场景
- `global_frame=map`、`odom_topic=/odom`、`robot_base_frame=base_link`
- local/global costmap 使用 `/scan` 作为最小障碍输入
- global costmap 订阅 `/map`，当前按 RTAB-Map 在线地图处理，`map_subscribe_transient_local=false`
- 速度和加速度限制采用保守值，只用于 smoke test
- 不包含 `AMCL / map_server` 参数，不作为最终导航调参配置

### 2.11 `yolopose_ros/system_supervisor_node.py`

作用：
- 订阅感知事件
- 将事件标准化
- 在感知超时、不可用、或退出后继续发布 supervisor status
- 同步输出最小 planner request，维持 perception-to-planner handoff 边界

当前它不负责真正规划，只负责把系统边界先打通。

### 2.12 `yolopose_ros/camera_stream_node.py`

作用：
- 从电脑摄像头读取实时图像
- 发布 `/camera/image_raw`
- 作为 `ros_image` 在线推理模式的最小图像源

当前它只负责最小图像发布，不负责 `camera_info`、标定或图像压缩。

### 2.13 `yolopose_ros/pose_stream_node.py` 可视化调试能力

当前额外支持：
- 可选发布调试图像 topic
- 图像中叠加关键点骨架、人体框、track id
- 图像中叠加 `fall score / raw state / stable state`
- 图像中叠加 `observation_state / observation_reason`
- 通过订阅 supervisor status 叠加 `planner_action / reason`

### 2.14 `yolopose_ros/task_planner_bridge_node.py`

作用：
- 订阅 `/task_planner/request`
- 将 `monitor / wait_for_update / need_reobserve / trigger_safe_mode / hold` 映射成最小任务层状态
- 发布 `/task_planner/status`
- 作为未来 `PlanSys2 / LTL` 消费端的占位替身

当前它不生成真实任务计划，只负责把 `planner_request` 后面的最小任务层接入补齐。

### 2.15 `yolopose_ros/planner_nav2_dispatcher_node.py`

作用：
- Phase 5 新增的受控中间层
- 订阅 `/task_planner/request`
- 使用 `nav2_msgs/action/NavigateToPose` 调用 `/navigate_to_pose`
- 默认 `dispatch_enabled=false`，只观察和拒绝，不产生机器人运动
- 通过 `allowed_actions`、reason 白名单、命名 goal、冷却时间和单 active goal 策略限制 Nav2 派发
- `hold` 只取消 dispatcher 自己派发的 active goal

说明：
- 该节点不是 `PlanSys2 / LTL`
- 该节点不改变 `PlannerRequest` schema
- 该节点不替换 `task_planner_bridge_node`
- 该节点不从 perception debug 字段推导导航目标

### 2.16 `yolopose_ros/planner_nav2_dispatcher_logic.py`

作用：
- 存放 Phase 5 dispatcher 的纯决策逻辑
- 支撑 `scripts/verify_planner_nav2_dispatcher.py` 做不依赖 ROS runtime 的边界验证

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

### 3.7 Phase 4a TurtleBot4 仿真 + RTAB-Map 最小接入

先安装外部运行依赖：

```bash
sudo apt install ros-humble-turtlebot4-simulator ros-humble-irobot-create-nodes ros-humble-rtabmap-ros
```

再启动最小系统入口：

```bash
ros2 launch yolopose_ros phase4a_turtlebot4_rtabmap.launch.py
```

如果 TurtleBot4 仿真实际 topic 与默认逻辑名不同，优先用 launch 参数覆盖：

```bash
ros2 launch yolopose_ros phase4a_turtlebot4_rtabmap.launch.py \
  rgb_topic:=/actual/rgb/image \
  depth_topic:=/actual/depth/image \
  camera_info_topic:=/actual/camera_info \
  odom_topic:=/odom \
  scan_topic:=/scan
```

该入口只负责最小挂载：

1. TurtleBot4 仿真发布 RGB / depth / camera_info / odom / tf / scan
2. `pose_stream_node(input_mode=ros_image)` 消费 RGB 图像并保持当前 perception 事件语义
3. RTAB-Map 消费同一组仿真传感器流并输出 `/map`、`/localization_pose`、`/tf`
4. `task_planner_bridge_node` 仍是 placeholder，不消费地图或定位输出
5. `/odom` 必须只有 `diffdrive_controller` 一个 publisher，当前默认不启动 `/rgbd_odometry`

### 3.8 Phase 4b Nav2 最小 precheck

Phase 4b 在 Phase 4a 基线之上启动 Nav2 navigation servers，用于检查 lifecycle、costmap、`/plan`、`/cmd_vel` 与 1 个短距离固定 goal。

先确保 Nav2 运行依赖存在：

```bash
sudo apt install ros-humble-navigation2 ros-humble-nav2-bringup
```

构建并启动：

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros phase4b_nav2_precheck.launch.py
```

该入口默认：

1. 启动 Phase 4a TurtleBot4 + RTAB-Map + perception 基线
2. 保持 TurtleBot4 自带 `nav2=false`
3. 保持 RTAB-Map `visual_odometry=false`、`publish_tf_odom=false`
4. 启动 Nav2 `navigation_launch.py`
5. 不启动 `map_server / AMCL`
6. 不让 `task_planner_bridge_node` 调用 `/navigate_to_pose`

第一轮只允许手动 goal：

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  "{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}"
```

### 3.9 Phase 5 planner 到 Nav2 受控派发

Phase 5 在 Phase 4b 基线之上新增 `planner_nav2_dispatcher_node`，但默认不允许自动派发：

```bash
ros2 launch yolopose_ros phase5_nav2_dispatcher.launch.py dispatch_enabled:=false
```

显式开启单动作 smoke test 时，必须同时打开总开关和动作白名单：

```bash
ros2 launch yolopose_ros phase5_nav2_dispatcher.launch.py \
  dispatch_enabled:=true \
  allowed_actions:='[trigger_safe_mode]'
```

当前受控派发边界：

- `monitor`：不触发导航
- `wait_for_update`：不触发导航
- `need_reobserve`：仅遮挡 / 低可见度类 reason 可派发到 `reobserve_vantage`，`temporal_window_not_ready` 默认禁止
- `trigger_safe_mode`：仅 `fall_detected / fall_detected_rule_fallback` 可派发到 `safe_mode_staging`
- `hold`：不触发新 goal，只取消 dispatcher 自己的 active goal
- 其他动作：全部拒绝

该阶段仍不接真实 `PlanSys2 / LTL`，也不让 `/task_planner/request` 直通 `/navigate_to_pose`。

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
        ↓  /task_planner/request (observed by Phase 5 dispatcher only when launched)
planner_nav2_dispatcher_node (optional, default dispatch disabled)
        ↓
Nav2 /navigate_to_pose
```

当前最小闭环约定：

- `mock` 模式周期性发布最小 perception event
- `video_file` 或 `camera` 模式在输入缺失、runner 初始化失败、或 runner 退出后，转为 `unavailable / error / completed` 状态事件
- `ros_image` 模式在图像流未到达或中断时，发布 `waiting_for_ros_image / ros_image_timeout` 状态事件
- `system_supervisor_node` 会在感知无消息超过 `perception_timeout_sec` 后发布 `perception_timeout` 状态，不会静默
- `need_reobserve` 需要连续 `reobserve_enter_frames` 帧 raw 候选才进入，并连续 `reobserve_exit_frames` 帧稳定可观测才退出
- `task_planner_bridge_node` 会消费监督层请求并持续发布占位 `planner_status`
- `visualization_enabled=true` 时，`pose_stream_node` 会额外发布调试图像 topic
- Phase 5 `planner_nav2_dispatcher_node` 是可选节点，默认 `dispatch_enabled=false`，不会让机器人自动运动

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
- Phase 4a TurtleBot4 + RTAB-Map 最小接入 launch/config
- Phase 4b Nav2 precheck launch/config
- Phase 5 planner 到 Nav2 受控派发节点 / launch / config
- 参数化 YAML 配置
- `mock / video_file / camera / ros_image` 四种输入模式骨架
- 无摄像头环境下可跑通的最小闭环

### 7.2 下一阶段

- 保持当前 perception / supervisor / planner request / planner status 语义不回改
- Phase 4a 按最小接入目标冻结，验收结论见 `docs/reviews/phase4a_acceptance_2026-04-16.md`
- Phase 4b 已新增最小 Nav2 precheck 入口，验收口径见 `docs/reviews/phase4b_nav2_precheck_2026-04-17.md`
- 后续若进入完整 `Nav2` 导航闭环或 `PlanSys2 / LTL`，应另起阶段并重新定义验收标准
- 当前 `task_planner_bridge_node` 仍保持 placeholder，不消费 `/map` 或 `/localization_pose`
- 当前 `planner_nav2_dispatcher_node` 只提供 Phase 5 受控派发边界，默认关闭自动派发

## 8. 后续系统挂载边界

### 8.1 `RTAB-Map / 建图定位层`

当前 Phase 4a 已提供最小 `RTAB-Map` 接入入口，但仍只把它作为空间层 sidecar：

- 最小输入：`/oakd/rgb/preview/image_raw`、`/oakd/rgb/preview/depth`、`/oakd/rgb/preview/camera_info`、`/scan`、`/odom`、`/tf`
- 最小输出：`/map`、`/localization_pose`、`/tf`
- 当前关系：不改变 `/perception/events -> /system/supervisor/status -> /task_planner/request` 语义
- 后续职责：向真实 planner 提供地图、定位和可达性信息
- 当前限制：不承诺地图质量，不把 `/map` 或 `/localization_pose` 接入 planner placeholder

### 8.2 `Nav2 / 导航执行层`

当前 Phase 4b 只接入 Nav2 precheck，不接完整任务闭环：

- 当前输入：人工发送的短距离固定 `/navigate_to_pose` goal
- 当前输出：Nav2 lifecycle、costmap、`/plan`、`/cmd_vel` 与 smoke test 结果
- 当前关系：`task_planner_bridge_node` 不调用 Nav2，只作为 planner placeholder
- 当前限制：不启动 `map_server / AMCL`，继续复用 RTAB-Map `/map` 与 `map -> odom`
- 后续职责：执行由真实 planner 产生的空间动作

Phase 5 新增 planner 到 Nav2 的受控派发边界：

- 新增节点：`planner_nav2_dispatcher_node`
- 输入：`/task_planner/request`
- 输出：Nav2 action `/navigate_to_pose`
- 默认：`dispatch_enabled=false`，不派发 goal
- 显式允许：`trigger_safe_mode -> safe_mode_staging`，`need_reobserve -> reobserve_vantage`
- 显式拒绝：`monitor`、`wait_for_update`、默认 `temporal_window_not_ready`、未知动作
- 单 active goal 策略：已有 dispatcher goal 时拒绝新 goal，`hold` 只取消 dispatcher 自己的 active goal
- 与当前链路关系：不改变 perception / supervisor / planner placeholder 语义

### 8.3 `PlanSys2 / LTL / 任务规划层`

当前不接入真实 `PlanSys2` 或 LTL 自动机，只冻结替换边界：

- 替换对象：`task_planner_bridge_node`
- 保留输入：`/task_planner/request`
- 保留输出：`/task_planner/status`
- 允许新增：内部 plan、action dispatch、execution feedback topic
- 不允许要求：上游 `pose_stream_node` 或 `system_supervisor_node` 为真实 planner 回改现有语义

### 8.4 当前明确不做

- 不接完整 `Nav2` 任务闭环
- 不接真实 `PlanSys2 / LTL`
- 不在默认配置下从 `/task_planner/request` 自动派发 action goal
- 不绕过 `planner_nav2_dispatcher_node` 的白名单和 reason 校验自动派发 action goal
- 不让 `/task_planner/request` 直通 `/navigate_to_pose`
- 不新增消息类型体系
- 不做大规模家居仿真环境
- 不做 Kalibr 标定流程
- 不让 planner placeholder 消费 `/map` 或 `/localization_pose`
- 不改 `models/*.pt`
- 不训练
- 不扩外部数据集
- 不让 planner 直接依赖感知研究态字段

## 9. 说明

这个骨架的目标不是一次性把所有模块都接完，而是先把工程边界和启动入口固定下来，避免后续把感知、建图、规划混成一个难以维护的文件堆。当前版本先优先保证 `mock` 默认可运行，再为真实视频和摄像头输入留出兼容入口。
