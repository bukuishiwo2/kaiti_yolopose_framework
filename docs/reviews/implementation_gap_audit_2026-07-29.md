# 公共空间动态语义多机器人方案：实现差距审计

日期：2026-07-29

审计对象：当前仓库代码、配置、ROS2 工作区、测试与已有实验记录

审计依据：`公共空间动态语义多机器人研究_对话总结与Codex评审任务.md`

## 1. 审计目标与结论

本次审计回答三个问题：

1. 新方案中的能力，哪些已经有可执行实现；
2. 哪些只有局部实现、离在线闭环还有接口差距；
3. 哪些是新场景必须新增、但不应在当前阶段扩大成重型研究工程的内容。

总判断：**现有仓库已经具备“事件稳定化—任务生成—MILP 分配—执行反馈—版本化重规划”的可复用骨架，但尚不具备医院公共空间多机器人实验所需的 3D 人体定位、语义区域图、多机器人命名空间、导航级动态核心安全区，以及在线 LocalRepair 闭环。**

因此，新方案不是推倒重来；合理做法是保留现有感知与规划核心，补齐时间戳、3D 定位、轻量语义地图和多机器人执行接口。完整动态场景图、自动语义建图、Hydra/Khronos 集成不属于毕业设计 MVP。

## 2. 审计快照与验证结果

### 2.1 可复现命令

```bash
cd /home/yhc/kaiti_yolopose_framework

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/run_planning_smoke.py
.venv/bin/python scripts/run_dynamic_repair_matrix.py

source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
colcon test --packages-select yolopose_ros
colcon test-result --verbose
```

### 2.2 实测结果

| 检查 | 结果 | 结构性结论 |
|---|---:|---|
| Python 单元测试 | `37 passed in 5.71s` | 感知后处理、状态机、规划与验证器当前回归通过 |
| 规划烟测 | `passed: true` | 静态 MILP、动态时间线、局部修复和持续阻塞不可行诊断可运行 |
| 动态修复矩阵 | 5 个场景全部执行完成 | 临时占用可局部修复；持续阻塞、低电量、导航失败、新事件可进入结构化回退 |
| ROS2 构建/测试 | 4 tests, 0 failures | `yolopose_ros` 当前骨架可构建 |
| ROS2 运行图 | 仅 `/parameter_events`、`/rosout` | 当前审计环境没有在线相机、RTAB-Map、Nav2 或多机器人节点，不能据此声称实机链路已验证 |

直接执行 `.venv/bin/python -m pytest -q` 会在测试收集前被系统 ROS 的
`launch_testing` pytest 插件阻断，因为虚拟环境缺少 `lark`。这不是项目测试失败，
但属于环境复现风险；当前使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 隔离无关插件。

### 2.3 运行环境依赖快照

| ROS2 包 | 当前环境 |
|---|---|
| `rtabmap_ros` / `rtabmap_launch` | 已安装 |
| `nav2_bringup` / `nav2_simple_commander` | 已安装 |
| `plansys2_bringup` | 已安装 |
| `orbbec_camera` | **未安装** |

`plansys2_bringup` 已安装不等于项目已经集成 PlanSys2；当前仓库仍以占位参数和现有
MILP 执行器为主。

## 3. 能力—证据—差距矩阵

状态定义：

- **IMPLEMENTED**：有代码、有测试或可复现脚本，并与目标语义基本一致；
- **PARTIAL**：核心存在，但缺少在线接入、目标场景数据或关键接口；
- **DESIGNED_ONLY**：文档或参数中提及，没有目标能力的可运行实现；
- **MISSING**：仓库中未发现对应实现；
- **BLOCKED**：需要当前环境不存在的硬件、驱动或运行图才能验证。

复现编号：

- `C1`：`rg -n "class EventEpisode|class WorldState|solve_sequence_milp|repair_after_disturbance|LtlfTraceMonitor" src ros2_ws`
- `C2`：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q`
- `C3`：`.venv/bin/python scripts/run_planning_smoke.py`
- `C4`：`.venv/bin/python scripts/run_dynamic_repair_matrix.py`
- `C5`：ROS2 工作区的 `colcon build/test/test-result` 命令，见 2.1；
- `C6`：`source /opt/ros/humble/setup.bash && ros2 pkg prefix rtabmap_ros nav2_bringup plansys2_bringup`
- `C7`：`source /opt/ros/humble/setup.bash && ros2 node list && ros2 topic list`
- `C8`：启动目标 Nav2 后运行 `python3 scripts/audit_nav2_waypoints.py --help` 所列参数；现有结果见 `reports/mapping/nav2_waypoint_audit_sdf_static_2026-07-17.json`。

“冻结影响：否”表示保留现有实现并增量扩展；“并行新增”表示只能在用户确认后另建场景
资产，不覆盖 house；“表述修正”表示需要收紧论文措辞。

| 能力 | 状态 | 仓库证据（路径/符号） | 复现 | 当前边界/问题 | 推荐动作 | 优先级 | 冻结影响 |
|---|---|---|---|---|---|---|---|
| YOLO Pose 帧级人体关键点 | IMPLEMENTED | `src/yolopose/pipeline/runner.py`，`pose_stream_node.py` | C1/C2 | 默认 `predict`，不能稳定提供跨帧 `track_id` | 医院配置切到 `track` 并验证遮挡后 ID 稳定性 | P0 | 否 |
| 54 维时序特征 | IMPLEMENTED | `src/yolopose/temporal/features.py` | C2 | 与骨架图模型输入不等价 | 保留为 Rule/LSTM/TCN/轻量 Transformer 的公平输入 | 保留 | 否 |
| LSTM 时序识别 | IMPLEMENTED | `sequence_fall_detector.py`、`model.py` | C2 | 序列长 32；公共空间遮挡/小目标未评估 | 保持主模型，做公共空间分层评估 | P0 | 否 |
| TCN 对比模型 | IMPLEMENTED | `model.py`、`configs/infer_pose_stream_tcn.yaml` | C2 | 只是候选，不应先验宣称优于 LSTM | 作为低误报候选 baseline | P1 | 否 |
| Transformer / ST-GCN | MISSING | `model.py` 仅有 LSTM、TCN | C1 | ST-GCN 需要图结构和不同预处理 | Transformer 做同特征增强对比；ST-GCN 延后 | P1/P2 | 否 |
| 四态语义稳定机 | IMPLEMENTED | `semantic_state.py:SemanticStateMachine` | C1/C2 | 质量权重与阈值以手工规则为主 | 增加遮挡、尺度、可见率和校准实验 | P0 | 否 |
| EventEpisode、去重、降级保持 | IMPLEMENTED | `world_state.py:EventEpisode/WorldState` | C1/C2 | 位置仍为符号；状态机与 Episode 是两个层次 | 保留 ID，新增 3D 位置与协方差 | P0 | 否 |
| 事件触发任务生成 | IMPLEMENTED | `world_state.py:EventTaskFactory` | C1/C3 | 固定 observe/verify/pickup/deliver，缺公共空间角色和服务点 | 改为模板化角色任务 | P0 | 否 |
| 序列 MILP | IMPLEMENTED | `sequence_milp.py:solve_sequence_milp` | C1/C3 | YAML 路程矩阵，不是 Nav2 路径；资源容量只支持 1 | 增加授权、服务点、期限、Nav2 路径代价 | P0 | 否 |
| 顺序、能力、能量、充电、回充余量 | IMPLEMENTED | `sequence_milp.py`、`validator.py` | C2/C3 | 能耗是任务序列简化模型 | 保留并校准，不扩成连续动力学 | 保留 | 否 |
| 资源互斥 | PARTIAL | `models.py:ResourceState`、`sequence_milp.py` | C2/C3 | 求解器/验证器显式限制 `capacity == 1` | 安全区用角色授权 + 容量 1 + 不同服务点 | P0 | 否 |
| LocalRepair 离线算法 | IMPLEMENTED | `dynamic_repair.py:repair_after_disturbance` | C4 | ROS 在线规划器没有调用该函数 | 执行反馈/资源变化接入局部修复，保留全局回退 | P0 | 否 |
| ROS 版本化重规划 | PARTIAL | `milp_planner_node.py`、`RevisionPlanningCoordinator.solve_latest` | C5 | 每次 revision 仍全量 `solve_milp` | 改为 LocalRepair 优先，记录冻结集和改动数 | P0 | 否 |
| LTLf/DFA 监测 | IMPLEMENTED | `ltlf_monitor.py:LtlfTraceMonitor`、`ltlf_specifications.json` | C1/C2 | 不合成任务，也未接入 ROS 在线规划器 | 定位为计划/轨迹验证器 | P1 | 表述修正 |
| 空间状态与走廊占用 | PARTIAL | `spatial_state.py`、`spatial_state_node.py` | C2/C3 | 矩形边界、家居 `corridor_H` 绑定 | 泛化为人工多边形、服务点、动态资源层 | P0 | 否 |
| Nav2 异常升级为语义边阻塞 | MISSING | 未发现 path failure/cost anomaly 的迟滞转换节点 | C1/C8 | 单次 Nav2 失败与持续通道阻塞尚未分层 | 加确认/解除阈值、冷却、缓存失效和 world revision | P0 | 否 |
| Nav2 路径可达性审计 | PARTIAL | `scripts/audit_nav2_waypoints.py`、既有 JSON 报告 | C8 | `getPath()` 未进入 MILP；稳定时长未校准 | 建路径长度/预计时长缓存和失效策略 | P0 | 否 |
| Nav2 连续任务执行 | PARTIAL | `milp_plan_executor_node.py`、Phase 5 脚本 | C5 | 实体连续 `NavigateToPose` 仍是既有计划的未完成门槛 | 先单机器人连续执行，再扩命名空间 | P0 | 否 |
| RTAB-Map RGB-D 骨架 | PARTIAL | `kaiti_house_turtlebot4_rtabmap.launch.py` | C5/C6 | 面向仿真 OAK-D；未验证 Orbbec、点云与 2D map 同时稳定 | P0 用已知图 + AMCL；RTAB 仅作 P1 点云/辅助建图，避免 TF 竞争 | P1 | 否 |
| Orbbec Gemini 336L | BLOCKED | 仓库无驱动/同步/D2C 配置；环境无 `orbbec_camera` | C6/C7 | 当前无法验证配准、内参和 TF | 先做硬件台架门禁 | P0 | 否 |
| 相机原始时间戳传递 | MISSING | `runner.py:_build_record`、`pose_stream_node.py:_on_ros_image` | C1/C2 | 使用处理时刻，未贯通 `header.stamp` | 保留 source stamp/frame_id/处理时延 | P0 | 否 |
| RGB-D 人体 3D 定位 | MISSING | 未发现 CameraInfo/反投影节点 | C1 | 当前只有 2D 骨架与符号区域 | 肩/髋/躯干窗口深度、异常剔除、鲁棒聚合、协方差 + TF | P0 | 否 |
| 轻量语义区域图 | MISSING | 当前仅场景专用矩形 region | C1 | 无医院区域、拓扑、授权和服务点 | 人工多边形 + 邻接 + 服务点 | P0 | 并行新增 |
| 完整 3D 动态场景图 | MISSING | 未发现 DSG/Hydra/Khronos 代码 | C1 | Humble 兼容性和集成成本高 | 只借鉴数据结构，不纳入 MVP | P3 | 否 |
| 动态人员/事件层 | PARTIAL | EventEpisode、空间资源状态 | C1/C2 | 无 3D person/event、TTL、位置协方差、群体密度 | 扩展轻量动态实体层 | P0/P1 | 否 |
| 导航级动态核心安全区 | MISSING | 当前只有统一 `ResourceState`，无动态 keepout 发布链 | C1/C3 | 仅任务层授权不能阻止 Nav2 路径穿越核心区 | P0 共享 keepout，R1/R2 均到边界外服务点；独立 mask 按需延后 | P0 | 否 |
| 多机器人命名空间与 TF | MISSING | 家居 launch 为单机器人 | C1/C5 | 不能验证并发、通信和跨机器人派发 | 先 2 台最小闭环，再评估 3 台 | P0 | 并行新增 |
| 医院公共空间仿真世界 | MISSING | 当前仅 `kaiti_house_world.sdf` 等资产 | C1 | 不能证明新场景适配 | 用户确认后新建，绝不覆盖 house | P0 | 并行新增 |
| PlanSys2 项目集成 | DESIGNED_ONLY | `plansys2_placeholder`、集成文档 | C1/C6 | 任务仍由 EventTaskFactory/MILP 生成执行 | MVP 不依赖；有余量再接入 | P2 | 否 |
| 自定义 ROS 消息 | MISSING | 当前主要为 `std_msgs/String` + JSON | C1/C5 | 缺编译期字段约束、stamp 和版本一致性 | 新建 `kaiti_interfaces`，分阶段迁移 | P1 | 否 |

## 4. 关键证据解释

### 4.1 “已经有 LocalRepair”与“在线还没有 LocalRepair”并不矛盾

`repair_after_disturbance()` 已经实现受影响任务识别、已完成/活动/未受影响任务冻结、
局部求解和全局回退，离线矩阵也能复现。但 ROS 节点调用的是
`RevisionPlanningCoordinator.solve_latest()`，该路径对新 revision 直接做全量
`solve_milp()`。因此论文可以把离线 LocalRepair 写成已有算法基础，不能把当前 ROS
闭环写成已经完成的在线局部修复。

### 4.2 当前 LTLf 是监测器，不是规划器

现有实现加载预生成 DFA 转移表，对有限轨迹输出
`SATISFIED / VIOLATED / INCONCLUSIVE`。任务由 Episode 规则和任务 DAG 生成，顺序由
MILP 决定。当前准确表述应为“LTLf/DFA 形式化验证”，而不是“LTLf 任务规划”。

### 4.3 当前 RTAB-Map 不等于“四层世界模型”

已有 launch 能接 RGB、Depth、CameraInfo、Scan、Odom 和 TF，但没有以下证据：

- Orbbec 336L 的 RGB-D 配准和时间同步；
- 人体骨架到 `map` 坐标系的 3D 投影；
- 3D 语义实体与区域图；
- 动态事件层和导航级动态核心安全区；
- 点云/OctoMap 对规划产生可测量影响。

因此 P0 应使用已知 2D 地图 + AMCL/Nav2 提供唯一 `map→odom`；人体三维地图坐标只需要
对齐深度、CameraInfo、相机外参和机器人地图位姿。RTAB-Map 移到 P1 作为点云展示或辅助
建图，不能单独支撑“动态语义场景图”贡献声明，也不得与 AMCL 竞争发布 `map→odom`。

## 5. 对现有冻结方案的影响

本次审计**不修改**以下已有资产和结论：

- 家居场景世界、地图和演示链；
- LSTM 作为当前默认学习模型；
- TCN 作为候选对比；
- 规则法作为 baseline；
- ROS2 默认 `mock` 输入；
- 现有 MILP、动态修复脚本和报告结果。

用户已于 2026-07-29 确认技术路线；P0 已在
[`research_plan_v3_0_1.md`](../research_plan_v3_0_1.md)中冻结。新医院场景仍必须使用
并行目录和配置，旧方案保留为 baseline 和系统回归场景，而不是被新场景覆盖。

## 6. 风险登记

| 风险 | 影响 | 触发信号 | 缓解方式 |
|---|---|---|---|
| Orbbec 配准/驱动不稳定 | 3D 定位主张无法成立 | 无对齐深度、时间戳漂移、TF 断裂 | 先做台架门禁；保留 2D 区域 fallback |
| 多机器人必要性不足 | 论文贡献被认为是单机器人串行任务的复杂化 | 实现允许 R1 离场取物，或 deadline 在实验后调整 | 预先固定“持续留场 + 异地取送”并发语义和期限，再做敏感性分析 |
| 公共空间数据不足 | LSTM 结果只代表家居数据 | 遮挡、远距离、群体场景误报高 | 采集/合成分层测试集，报告跨场景泛化 |
| 3D 只用于可视化 | 世界模型贡献不成立 | MILP/Nav2 不使用 3D 派生变量 | 比较区域中心、2D 地面投影、单点深度、鲁棒 RGB-D，量化路径与安全距离 |
| 安全区只在任务层 | Nav2 仍可能在执行其他任务时穿过人员核心区 | 无 keepout/filter 输出或路径穿越测试失败 | P0 使用所有机器人共享的动态 keepout，服务点全部位于边界外 |
| LocalRepair 只停留在脚本 | 系统闭环贡献不成立 | ROS revision 始终全量重规划 | 在线接入并记录冻结集、修改数、时延和回退原因 |
| 接口继续使用 JSON | 多节点扩展脆弱 | 字段漂移、stamp 丢失、解析失败 | P1 引入自定义消息，先覆盖事件、计划和反馈 |
| 工作量扩张 | 正常 10–14 周仍可能延期 | 同时做第三机器人、Transformer、稠密点云、PlanSys2 | 保留约 2 周缓冲；先删除 P1/P2，不牺牲在线修复与双机器人闭环 |

## 7. 审计后的最小下一步

在用户确认新路线前，只建议执行不改变冻结方案的证据门禁：

```bash
cd /home/yhc/kaiti_yolopose_framework
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
.venv/bin/python scripts/run_dynamic_repair_matrix.py
```

路线确认后，第一个实现批次应依次处理：

1. 原始图像时间戳与 `frame_id` 贯通；
2. Orbbec 336L 台架与 RGB-D 对齐验证；
3. 关键点 3D 投影和 `map` 坐标变换；
4. 已知图 + AMCL/Nav2 的唯一 TF 链；
5. 人工语义多边形、共享核心 keepout 和边界外服务点；
6. 持续阻塞迟滞、路径缓存失效和 ROS 在线 LocalRepair；
7. 两机器人命名空间与事件响应闭环。
