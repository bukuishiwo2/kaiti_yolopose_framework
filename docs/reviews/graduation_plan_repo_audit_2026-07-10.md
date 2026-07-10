# 毕业设计研究方案与仓库现状审计（2026-07-10）

## 1. 任务目标与审计口径

本报告以仓库根目录的 `毕业设计研究内容与实施方案_叶豪成.docx` 为方案基准，对当前工作树、稳定文档、源码、配置、ROS2 启动文件、benchmark 摘要和本地验收命令进行交叉核验，回答以下问题：

1. 研究方案中的内容已经完成到什么程度；
2. 哪些内容只有代码骨架或历史记录，不能算作已完成；
3. 方案是否需要收缩、纠错或改写；
4. 哪些成熟技术应直接复用，避免重复造轮子；
5. 下一步应按什么顺序推进；
6. 哪些文件可以清理，哪些只能在确认后处理。

状态定义：

- **完成**：有实现、有可复现命令、有结果或验收证据；
- **部分完成**：已有核心实现，但缺少真实输入、闭环、消融或当前验收失败；
- **骨架**：接口或节点存在，但没有证明实现了方案承诺；
- **未完成**：仓库中没有对应实现或结果。

注意：当前分支存在大量未提交改动。本报告按“当前工作树”审计，不把历史 benchmark 自动视为当前仍可复现。

## 2. 总体结论

项目已经超过“感知子系统 + ROS2 占位骨架”的旧定位，实际完成了四块可用原型：

- `YOLO Pose + LSTM/TCN + 规则法` 的训练、推理、评估链；
- 质量分数驱动的四状态语义状态机；
- 任务相关区域的 OccupancyGrid 抽象、静态 MILP、三类启发式基线和局部修复原型；
- 单机器人 house 仿真中的 ROS2、RTAB-Map、Nav2、MILP plan executor 接入尝试。

但当前还不能表述为“动态家居环境下多机器人闭环系统已经完成”。最关键的事实是：

- 当前正式感知指标是在参与训练/微调的 UR Fall 数据集全集上再次评估，适合作为开发集结果，不足以作为独立测试集结论；
- 四状态语义方法只有实现和合成示例，没有方案承诺的校准实验与消融结果；
- 离线“跌倒事件插入”实际上在 `t=0` 就把 `T3/T4` 放进问题，只在 `release=30` 后执行，不是真正的在线任务创建；
- ROS2 `milp_planner_node` 订阅了语义状态，但当前只把它附在输出中，没有用它增删任务或触发局部修复；
- 当前空间层配置读取 `/map`，能获得静态占用但不能代表动态 Nav2 costmap；
- PlanSys2 尚未接入，多机器人 namespace、三车仿真和实物验证尚未完成；
- 2026-06 的动态重规划与局部修复 benchmark 曾通过，但当前工作树上的两个验收命令均因 `corridor_H=blocked` 失败。

因此，建议保留方案主线，但把论文核心进一步收口为：

> 面向动态家居事件的多机器人任务分配、资源排程与最小扰动修复；感知、RTAB-Map、Nav2 和 PlanSys2 均作为可复用输入/执行组件。

## 3. 研究方案完成度矩阵

| 方案模块 | 当前状态 | 已有证据 | 仍缺内容/不能过度表述之处 |
|---|---|---|---|
| YOLO Pose 姿态提取 | 完成 | `PoseRunner`、离线视频、相机和 ROS Image 入口 | 不是论文创新；默认配置仍为 `mode: predict` |
| 多目标跟踪 | 部分完成 | 已直接调用 Ultralytics `model.track()`，支持 ByteTrack | 默认正式配置没有启用 `track`；尚无 ID switch/跟踪连续性评估 |
| LSTM 时序跌倒检测 | 完成（开发集口径） | 默认模型、训练脚本、UR Fall/FallVision 报告；当前摘要 F1=0.7979 | 需要冻结独立测试集；不能把 UR Fall 全集复评当作无泄漏泛化结果 |
| TCN 与规则法对照 | 完成 | Rule/LSTM/TCN benchmark | TCN 保持对照即可，不应继续扩模型族 |
| 概率校准 | 未完成 | 无 temperature scaling、ECE、Brier score 实现或报告 | 方案 4.2/4.3 的“校准后概率”目前不成立 |
| 四状态语义生成 | 部分完成 | `SemanticStateMachine`、ROS2 节点、合成状态样例 | 权重为手工固定；缺状态翻转、误触发、重复任务、退化识别消融 |
| 事件 ID、保持、冷却 | 部分完成 | 状态机已有 event ID、hold、cooldown | 退化时直接清空 event ID；缺真实长视频中的事件生命周期验证 |
| 区域掩膜、占用率、EMA、通行宽度 | 部分完成 | `SpatialStateEstimator`、区域 YAML、OccupancyGrid replay | 当前算法改动导致历史 replay 回归；真实动态障碍精度未评估 |
| 在线地图/代价地图输入 | 骨架/部分完成 | ROS2 节点可订阅 `OccupancyGrid` | 当前配置改为 `/map`，只有静态占用；应分离静态地图和动态 costmap overlay |
| Nav2 路径代价矩阵 | 未完成 | 目前仍主要使用 YAML 人工矩阵；`_path_cost_for_region()` 为硬编码 | 应调用 Nav2 `ComputePathToPose`/Simple Commander `getPath()`，不自写全局路径算法 |
| co-safe LTL/LTLf | 未完成 | DOCX 中有公式，代码只有 `precedence` DAG | 没有解析器、自动机、运行时 monitor 或满足率实现 |
| 静态 MILP | 完成（小规模原型） | PuLP/CBC 求解为 Optimal；validator 通过 | 数学模型和代码仍有若干简化错误，见第 5 节 |
| 三类规划基线 | 完成 | nearest/priority/request-response 均可运行 | 主场景过小，MILP 与两个启发式结果相同，区分度不足 |
| 动态完整重规划 | 部分完成且当前回归 | 历史报告有 `t=30/45/80` 时间线 | 当前验收失败；语义任务预先存在，不是真插入；blocked 没有可行降级策略 |
| 局部计划修复 | 部分完成且当前回归 | 影响传播、冻结前缀、扩展场景对比 | 当前验收失败；缺随机实例统计、求解时间/变量规模和回退成功率 |
| ROS2 `/planning/*` 链 | 部分完成 | 节点、launch、String+JSON schema、当前 colcon build 通过 | planner 没有真正消费语义事件；消息仍未类型化；反馈未触发重规划 |
| MILP -> Nav2 单车执行 | 部分完成 | 当前工作树有 executor、waypoint、July worklog | 仍是未提交实验链；周期性 planner 被执行器冻结；没有正式成功率报告 |
| PlanSys2 动作生命周期 | 未完成 | 仅 placeholder 与接入计划 | 未见 PDDL domain、action performer、PlanSys2 executor 闭环 |
| 三机器人仿真 | 未完成 | 配置中有 R1/R2/R3 逻辑对象 | Gazebo 当前仍是单车承载逻辑机器人任务，不等于三车协同 |
| 4–6 机器人扩展实验 | 未完成 | 无统计报告 | 需要随机实例、重复次数、求解时间、可行率和置信区间 |
| 1–2 台实物关键链路 | 未完成 | 无实物验收 | 可作为增强项，不应阻塞最低毕业目标 |

## 4. 当前可以引用的结构性结果

### 4.1 感知层

仓库报告给出的同口径开发结果为：

| 方法 | Precision | Recall | F1 |
|---|---:|---:|---:|
| 规则法 | 0.7558 | 0.4196 | 0.5396 |
| 默认 LSTM | 0.8657 | 0.7401 | 0.7979 |
| TCN | 0.8990 | 0.5882 | 0.7111 |

可得结论：LSTM 适合作为主线，TCN 适合作为低误报对照，规则法保留 baseline。不可直接得出“在未知家居环境中 F1=0.7979”，因为训练/微调与最终 UR Fall 全集评估并未形成严格独立测试集。

### 4.2 规划层

当前静态命令可复现：

- PuLP/CBC 状态：`Optimal`；
- 目标值：`108.2`；
- 事件响应开始：`38 s`；
- makespan：`78 s`；
- validator 当前静态约束检查通过。

历史报告中局部修复扩展场景给出：Full-Replan 修改 2 个未来任务，LocalRepair 修改 0 个。但该结论当前只能称为“历史可复现实验记录”，因为当前工作树上的动态验收已失败。

### 4.3 系统层

本次审计实测：

- `python -m compileall` 通过；
- `colcon build --symlink-install --packages-select yolopose_ros` 通过；
- `verify_need_reobserve_case.py` 通过；
- `verify_planner_placeholder_mapping.py` 通过；
- `verify_planner_nav2_dispatcher.py` 通过；
- 动态 replay 与 local repair 当前失败，错误均为 `task T4 requires blocked resources: blocked:corridor_H`。

## 5. 方案与实现必须修订的问题

### 5.1 DOCX 中的能力约束写反

DOCX 第 5.8 节已经写对：若 `C_j` 不是 `C_i` 的子集则禁止分配。

但第 8.2 节又写成了：

```text
x_ij = 0, if C_i ⊄ C_j
```

正确形式应统一为：

```text
x_ij = 0, if C_j ⊄ C_i
```

当前代码使用 `set(task.capabilities).issubset(set(robot.capabilities))`，代码方向正确，应修 DOCX 而不是改代码。

### 5.2 LTL、co-safe LTL 与 LTLf 表述混用

方案中的 `G(fall_confirmed -> F verified)` 是持续响应性质。在无限轨迹语义下，它不是普通的 co-safe 性质；在有限任务语义下可以用 LTLf 解释，但必须明确任务何时结束、如何判定 trace 接受。

建议二选一：

1. **最低风险路线**：论文把任务图/DAG 作为实际实现，LTLf 只用于需求规格和离线满足性检查；
2. **完整路线**：复用 Spot 的 LTLf 转换能力生成自动机/monitor，只实现 3–4 条冻结公式，不自写 LTL parser 和 automata 算法。

若时间紧，推荐路线 1，并将创新点从“LTL 规划算法”改成“由有限任务规格提取的前驱约束 + MILP 排程”。

### 5.3 当前动态语义事件没有真正生成任务

`T3/T4` 在 YAML 中从一开始就是 `must_complete: true`，只设置 `release: 30`。因此 `t=30 fall_confirmed` 发生前，静态计划已经知道这两个任务。

需要改为：

- 初始问题只含常规任务和必要充电任务；
- `event_confirmed` 到达时创建带 event ID 的 `verify_fall`；
- `verify_fall` 完成或确认后再释放 `deliver_supply`；
- `event_closed` 取消尚未开始的事件任务并恢复巡检；
- 同一 event ID 必须幂等，不能重复生成任务。

这是下一阶段优先级最高的算法闭环，而不是继续调 Gazebo 外观。

### 5.4 ROS2 planner 当前没有使用语义状态做决策

`milp_planner_node` 目前订阅 `/planning/semantic_state`，但只是把最新 payload 原样写到输出。求解调用仍使用固定 `_problem`，没有任务增删、事件触发、旧计划、执行前缀或局部修复。

必须改成事件驱动状态机：

```text
semantic/spatial/execution event
    -> update planning world state
    -> deduplicate by event_id/version
    -> choose no-op/full-replan/local-repair
    -> publish versioned plan
```

周期性重复求解只能作为 health/status，不应不断生成新的执行计划。

### 5.5 空间状态不应在 `/map` 与动态 costmap 之间二选一

`/map` 适合提供稳定静态结构，Nav2 global/local costmap 适合提供动态障碍与膨胀代价。当前把 spatial input 改成 `/map` 虽然缓解误判，但同时失去了动态障碍证据。

建议双输入：

- 静态地图：校验区域边界、墙体、基础可达性；
- 动态 costmap：只统计去除 unknown、墙体基线和机器人自占用后的新增占用；
- 每个区域保存静态基线，在线只计算 `dynamic_delta`；
- 用时间滞回区分 `temporary_occupied` 与 `blocked`；
- 地图尺寸/原点变化时重新投影 region，不沿用旧 cell index。

当前 replay 回归的直接原因是 `corridor_H` region 收窄后，`t=45` 的障碍覆盖比例超过 `blocked_threshold`。测试场景与区域标定必须分开配置，不能让 house 实图参数破坏冻结 replay。

### 5.6 MILP 模型仍有论文级缺口

当前原型可运行，但至少有以下简化需要修复或在论文中明确：

- 目标函数的 travel cost 只计算机器人初始点到每个任务，不计算实际任务顺序上的边成本；
- 电量也按“初始点到每个任务”累加，未按任务序列递推，未保留返回充电位的能量；
- `energy_after` 是机器人终局电量，却被重复写到该机器人每个 assignment 上；
- `R3=35 + charge_gain 60` 得到 95，超过配置中的 `full_battery=90`；
- `T4` 的 pickup `S` 只在 executor 展开，MILP 时间、路程、资源和电量没有建模 `当前位置 -> S -> B`；
- `C_interrupt` 当前以 `interrupt_penalty * start_time` 近似，不是真正的“是否中断/恢复”变量；
- `C_resource` 中 temporary wait 是常数项，对优化决策几乎不起作用；
- 资源 `capacity` 字段存在，但求解只实现了容量 1 的成对互斥；
- blocked 资源直接抛异常，没有等待、绕路、任务延期或不可行状态的结构化降级；
- Big-M 固定为 10000，尚未根据 planning horizon 收紧；
- 没有 4–6 机器人随机实例上的变量数、约束数、求解时间和 gap 统计。

论文可以继续称其为“小规模连续时间 MILP 原型”，但在修正序列路程、电量和 pickup 之前，不应声称已完整实现方案第 5/8 章全部数学模型。

### 5.7 感知实验需要独立测试协议

当前数据构建做了视频级 train/val split，这是正确方向；但最终 `eval_fall_batch.py` 又在整套 UR Fall 视频上评估，而模型已经在 UR Fall 上训练或 fine-tune。

建议立即冻结：

- train/val/test 三个视频 ID 清单，test 永不参与训练、阈值选择和 hard-negative 选择；
- 主结果报告 test 指标；开发阶段历史指标改名为 `development benchmark`；
- 至少增加一个跨数据集或自采家居 ADL/fall 小测试集；
- 四状态方法报告任务误触发数、重复事件数、状态翻转数和触发延迟，而不只报分类 F1；
- 概率校准若不做，就从方案中删除“校准后概率”表述；若保留，则增加 ECE/Brier/reliability diagram。

## 6. 防止重复造轮子的技术边界

### 6.1 必须复用

| 能力 | 复用方案 | 本项目只做什么 |
|---|---|---|
| 姿态检测与 track ID | Ultralytics Pose + `model.track(..., persist=True)`；移动相机优先 BoT-SORT，静态相机可用 ByteTrack | 关键点特征、跌倒时序分类、质量门控和事件状态 |
| SLAM/定位 | RTAB-Map 官方 ROS2 包及 TurtleBot4/Nav2 demo | 区域资源抽象，不改 SLAM 后端 |
| 路径规划与动态避障 | Nav2 `NavigateToPose`、`ComputePathToPose` 或 Simple Commander | 从路径长度/耗时生成 MILP 代价，消费执行结果 |
| 多机器人 Nav2 客户端 | Nav2 namespace 能力，每车独立 namespace/TF/topic/action | 机器人任务分配和共享资源预约 |
| 动作生命周期 | PlanSys2 action performer、controller、Nav2 move action 示例 | 将 MILP 已决定的任务顺序交给动作执行器，不让 PlanSys2 再做全局分配 |
| LTLf 转自动机（若保留） | Spot `from_ltlf()`、`translate()`、`to_finite()` | 公式模板、谓词映射和满足性统计 |
| MILP 求解 | PuLP/CBC；有许可时可增加 Gurobi 对照 | 建模、局部修复、实验分析，不自写 branch-and-bound |
| 消息传输 | ROS2 action/service/custom msg | 定义领域 schema，不长期依赖自由 JSON 字符串 |

官方可运行参考：

- Ultralytics tracking 支持 Pose 模型以及 BoT-SORT/ByteTrack，不需要自行实现 Kalman/匈牙利匹配：[Ultralytics Track Mode](https://docs.ultralytics.com/modes/track)
- RTAB-Map 官方仓库明确提供 TurtleBot4 与 Nav2 integration demos：[rtabmap_ros](https://github.com/introlab/rtabmap_ros)
- Nav2 Simple Commander 已提供 `getPath()`、`goToPose()`、`getGlobalCostmap()`，构造器也支持 namespace：[Nav2 Simple Commander API](https://docs.nav2.org/commander_api/index.html)
- PlanSys2 官方 patrol 示例已经展示 controller、action performer 与 Nav2 `navigate_to_pose` 的反馈桥接：[PlanSys2 planning controller](https://plansys2.github.io/tutorials/docs/controller_example.html)
- Spot 已提供 LTLf 到有限自动机的转换流程：[Spot finite-semantics tutorial](https://spot.lre.epita.fr/tut12.html)

### 6.2 允许自研并作为论文贡献

- 视觉质量与时序概率到四状态规划谓词的转换；
- 静态地图 + 动态 costmap 到任务相关资源状态/时间窗的转换；
- 多机器人任务、资源、电量、优先级和时序的统一 MILP；
- 事件 ID 驱动的影响传播、冻结前缀和最小扰动局部修复；
- 感知不确定性对任务误触发和计划扰动的跨层实验。

### 6.3 明确不做

- 新 YOLO 架构、全新 tracker、SLAM 后端、局部规划器、行为树引擎；
- 自写 LTL parser/automata translator；
- PlanSys2 的替代实现；
- 新 MILP 求解器；
- 多机器人连续构型联合优化、完整 TAMP、POMDP 或自主探索系统。

## 7. 下一步优先计划

### P0：恢复可复现基线（1–2 天）

1. 将冻结 replay 的 region 配置与 house 实图 region 配置拆成两个文件；
2. 让动态 replay 和 local repair 两个验收命令重新通过；
3. 为 `static/baseline/dynamic/local-repair` 建立一键 smoke test；
4. 不覆盖当前工作，先提交或备份 July 未提交的 house/Nav2 改动。

验收：四个规划命令全部退出码 0，报告中的关键指标由脚本自动生成而非手工抄写。

### P1：修复研究有效性（3–5 天）

1. 冻结 UR Fall 视频级 train/val/test manifest；
2. 重跑默认 LSTM、规则法、TCN 的真正 test 指标；
3. 完成四状态 vs 单阈值 vs 普通迟滞消融；
4. 增加事件级指标：误触发、重复事件、翻转、触发延迟。

验收：形成一份不可变 test 报告，训练脚本无法读取 test split。

### P2：做成真正的事件驱动规划（约 1 周）

1. 初始问题移除 `T3/T4`；
2. `fall_confirmed(event_id, B)` 动态创建任务；
3. planner 保存 incumbent、completed、active、pending 状态；
4. spatial/execution event 选择 full replan 或 local repair；
5. plan 增加 `plan_id/revision/trigger/valid_from`，executor 幂等消费。

验收：没有事件时计划中不存在 T3/T4；同一 event ID 重复发布不会重复建任务；新事件到达后才产生事件任务。

### P3：补齐 MILP 关键数学一致性（约 1 周）

1. 路径/能量按机器人任务序列递推；
2. 将 delivery 拆成 pickup 和 drop 两个有前驱关系的任务或显式 route legs；
3. 充电后电量封顶并加入返航储备；
4. blocked 资源支持等待/绕路/延期/不可行状态；
5. 增加模型规模和 3–6 机器人统计。

验收：论文公式、YAML、solver 与 validator 使用同一语义，validator 能构造反例并拦截错误计划。

### P4：复用官方 Demo 完成系统闭环（约 1–2 周）

1. 先用 Nav2 官方 action/Simple Commander 获取路径和执行结果；
2. 再按 PlanSys2 patrol-navigation 示例实现 `navigate/observe/verify/pickup/drop/charge` action performer；
3. 单车稳定后复制为 namespace 化 R1/R2/R3；
4. 最后接入真实感知事件，不在三车调试期同时调模型。

验收：手动 Nav2 goal、MILP 单车执行、PlanSys2 单车动作、三车 namespace 四级分别有独立 smoke test。

## 8. 文件清理候选（本次未删除）

### 8.1 可安全重建，建议清理

| 路径 | 当前规模/现象 | 建议 |
|---|---:|---|
| `ros2_ws/build/` | 约 268 KB | 可删，colcon 重建 |
| `ros2_ws/install/` | 约 472 KB | 可删，colcon 重建 |
| `ros2_ws/log/` | 约 5.4 MB | 可删，运行日志 |
| 仓库内 11 个 `__pycache__` | 约 0.5 MB（不含 venv） | 可删 |
| `src/kaiti_yolopose_framework.egg-info/` | editable install 生成 | 可删，重新 `pip install -e` 会生成 |
| `outputs/vis/` | 约 1.1 GB | 生成视频；保留论文需要的一份代表样例即可 |
| `outputs/vis_debug/` | 约 126 MB | 调试视频；若已有图/摘要可删 |
| `outputs/pose_events.jsonl` | 约 8.2 MB | 可重跑生成 |

`outputs/vis/predict2`、`predict3`、`predict4` 中三个 321,114,540-byte AVI 的 SHA256 完全相同，至少两份是确定重复副本，可释放约 612 MB；若论文不需要视频，三份都可删。

### 8.2 明确重复或位置不合理

- 根目录 `yolo11n-pose.pt` 与 `ros2_ws/yolo11n-pose.pt` SHA256 完全相同；最多保留一个统一缓存，或允许 Ultralytics 自动下载；
- 根目录 DOCX 与 `../下载/毕业设计研究内容与实施方案_叶豪成.docx` SHA256 完全相同；建议明确唯一主版本，仓库长期保留 Markdown 方案，DOCX 放论文资料目录；
- `rviz_screenshot_2026_07_07-21_58_54.png` 若是验收证据，应移动到 `reports/figures/<topic_date>/` 并配图注，否则删除；
- 根目录 `matplotlibrc` 只有 `backend: Agg`，若只为无头绘图，建议改为脚本环境变量或放入明确配置目录，不要作为无说明根文件；
- `.venv/` 约 6.5 GB，不应提交。若磁盘紧张可重建，但需先确认 CUDA/ROS Python 混用环境可恢复。

### 8.3 必须先确认，不能按“垃圾文件”直接删除

- `data/external/` 约 4.5 GB；包含原始压缩包和解压视频，存在可去重空间，但属于下载数据资产；
- `data/Fall Detection Video Dataset/` 约 738 MB；
- `data/urfall/` 约 94 MB；
- `data/processed/` 约 132 MB；
- `models/` 约 9.5 MB；至少保留默认正式 LSTM checkpoint 和能够复现实验的必要历史模型；
- `maps/`、`planner_waypoints.yaml`、July worklogs 和 house launch/node 是当前未提交研究进展，不是无用文件；
- `outputs/eval_*` 是原始实验证据，只有在确认对应 Markdown 摘要足够且可重跑后才能清理。

特别风险：`scripts/clean_local_artifacts.sh` 会直接删除 `data/processed`、`data/urfall`、FallVision 数据和全部模型权重，与仓库 AGENTS 的 Do-Not-Touch 原则存在冲突。当前不要直接运行；应先改成 `--dry-run` + 二次确认，或拆分为 `clean_cache` 与 `purge_local_assets`。

## 9. 值得继续改进的工程项

- 增加 `tests/`，把当前 verify 脚本中的断言改成 pytest；
- 给每个 benchmark 保存 Git commit、配置 hash、数据 manifest hash、随机种子和运行环境；
- 把 benchmark Markdown 改为脚本从 JSON 自动生成，减少结果与代码漂移；
- 将 ROS2 `String + JSON` 逐步换成自定义 msg/action，至少对 plan 和 execution feedback 类型化；
- 为 region 配置增加 map frame、map hash、版本号和可视化检查图；
- 为 planner 增加 structured infeasible result，不用异常表示动态资源不可行；
- 将 README 的“当前准确定位”更新为包含规划原型和 house 单车执行链，但仍明确不是三车闭环；
- 将 `Makefile` 增加 planning smoke、ROS build、test、benchmark-report 入口；
- 固定 ROS Humble 依赖版本和 PlanSys2/Nav2/RTAB-Map 安装检查脚本；
- 先完成单车的可测闭环，再做 namespace 复制，不要同时调 RTAB-Map、Nav2、PlanSys2、三车和感知。

## 10. 下一步命令

先保存当前未提交工作，再执行只读/可重建验证：

```bash
git status --short
git diff --stat
```

```bash
.venv/bin/python scripts/run_milp_planner.py \
  --config configs/planner_minimal_experiment.yaml \
  --backend pulp
```

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
```

动态验收在拆分 replay/house region 配置后应恢复为：

```bash
.venv/bin/python scripts/replay_dynamic_planning_case.py \
  --config configs/planner_minimal_experiment.yaml \
  --backend pulp \
  --regions configs/planner_regions_replay.yaml \
  --spatial-replay configs/planner_spatial_replay.yaml
```

```bash
.venv/bin/python scripts/eval_local_repair.py \
  --config configs/planner_local_repair_comparison.yaml \
  --backend pulp \
  --regions configs/planner_regions_replay.yaml \
  --spatial-replay configs/planner_spatial_replay.yaml
```

上述 `planner_regions_replay.yaml` 尚未创建，它是 P0 的第一个实施项；不要为了让测试通过而覆盖当前 house 实图标定。
