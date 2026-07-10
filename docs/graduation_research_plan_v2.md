# 动态家居环境下语义事件与资源状态驱动的多机器人协同任务规划与局部修复研究

毕业设计研究内容与实施方案（修订冻结版 v2.0）

- 学生：叶豪成
- 研究方向：动态家居环境中的多机器人协同任务规划
- 核心方法：质量门控语义事件 + 动态资源状态 + 序列 MILP + 最小扰动局部修复
- 系统载体：ROS2 Humble、TurtleBot4、Nav2、RTAB-Map、PlanSys2
- 文档状态：唯一人工维护源；DOCX 仅由生成脚本同步产生
- 修订日期：2026-07-10

## 1. 研究定位与边界

本课题面向动态家居环境中的长期巡检、跌倒事件核验、应急物资配送和充电任务，研究语义事件与任务相关资源状态如何驱动多机器人任务分配、时间排程和局部计划修复。

论文核心不是重新设计视觉检测器、SLAM、导航器、任务执行框架或数学求解器，而是建立以下闭环：

```text
人体姿态与时序感知
  -> 稳定语义事件与事件实例
  -> 静态地图/动态代价地图资源状态
  -> 事件驱动多机器人序列 MILP
  -> PlanSys2 动作生命周期
  -> Nav2 导航执行
  -> 执行反馈与最小扰动局部修复
```

研究边界固定如下：

| 模块 | 本文职责 | 明确不做 |
|---|---|---|
| 人体感知 | 复用 YOLO Pose 和内置 tracker，训练/评估 LSTM 时序分类 | 新 YOLO、通用 tracker、ReID 框架 |
| 语义状态 | 概率校准、质量门控、四状态感知、事件 episode 管理 | 大型行为识别网络、POMDP |
| 空间状态 | 静态地图与动态 costmap 到资源状态、时间窗和路径可行性 | 新 SLAM 后端、连续动态场景重建 |
| 形式化规格 | LTLf 有限任务规格与轨迹验收 | 自写 LTL parser、自动机规划器 |
| 协同规划 | 序列路径、资源预约、电量和优先级联合 MILP | 新 MILP 求解器、连续空间 TAMP |
| 执行 | PlanSys2 执行外部 MILP 计划，Nav2 执行导航 | 让 PlanSys2 Planner 替代 MILP |
| 验证 | 3 车仿真、至少 2 车实物关键闭环 | 3 台以上实物作为毕业硬门槛 |

## 2. 研究问题与目标

### 2.1 核心研究问题

1. 当跌倒概率、关键点可见性和跟踪连续性波动时，如何形成不会反复触发任务的稳定事件实例？
2. 当窄通道、充电位和事件服务区发生短时占用或持续阻塞时，如何向任务规划器提供可消费的资源状态、路径代价和时间窗？
3. 如何在机器人能力、任务先后、真实序列路径、共享资源、电量和截止时间约束下完成多机器人分配与排程？
4. 状态变化后，如何只修改受影响计划，减少任务重分配、时间偏移和执行震荡？

### 2.2 总体目标

- 建立质量门控的四状态感知模型和独立事件 episode 生命周期；
- 建立静态地图与动态 costmap 联合的任务资源状态估计；
- 建立以直接后继 arc 为核心的多机器人序列 MILP；
- 实现 Full-Replan 与 LocalRepair，形成可复现实验；
- 使用 LTLf 监视器统计有限任务轨迹满足情况；
- 完成单车执行、3 车仿真和至少 2 车实物协同验证。

## 3. 场景、对象与最小主实验

### 3.1 环境与机器人

环境包含客厅 A、卧室 B、厨房 C、充电区 D、物资点 S、窄通道 `corridor_H` 和事件服务区 `event_zone_B`。

主实验机器人：

| 机器人 | 初始位置 | 初始电量 | 能力 |
|---|---|---:|---|
| R1 | A | 80% | move, camera, patrol |
| R2 | C | 70% | move, camera, patrol, carry |
| R3 | D | 35% | move, charge |

### 3.2 初始任务与动态任务

初始问题只包含常规任务和必要充电任务：

- `patrol:A`；
- `patrol:C`；
- `charge:R3`（由低电量状态决定是否激活）。

事件任务在 `fall_confirmed` 前不存在。事件 `E` 确认后按生命周期创建：

- `verify:E@B`；
- `pickup:E@S`；
- `deliver:E@B`。

其中 `verify:E` 必须先完成；只有确认需要应急响应后，`pickup:E` 和 `deliver:E` 才进入活动任务集。pickup 与 deliver 必须由同一机器人完成，本文不允许隐式物资交接。

### 3.3 冻结动态脚本

- `t=30s`：卧室 B 产生确认跌倒事件；
- `t=45s`：`corridor_H` 短时占用；
- `t=80s`：走廊恢复；
- 扩展扰动：持续阻塞、机器人低电量、导航失败、新事件插入。

## 4. 总体架构与复用原则

### 4.1 必须复用

- Ultralytics Pose 与 ByteTrack/BoT-SORT；
- RTAB-Map 官方 ROS2 包；
- Nav2 `ComputePathToPose/NavigateToPose` 或 Simple Commander；
- PlanSys2 Domain/Problem/Executor 和 action performer；
- Spot 的 LTLf 转换能力；
- PuLP/CBC，Gurobi 只作为可选性能对照。

### 4.2 本文自研部分

- 感知状态到事件 episode 的稳定转换；
- 动态占用到任务资源状态的抽象；
- 多机器人序列 MILP 与资源预约；
- 影响传播、冻结前缀和最小扰动局部修复；
- 感知稳定性对任务误触发和计划扰动的跨层实验。

## 5. 研究内容一：质量门控语义事件与事件实例

### 5.1 感知状态

感知状态定义为：

```text
normal / uncertain / confirmed / degraded
```

输入包括校准后的跌倒概率、关键点可见比例、跟踪连续性、窗口完整度和关键点几何有效性。概率校准仅在 validation logits 上拟合 temperature，不使用 test 数据。

质量分数采用可解释加权模型或 validation 上拟合的逻辑回归。高低阈值、连续窗口、最小保持时间和冷却时间用于降低状态翻转。

### 5.2 事件 episode

事件实例独立于瞬时感知状态：

```text
candidate
  -> observe_pending
  -> verify_pending
  -> verify_active
  -> verified
  -> supply_pending
  -> completed / closed / escalated
```

规则：

- 首次 uncertain 创建或恢复稳定 episode ID；
- confirmed 沿用当前 episode；
- degraded 保留 active episode，不创建新 ID；
- uncertain 回到 normal 时只取消未开始的 observe；
- verify 的执行失败触发重试或修复，不关闭事件；
- `verify_result=no_fall` 才关闭事件；
- completed、明确关闭或超时升级后才结束 episode；
- 任务 ID 使用 `action:event_id`，重复消息只刷新状态。

### 5.3 评价指标

- frame/window/event level Precision、Recall、F1；
- ECE、Brier score、reliability diagram；
- 状态翻转次数；
- 误触发、重复事件和事件触发延迟；
- degraded 识别率和恢复时间；
- tracker 的 ID fragmentation、事件重复率和运行速度。

## 6. 研究内容二：任务相关动态资源状态

### 6.1 双层地图输入

- `/map` 定义静态墙体、区域边界和已知自由空间；
- global costmap 提供较稳定的动态障碍；
- local costmap 提供近场快速变化；
- 所有输入使用 ROS time，并通过 TF 统一到共享 `map` 坐标系。

只在静态可通行区域内统计动态增量；自身 footprint 被剔除，其他机器人 footprint 作为 temporary occupancy 保留。

### 6.2 区域与路径特征

每个资源区域输出：

```text
occupancy_ratio
dynamic_occupancy_ratio
largest_contiguous_width
path_exists
path_length
detour_ratio
observed_at / valid_until
map_revision / costmap_revision
reason_code
```

对每个有效横截面计算最大连续空闲段，取低分位或最小有效瓶颈宽度，不把被障碍分割的多段空闲宽度相加。

路径可行性和绕行比例优先由 Nav2 path adapter 提供。调用失败或返回空路径时输出结构化 route unavailable，而不是继续使用硬编码代价。

### 6.3 资源状态

```text
FREE
TEMPORARY_OCCUPIED
BLOCKED
```

规划结果进一步区分：

```text
WAITING_FOR_RESOURCE
INFEASIBLE_ROUTE_BLOCKED
REROUTED
```

temporary 状态必须带 `earliest_retry_time`；blocked 只有在没有替代路径时才判为 route infeasible。

## 7. LTLf 有限任务规格

LTLf 只用于规格与轨迹验收，不生成机器人分配。冻结性质包括：

1. 每个 confirmed 事件最终完成 verify；
2. 确认需要响应后最终完成 deliver；
3. 每台 low-battery 机器人最终完成 charge；
4. 被中断巡检最终恢复或明确取消。

每个事件或机器人独立实例化监视器，防止一个实例的完成命题满足另一个实例。

在线前缀与终止轨迹输出：

```text
SATISFIED / VIOLATED / INCONCLUSIVE
```

Spot 在独立环境中把公式生成有限自动机和 transition table；ROS2 运行时只读取生成的 JSON，不依赖 Spot。

## 8. 研究内容三：序列 MILP 协同规划

### 8.1 集合与参数

- `I`：机器人集合；
- `J`：服务任务集合；
- `A`：候选直接后继 arc；
- `K_uv`：arc `(u,v)` 的候选路径；
- `R`：共享资源集合；
- `P`：任务前驱关系；
- `c_uvk/t_uvk`：路径距离与时间；
- `Q_uvk`：路径经过的共享资源集合。

每台机器人增加虚拟起点 `0_i` 和虚拟终点 `n_i`。

### 8.2 决策变量

- `x_ij`：机器人 i 是否执行任务 j；
- 直接后继变量 `a_iuvk`：机器人 i 是否选择路径 k，使 v 直接后继 u；
- `s_j/f_j`：服务开始与完成时间；
- `E_ij_before/E_ij_after`：任务前后电量；
- `L_j`：延误；
- `wait_iuvr`：路径资源等待时间；
- `m_j/reassign_j/shift_j/order_change_j`：相对旧计划的变化变量；
- 资源顺序变量：容量为 1 的预约区间互斥。

### 8.3 主要约束

1. 必须任务唯一分配；
2. 任务能力需求必须是机器人能力子集；
3. 每个已分配任务恰有一个直接前驱和直接后继；
4. flow/MTZ 约束消除子回路；
5. arc 旅行时间连接前序完成与后序开始；
6. 任务释放、截止和前驱约束；
7. `pickup:E` 与 `deliver:E` 对每台机器人满足相同分配变量；
8. 电量沿选中 arc 递推，包含移动、服务和充电；
9. 电量始终位于安全下限与满电上限之间；
10. 普通任务完成后保留到最近充电位的返航储备；
11. 资源预约按路径进入/离开区间互斥；
12. committed prefix、已完成任务和不可中断动作保持不变。

Big-M 根据 planning horizon、最大旅行时间和最大服务时间计算，不使用固定 10000。

### 8.4 目标函数

```text
min J =
  alpha * selected_arc_travel
  + beta * priority_weighted_delay
  + gamma * actual_interrupt_cost
  + delta * resource_wait_and_detour
  + eta * energy_risk
  + mu * plan_change
```

资源代价必须依赖实际等待或绕行；中断代价由 interrupted/reassigned/shifted/order-changed 变量组成，不使用 `interrupt_penalty * start_time` 近似。

### 8.5 求解状态

```text
OPTIMAL
FEASIBLE
TIME_LIMIT_FEASIBLE
WAITING_FOR_RESOURCE
INFEASIBLE_ROUTE_BLOCKED
INFEASIBLE
ERROR
```

三车主场景默认 CBC time limit 为 5s、目标 gap 1%；扩展实验为 30s、目标 gap 5%。合法但不可行的问题仍输出结构化结果。

## 9. 局部计划修复

状态变化后执行：

1. 根据 event/resource/robot/action 变化选择种子任务；
2. 沿任务前驱、直接后继、机器人链和资源预约传播影响；
3. 冻结 completed、active non-preemptible 和未受影响计划；
4. 只对受影响子问题求解；
5. 加入变化惩罚；
6. local infeasible 时回退 Full-Replan；
7. 新世界 revision 到达时丢弃过期求解结果。

对比至少覆盖：短时占用、持续阻塞、低电量、导航失败和新事件插入。

## 10. ROS2 与执行系统

### 10.1 正式接口

新增 `kaiti_interfaces`，定义 `SemanticEvent`、`ResourceState`、`Plan`、`TaskAssignment`、`ResourceReservation` 和 `ExecutionFeedback`。

所有计划带：

```text
planner_instance_id
plan_id / revision / world_revision
generated_at / valid_from / expires_at
solver_status / runtime / gap
objective_components
assignments / resource_reservations
```

幂等键为：

```text
(planner_instance_id, plan_id, revision, task_id, attempt)
```

计划使用 reliable + transient local；语义与反馈使用 reliable；costmap 沿用 Nav2 原生 QoS。

### 10.2 事件驱动求解

规划器维护：

```text
world_revision
solve_in_progress
pending_trigger
last_solved_revision
```

状态变化经过短时间 debounce 后只对最新 revision 求解。timer 只发布 health，不周期性刷新执行计划。

### 10.3 PlanSys2 中央执行

部署一个中央 PlanSys2 Domain/Problem/Executor，不调用 PlanSys2 Planner。MILP plan 转换为 `plansys2_msgs/Plan`，action 第一个参数固定为 robot ID。

每台车运行专用 performer，并通过 `specialized_arguments=[robot_id]` 竞价接收动作。PDDL 显式编码机器人可用性和资源 acquire/release，保持 MILP 的串行与资源依赖。

### 10.4 多机器人命名空间

- 共享 `map`；
- `/r1`、`/r2`、`/r3` 分别维护 AMCL、Nav2、costmap 和 lifecycle；
- frame 使用 `r1/base_link`、`r1/odom` 等前缀；
- 中央规划与执行层消费统一世界状态。

## 11. 实验设计

### 11.1 感知实验

- 视频/事件级 train/val/test；
- 同一事件和多视角不得跨 split；
- Rule、LSTM、TCN；
- single threshold、hysteresis、four-state；
- ByteTrack 与 BoT-SORT validation 对比；
- test 只用于最终报告。

F1=0.75 为目标，不是系统完成硬门槛。必须证明四状态方法在误触发、重复事件、状态翻转中至少改善两项。

### 11.2 规划与修复实验

基线：Nearest、Priority-Greedy、Request-Response、Full-Replan、LocalRepair、Proposed Full。

统计任务完成率、响应时间、总路程、资源等待、延误、电量、修改/重分配/偏移任务数、求解时间、gap 和 LTLf 三值结果。

### 11.3 系统实验

- M1：单车人工事件完整链；
- M2：两车人工事件、静态地图与共享资源协同；
- M3：两车真实感知闭环，作为增强项；
- 3 车仿真至少 20 次；
- 2 车实物 M2 至少 10 次。

3 车仿真目标完成率不低于 90%，共享资源冲突和碰撞为 0。两车实物端到端至少 8/10 成功，并分别报告规划、导航、动作、端到端、急停和最小车距。

## 12. 实施阶段与门禁

1. 保护代码、冻结方案、恢复 regression；
2. WorldState、episode 和动态任务工厂；
3. 序列 MILP、电量和资源预约；
4. 动态重规划、LocalRepair 和 LTLf；
5. 严格感知实验；
6. 正式消息与单车 Nav2；
7. 中央 PlanSys2 Executor；
8. 3 车仿真；
9. 2 车实物 M2；
10. 正式实验、论文和演示交付。

每阶段必须通过 `docs/graduation_execution_plan_v2.md` 中对应门禁后才能进入下一阶段。

## 13. 预期创新与成果

### 13.1 创新点

1. 面向规划触发的质量门控事件 episode 生成方法；
2. 面向共享资源预约的动态空间状态抽象；
3. 融合序列路径、资源预约、电量和事件优先级的多机器人 MILP；
4. 基于影响传播与冻结前缀的最小扰动局部修复。

核心创新为第 3 和第 4 项，前两项作为跨层支撑。

### 13.2 交付物

- 同步的研究方案 Markdown/DOCX/manifest；
- 可复现的感知数据 manifest、模型与评估报告；
- MILP、validator、Full-Replan 和 LocalRepair；
- LTLf transition table 与 trace 报告；
- ROS2 正式接口、Nav2 adapter 和 PlanSys2 performers；
- 3 车仿真与 2 车实物实验；
- 自动生成的论文图表、运行手册和一键验收入口。

## 14. 风险与降级策略

- 感知新 test F1 未达目标：如实报告，以跨层误触发改善支撑贡献；
- Spot 环境不适合 ROS：只离线生成 transition table；
- LocalRepair 局部不可行：自动回退 Full-Replan；
- 在线 RTAB-Map 不稳定：正式执行使用静态地图 + AMCL；
- M3 真实感知双车不稳定：保留感知回放 + 两车真实执行，M2 仍为正式目标；
- 第三台实物不可用：不影响 3 车仿真与 2 车实物最低完整目标。
