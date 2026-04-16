# Phase 4a Acceptance 2026-04-16

## 1. 验收目标

本次验收只覆盖 Phase 4a：

- TurtleBot4 仿真
- OAK-D preview 图像与深度 topic
- RTAB-Map sidecar 建图定位
- 现有 perception -> supervisor -> planner placeholder 语义链路

本次不进入：

- Nav2
- PlanSys2 / LTL
- RTAB-Map 地图质量调参
- 新消息类型
- 模型训练或外部数据扩展

## 2. 三角色状态判断

`architect`：

- Phase 4a 已具备最小可运行链路，可按“系统侧 RTAB-Map sidecar 接入”冻结。
- 冻结条件是运行默认入口时不启动 `/rgbd_odometry`，且 `/odom` 只有 TurtleBot4 底盘侧 `diffdrive_controller` 一个 publisher。
- 当前结论不等价于“地图质量可用于 Nav2”。

`system_planner`：

- TurtleBot4 仿真、OAK-D preview、`/scan`、`/odom`、`/tf`、RTAB-Map、perception 主线已并行工作。
- RTAB-Map 已订阅 `/oakd/rgb/preview/image_raw`、`/oakd/rgb/preview/depth`、`/oakd/rgb/preview/camera_info`、`/scan`、`/odom`。
- `/map`、`/localization_pose`、`/tf` 可观察，TF 链路可查询。

`perception`：

- 不改模型、不训练。
- `pose_stream_node(input_mode=ros_image)` 已订阅 `/oakd/rgb/preview/image_raw`。
- `/perception/events` 持续发布，并被 supervisor 消费。

## 3. 已通过项

- `/rgbd_odometry` 不在 node graph 中。
- `/odom` 只有 `diffdrive_controller` 一个 publisher。
- `/rtabmap` 订阅 OAK-D preview RGB / depth / camera_info、`/scan`、`/odom`。
- `/pose_stream_node` 订阅 `/oakd/rgb/preview/image_raw`。
- `/perception/events`、`/system/supervisor/status`、`/task_planner/request`、`/task_planner/status` 均有正常 publisher / subscriber 边界。
- `/map` 由 `rtabmap` 发布，为非空 occupancy grid。
- `/localization_pose` 由 `rtabmap` 发布。
- `/info` 由 `rtabmap` 发布。
- `map -> odom`、`odom -> base_link`、`base_link -> oakd_rgb_camera_optical_frame`、`base_link -> turtlebot4/rplidar_link/rplidar` TF 可查询。
- perception 当前样例为 `input_mode=ros_image`、`pipeline_state=running`、`perception_available=true`。
- supervisor 当前样例为 `monitoring / wait_for_update / no_person_present`。
- planner placeholder 当前样例为 `waiting / wait_for_update / request_supported=true`。

## 4. 当前验收样例

运行态采样：

- `/map`：`frame=map`，`603x507`，`resolution=0.05`，`occupied_gt50=3172`
- `/localization_pose`：`frame=map`，位置约 `(3.900, -0.315, 0.000)`，`cov_x=0.106`，`cov_y=0.106`，`cov_yaw=1.060`
- `/info`：`ref_id=116`，`wm_state_len=51`
- `/perception/events`：`source=ros:///oakd/rgb/preview/image_raw`

频率采样：

- `/oakd/rgb/preview/image_raw`：约 `16-20 Hz`
- `/oakd/rgb/preview/depth`：约 `27 Hz`
- `/oakd/rgb/preview/camera_info`：约 `23-25 Hz`
- `/scan`：约 `51-53 Hz`
- `/odom`：约 `52-54 Hz`
- `/perception/events`：约 `16 Hz`
- `/system/supervisor/status`：约 `15-16 Hz`
- `/task_planner/status`：约 `17-20 Hz`

## 5. 未通过项

无阻塞项。

说明：

- `/map_updates` 当前没有 publisher，不作为 Phase 4a 阻塞项；Phase 4a 验收以 `/map` 全量 occupancy grid 可观察为准。
- 本阶段不验收 Nav2 代价地图、路径规划或导航动作。

## 6. 仍待验证项

- 长时间运行下 `/map` 与 `/localization_pose` 是否持续稳定。
- 不同 TurtleBot4 simulator 版本或模型配置下 OAK-D topic 名是否保持一致。
- 地图质量是否足以支撑 Nav2，留到后续阶段单独验证。
- 动态家居场景、复杂障碍与导航闭环均不在 Phase 4a 范围内。

## 7. 验收结论

建议正式冻结 Phase 4a。

冻结口径：

- Phase 4a 完成的是“仿真机器人 + 相机 + RTAB-Map 最小接入”。
- RTAB-Map 当前作为空间层 sidecar，不进入 planner placeholder。
- 当前系统语义链路保持不变：`/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status`。
- 后续不得把 Phase 4a 结论表述为 Nav2 可用地图或完整任务闭环。

## 8. 下一步命令

默认启动：

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch yolopose_ros phase4a_turtlebot4_rtabmap.launch.py
```

验收复查：

```bash
ros2 node list | rg 'rgbd_odometry|rtabmap|pose_stream|system_supervisor|task_planner'
ros2 topic info -v /odom
ros2 topic echo --once /map
ros2 topic echo --once /localization_pose
ros2 topic echo --once /perception/events
ros2 topic echo --once /system/supervisor/status
ros2 topic echo --once /task_planner/status
ros2 run tf2_ros tf2_echo odom base_link
```
