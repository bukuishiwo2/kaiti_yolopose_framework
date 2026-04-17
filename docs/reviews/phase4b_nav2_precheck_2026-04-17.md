# Phase 4b Nav2 Precheck 2026-04-17

## 1. 验收目标

本阶段只覆盖 `Nav2` 最小 precheck，不实现完整导航闭环。

本阶段目标：

- 复用 Phase 4a 的 TurtleBot4 仿真、OAK-D preview topics、RTAB-Map sidecar 和 perception 主线基线。
- 新增最小 Nav2 precheck launch 与参数文件。
- 检查 Nav2 lifecycle、action server、global/local costmap、`/plan`、`/cmd_vel`。
- 通过 RViz2 手动初始位姿估计和手动 `NavigateToPose` goal 完成 1 个短距离 smoke test。

本阶段不进入：

- 完整导航闭环。
- 真实 `PlanSys2 / LTL`。
- 从 `/task_planner/request` 自动派发导航 goal。
- 新消息类型体系。
- 感知模型训练、模型替换或外部数据集扩展。
- 动态家居、多点任务或摔倒救援任务闭环。

## 2. 三角色状态判断

`architect`：

- Phase 4b 已完成“最小 Nav2 precheck 实现 + 运行态验收”。
- 结论只能表述为“Nav2 precheck 通过”，不能扩大为完整导航闭环或任务系统闭环已完成。
- 建议将 Phase 4b 冻结为 Nav2 接入前置基线。

`system_planner`：

- `phase4b_nav2_precheck.launch.py` 和 `phase4b_nav2_precheck.yaml` 已可启动并完成运行态验证。
- Nav2 lifecycle nodes、`/navigate_to_pose` action server、global/local costmap、`/plan`、`/cmd_vel` 均已可观察。
- RViz2 手动初始位姿估计后，手动发送 goal 可以正常到达。
- `task_planner_bridge_node` 仍保持 placeholder，不调用 `/navigate_to_pose`。

`perception`：

- 本阶段未改模型、未训练、未扩数据集。
- Nav2 precheck 未破坏现有 `/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status` 链路。
- perception 与 supervisor 仍只作为并行系统健康流观察，不接入 Nav2 决策。

## 3. 实现边界

本阶段新增运行入口：

- `ros2_ws/src/yolopose_ros/launch/phase4b_nav2_precheck.launch.py`
- `ros2_ws/src/yolopose_ros/config/phase4b_nav2_precheck.yaml`
- `ros2_ws/src/yolopose_ros/package.xml`

文档与记录：

- `docs/reviews/phase4b_nav2_precheck_2026-04-17.md`
- `docs/worklogs/worklog_2026-04-17.md`
- `docs/system_bringup_skeleton.md`
- `ros2_ws/README.md`

Nav2 precheck 参数边界：

- 使用 `nav2_bringup` 的 `navigation_launch.py`。
- 不启动 `localization_launch.py`。
- 不启动 `map_server / AMCL`。
- 继续使用 RTAB-Map `/map` 与 `map -> odom`。
- `/scan` 作为 local/global costmap 的最小障碍输入。
- `/cmd_vel` 由 Nav2 velocity smoother 输出。
- 第一轮 goal 只允许 RViz2 或 CLI 手动触发。

## 4. 运行态验收样例

启动入口：

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros phase4b_nav2_precheck.launch.py
```

### 4.1 Lifecycle nodes

命令：

```bash
ros2 lifecycle nodes
```

观察到：

- `/behavior_server`
- `/bt_navigator`
- `/controller_server`
- `/global_costmap/global_costmap`
- `/local_costmap/local_costmap`
- `/planner_server`
- `/smoother_server`
- `/velocity_smoother`
- `/waypoint_follower`

结论：

- Nav2 lifecycle 管理节点已出现。

补充状态查询：

```bash
ros2 lifecycle get /controller_server
ros2 lifecycle get /planner_server
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /behavior_server
ros2 lifecycle get /velocity_smoother
ros2 lifecycle get /smoother_server
ros2 lifecycle get /waypoint_follower
ros2 lifecycle get /global_costmap/global_costmap
ros2 lifecycle get /local_costmap/local_costmap
```

已确认 `active [3]`：

- `/controller_server`
- `/planner_server`
- `/bt_navigator`
- `/behavior_server`
- `/velocity_smoother`
- `/smoother_server`
- `/waypoint_follower`
- `/global_costmap/global_costmap`
- `/local_costmap/local_costmap`

说明：

- 所有本轮关注的 Nav2 lifecycle nodes 均已确认 `active [3]`。
- RViz2 中 global costmap display 为 OK；local costmap display 曾出现 Warn，但 lifecycle、topic 数据、`/plan`、`/cmd_vel` 与手动 goal smoke test 均通过。
- local costmap RViz2 Warn 不作为 Phase 4b 阻塞项，可在后续正式导航稳定化时再复查显示配置或瞬时状态原因。

### 4.2 NavigateToPose action

命令：

```bash
ros2 action info /navigate_to_pose
```

观察到：

- Action clients：`/bt_navigator`、`/waypoint_follower`
- Action servers：`/bt_navigator`

结论：

- `/navigate_to_pose` action server 已可用。

### 4.3 Global costmap

命令：

```bash
ros2 topic echo --once /global_costmap/costmap
```

观察样例：

- `frame_id: map`
- `resolution: 0.05`
- `width: 429`
- `height: 365`
- `origin.x: -9.7507`
- `origin.y: -8.2375`
- `data` 非空，包含 unknown / free / occupied cost 数据。

结论：

- global costmap 已发布，且 frame、尺寸和数据均有效。

### 4.4 Local costmap

命令：

```bash
ros2 topic echo --once /local_costmap/costmap
```

观察样例：

- `frame_id: odom`
- `resolution: 0.06`
- `width: 50`
- `height: 50`
- `origin.x: -1.44`
- `origin.y: -1.44`
- `data` 非空，包含局部障碍 cost 值。

结论：

- local costmap 已发布，且能反映局部障碍代价。

### 4.5 Plan

命令：

```bash
ros2 topic echo --once /plan
```

观察样例：

- `frame_id: map`
- 已发布多点 path。
- 样例 path 起点附近为 `(-2.3975, -4.2265)`，后续点逐步向 goal 延伸。

结论：

- global planner 已能生成 `/plan`。

### 4.6 Cmd Vel

命令：

```bash
ros2 topic echo /cmd_vel
```

观察样例：

- `linear.x: 0.2084`
- `angular.z: -0.0474`

结论：

- local controller / velocity smoother 已能输出 `/cmd_vel`。

### 4.7 手动 goal smoke test

操作：

- 在 RViz2 中进行手动初始位姿估计。
- 手动放置一个短距离 `NavigateToPose` goal。

观察结果：

- 机器人可以正常规划并移动到目标点。

结论：

- Phase 4b 的 1 个短距离固定 goal smoke test 已通过。

## 5. 已通过项

- `phase4b_nav2_precheck.launch.py` 可启动。
- Nav2 lifecycle nodes 可观察，且本轮关注的 9 个 lifecycle nodes 均已确认 `active [3]`。
- `/navigate_to_pose` action server 可用。
- `/global_costmap/costmap` 已发布并有有效数据。
- `/local_costmap/costmap` 已发布并有有效数据。
- `/plan` 可生成。
- `/cmd_vel` 可输出。
- RViz2 手动初始位姿估计后，手动 goal 可以正常到达。
- 未接入 `PlanSys2 / LTL`。
- 未从 `/task_planner/request` 自动派发 goal。
- 未改 perception / supervisor / planner placeholder 语义。

## 6. 未完成项与限制

这些不是 Phase 4b 阻塞项，但进入下一阶段前需要单独处理：

- 尚未做长时间运行稳定性测试。
- 尚未量化 RTAB-Map 在线地图与 `map -> odom` 漂移。
- 尚未比较“RTAB-Map 在线 `/map`”与“保存静态 map + `map_server / AMCL`”两种基线。
- 尚未固定一组可复现实验 goal、初始位姿和评价指标。
- RViz2 中 local costmap display 曾出现 Warn；由于 lifecycle、topic 数据和 smoke test 均通过，该项只作为后续正式导航稳定化时的可选复查项。
- 尚未记录 ROS bag 或自动提取导航指标。
- 尚未把 Nav2 feedback / result 接入真实 planner 或任务日志。
- 尚未进入动态家居、多点任务、摔倒救援或语义触发导航。

## 7. 风险

- RTAB-Map 在线地图可用于本次 smoke test，但不等同于长期稳定可导航地图。
- 在线地图持续变化可能导致后续 global plan 或 costmap 行为波动。
- 同时运行 Gazebo、RTAB-Map、YOLOPose 和 Nav2 仍可能有实时性压力。
- TurtleBot4 simulator 自带 Nav2 与本项目 Nav2 不能同时启动，避免 action、costmap、`/cmd_vel` 或 lifecycle 冲突。
- 下一阶段若接 planner，必须新增明确的导航派发边界，不能直接让 placeholder 随意调用 Nav2。

## 8. 验收结论

建议正式冻结 Phase 4b。

冻结口径：

- Phase 4b 完成的是“基于 Phase 4a 空间层的 Nav2 最小 precheck”。
- 当前已经证明 Nav2 lifecycle/action/costmap/plan/cmd_vel 最小链路可工作。
- 当前已确认 `controller_server / planner_server / bt_navigator / behavior_server / velocity_smoother / smoother_server / waypoint_follower / global_costmap / local_costmap` 为 `active [3]`。
- 当前已经证明 RViz2 手动初始位姿估计后，手动短距离 goal 可以到达。
- 当前不等价于完整导航闭环。
- 当前不等价于任务规划闭环。
- 当前不接 `PlanSys2 / LTL`。
- 当前不允许 `/task_planner/request` 自动派发导航 goal。

## 9. 下一步建议

当前阶段不强制继续做 Phase 4c。若后续需要进入正式导航实验或任务层对接，再做 Phase 4c：Nav2 baseline 稳定化。

可选 Phase 4c 建议目标：

1. 固定 2-3 个短距离 `map` frame goal 和初始位姿。
2. 对每个 goal 重复运行，记录到达率、耗时、是否触发恢复、最大偏航或卡滞情况。
3. 对比 RTAB-Map 在线 `/map` 与静态 map baseline。
4. 复查 RViz2 local costmap Warn 是否来自显示配置、瞬时 topic 状态或 costmap layer 状态。
5. 按需增加最小 ROS bag 采集清单：`/tf`、`/odom`、`/map`、costmap、`/plan`、`/cmd_vel`、`/navigate_to_pose/_action/feedback`。
6. 若要接 planner，再设计 planner 到 Nav2 的受控派发接口。

复查命令：

```bash
ros2 lifecycle nodes
ros2 action info /navigate_to_pose
ros2 topic echo --once /global_costmap/costmap
ros2 topic echo --once /local_costmap/costmap
ros2 topic echo --once /plan
ros2 topic echo /cmd_vel
```
