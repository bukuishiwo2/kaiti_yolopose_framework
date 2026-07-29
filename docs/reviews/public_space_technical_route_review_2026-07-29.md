# 医院公共空间动态语义多机器人：技术路线评审

日期：2026-07-29

评审状态：**有条件通过（Conditional Go）**

用户已于 2026-07-29 确认场景与 MVP 边界。P0 参数、接口、安全边界和验收门槛已收口到
[`research_plan_v3_0_1.md`](../research_plan_v3_0_1.md)；后续按 S0、S1 顺序实施，
不覆盖现有家居冻结方案。

二次评审意见的取舍依据见
[GPT 二次评审意见采纳决策](secondary_review_adoption_2026-07-29.md)。

## 1. 建议冻结的新研究场景

### 1.1 场景定义

建议采用：

> **医院门诊大厅—候诊区—连接走廊中的跌倒事件驱动多机器人协同响应**

环境包含：

- 候诊区、走廊、护士站、物资点和充电点；
- 正常行人、短时聚集、遮挡和临时通道占用；
- 一个由视觉触发、可能经历“不确定—确认—感知降级”的跌倒 Episode；
- 2 台机器人作为 MVP，第三台引导机器人作为增强项。

建议的最小角色：

- `R1 patrol-verifier`：携带 Orbbec Gemini 336L 巡检，发现事件后调整视角复核，并在核验服务点持续留场监护；
- `R2 courier`：取急救包并送到事件周界的物资服务点；
- `R3 guide`：引导人员绕行或疏散，仅作为 P1 增强。

### 1.2 事件发现源

MVP 明确采用**移动机器人 R1 自身视觉**，不使用固定监控摄像头：

1. R1 巡检时由 YOLO11 Pose + LSTM 产生候选跌倒事件；
2. 不确定事件触发 R1 原地或小范围调整视角执行 `reobserve`；
3. 确认后，用 Orbbec 对齐深度、CameraInfo 和
   `map→base_link→camera_optical_frame` 在原图时间戳处计算人体地图坐标；
4. R1 前往核心保护区边界外的核验服务点并持续留场；
5. R2 并发执行物资取送任务。

固定摄像头会额外引入外参标定、跨摄像头身份关联、网络时延和独立时间同步，暂列 P2，
不进入 MVP。

### 1.3 为什么不是家居场景的简单换皮

新场景带来四类可量化的新问题：

1. 多人遮挡、远距离和群体背景使跌倒识别更不稳定；
2. 事件位置不再适合只用房间标签，需要局部 3D 定位和区域归属；
3. 跌倒周围的核心区域对所有机器人禁入，核验机器人和物资机器人从不同边界外服务点接近；
4. 走廊临时占用、任务期限和“核验机器人必须留场”共同导致真正的并发 MRTA。

### 1.4 多机器人必要性的验收条件

场景只有满足以下条件，才适合在论文中主张多机器人贡献：

- R1 一旦确认事件，`monitor_event` 必须持续执行到 R2 完成交付；
- `monitor_event` 与 `pickup_and_deliver` 在时间区间和空间位置上不可由同一机器人同时执行；
- 物资送达期限必须在实验前由场景协议固定，并做期限敏感性分析，不能在看到实验结果后反向调整；
- 两机器人可以在安全区角色授权和资源互斥约束下完成任务；
- 动态走廊变化会影响部分任务，但 LocalRepair 的任务改动数小于全局重规划；
- 对照实验明确包含单机器人串行、全量重规划和无 3D 服务点版本。

单机器人对照的预期结果不是依靠人为收紧 deadline 得到，而是由“持续留场”和“异地取送”
这两个同时成立的任务语义产生结构性不可行。若实现中允许 R1 离场取物，则该场景不能再
作为多机器人必要性的证据。

## 2. 四层世界模型评审

### 2.1 推荐形式

| 层 | MVP 表达 | 主要消费者 | 不在 MVP 中做什么 |
|---|---|---|---|
| L1：二维导航层 | 已知 2D 栅格、AMCL、Nav2 global/local costmap、可达路径 | Nav2、路径代价适配器 | 不要求在线重建整张医院地图，不让 RTAB-Map 与 AMCL 竞争 `map→odom` |
| L2：局部三维度量层 | 对齐深度、鲁棒人体中心、位置协方差、原图时刻的 `camera→map` TF | 事件定位、服务点生成、实验评估 | 不要求完整稠密 3D 语义重建 |
| L3：语义区域图 | 人工标注多边形、邻接边、护士站/物资点/充电点/周界服务点 | Episode、MILP、可视化 | 不做自动房间分割和开放词汇图 |
| L4：动态人员/事件层 | person/event/temporary-zone、状态、置信度、TTL、revision | 感知稳定、任务生成、LocalRepair | 不做通用人群行为预测和长期数字孪生 |

该模型与当前仓库兼容：L1 沿用 Nav2，L4 沿用 `WorldState`，主要新增 L2 和通用化
的 L3。

### 2.2 3D 必须怎样进入规划

不能只在 RViz 显示点云。MVP 至少让 3D 定位产生以下规划变量：

1. 事件所在语义区域；
2. 事件周界半径和不确定性膨胀量；
3. `verifier_service_point` 与 `courier_service_point`；
4. 对应 Nav2 路径长度/预计时间；
5. 错区或不确定位置时的 `reobserve` 任务。

建议的 P0 三维落点步骤：

1. 从肩、髋和躯干区域选择可见性较高的稳定关键点；
2. 对每个关键点使用小窗口有效深度中值，拒绝零值、越界值和局部跳变；
3. 使用 CameraInfo 内参把有效关键点反投影到相机坐标系；
4. 按关键点置信度和深度离散程度做加权鲁棒聚合，得到人体中心；
5. 在原始图像时间戳查询 TF，并转换到 `map`；
6. 将人体中心投影到地面平面，得到规划事件点；
7. 由关键点空间离散、深度噪声和 TF 时差估计平面协方差 `Σ_xy`；
8. 有效关键点不足、深度离散过大或 TF 超时时，不发布确认位置，而是生成 `reobserve`。

推荐对比：

| 版本 | 事件位置方法 | 作用 |
|---|---|---|
| Zone centroid | 使用已知语义区域中心 | 最弱但可复现的符号区域 baseline |
| 2D ground projection | 由图像底部点/关键点和地面平面假设求交 | 检验“不用深度”能达到什么水平 |
| Single-depth | 从单个躯干点读取深度并反投影 | 检验单点深度跳变风险 |
| Robust RGB-D | 多关键点窗口中值、鲁棒聚合和协方差 | 建议方法 |

指标包括：区域判断准确率、3D/2D 定位误差、错区任务率、响应路径长度、首次到达时延、
目标安全距离违规次数。若这些指标没有差异，3D 层只能被表述为可视化增强。

## 3. 端到端技术链评审

### 3.1 建议保留、替换与降级

| 模块 | 决策 | 理由 |
|---|---|---|
| YOLO11 Pose | 保留 | 与当前数据/代码直接兼容；可输出可解释骨架 |
| LSTM | 保留为主模型 | 当前默认、已实现 54 维序列链路；需补公共空间评估 |
| Rule / TCN | 保留为基线 | Rule 提供可解释下界，TCN 是现有低误报候选 |
| 轻量 Transformer | P1 新增对比 | 可共享同一序列特征，比较更公平 |
| ST-GCN | P2 | 输入图结构和预处理不同，工作量更大 |
| AMCL + 已知 2D 地图 | P0 定位导航基础 | 提供唯一 `map→odom`，降低多机器人定位与 TF 冲突风险 |
| RTAB-Map | P1 3D 展示/辅助建图 | 不是人员 3D 落点的前置条件，不与 AMCL 同时发布 `map→odom` |
| Orbbec 336L | P0 台架依赖 | 官方支持不代表本机链路已验证 |
| CBC MILP | 保留 | 当前约束、验证器和测试完整，问题规模仍小 |
| CP-SAT | 条件替换候选 | 仅当 3–6 机器人/双事件下 CBC p95 超出预算或频繁无解时比较 |
| LTLf/DFA | 保留为验证器 | 当前没有 DFA 任务合成，不应把它写成规划核心 |
| LocalRepair | 保留并在线化 | 离线算法已存在，是最接近可形成系统贡献的部分 |
| PlanSys2 | P2 可选 | 当前执行器足以闭环；PlanSys2 不是 MVP 必需依赖 |
| Hydra/Khronos/HOV-SG | 不集成 | 仅借鉴分层；版本、构建和研究范围成本过高 |

### 3.2 感知侧必须讲清的问题

#### 为什么使用 LSTM

当前每帧包含 17 个关键点的归一化位置/置信度和 3 个全局几何量，共 54 维；
长度为 32 的序列需要模型识别从直立、失衡到倒地的时间演化。LSTM 与该输入天然匹配，
参数规模可控，并已经进入项目默认闭环。

#### P0 为什么不继续扩张模型

论文应通过同输入对比回答，而不是先验判断：

- Rule：无学习时序 baseline；
- LSTM：当前主模型；
- TCN：现有卷积时序候选；
- P0 只比较 Rule、LSTM、TCN；
- Tiny Transformer 使用同 54 维、同 32 帧、近似参数量，但列入 P1。

ST-GCN 使用人体关节图，输入归纳偏置与 54 维扁平序列不同，应作为扩展实验单列。

#### 公共空间评估切片

测试集至少按以下因素报告：

- 单人 / 多人；
- 无遮挡 / 局部遮挡 / 重遮挡；
- 近、中、远距离；
- 正常坐下、弯腰、躺卧、捡物等 hard negatives；
- 有稳定 track / track 丢失或切换；
- 室内光照与相机视角变化。

除 Accuracy/F1 外，还应报告事件级误报率、漏报率、确认时延、Episode 重复触发数和
轨迹 ID 切换后的恢复时间。

## 4. 事件安全区的可实现方案

### 4.1 不建议的做法

不能只依靠“不给无关机器人分配核心区任务”来保证安全，因为机器人前往其他目标时，
Nav2 仍可能选择穿过该区域。

### 4.2 MVP 方案

采用“共享核心 keepout + 任务层授权 + 边界外角色服务点”：

1. 根据事件地面点和位置协方差生成核心保护区；
2. 核心保护区通过共享 Nav2 keepout mask 对所有机器人强制禁入；
3. 在保护区边界外生成相互分离的 `verifier_service_point` 和
   `courier_service_point`；
4. R1 和 R2 都只到达各自服务点，不进入核心区；
5. MILP 负责服务点角色授权、区域资源、任务顺序和持续留场约束；
6. Nav2 local costmap 继续处理行人等短时障碍。

初始安全半径定义为：

```text
r_safe = r0 + r_robot + k * sqrt(lambda_max(Σ_xy))
```

其中 `r0` 是人员基础保护半径，`r_robot` 是机器人外接半径，`Σ_xy` 是事件平面位置
协方差，`k` 是置信膨胀系数。安全区禁入是硬约束，不能被目标函数中的代价权重抵消。
只有未来确实需要某类机器人进入核心区时，才把每机器人独立 filter mask 列为 P1。

### 4.3 三类动态对象必须分开

| 对象 | P0 处理层 | 是否触发任务重规划 |
|---|---|---|
| 核心安全区 | 共享 Nav2 keepout + MILP 服务点/资源 | 创建、移动、扩张或撤销时触发 |
| 短时动态行人/围观者 | Nav2 local costmap | 否 |
| 持续走廊阻塞 | 语义拓扑边状态 + WorldState revision | 迟滞确认后触发 LocalRepair |

R3 疏导任务仍是 P1。P0 可以用动态行人制造拥堵，但不声称已经完成人群疏散。

### 4.4 持续通道阻塞的触发与恢复

短时避让只留在 Nav2；只有持续异常才升级为任务层世界状态。建议把下列值作为初始工程
配置，随后用仿真日志校准，而不是写死在代码中：

| 参数 | 初始建议 | 语义 |
|---|---:|---|
| `path_probe_hz` | 1 Hz | 对活动计划相关语义边探测路径 |
| `block_confirm_sec` | 5 s | 路径连续不存在，或代价比基线持续超过阈值时确认阻塞 |
| `block_cost_ratio` | 1.8 | `current_cost / baseline_cost` 的初始异常阈值 |
| `release_confirm_sec` | 10 s | 连续可达且代价恢复后解除阻塞 |
| `release_cost_ratio` | 1.3 | 解除阈值，低于阻塞阈值形成迟滞 |
| `state_cooldown_sec` | 10 s | 防止同一边频繁 blocked/free 抖动 |

状态转换：

```text
Nav2 局部绕行
  → 持续 path failure / cost anomaly
  → semantic edge = blocked, world_revision += 1
  → affected-task propagation
  → LocalRepair
  → 若局部问题不可行，再 Full-Replan fallback
```

路径代价缓存至少在以下情况下失效：地图版本变化、语义边状态变化、事件服务点移动超过
阈值、Nav2 执行失败、机器人起点跨区域或世界版本更新。单次局部规划失败不得直接触发
任务级重规划。

## 5. 核心方法与接口契约

### 5.1 论文方法的最小形式化

#### 语义事件

```text
e_k = (id, type, state_k, p_k, Σ_k, region_k, ttl_k, revision_k)
```

其中 `p_k` 和 `Σ_k` 是地图坐标中的事件位置及协方差；`state_k` 来自四态稳定机；
`revision_k` 用于拒绝过期感知或执行反馈。

#### 事件到任务 DAG

```text
G_T(e_k) = (V_T, E_T)
V_T = {reobserve?, verify_and_monitor, pickup, deliver}
E_T = precedence and episode-lifecycle edges
```

`reobserve` 只在位置质量不达标时出现；`verify_and_monitor` 从确认后持续到 `deliver`
完成，形成两机器人不可由单机器人同时执行的并发语义。

#### 动态安全区与角色服务点

安全区使用 4.2 的不确定性膨胀半径。核心区是所有机器人必须满足的 Nav2/MILP 硬约束；
角色服务点位于边界外，并由可达性、与人员朝向的关系、服务点间距和对应角色共同筛选。

#### 版本变化后的受影响任务

```text
A(ΔW) =
  tasks_using_changed_resource
  ∪ tasks_whose_path_uses_changed_edge
  ∪ tasks_bound_to_moved_event_or_service_point
  ∪ descendants_of_these_tasks
```

已完成任务、正在执行的安全承诺和未受影响未来任务构成冻结集；只有
`A(ΔW)` 进入局部求解。如果冻结集导致局部问题不可行，才允许结构化 Full-Replan
回退，并记录原因。

#### LocalRepair 目标

```text
min J =
  α * C_max
  + β * sum(task_lateness)
  + γ * N_change
  + η * travel_and_energy_cost
```

`N_change` 统计机器人重分配、任务顺序变化和显著时间偏移。安全区、能力、前驱、持续
留场和资源互斥均为硬约束，不进入可以被其他收益抵消的软安全惩罚。

以下是评审级字段草案，待路线确认后再实现 `kaiti_interfaces`。

### 5.2 `SemanticEvent3D`

```text
std_msgs/Header header
string event_id
string track_id
string event_type
string perception_state
float32 confidence
float32 observation_quality
geometry_msgs/PoseWithCovariance pose_map
string[] region_candidates
float32[] region_probabilities
float32 ttl_sec
uint64 perception_revision
```

### 5.3 `DynamicZone` 与 `RoleServicePoint`

```text
std_msgs/Header header
string zone_id
string event_id
geometry_msgs/Polygon polygon
bool hard_keepout
float32 safe_radius
float32 valid_until_sec
uint64 world_revision
```

```text
std_msgs/Header header
string service_point_id
string zone_id
string allowed_role
geometry_msgs/PoseStamped target
float32 clearance
uint64 world_revision
```

### 5.4 `TaskPlan` 与 `ExecutionFeedback`

计划至少包含 `plan_revision`、`source_world_revision`、机器人、任务、目标服务点、最早
开始、期限、资源和前驱；反馈至少包含原计划版本、执行状态、失败类别、实际位姿和时间戳。
旧 revision 的反馈不得直接覆盖新 Episode 状态。

## 6. 拟修改位置

以下仅是实施边界，**本轮没有修改这些代码**。

| 位置 | 计划改动 |
|---|---|
| `src/yolopose/pipeline/runner.py` | 接收并保留 source timestamp/frame metadata |
| `ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py` | 从 ROS Image 贯通 `header.stamp` 和 `frame_id` |
| `ros2_ws/src/yolopose_ros/yolopose_ros/event_localizer_3d_node.py` | 新增对齐深度、关键点反投影、TF 与位置协方差 |
| `src/kaiti_planning/models.py` | 扩展事件位置、区域候选、角色授权与服务点字段 |
| `src/kaiti_planning/semantic_map.py` | 新增人工语义多边形、邻接、点在多边形内判断 |
| `src/kaiti_planning/world_state.py` | Episode 接收 3D/区域状态和 TTL |
| `src/kaiti_planning/sequence_milp.py` | 增加角色—区域授权、服务点、期限与路径代价 |
| `src/kaiti_planning/dynamic_repair.py` | 明确位置变化/区域变化/通道变化的影响传播 |
| `ros2_ws/.../semantic_edge_monitor_node.py` | 把持续路径失败/代价异常经迟滞转换为语义边状态 |
| `ros2_ws/.../dynamic_keepout_node.py` | 发布所有机器人共享的核心保护区 mask |
| `milp_planner_node.py` | 把 revision 路径从全量求解改为 LocalRepair 优先、全量回退 |
| 医院 Nav2/AMCL launch 与 YAML | 每机器人命名空间、唯一 TF 发布者、共享静态图和动态 keepout |
| `ros2_ws/src/kaiti_interfaces/` | P1 新增强类型事件、区域、计划与反馈消息 |

## 7. 分阶段实施与门禁

### P0：毕业设计 MVP

工期判断：

- 乐观：9–10 周，仅仿真且 Orbbec/命名空间没有重大阻塞；
- 正常：10–14 周，包含约 2 周缓冲；
- 若要求稳定真实双机器人实验：可能超过 14 周。

| 阶段 | 内容 | 通过门禁 | 预计 |
|---|---|---|---:|
| S0 方法与场景冻结 | R1 传感器归属、2 机器人任务语义、预注册 deadline/阈值/指标 | 一页场景协议、公式和对照组确认 | 0.5 周 |
| S1 现有基线收口 | 单车连续 Nav2、路径代价适配器、house 回归 | 连续任务执行与代价日志稳定 | 1–1.5 周 |
| S2 时间/Orbbec 台架 | source stamp、D2C、CameraInfo、外参和 TF | 深度误差、同步时延和 TF 完整性报告 | 1.5–2 周 |
| S3 3D 事件与安全区 | 四种定位 baseline、协方差、共享 keepout、边界服务点 | 定位、区域、安全距离门禁通过 | 1.5–2 周 |
| S4 语义动态层 | 人工多边形、拓扑、阻塞迟滞、缓存失效、TTL | 动态边状态无高频抖动且可复现 | 1–1.5 周 |
| S5 在线修复与双机器人 | ROS LocalRepair、AMCL/Nav2 命名空间、并发核验/取送 | Episode 闭环、冻结集和 fallback 正确 | 2–3 周 |
| S6 数据与论文证据 | 公共场景 hard negatives、Rule/LSTM/TCN、3D/MRTA 消融 | 指标表、失败案例、日志和视频齐备 | 2–3 周 |

部分数据采集与仿真资产可以并行，但不得把并行假设当成承诺工期。若时间不足，应优先
删减第三机器人、Tiny Transformer、RTAB 稠密点云和 PlanSys2，而不是删掉 P0 的在线
LocalRepair、共享核心 keepout、双机器人闭环和 3D 定位公平消融。

### P1：增强项，额外 3–5 周

- 第三台引导/疏散机器人；
- Tiny Transformer 对比；
- RTAB-Map 点云与局部 3D 地图展示；
- 只有出现角色进入核心区需求时，才做每机器人独立 keepout/filter mask；
- 自定义 ROS 消息全面替换 JSON；
- 3–6 机器人、双事件 CBC/CP-SAT 性能比较。

### P2：论文扩展

- ST-GCN；
- 任务时长/成功率不确定性；
- PlanSys2 正式行为执行；
- 半自动语义区域生成。

### P3：明确不纳入当前毕业设计

- 完整 Hydra-Multi/Khronos/HOV-SG 集成；
- 开放词汇或 VLM 导航；
- 自动多楼层场景图；
- 通用人群轨迹预测；
- 大规模异构机器人联盟和任务接力。

## 8. 实验设计

### 8.1 感知实验

P0 比较 Rule/LSTM/TCN，保持相同帧率、32 帧窗口、54 维输入和训练划分；报告帧级与
事件级指标、确认时延和 hard-negative 误报。Tiny Transformer 只在 P0 按期完成后进入
P1。

### 8.2 3D 与语义实验

比较 Zone centroid、2D ground projection、Single-depth 和 Robust RGB-D 四种方法；
报告 3D/地面定位误差、区域准确率、协方差校准、服务点有效率和错区任务率。

### 8.3 规划实验

比较：

1. 单机器人，在预先固定的“持续留场 + 异地取送”任务语义下验证不可行原因；
2. 两机器人全量重规划；
3. 两机器人 LocalRepair；
4. 去掉共享导航级 keepout，只保留任务层授权；
5. LocalRepair 使用固定区域中心而非 Robust RGB-D 服务点；
6. 不同预注册 deadline 下的敏感性分析。

指标：

- 事件确认/物资送达 makespan；
- deadline violation；
- 任务成功率；
- 安全区违规；
- 求解 p50/p95；
- plan churn（修改任务数、机器人变更数）；
- LocalRepair 回退率；
- Nav2 实际时长与估计时长误差。

### 8.4 CBC 的替换触发条件

先用 2、3、4、6 台机器人和 1/2 个事件进行压力测试。在固定硬件上，若 CBC：

- p95 求解时间超过系统允许的重规划预算；
- 频繁达到 time limit 且 gap 不可接受；
- 或扩展约束难以稳定表达，

再以同一问题实例比较 CP-SAT。未触发这些条件时，保留 CBC 能减少实现风险并保持现有
验证器复用。

## 9. 对原任务 18 个关键问题的直接回答

复现命令编号沿用
[实现差距审计](implementation_gap_audit_2026-07-29.md)中的 `C1–C8`。

| # | 状态 | 直接回答 | 证据与当前限制 | 推荐动作/冻结影响 |
|---:|---|---|---|---|
| 1 | IMPLEMENTED / PARTIAL | EventEpisode、WorldState、MILP 和离线 LocalRepair 都存在；在线 ROS LocalRepair 未完成 | `world_state.py`、`sequence_milp.py`、`dynamic_repair.py`；C1–C4 | 保留主线；P0 接入 ROS，不覆盖旧场景 |
| 2 | IMPLEMENTED（验证） | LTLf/DFA 只做有限轨迹监测，不参与任务生成或 MILP 求解 | `ltlf_monitor.py:LtlfTraceMonitor`；C1/C2 | 修改论文口径为“形式化验证” |
| 3 | IMPLEMENTED / PARTIAL | MILP 同时建模分配、排序、离散路径代价、能力、电量和容量 1 资源 | `sequence_milp.py`、`validator.py`；C2/C3 | 增加 Nav2 代价、角色授权和期限；不重写求解器 |
| 4 | PARTIAL | Nav2 审计能返回可行性、路径点数和长度，但时间只可由速度假设估计，尚无在线稳定校准 | `audit_nav2_waypoints.py`、既有 JSON 报告；C8 | P0 加路径时长适配器和实际/估计误差记录 |
| 5 | PARTIAL / BLOCKED | 现有 RTAB launch 具备 RGB-D/scan/odom/TF 输入骨架，但没有当前运行证据证明定位、点云和 2D map 同时稳定 | `kaiti_house_turtlebot4_rtabmap.launch.py`；C5–C7 | P0 使用已知图 + AMCL；RTAB 移到 P1，禁止两者竞争 `map→odom` |
| 6 | BLOCKED | Orbbec 彩色/深度对齐、CameraInfo 与 TF 当前未验证 | 无项目配置且 `orbbec_camera` 未安装；C6/C7 | 首个硬件 P0 台架任务，不通过则保留 2D fallback |
| 7 | BLOCKED | `map→odom→base_link→camera_optical_frame` 的时间一致性无法在无运行图时确认 | C7 只有系统主题 | 用 `tf2_echo`、stamp 延迟统计和 rosbag 回放验证 |
| 8 | PARTIAL | Pose record 可保留 track_id，但默认 `predict` 通常没有 track；原始 Image stamp 未保留 | `runner.py:_build_record`、`pose_stream_node.py:_on_ros_image`、默认 YAML；C1/C2 | P0 切 `track` 并贯通 source stamp；保留现有模型 |
| 9 | MISSING（可行） | 可以先完成三维骨架，不需要新增分割模型 | 当前无反投影节点 | 肩/髋/躯干小窗口深度中值、异常剔除、鲁棒聚合、协方差和 map TF |
| 10 | PARTIAL | 当前没有动态人—静态点云分离；MVP 可把人体保留在独立 TTL 动态层，并避免写入长期静态语义图 | EventEpisode 已有，点云过滤缺失 | P0 分层不融合；P1 用人体 mask/时序衰减过滤动态点 |
| 11 | MISSING（方案已明确） | 核心安全区对所有机器人禁入；R1/R2 均停在边界外角色服务点 | 当前 `ResourceState` 只覆盖任务资源，没有导航级动态区 | P0 共享 keepout + MILP 授权；仅未来有角色入区需求时才做独立 mask |
| 12 | MISSING（方案已明确） | MVP 应人工配置语义多边形和服务点 | 当前只有家居矩形 region | 半自动提取为 P2，自动分割为 P3；医院资产并行新增 |
| 13 | IMPLEMENTED / MISSING | LSTM 更适合继续做主模型；ST-GCN 当前只值得做 P2 对照 | `model.py` 只有 LSTM/TCN；C1/C2 | P0 只做 Rule/LSTM/TCN；Tiny Transformer P1 |
| 14 | BLOCKED | 当前没有目标规模 CBC p95 数据，不能据此换 CP-SAT | 小规模烟测可运行；C3/C4 | 先压测 3–6 机器人/双事件，触发阈值后再公平比较 |
| 15 | DESIGNED_ONLY | 三机器人必要性未证明；两机器人由“R1 持续留场直到交付完成 + R2 异地取送”的任务语义产生结构性并发 | 当前只有单机器人 house | MVP 冻结 2 台；deadline 实验前固定并做敏感性分析，不事后调参制造需求 |
| 16 | PARTIAL | LocalRepair 已能与 Full-Replan 比较修改任务数，但还缺在线时延、冻结违规、回退率和 Nav2 执行结果 | `run_dynamic_repair_matrix.py`；C4 | P0 接入 ROS 后报告 plan churn、p95、fallback、安全/期限违规 |
| 17 | DESIGNED_ONLY | 3D 必须通过区域准确率、服务点、路径长度、响应时延和安全距离影响规划 | 当前无 3D 定位 | 比较 Zone centroid、2D ground projection、Single-depth、Robust RGB-D |
| 18 | PARTIAL | 乐观 9–10 周，正常 10–14 周；稳定真实双机器人可能超过 14 周 | 当前核心回归通过，但硬件链、多机器人和公共数据缺失 | 保留约 2 周缓冲；优先删 P1/P2，不删在线修复、安全区和双机器人闭环 |

## 10. 最终决策

### 10.1 可以冻结的核心

- 医院门诊大厅/候诊区/走廊跌倒事件响应；
- R1 携带 Orbbec 巡检、发现、复核和留场，R2 取送物资；
- YOLO11 Pose + LSTM + Episode；
- 已知 2D 地图 + AMCL、局部 RGB-D 落点、人工语义图和动态层；
- 不确定性膨胀的共享核心 keepout + 两个边界外角色服务点；
- CBC MILP + Nav2 + LocalRepair；
- LTLf/DFA 作为验证器；
- Rule、TCN、单机器人、Full-Replan 和四级 3D 定位方法作为对照。

### 10.2 暂不能冻结的内容

- 第三台引导机器人是否进入主实验；
- Tiny Transformer 是否纳入最终论文；
- RTAB-Map 稠密 3D/OctoMap 是否进入主链；
- PlanSys2 正式接入；
- 完整自定义消息迁移范围。

这些内容必须在 P0 门禁完成后，根据剩余周期和实测瓶颈决定。

## 11. 下一步命令

当前先复核 V3 冻结内容，不直接启动 S2 之后的模块：

```bash
cd /home/yhc/kaiti_yolopose_framework
sed -n '1,280p' docs/research_plan_v3_0_1.md
```

P0 已冻结。下一步只执行 V3 的 S0，S0 diff 经用户检查后再进入 S1。
