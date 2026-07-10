# Technology Reuse Demo Runbook

本文件把毕业设计依赖的成熟组件按“先跑官方 demo，再接本项目”的顺序固化下来。目的不是增加新的研究主线，而是验证外部组件边界，避免在项目内重复实现 tracker、SLAM、导航器、动作生命周期或 LTL translator。

## 1. 当前机器前置检查

```bash
source /opt/ros/humble/setup.bash

ros2 pkg prefix nav2_bringup
ros2 pkg prefix rtabmap_demos
ros2 pkg prefix plansys2_bringup
ros2 pkg prefix turtlebot4_simulator
```

2026-07-10 审计时，本机已经安装：

- Nav2 `1.1.20`；
- RTAB-Map ROS `0.23.7`；
- PlanSys2 `2.0.9`；
- TurtleBot4 simulator。

这些包已经存在时，不要把它们的源码复制进本仓库。

## 2. Ultralytics Pose Tracking Demo

项目内已经复用 Ultralytics `model.track()`，无需另写 tracker。移动机器人相机先使用 BoT-SORT（含相机运动补偿），固定摄像头可比较 ByteTrack。

使用当前项目入口和官方 track mode：

```bash
source .venv/bin/activate

python scripts/run_pose_infer.py \
  --config configs/infer_pose_stream.yaml \
  --source data/samples/169808764-29e5678c-6762-4f43-8666-c3e60f94338f.mp4 \
  --mode track \
  --device 0 \
  --save-debug-video \
  --debug-output outputs/vis_debug/track_demo.mp4
```

当前配置中的 `tracker: bytetrack.yaml` 可作为固定相机轻量基线。移动机器人版本应复制配置并改为：

```yaml
mode: track
tracker: botsort.yaml
```

验收字段：

- `seq_track_id` 在连续帧中稳定；
- `seq_debug_mode=per_track`；
- 短时遮挡后 ID 恢复情况可记录；
- 对比 `predict` 与 `track` 下的事件翻转、误触发和延迟。

参考：[Ultralytics Track Mode](https://docs.ultralytics.com/modes/track)

## 3. RTAB-Map TurtleBot4 Official Demo

先确认官方 TurtleBot4 + RTAB-Map + Nav2 能跑，再判断 house world 问题属于外部栈还是本项目配置。

查看本机 Humble demo 参数：

```bash
source /opt/ros/humble/setup.bash
ros2 launch rtabmap_demos turtlebot4_sim_demo.launch.py --show-args
```

运行官方 demo：

```bash
source /opt/ros/humble/setup.bash
ros2 launch rtabmap_demos turtlebot4_sim_demo.launch.py \
  rviz:=true \
  rtabmap_viz:=false \
  nav2:=true \
  use_sim_time:=true
```

验收顺序：

```bash
ros2 topic echo /map --once --field info
ros2 run tf2_ros tf2_echo map odom --ros-args -p use_sim_time:=true
ros2 run tf2_ros tf2_echo odom base_link --ros-args -p use_sim_time:=true
ros2 action list | rg navigate_to_pose
```

本项目只复用其传感器、TF、map 和 Nav2 接法；不复制 RTAB-Map 后端代码。参考：[rtabmap_ros official repository](https://github.com/introlab/rtabmap_ros)

## 4. Nav2 Single-Robot And Multi-Robot Demos

### 4.1 单机器人基线

```bash
source /opt/ros/humble/setup.bash
export TURTLEBOT3_MODEL=waffle
ros2 launch nav2_bringup tb3_simulation_launch.py headless:=False
```

参考：[Nav2 Getting Started](https://docs.nav2.org/getting_started/index.html)

### 4.2 官方双机器人 namespace 基线

Humble 已带多机器人 launch，可先运行它验证 namespace、TF 和 action 命名，再移植到 house world：

```bash
source /opt/ros/humble/setup.bash
ros2 launch nav2_bringup unique_multi_tb3_simulation_launch.py \
  use_rviz:=True \
  autostart:=True
```

查看参数：

```bash
ros2 launch nav2_bringup unique_multi_tb3_simulation_launch.py --show-args
```

验收：

```bash
ros2 node list | sort
ros2 action list | sort | rg navigate_to_pose
ros2 topic list | sort | rg 'robot1|robot2'
```

项目扩展到 R1/R2/R3 时应沿用同一 namespace 模式，不自行发明多机器人导航协议。

### 4.3 路径代价和执行 API

不要继续长期维护人工 travel-time 矩阵。Nav2 Simple Commander 已提供：

- `getPath(start, goal)`；
- `getPathThroughPoses(start, goals)`；
- `getGlobalCostmap()` / `getLocalCostmap()`；
- `goToPose()` / `followWaypoints()`；
- namespace 化构造器。

建议新增独立 adapter，把 `nav_msgs/Path` 的长度和预计时间写回规划问题；MILP 不直接依赖 Nav2 内部实现。参考：[Nav2 Simple Commander API](https://docs.nav2.org/commander_api/index.html)

## 5. PlanSys2 Official Example First

本机安装了 PlanSys2 runtime，但没有安装官方 examples package。按官方教程克隆 Humble 分支到独立验证工作区，确认后只把本项目自己的 PDDL/action adapter 放进 `ros2_ws/src`：

```bash
mkdir -p /tmp/plansys2_demo_ws/src
cd /tmp/plansys2_demo_ws

git clone -b humble \
  https://github.com/IntelligentRoboticsLabs/ros2_planning_system_examples.git \
  src/ros2_planning_system_examples

source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

先运行 fake navigation：

```bash
ros2 launch plansys2_patrol_navigation_example patrol_example_fakesim_launch.py
```

另一个终端：

```bash
source /opt/ros/humble/setup.bash
source /tmp/plansys2_demo_ws/install/setup.bash
ros2 run plansys2_patrol_navigation_example patrolling_controller_node
```

再运行 Nav2 版本：

```bash
ros2 launch plansys2_patrol_navigation_example patrol_example_launch.py
```

本项目应复用该例的：

- mission controller；
- `ActionExecutorClient` 生命周期；
- `move` action 到 Nav2 `navigate_to_pose` 的反馈桥接；
- action 完成/失败回传。

本项目不让 PlanSys2 重新计算多机器人全局分配；MILP 仍输出 assignment/schedule，PlanSys2 只执行已经决定的动作。参考：[PlanSys2 planning controller tutorial](https://plansys2.github.io/tutorials/docs/controller_example.html)

## 6. LTLf/Automaton Optional Demo

只有论文确定保留“可执行 LTLf monitor”时才做本节。先用 Spot 处理冻结公式，不实现自有 parser：

```python
import spot

formula = spot.from_ltlf("fall_confirmed -> F verified")
automaton = formula.translate("small", "buchi", "sbacc")
finite = spot.to_finite(automaton)
print(finite.to_str("hoa"))
```

验收只需覆盖：

- 事件确认最终核验；
- 核验后最终完成物资任务；
- 低电量最终充电；
- 中断巡检最终恢复。

若 Spot 安装或有限自动机执行接入耗时过高，则按实施方案降级为“LTLf 规格 + 前驱图 + 离线 trace 检查”。参考：[Spot finite-semantics tutorial](https://spot.lre.epita.fr/tut12.html)

## 7. 接入顺序与停止条件

固定顺序：

1. 每个官方 demo 单独通过；
2. 本项目 adapter 只接一个能力；
3. 单机器人闭环通过；
4. 事件驱动 planner 通过；
5. 再复制到多机器人 namespace；
6. 最后接真实感知。

任何一步失败时，先回到对应官方 demo。官方 demo 同样失败，修环境/TF/topic；官方 demo 通过而本项目失败，再检查本项目 adapter。不要用修改 MILP 规避 TF、地图或 Nav2 生命周期问题。
