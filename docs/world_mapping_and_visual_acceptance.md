# House World、建图复用与 v2 可视化验收

## 1. 冻结结论

当前 `kaiti_house_world` 的墙体结构不需要整体重做。它已经具备本课题需要的四类空间语义：起始/巡检点、跌倒核验区 B、物资点 S、充电点 D，以及一个可形成共享资源冲突的窄通道。

但 2026-07-10 的 Nav2 现场 `getPath()`/NavigateToPose 检查表明：现有保存地图能生成 `A→B`、`A→S` 路径，不能生成 `A→C` 路径，D 周围也存在较大 unknown 区域。因此 `maps/kaiti_house.yaml` 只能作为当前单车 B/S 门禁的临时地图，不能直接冻结为三车正式地图。W7 结束前必须在不修改墙体的前提下重新覆盖 C/D 区域、保存新地图，并逐点通过 Nav2 path audit。正式实验再冻结新地图的 hash，并使用 AMCL + saved map 保证重复性。

本轮修正了两个会直接影响实验有效性的问题：

- `corridor_H` 现在覆盖内墙在 `x=2.45, y≈2.10` 的真实门洞，不再覆盖无关的大块房间区域；
- `event_zone_B` 同时覆盖机器人核验停靠点 `B=(3.35, 2.55)` 和跌倒人物标记 `(3.45, 3.15)`。

人物、床和货架目前保持为视觉模型，不增加碰撞体。原因是现有静态地图按墙体几何保存；若现在只给 Gazebo 家具增加碰撞而不重新建图，会造成 Gazebo 真值、AMCL 静态地图和 Nav2 costmap 三者不一致。以后若决定把家具作为固定障碍，必须同时重新生成并冻结地图、waypoint、region mask 和基准路径。

## 2. 当前 world 能验证什么

适合正式验证：

- 事件驱动任务插入；
- `verify → pickup → deliver` 的任务顺序；
- MILP 离散任务序列到 Nav2 连续路径执行；
- 门洞临时占用/持续阻塞；
- 单车、三车 namespace 和共享资源预约；
- AMCL 已知地图重复实验。

不把它用于感知精度结论。当前人物只是跌倒位置的场景标记，没有真实人体动画、遮挡变化、相机噪声和足够的视觉域随机化。感知 F1、重复 episode、延迟等指标仍使用冻结视频 test 和真实摄像头；Gazebo 只验证“语义事件到执行”的系统链路。

## 3. 是否引入 m-explore-ros2

结论：**不接入正式任务执行主线，也不把源码复制进本仓库。**

`m-explore-ros2` 的 `explore_lite` 适合在未知地图中做 frontier exploration；其多机器人部分还包含 map merge。毕业设计的研究变量是语义事件、资源状态、MILP 与局部修复，而不是探索策略。若在正式实验时同时在线探索和建图，会让地图变化、定位误差和探索目标成为额外变量，破坏 20 次仿真和 10 次实物实验的可重复性。

可选使用边界：

1. 只在“地图准备”阶段单独验证探索；
2. 输出保存地图后停止 exploration；
3. 正式规划重新启动 AMCL + saved map；
4. 依赖放在独立验证工作区或 pinned `.repos`，记录 commit 和 license；
5. 不把 exploration 成功率写成核心论文贡献。

当前地图确实需要补齐 C/D，因此推荐先用仓库已有 RTAB-Map/遥控方式重建一次；若人工覆盖仍容易漏区，再在独立工作区使用 `explore_lite` 自动扫图。它在这里是一次性地图制作工具，不是任务规划运行依赖。

该项目 README 说明 Humble 及以上需从源码构建，并将多机器人 map merge 的部分依赖描述为非官方/实验分支，因此当前没有必要把它变成核心运行依赖：[robo-friends/m-explore-ros2](https://github.com/robo-friends/m-explore-ros2)。

## 4. 成熟组件复用边界

- 仿真底座继续使用已安装的 TurtleBot4 simulator，不自制机器人动力学和传感器插件：[TurtleBot4 simulator manual](https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html)。
- 定位和路径执行继续使用 Nav2/AMCL，不实现自有 A*、controller 或 recovery：[Navigation2](https://github.com/ros-navigation/navigation2)。
- 路径代价后续通过 Nav2 Simple Commander adapter 获取，不长期维护纯人工距离矩阵。
- 多机器人先复用官方 namespace 模式；PlanSys2 只执行 MILP 外部计划。
- 第三方源码默认不 vendor。优先使用系统包/rosdep；必须源码构建时使用独立工作区或 pinned `.repos`。

通用 depot、maze、warehouse world 可作为后续“场景迁移”对照，但不替换 house 主场景，因为通用场景没有 B/S/D 和共享走廊的课题语义。

地图重建后，在 Nav2 已启动的终端执行：

```bash
python3 scripts/audit_nav2_waypoints.py --start A --goals B,C,D,S --require-all
```

只有全部 `path_exists=true`，并且 B/S/D waypoint 仍位于对应 region 内，地图才允许进入正式实验。

## 5. v2 单车可视化验收

`planner_graduation_v2_single_robot_demo.yaml` 只用于已知地图的单车可视化门禁。正式三车实验仍使用 `planner_graduation_v2.yaml`。

### 5.1 构建和启动

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash

ros2 launch yolopose_ros kaiti_house_official_nav_planning.launch.py \
  turtlebot4_rviz:=true \
  execution_enabled:=true \
  planner_problem_config:=configs/planner_graduation_v2_single_robot_demo.yaml \
  verification_result_on_success:=fall
```

`verification_result_on_success:=fall` 只用于这个可视化门禁：它用 Nav2 到达 B 代替尚未实现的 verify performer。正式栈默认值为空，不能把“到达 B”误写成“确认跌倒”。

### 5.2 记录证据

另开终端：

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
python3 scripts/record_v2_execution_evidence.py \
  --duration-sec 240 \
  --output outputs/visual_acceptance/v2_single_robot_trace.jsonl
```

规划栈启动稳定后，用一个 5 Hz 命令连续发送两个同 track 的高质量窗口：

```bash
ros2 topic pub --times 2 --rate 5 /perception/events std_msgs/msg/String \
  "data: '{\"seq_fall_score\":0.95,\"seq_visible_keypoint_count\":17,\"seq_window_ready\":true,\"seq_feature_valid\":true,\"seq_track_id\":7,\"event_location\":\"B\"}'"
```

### 5.3 画面与机器验收

RViz 保留标准 Nav2 global plan、local plan、robot model、map；Gazebo 用于观察实体运动。期望任务级序列为：

```text
verify:event_001@B
→ pickup:event_001@S
→ deliver:event_001@B
```

B 出现两次是两项不同任务：第一次核验，第二次送达，不是重复派发。同一 `(task_id, step_name, attempt)` 被再次发给 Nav2 才属于本轮要阻止的 bug。

记录完成后执行：

```bash
.venv/bin/python scripts/verify_v2_execution_trace.py \
  outputs/visual_acceptance/v2_single_robot_trace.jsonl \
  --require-task-prefix verify \
  --require-task-prefix pickup \
  --require-task-prefix deliver \
  --require-terminal-completed
```

通过条件：

- `duplicate_keys=[]`；
- plan revision 单调递增；
- trace 同时含 `/plan` 和 `/amcl_pose` 样本；
- RViz 可见当前 Nav2 路径，Gazebo 可见机器人依次到达 B/S/B；
- executor 的新 revision 只在完整队列边界应用，不在单个 goal 完成时重置剩余队列。

## 6. 仍需现场确认的风险

- 本轮自动测试能确认 revision/幂等/区域契约，不能替代 Gazebo GUI 的一次实际运行；
- AMCL 初始位姿若与仿真 spawn 不一致，需要在 RViz 校准，之后固定参数；
- `/plan` 的实际 topic 名可能因 TurtleBot4 namespace 改变，三车阶段 recorder 需参数化；
- 当前 executor 是 W7 的 Nav2-only 门禁，不是 W8 的 PlanSys2 action performer。
