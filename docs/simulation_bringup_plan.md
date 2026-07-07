# Simulation Bringup Plan

## 1. Recommendation

当前阶段优先选择：

- `TurtleBot4 standard`
- `Gazebo / Gazebo Sim`
- `RTAB-Map`
- `Nav2`

不建议现在把主线切到 `Isaac Sim`。

原因不是 `Isaac Sim` 不能做，而是它对你当前课题不是最短路径：

- 你的系统主线已经围绕 `ROS2 + TurtleBot4 + RTAB-Map + Nav2` 留好了边界
- `TurtleBot4` 官方仿真链路直接支持 Gazebo/Gazebo Sim
- 你当前更需要的是任务层、规划层和动态资源扰动验证，而不是更强的渲染质量或合成数据流水线

`Isaac Sim` 更适合后续两类需求：

- 高保真视觉/激光仿真
- 大规模感知数据合成

对当前毕业设计主线而言，它不是第一优先级。

## 2. External Reference Interpretation

参考仓库 `aws-robotics/aws-robomaker-small-house-world` 的价值在于：

- 提供了一个“多房间 + 家具”的家居型世界参考
- 证明 `Gazebo` 表达家居环境是完全可行的

但它不是本项目的直接运行底座，原因是：

- 该仓库是面向 ROS1 / Gazebo Classic 的老世界资源
- 其 README 明确给出的是 `worlds/small_house.world` 与 `gazebo` / `gzserver` 的经典使用方式
- 你的当前系统主线是 `ROS2 Humble + TurtleBot4 + Gazebo Sim`

因此，正确做法不是直接照搬，而是：

1. 参考它的“多房间小住宅”组织方式
2. 重新用当前项目自己的区域定义构建新场景
3. 用 `TurtleBot4` 和 `Gazebo Sim` 的现有链路承载该场景

## 3. Gazebo Vs Isaac Decision

### 3.1 Gazebo First

优先选 `Gazebo` 的理由：

- `TurtleBot4` 官方文档明确提供 simulator metapackage 和 Gazebo/Gazebo Sim bringup
- 官方 launch 参数直接支持：
  - `model`
  - `world`
  - `namespace`
  - `x / y / z / yaw`
  - `slam`
  - `nav2`
- 这正好匹配你后续需要的：
  - 多机器人 namespace
  - 分阶段打开 `RTAB-Map`
  - 分阶段打开 `Nav2`
  - 保留 `PlanSys2` 为生命周期层

### 3.2 Isaac Later

`Isaac Sim` 当前不作为第一实现的理由：

- 官方 ROS2 TurtleBot 教程聚焦的是 `Turtlebot3 / URDF import / Differential Controller`
- 当前并没有一条和 `TurtleBot4 + Create 3 + OAK-D + Nav2` 同样直接的现成路径
- 你若现在切到 `Isaac Sim`，主要工作会变成：
  - 机器人资产适配
  - 控制器配置
  - ROS bridge 重新打通
  - 传感器与导航参数重新校准

这会明显稀释毕业设计主线。

结论：

- 第一实现：`Gazebo`
- 第二阶段增强：如后续需要更高保真跌倒视觉或合成数据，再考虑 `Isaac Sim`

## 4. Robot Selection

### 4.1 Robot Model

建议机器人型号：

- `TurtleBot4 standard`

原因：

- 与当前仓库已有 `phase4a_turtlebot4_rtabmap` 链路一致
- 自带 `Create 3` 底盘语义与 `OAK-D` 感知链路更贴近现有系统文档
- 后续接 `Nav2`、`RTAB-Map` 的路径更直接

### 4.2 Robot Count

建议分两层定义：

1. 论文主实验机器人数量：`3`

用于与当前冻结 MILP 主场景保持一致：

- `R1 @ A`
- `R2 @ C`
- `R3 @ D`

2. 系统 bringup 分阶段数量：

- Stage S1：`1` 台
- Stage S2：`2` 台
- Stage S3：`3` 台

这样做的原因是：

- 你的研究内容三最终需要 `3` 机器人语义
- 但 `Nav2 + RTAB-Map + planning topics + dispatcher` 不适合一上来就三机并行调通

## 5. House Scene Design

本项目新增的家居环境不再沿用 `warehouse`，而是定义为一个小型住宅平面，核心区域与毕业设计规划模型保持一一对应：

- `A`: 巡检起始/常规服务区
- `C`: 第二巡检区
- `B`: 跌倒事件区
- `D`: 充电区
- `S`: 物资点
- `corridor_H`: 关键共享走廊
- `event_zone_B`: 事件局部作业区
- `charger_D`: 充电站区域
- `supply_point_S`: 物资点区域

对应资源意义如下：

- `corridor_H`：动态共享资源，支持 `free / temporary / blocked`
- `event_zone_B`：事件处理互斥区域
- `supply_point_S`：物资操作区域
- `charger_D`：充电操作区域

## 6. Fall Event Animation Strategy

要表达跌倒事件动画，不需要一开始就做高保真人体动力学。

当前建议采用两层结构：

### 6.1 Visual Layer

用 `Gazebo actor` 或人物模型表达：

- 正常步行
- 到达 `B`
- 在 `t=30` 转为跌倒姿态
- 在地面保持静止

这一层主要服务：

- 论文演示
- 语义事件说明
- 仿真环境可解释性

### 6.2 Planning Layer

用脚本化事件驱动规划：

- `t=30`: `fall_confirmed@B`
- `t=45`: `corridor_H temporary`
- `t=80`: `corridor_H free`

这一层主要服务：

- 规划器输入稳定
- 可重复实验
- 与当前离线 benchmark 对齐

这两层分开是正确做法，因为：

- 你的课题不要求新的人体物理仿真
- 规划实验更需要可控、可复现的事件脚本

## 7. Added Repository Assets

本轮已新增以下仿真骨架资产：

- `ros2_ws/src/yolopose_ros/worlds/kaiti_house_world.sdf`
- `ros2_ws/src/yolopose_ros/config/kaiti_house_scene.yaml`
- `ros2_ws/src/yolopose_ros/config/kaiti_house_event_script.yaml`
- `ros2_ws/src/yolopose_ros/launch/kaiti_house_sim.launch.py`
- `ros2_ws/src/yolopose_ros/launch/kaiti_house_turtlebot4_sim.launch.py`
- `ros2_ws/src/yolopose_ros/launch/kaiti_house_turtlebot4_rtabmap.launch.py`
- `ros2_ws/src/yolopose_ros/launch/kaiti_house_nav2_precheck.launch.py`

用途分别为：

- 世界几何与区域标注
- 场景与机器人配置
- 跌倒/动态障碍脚本
- Gazebo world only 最小启动入口
- 自定义 world 下的 TurtleBot4 单机生成入口
- 自定义 world 下的 RTAB-Map 最小接入入口
- 自定义 world 下的 Nav2 最小 precheck 入口

## 8. Recommended Build Sequence

建议按以下顺序推进：

1. 先启动 `kaiti_house_world.sdf`，确认世界和区域定义可视化正确
2. 单机器人 `TurtleBot4 standard` 进场，验证 `/scan`、`/odom`、相机 topic
3. 接 `RTAB-Map`，验证 `/map` 和任务区域对应关系
4. 接 `Nav2`
5. 接 `/planning/semantic_state`、`/planning/spatial_state`、`/planning/plan`
6. 再接 `PlanSys2` 动作生命周期
7. 最后扩展到 `3` 机器人

当前启动链路额外固化两条保护：

- `controller_ready_node` 已替代上游 `spawner`，把 `joint_state_broadcaster` / `diffdrive_controller` 最终进入 `active` 作为成功标准。
- `kaiti_house_turtlebot4_rtabmap.launch.py` 默认使用 `rtabmap_start_delay:=12.0`，避免 RGBD 和 lidar 传感器尚未稳定时产生假性 `Did not receive data since 5 seconds` 告警。
- `kaiti_house_nav2_precheck.launch.py` / `kaiti_house_planning_precheck.launch.py` 现由 `robot_ready_gate_node` 在 `/map`、`/odom`、`joint_states` 和关键 TF 树就绪后再放行 `Nav2`，避免早期 `map`/`base_link` 生命周期告警。

当前阶段新增的统一联调入口：

- `ros2 launch yolopose_ros kaiti_house_planning_precheck.launch.py`

它适合作为进入 `Nav2 + planning stack` 阶段前的单机基线。

## 9. Acceptance Commands

世界文件最小拉起：

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros kaiti_house_sim.launch.py
```

后续与现有链路结合时，优先复用：

```bash
ros2 launch yolopose_ros kaiti_house_turtlebot4_rtabmap.launch.py
ros2 launch yolopose_ros kaiti_house_nav2_precheck.launch.py
ros2 launch yolopose_ros planning_stack.launch.py
```
