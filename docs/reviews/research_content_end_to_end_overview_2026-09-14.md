# 医院公共空间动态语义事件驱动多机器人研究内容全景说明

日期：2026-09-14  
研究计划依据：[硕士学位论文研究计划 V3.0.1](../research_plan_v3_0_1.md)  
当前实施依据：[Public-space V3 S1 baseline closure](public_space_v3_s1_closure_2026-07-29.md)  
文档用途：组会汇报、开题/中期材料修订、论文总体技术路线说明和后续阶段实施对照。

## 1. 一句话说明本研究

本研究面向医院门诊大厅、候诊区和连接走廊中的人员跌倒事件，研究如何将不稳定的视觉
检测结果转化为带位置、不确定性和版本号的稳定语义事件，再由事件生成安全区、角色服务
点和协同任务，使巡检机器人持续留场监护、配送机器人异地取送物资，并在通道阻塞、位置
变化、导航失败等扰动出现后，只修复受影响的任务；局部修复不可行时，系统安全回退到
Full-Replan 或 `HOLD_SAFE`。

虽然完整系统包含感知、三维定位、安全区、服务点、导航和安全停止等多个工程模块，但论文
研究内容始终归纳为以下三个部分。医院只是新的实验与展示场景，没有改变原课题的主要
内核：

1. **研究内容一：视觉检测。** 从连续图像中提取人体姿态，识别跌倒并输出带质量信息的
   视觉判断；
2. **研究内容二：视觉语义事件稳定与机器人任务层形成。** 将波动的检测结果稳定为事件
   Episode，再补充位置、区域、安全区、服务点和动态资源语义，形成机器人规划可以直接
   使用的任务、状态和约束；
3. **研究内容三：单/多机器人协同分配、排程与局部计划修复。** 在单机器人和多机器人
   条件下完成任务分配与时序排程，并针对动态变化进行LocalRepair、Full-Replan和安全
   回退，通过医院公共空间实验场景验证方法。

研究的重点不是重新发明 YOLO、LSTM、MILP 或 Nav2，而是解决以下跨层问题：

```text
视觉结果是否可信
  -> 是否应该形成一个任务级事件
  -> 事件在地图中的位置和不确定性是什么
  -> 机器人应该停在哪里才安全且可达
  -> 哪台机器人做什么、何时做、走哪条路径
  -> 环境变化后哪些任务必须改、哪些任务应保持不动
  -> 新计划失效或不可行时如何确保机器人真正停止
```

## 2. 研究背景与场景演化

### 2.1 前期研究从哪里开始

项目最初以动态家居环境为场景，已经建立了以下可迁移能力：

- YOLO Pose 人体关键点检测；
- 基于姿态几何关系的跌倒规则基线；
- LSTM/TCN 短时序跌倒识别；
- 质量门控四状态和 EventEpisode；
- 事件触发的任务生成；
- 序列 MILP、资源互斥、电量和 deadline 约束；
- 离线 Full-Replan 与 LocalRepair；
- ROS2 感知—监督—规划桥接骨架；
- 单机器人 known-map、AMCL、Nav2 和路径审计。

家居世界仍保留为 V2 回归基线，不能被医院场景覆盖。它的作用是证明已有算法和接口没有
在场景迁移中退化，而不是作为 V3 最终论文场景。

### 2.2 为什么改为医院公共空间

家居场景中的动态任务较少、空间尺度较小，多机器人协同和任务级动态修复不容易清晰
展示。医院公共空间更自然地包含：

- 候诊区人员跌倒、坐下、弯腰等易混淆动作；
- 巡检、核验、持续监护、物资取送等有先后与并发关系的任务；
- 人群造成的短时局部避障和持续走廊阻塞；
- 跌倒人员周围必须对所有机器人生效的安全区；
- 服务点、物资点、等待点和窄走廊等任务级资源；
- 任务期限、安全硬约束和失败降级。

因此，场景切换不是更换故事包装，而是让“感知如何影响任务、动态空间如何触发修复、
双机器人为何必要”能够被实验明确验证。

### 2.3 与普通扫地机器人的区别

| 维度 | 普通扫地/清洁机器人 | 本研究系统 |
|---|---|---|
| 任务触发 | 定时或覆盖区域 | 非预期视觉语义事件 |
| 任务结构 | 覆盖、避障、回充 | 核验、持续监护、取物、配送、恢复巡检 |
| 动态处理 | 多数由局部避障解决 | 持续变化会修改任务、资源、期限和分配 |
| 多机器人关系 | 区域拆分或独立工作 | 异构角色、前驱关系、并发占位和共享资源 |
| 安全语义 | 避免碰撞 | 人体核心区、版本 ACK、持续留场和安全停止 |
| 规划目标 | 路程、覆盖率、电量 | 响应时间、任务成功、安全和计划稳定性 |

## 3. 冻结研究场景与任务语义

### 3.1 最小场景

P0 场景冻结为：

> 医院门诊大厅—候诊区—连接走廊中，由巡检机器人视觉发现人员跌倒后触发的双机器人
> 协同核验、持续监护和急救物资取送。

最小环境包含候诊区、门诊大厅、连接走廊、护士站、物资点、安全等待点以及两个机器人
起点。P0 使用已知二维栅格地图、AMCL 和 Nav2，不把完整三维动态语义 SLAM 作为主链。

### 3.2 两台机器人的角色

| 机器人 | 角色 | 主要输入 | 核心能力 | 事件确认后的职责 |
|---|---|---|---|---|
| R1 | `patrol_verifier` | RGB、aligned depth、CameraInfo、TF | camera、move、patrol、verify | 发现事件，到核验服务点，并持续留场至交付完成或事件关闭 |
| R2 | `courier` | 计划、Nav2状态、物资点和服务点 | move、carry | 前往物资点 pickup，再到事件边界外交付点 deliver |

事件只由 R1 的移动视觉产生。固定摄像头、跨摄像头 ReID、第三台人群引导机器人不属于
P0。

### 3.3 任务 DAG

```text
event_confirmed
  ├─> verify_and_monitor:E ───────────────┐
  └─> pickup:E -> deliver:E -> monitor_end:E
                                         └─ monitor 必须持续到 deliver 完成
```

`verify_and_monitor` 与 `pickup` 在安全区和两个服务点有效后并发释放。持续监护是硬约束，
不是目标函数中的软惩罚：

```text
robot(verify_and_monitor:E) = R1
robot(pickup:E) = robot(deliver:E) = R2
start_monitor <= start_pickup
end_monitor >= finish_deliver
R1 在 monitor 区间内保持在 verifier service point
```

这也是双机器人必要性的来源。公平的单机器人基线会让一台机器人同时拥有 camera、verify、
carry、move、patrol 能力，但它仍不能在持续留场期间前往异地取物。这样证明的是并发任务
语义造成的结构性不可行，而不是通过硬编码 R1/R2 能力人为制造不可行。

## 4. 总体系统数据流

```text
R1 RGB图像、对齐深度、CameraInfo、原始时间戳
  -> YOLO11 Pose + tracker
  -> 32帧LSTM、规则法/TCN对照、观测质量
  -> normal / uncertain / confirmed / degraded
  -> EventEpisode与去重
  -> map坐标中的Robust RGB-D落点与协方差
  -> 动态核心安全区DynamicZone
  -> verifier/courier角色服务点
  -> 事件任务DAG
  -> 序列MILP任务分配与排序
  -> Nav2路径查询与执行
  -> 执行、路径、边状态和机器人状态反馈
  -> world_revision
  -> LocalRepair
  -> 必要时Full-Replan
  -> 仍不可行则HOLD_SAFE并验证物理停止
```

系统不是把全部信息堆在一张三维地图里，而是使用四层轻量世界模型：

| 层 | 内容 | 下游用途 |
|---|---|---|
| L1 二维导航层 | map、AMCL、Nav2 costmap、路径长度和时间 | 可达性、导航、路径代价 |
| L2 局部三维层 | 人体中心、地面点、位置协方差 | 区域、安全区和服务点 |
| L3 语义图层 | 人工多边形、拓扑边、护士站、物资点、等待点 | 任务位置和共享资源 |
| L4 动态层 | event、zone、service point、edge、robot、TTL、revision | DAG、MILP、LocalRepair |

## 5. 三项研究内容的输入、输出、目标和当前状态

### 5.1 研究内容一：人体姿态与时序跌倒检测

#### 目标

从连续 RGB 图像中检测人体姿态和跌倒过程，为研究内容二提供跌倒分数、人体姿态和观测
质量。研究内容一只回答“视觉上是否像跌倒、证据质量如何”，不直接创建机器人任务。

#### 输入

- RGB 图像或视频帧；
- 原始 `Image.header.stamp` 和 `frame_id`；
- YOLO Pose 人体框、17 个关键点及置信度；
- 连续 32 帧姿态序列。

当前时序特征以关键点坐标、置信度、人体框比例/面积和有效标记组成固定维度特征。P0
目标输入频率为 10 Hz。

#### 方法

1. YOLO11n-Pose 提取人体框和骨架关键点；
2. 规则分支根据人体框宽高比、躯干方向和髋—踝垂直关系给出单帧判断；
3. LSTM 使用 32 帧姿态变化识别跌倒过程；
4. TCN 保留为低误报对照；
5. raw输出可经基础连续帧稳定器形成检测侧stable结果，用于对照和调试；任务级事件是否
   成立仍由研究内容二的四状态和EventEpisode决定。

选择 LSTM 而不直接使用 Transformer 的原因不是 Transformer 不可用，而是当前问题具有
32 帧短序列、数据规模有限、需要在线因果推理等特点。现阶段主要误差来自遮挡、关键点
质量和数据域偏移，扩大模型容量不会自动解决这些问题。轻量 Transformer 只作为后续同
特征、同划分对照，不进入 P0 主链。

#### 输出

当前逐帧记录至少包含：

```text
person_count
raw_fall_detected / stable_fall_detected
seq_fall_score
seq_raw_fall_detected / seq_stable_fall_detected
seq_window_ready
seq_visible_keypoint_count
source_ros_stamp_ns / source_frame_id
processing_started_at / processing_finished_at
monotonic_elapsed_sec
reason_code
```

ROS2当前输出为`/perception/events`和可选`/perception/debug_image`。在三项研究内容的
边界上，研究内容一向研究内容二交付的是分数、姿态、质量和时间信息；最终V3不会让规划器
直接消费这些模型调试字段，而是由研究内容二将其转换为稳定任务事件。

#### 具体问题与解决办法

| 问题 | 解决办法 |
|---|---|
| 单帧难区分跌倒、弯腰、坐下和躺靠 | 使用32帧LSTM识别姿态变化过程，规则法仅作baseline/debug |
| 日常活动误报 | 加入5% FallVision no-fall困难负样本，再回到UR Fall微调 |
| 模型瞬时抖动 | raw状态后增加连续帧稳定器，上层只消费stable语义 |
| 遮挡或关键点不足 | 输出可见率、窗口完整度和几何有效性，交给质量门控状态机 |
| 训练域与公共空间存在差异 | 后续建立远距离、遮挡、慢跌倒和公共空间hard-negative独立测试集 |

#### 已完成内容与结果

- 规则法、LSTM、TCN均已实现训练、推理、评估和可视化；
- 当前默认模型为
  `models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`；
- 当前默认时序参数为 `score_threshold=0.6`、`min_true_frames=3`、
  `min_false_frames=5`；
- 70段UR Fall仓库内同口径稳定逐帧结果如下。

| 方法 | Precision | Recall | F1 | 定位 |
|---|---:|---:|---:|---|
| 规则法 | 0.7558 | 0.4196 | 0.5396 | 可解释基线 |
| 原始LSTM | 0.8059 | 0.7557 | 0.7800 | 学习型基线 |
| 5% hard-negative + 微调LSTM | **0.8657** | 0.7401 | **0.7979** | 当前主模型 |
| TCN | 0.8990 | 0.5882 | 0.7111 | 低误报候选 |

5% hard-negative 两阶段训练将 ADL 误报帧由 273 降至 162，下降 40.7%。这些是当前开发
口径结果，不应表述为未知医院公共空间上的最终泛化性能。

#### 尚未完成

- 冻结的公共空间独立 test split；
- 远距离、小目标、遮挡、慢跌倒分层实验；
- tracker连续性和四状态消融；
- 轻量Transformer公平对照；
- 最终event-level F1和概率校准报告。

### 5.2 研究内容二：视觉语义事件稳定与机器人任务层形成

这一部分承接研究内容一的视觉结果，目标是回答“什么视觉结果应该成为机器人任务，以及
机器人要在什么位置、遵守什么安全和资源约束来处理该任务”。四状态、EventEpisode、
RGB-D落点、安全区、服务点、语义边和任务模板都是这一个研究内容内部的连续步骤，不是
互相独立的论文研究内容。

#### 5.2.1 观测质量、四状态语义与 EventEpisode

#### 目标

解决“模型概率变化是否应该立刻创建、取消或重复创建任务”的问题。把感知概率转换成任务
层可以长期维护的事件事实。

#### 输入

- LSTM跌倒概率；
- 关键点可见率；
- track连续性；
- 32帧窗口完整度；
- 关键点几何有效性；
- 事件时间、track ID和已有episode状态。

#### 方法

使用四状态机：

```text
normal
event_uncertain
event_confirmed
perception_degraded
```

冻结初始判据为：质量低于0.55进入`perception_degraded`；质量有效且分数连续2个窗口不低于
0.75才确认；0.45到0.75之间为不确定；不高于0.45连续2个窗口才清除候选。

状态机之外再维护 EventEpisode：

- 同一track或时空邻近事件复用episode ID；
- confirmed后短时回到normal不自动关闭；
- degraded时保留已激活episode；
- 只有`verify_no_fall`、`scene_clear`、supervisor close或明确超时策略才能关闭；
- 使用TTL、去重时间/距离和revision防止重复任务与旧消息覆盖。

#### 输出

```text
event_id
semantic_state
confidence
observation_quality
episode lifecycle
perception_revision
valid_until_ns
reason_code
requested action = patrol | reobserve | create response tasks | hold
```

#### 具体问题与解决办法

| 问题 | 解决办法 |
|---|---|
| 单阈值附近反复翻转 | 高低双阈值、连续窗口和debounce |
| 同一跌倒重复生成任务 | EventEpisode ID、时间/空间去重和cooldown |
| 遮挡后事件被错误删除 | confirmed episode在degraded期间保持 |
| 3D暂时无效但事件已确认 | 保留episode，生成reobserve，不派发deliver |
| 旧感知消息覆盖新状态 | 单调`perception_revision`和stale拒绝规则 |

#### 当前状态

V2中的四状态机、EventEpisode、去重和任务生成已有实现与测试；V3.0.1已在S0将状态、
枚举、reason code和状态—动作映射固化为机器可读配置和测试向量。V3医院场景的真实在线
episode与三维事件尚未联调。

#### 5.2.2 原始时间戳与 Robust RGB-D 三维落点

#### 目标

把“图像中有人跌倒”转换为“在map坐标的哪个位置跌倒、位置有多不确定”，为安全区、
服务点和任务路径提供几何依据。

#### 输入

- R1 RGB图像和原始ROS时间戳；
- 对齐到RGB的深度图；
- CameraInfo内参；
- 肩、髋关键点 `[5,6,11,12]`；
- source stamp时刻的 `map -> robot -> camera` TF；
- AMCL机器人地图位姿。

#### 方法

1. 选择可见的肩/髋稳定关键点；
2. 每个关键点读取5×5深度窗口；
3. 删除零值、越界值和MAD异常值；
4. 使用CameraInfo反投影为相机坐标三维点；
5. 按关键点置信度和深度离散度鲁棒加权；
6. 在原始图像时间戳查询TF并转换到`map`；
7. 投影到地面；
8. 输出位置和协方差；无效时输出明确reason并触发reobserve。

平面协方差至少考虑关键点离散、深度误差和TF误差，不能在无法估计时发布零协方差。

#### 输出

目标逻辑消息`SemanticEvent3D`包含：

```text
stamp_ns / frame_id=map
event_id / track_id
semantic_state / confidence / observation_quality
pose_valid
position[3] / covariance[36]
observer_robot_id / observer_pose_map / observation_distance_m
region_id / region_probability
valid_until_ns / perception_revision / reason_code
```

#### 具体问题与解决办法

| 问题 | 解决办法 |
|---|---|
| 推理完成时间晚于图像采集时间 | 保存source ROS stamp，TF和stale判断只使用source time |
| 单点深度容易命中背景或空洞 | 多个肩/髋点、小窗口、MAD剔除和加权聚合 |
| 深度或TF无效 | 输出`pose_valid=false`、原因码和reobserve，不伪造位置 |
| 位置随遮挡和延迟失真 | 使用协方差、stale增长、2秒stale和5秒expire策略 |
| ROS时间与Unix墙钟混用 | 分离source/event ROS time、wall time、monotonic runtime和simulation elapsed |

#### 当前状态

S1已完成原始图像时间戳贯通。真实ROS图像100帧检查中，输入图像、事件和debug图像
100/100保持相同source stamp和`oakd_rgb_camera_optical_frame`；推理单调时钟延迟样本p95
为0.052秒。

Orbbec驱动、D2C、深度窗口、反投影、TF落点、协方差和区域判断属于S2/S3，尚未实施。

#### 5.2.3 不确定性驱动的动态核心安全区

#### 目标

保证任意机器人和任意已有任务都不能穿越跌倒人员周围的核心处置区，并使定位越不确定，
安全区越保守。

#### 输入

- 人体平面中心 `p_e=(x_e,y_e)`；
- 位置协方差 `Sigma_xy`；
- 机器人半径；
- 当前zone、world和perception revision；
- 事件生命周期和stale时间。

#### 方法

安全半径定义为：

```text
r_safe = clamp(
  0.60 + robot_radius + 2.0 * sqrt(lambda_max(Sigma_xy)),
  0.90,
  2.00
)
```

用24边形近似安全圆并发布共享Nav2 keepout。R1、R2均不得进入核心区。zone创建、移动、
膨胀或撤销时递增`zone_revision/world_revision`，依赖新zone的计划只有在两台活动机器人均
返回当前revision的`ZoneApplyAck`后才可派发。

事件确认时还要满足：

```text
distance(R1, event_center)
>= r_safe + xy_goal_tolerance + confirmation_margin
```

P0通过把R1发现距离冻结在2.5到3.0米，避免zone创建瞬间把R1包在keepout内部。如果条件
不成立，返回`SCENARIO_PRECONDITION_FAILED`并进入安全停止，不把该样本计为方法成功。

#### 输出

`DynamicZone`、每台机器人`ZoneApplyAck`、新的world revision，以及zone生命周期和原因码。

#### 具体问题与解决办法

| 问题 | 解决办法 |
|---|---|
| 任务层禁止接近但Nav2路径仍穿过人员 | 将安全区落实为所有机器人共享的导航级keepout |
| 定位误差未反映到安全距离 | 用协方差最大特征值自适应膨胀半径 |
| 新zone尚未进入costmap就派发任务 | revision ACK门禁，2秒超时进入HOLD_SAFE |
| confirmed但3D无效 | 有历史zone则保持；否则使用provisional最大半径或HOLD_SAFE |
| R1确认时已在核心区 | P0冻结观测距离前提，不在本阶段引入“区内安全退出”复杂状态 |

#### 当前状态

安全区公式、字段、参数、ACK、stale规则、安全检查器接口和测试向量已在S0完成。动态
keepout发布、Nav2 filter更新和真实ACK链属于S4，尚未实现。

#### 5.2.4 角色服务点生成

#### 目标

让R1和R2都停在核心安全区边界外，同时保证R1可观察人员、R2可交付物资、两点之间有
安全间距，并且两个目标都能被Nav2到达。

#### 输入

- DynamicZone中心与半径；
- 静态地图和costmap；
- R1/R2当前位姿；
- 相机观察方向；
- Nav2路径查询接口；
- zone/service/map revision。

#### 方法

候选半径为`r_safe + 0.50 m`。初始圆周及最多3个外扩圆周每15度采样，依次执行：

1. 删除地图外、障碍内、核心区内和净空不足0.35米的点；
2. 每个角色按启发式距离保留最多6个候选；
3. 使用Nav2 getPath删除不可达候选；
4. R1候选朝向事件中心且视角误差不超过30度；
5. verifier与courier点间距不低于0.75米；
6. 联合选择R1和R2路径总长最小的服务点对；
7. 全流程4秒超时，失败时返回结构化原因，不沿用旧服务点。

#### 输出

`RoleServicePointArray`：顶层给出pair是否有效、生成状态、运行时间、zone/service revision；
每个点给出角色、map位姿、净空、路径长度、预计时间、有效期和原因码。

#### 当前状态

算法流程、参数和逻辑schema已在S0固化，真实服务点生成器和Nav2在线组合选择属于S4，
尚未实现。S1 path-cost adapter为这一模块提供了已经验证的路径查询基础。

#### 5.2.5 路径代价、短时避障与持续语义边状态

#### 目标

区分“行人短暂经过，Nav2局部绕一下即可”和“走廊持续不可用，必须修改任务计划”两类
动态，防止每个局部障碍都触发任务级重规划。

#### 输入

- 命名起点和终点；
- Nav2 `ComputePathToPose`响应；
- 路径是否存在、长度、运行时间；
- map/costmap revision；
- 连续路径探测结果；
- 导航失败次数和时间窗口。

#### 方法

- 短时行人只进入local costmap，不修改world revision；
- 路径仍存在但代价比连续5秒不低于1.80，记为`TEMPORARY_OCCUPIED`；
- 路径连续5秒不存在，记为`BLOCKED`；
- 路径连续10秒恢复且代价比不高于1.30，记为`FREE`；
- 单次服务失败或空路径只返回原因码，不立刻触发LocalRepair；
- map、edge、zone、world、起终点或plan revision变化时使路径缓存失效。

#### 输出

`SemanticEdgeState`：

```text
edge_id / from_region / to_region
FREE | TEMPORARY_OCCUPIED | BLOCKED
path_exists / path_length / baseline_length / cost_ratio
state_since / valid_until / edge_revision / reason_code
```

S1 path-cost adapter已经输出结构化：

```text
start_id / goal_id
source stamp / frame_id
path_exists / path_length_m / estimated_time_sec
map/costmap可追踪标识
runtime_sec / reason_code
```

查询失败时禁止静默回退YAML旧路径长度。

#### 已完成内容与结果

S1真实Nav2命名路径结果：

| 路径 | 是否可达 | 长度 | 预计时间 | 查询单调时钟运行时间 |
|---|---|---:|---:|---:|
| A→B | 是 | 2.926 m | 11.705 s | 0.0097 s |
| B→C | 是 | 3.552 m | 14.209 s | 0.0104 s |
| C→D | 是 | 3.671 m | 14.683 s | 0.0075 s |
| D→S | 是 | 10.584 m | 42.337 s | 0.0173 s |

查询runtime p95为0.0163秒，满足不超过1秒的S1门槛。正常、不可达、空路径、TF不可用、
非法起终点、超时、stale和服务不可用均有结构化reason code测试。

#### 尚未完成

持续在线探测、迟滞边状态、缓存失效与world revision的真实ROS闭环属于S5，尚未实施。

#### 5.2.6 从稳定事件到机器人任务层

这一环节是研究内容二的最终输出，不负责求解“任务分给谁”，而是把视觉语义翻译为规划
器能够消费的任务、目标、前驱和安全约束。

##### 输入

- EventEpisode的`normal/uncertain/confirmed/degraded/closed`状态；
- 事件三维位置、区域、DynamicZone和角色服务点；
- edge状态、物资点和等待点；
- 机器人可执行动作模板。

##### 方法

根据冻结的状态—动作表完成事件到任务的转换：

- `normal`且无active episode：不创建事件任务；
- `event_uncertain`：创建或刷新同一candidate，主要产生R1的`reobserve`；
- `event_confirmed`且3D、zone和service pair有效：并发释放
  `verify_and_monitor`与`pickup`，并建立`pickup -> deliver -> monitor_end`前驱关系；
- `event_confirmed`但3D无效：保持episode并生成`reobserve`，禁止派发deliver；
- `perception_degraded`且已有confirmed episode：保留任务和旧zone，不创建新ID；
- `verify_no_fall`或`scene_clear`：关闭episode并取消未开始的响应任务；
- 任何状态变化都携带reason code和source/world revision。

##### 输出

研究内容二向研究内容三交付的不是模型概率，而是：

```text
稳定event_id和事件生命周期
任务集合：reobserve / verify_and_monitor / pickup / deliver
任务DAG和释放条件
任务目标：verifier/courier service point、supply point
安全约束：keepout和required zone revision
动态资源：semantic edge及其可用状态
任务deadline、能力需求、持续监护语义
```

##### 当前状态

V2 EventTaskFactory和任务生命周期已有实现；V3的四个任务模板、状态—动作表、消息schema、
reason code和revision拒绝规则已在S0固化。将真实SemanticEvent3D、服务点和edge在线转换为
V3任务DAG的运行链尚未完成。

### 5.3 研究内容三：单/多机器人协同分配、排程与局部计划修复

这一部分消费研究内容二形成的稳定事件、任务DAG、服务点、路径代价和动态资源状态，
研究单机器人与多机器人条件下如何进行任务分配和时序排程，以及环境变化后如何在保证
安全和可行性的前提下少改计划。Nav2执行、HOLD_SAFE和实验场景是验证该研究内容的方法
与系统支撑，不单独列为新的研究内容。

#### 5.3.1 单/多机器人序列MILP分配与排程

#### 目标

消费研究内容二生成的任务DAG，联合决定任务由哪台机器人执行、以什么顺序执行、何时
开始、占用哪些共享资源，并同时满足安全、能力、前驱、持续监护、电量和deadline约束。

#### 输入

- confirmed EventEpisode；
- reobserve、verify_and_monitor、pickup、deliver任务模板；
- R1/R2能力、位姿、电量和可用状态；
- DynamicZone、角色服务点和semantic edge；
- Nav2路径长度与预计时间；
- 任务前驱、资源、service duration和deadline；
- 当前world/zone/service/plan revision。

#### 方法

序列MILP使用直接后继关系表达同一机器人任务顺序，同时建模：

- 每个任务唯一分配；
- 机器人能力匹配；
- pickup和deliver同机器人；
- 任务DAG前驱；
- 同机器人时间不重叠；
- 共享走廊、服务点等容量为1；
- 持续监护区间覆盖deliver；
- 电量下限和返航余量；
- deadline与动态资源可用时间；
- committed/active/frozen任务不可被随意修改。

目标函数先把各项归一化，再加权：

```text
min J =
  1.0 * normalized_makespan
  + 4.0 * normalized_lateness
  + 2.5 * normalized_plan_changes
  + 1.5 * normalized_resource_wait_and_detour
  + 3.0 * normalized_energy_risk
```

安全区、能力、持续留场、前驱、资源互斥和电量下限都是硬约束，不能用目标权重交换。

#### 输出

`TaskPlan`包含plan ID/revision、source world/zone revision、计划类型、任务分配、资源预约、
affected/frozen集合、归一化目标分量、运行时间、gap和validator结果。

#### 已完成内容与证据

V2离线序列MILP已经实现并能得到`OPTIMAL`解，validator覆盖唯一分配、能力、前驱、同机
互斥、资源冲突、动态时间窗、电量、事件响应和冻结前缀。

已有动态回放中，`corridor_H`在t=45变为临时占用，等待20秒，使任务T4开始时间由53秒
推迟至65秒，makespan由78秒变为90秒，说明“空间状态→资源时间窗→新计划”的链路成立。

#### 尚未完成

V3的持续监护、角色服务点、真实Nav2路径代价和医院任务模板尚未进入在线MILP；S6以前
不能宣称V3在线规划闭环完成。

#### 5.3.2 版本驱动的 LocalRepair

#### 目标

环境变化后保持已完成、正在执行和未受影响的任务稳定，只修复确实受影响的子计划，减少
无意义的机器人重分配、任务换序和开始时间震荡。

#### 输入

13类规划触发：

```text
NEW_CONFIRMED_EVENT
EVENT_POSE_CHANGED
EVENT_CLOSED
ZONE_CHANGED
SERVICE_POINT_CHANGED
EDGE_TEMPORARY
EDGE_BLOCKED
EDGE_RELEASED
ROBOT_LOW_BATTERY
ROBOT_UNAVAILABLE
NAVIGATION_FAILED
ACTION_FAILED
EXECUTION_COMPLETED
```

以及旧计划、执行反馈、world revision、任务DAG、机器人序列和变更资源。

#### 方法

受影响集合由以下关系传播：

```text
使用变化资源的任务
∪ 路径经过变化边的任务
∪ 绑定变化事件/zone/service point的任务
∪ 分配给变化机器人的任务
∪ DAG后继任务
∪ 同一机器人序列中的下游任务
```

completed、不可抢占active、R1 active monitor和未受影响future task构成冻结集合。若冻结
动作与新keepout冲突，安全优先并进入HOLD_SAFE，不强行维持旧计划。

小任务集不使用简单比例强制全局重规划：

```text
if remaining_tasks >= 5 and affected_ratio > 0.60:
    Full-Replan
elif all_active_robots_affected:
    Full-Replan
elif global_resource_or_safety_structure_changed:
    Full-Replan
else:
    LocalRepair
```

LocalRepair使用2秒时限和1% gap；Full-Replan使用5秒和1% gap。求解期间若出现新
`world_revision`，旧solver结果必须丢弃。

#### 输出

`RepairStatus`包含触发、求解world revision、Local/Full选择、affected/frozen任务、比例
门禁、回退原因、任务变化记录、运行时间、validator和是否发布。

一次plan change定义为任务发生任一变化：机器人重分配、相对顺序变化、服务点变化，或
开始时间偏移严格超过5秒。同一任务多种变化只计一次，但保留change flags。

#### 已完成内容与证据

- V2离线`repair_after_disturbance`已经实现影响传播、冻结和Full-Replan回退；
- dynamic repair matrix五类场景均返回结构化结果；
- 扩展判别场景中Full-Replan修改2个未来任务，LocalRepair修改0个，两者资源冲突和
  deadline违例均为0，validator均通过。

这证明已有离线算法原型能够体现“少改计划”，但不能代表V3在线LocalRepair已经完成。

#### 尚未完成

- ROS world revision真实触发LocalRepair；
- V3全部13类触发的在线执行；
- service point、keepout和persistent edge参与影响传播；
- 与No-Repair、Full-Replan、无变化惩罚LocalRepair的大样本配对实验。

以上属于S6/S8。

#### 5.3.3 Full-Replan回退与 HOLD_SAFE物理停止

#### 目标

当局部修复或完整重规划不可行时，系统不能继续执行旧计划，也不能只停止“派发新目标”
却让机器人继续沿旧Nav2目标运动。

#### 输入

- LocalRepair求解/validator状态；
- 9项Full-Replan顶层回退条件；
- active Nav2 goal；
- 当前速度、cancel请求与ACK；
- command/world/plan revision。

#### 方法

以下情况包括LocalRepair不可行/报错、2秒无可行解、硬约束失败、冻结任务与新安全区冲突、
无服务点对、规模/结构门禁、连续局部失败、机器人不可用破坏关键能力，以及多edge/zone
变化导致局部边界失效。任一成立即进入Full-Replan。

Full-Replan仍失败时：

1. 发布带`command_id`和revision的`HoldSafeCommand`；
2. 0.50秒内向所有active Nav2 goal发送cancel；
3. cancel后0.50秒内收到ACK；
4. ACK后0.50秒内验证线速度不超过0.02 m/s、角速度不超过0.05 rad/s；
5. 锁定新目标派发；
6. 保持keepout；
7. 只有新revision上通过validator的新计划或supervisor命令才能解除锁定。

#### 输出

`HoldSafeCommand`和每台机器人`SafetyStopStatus`。只有cancel已确认、active goal消失、速度
达标且dispatch lock生效，才能报告`STOPPED`。旧command/revision的STOPPED不能解锁新
安全状态。

#### 当前状态

S0已经实现协议validator、13条仿真安全规则的纯检查器接口和正反测试；真实Nav2 cancel、
ACK、速度闭环和锁定执行器尚未实现，属于S6/S7。

#### 5.3.4 Nav2执行、反馈与医院实验场景验证

#### 目标

把任务计划转换为真实导航目标，完整记录发送、接受、执行、完成/失败、到达位姿、路径、
定位协方差、恢复行为和安全距离，并最终扩展为R1/R2命名空间下的并发执行。

#### 输入

- TaskPlan assignment；
- target pose和required zone revision；
- Nav2 action server、TF、AMCL、scan/costmap；
- 当前plan/world revision。

#### 输出

`ExecutionFeedback`至少包含robot、plan/task/revision、执行状态、failure class、实际位姿、
Nav2错误码和reason code。旧plan/world revision反馈只进入日志，不能完成新计划任务。

#### S1已经完成的部分

- 单机器人连续导航runner和逐目标结构化日志；
- path-cost adapter；
- 静态地图、global costmap、TF、AMCL、完整path和planner日志诊断；
- ROS图像header审计；
- V3 11个逻辑topic的协议smoke，production publishing保持关闭；
- ROS时间、Unix墙钟、单调运行时间和仿真耗时的明确分离。

最初使用受保护`maps/kaiti_house.yaml`时，C/D位于致命或膨胀costmap，S与A/B不在同一
自由空间连通分量。S1没有移动V2航点或缩小机器人半径，而是使用从当前SDF世界生成且已
追踪的S1专用同源地图`maps/candidates/2026-07-17/kaiti_house_sdf_static.yaml`。换图后
A/B/C/D/S均位于同一可达分量并满足0.45米静态净空。

#### 当前真实阻塞

S1要求A→B→C→D→S连续完成3轮。2026-07-29正式报告中，第一轮A/B/C/D成功，D→S在
120秒仿真时限后超时。2026-09-14最新复测仍为第一轮A/B/C/D成功、S失败：

| 目标 | 状态 | 仿真耗时 | 单调时钟耗时 | 恢复次数 | 最小障碍距离 |
|---|---|---:|---:|---:|---:|
| A | 成功 | 0.464 s | 0.640 s | 0 | 0.653 m |
| B | 成功 | 23.660 s | 23.564 s | 5 | 0.474 m |
| C | 成功 | 21.360 s | 21.472 s | 0 | 0.437 m |
| D | 成功 | 21.256 s | 21.265 s | 0 | 0.461 m |
| S | 失败 | 116.004 s | 115.941 s | 22 | 0.298 m |

由于D→S全局路径已经存在，当前问题定位为控制器进展、局部costmap、恢复行为或Create3
安全仲裁问题，而不是全局路径不可达。必须继续停留在S1诊断，不能通过放宽门禁进入S2。

#### 尚未完成

- A→B→C→D→S连续3轮成功；
- 双机器人`/r1`、`/r2`命名空间、AMCL/Nav2/TF；
- 医院世界；
- 动态keepout、服务点和在线计划派发；
- 20-seed双机器人端到端门禁。

#### 5.3.5 用于体现研究问题的医院公共空间实验场景

实验场景服务于研究内容三的验证，不另算第四项研究内容。所有方法使用相同地图、事件
位置、机器人初始状态、障碍轨迹、任务时长、deadline和随机种子。

##### 场景E0：无扰动静态基线

```text
R1从巡检区发现跌倒E1
R1前往verifier service point并持续监护
R2前往aid station取物并送到courier service point
通道保持FREE
```

目的：验证事件任务DAG、基础任务分配、排程、持续监护和物资配送能完成。输出任务成功率、
makespan、响应时间、路径长度、最小人机/机间距离和validator结果。

##### 场景E1：公平的单机器人—双机器人对照

单机器人拥有camera、verify、carry、move和patrol全部能力，速度、电量和Nav2配置与双
机器人中的单台一致。保持“监护期间不得离开verifier point”和“不得使用远程摄像头替代
留场”。双机器人使用同一事件、任务、路径和deadline。

目的：证明双机器人优势来自“持续留场+异地取送”的并发占位语义，而不是能力名称硬编码。
同时去掉持续留场约束做sanity check；若单机仍不可行，应先排查模型或场景。

##### 场景E2：短时行人经过

行人在连接走廊短时经过，障碍持续时间低于`block_confirm_sec`，只进入local costmap。

目的：验证Nav2能够局部避障，任务层不产生world revision和LocalRepair。关键指标为短时
行人误触发任务级修复比例不超过1%。

##### 场景E3：持续走廊阻塞

同一走廊连续5秒路径不存在或代价比持续超过1.80，使edge进入`BLOCKED`或
`TEMPORARY_OCCUPIED`。

目的：比较Nav2-only、Full-Replan和LocalRepair。观察等待/绕行、任务重分配、开始时间
偏移、计划变化数、runtime、deadline和成功率，体现局部修复“少改未受影响任务”的价值。

##### 场景E4：事件位置、zone或服务点变化

由于新的有效RGB-D观测，event center移动超过0.25米或安全半径变化超过0.10米，导致
zone revision和service point更新。

目的：验证旧服务点和路径缓存失效、两机器人zone ACK、新计划只在当前revision发布，
以及LocalRepair能只调整绑定该事件的任务。

##### 场景E5：导航失败或配送机器人不可用

R2连续两次导航失败，或机器人状态变为unavailable/low battery。

目的：验证执行反馈能形成结构化规划触发；若局部仍有替代路径则LocalRepair，否则回退
Full-Replan。若持续监护或pickup-deliver能力被破坏，结果应明确不可行，不能静默跳过。

##### 场景E6：感知退化和三维位置过期

事件确认后模拟遮挡、深度缺失或TF无效，使事件位置先stale后expire。

目的：验证episode不丢失、协方差随时间膨胀、R1执行reobserve、R2停止接收新deliver目标，
并且无效深度不会被伪装成有效三维事件。

##### 场景E7：求解期间世界更新和完全不可行

LocalRepair求解过程中注入新的world revision；另一个case让LocalRepair与Full-Replan均
不可行。

目的：前者验证stale solver result被100%拒绝；后者验证系统进入HOLD_SAFE，在规定时间
内cancel、收到ACK、物理停止并锁定新目标派发。

##### 实验场景当前状态

- E0在V2简化任务和单车Nav2层已有部分基础，但V3医院双机器人闭环未实现；
- E2/E3的离线空间回放、Full-Replan和LocalRepair已有V2证据；
- E1、E4、E5、E6、E7的参数、状态映射和测试协议已在S0固化；
- 真正的医院世界、动态keepout、双机器人Nav2和在线LocalRepair要在S4–S7完成；
- S7使用20个固定种子做工程门禁，S8使用每扰动每方法20–30个配对种子形成论文结论。

## 6. 三项研究内容输入—输出总表

| 三项研究内容 | 主要输入 | 核心研究过程 | 主要输出 | 当前状态 |
|---|---|---|---|---|
| 1. 视觉检测 | RGB图像、人体框、17个关键点、连续32帧序列 | YOLO Pose提取姿态；Rule/LSTM/TCN识别；输出质量和稳定检测状态 | 人体姿态、跌倒分数、raw/stable判断、观测质量和原始时间信息 | 已实现并有开发集结果；公共空间独立test待完成 |
| 2. 视觉语义事件稳定与机器人任务层形成 | 检测分数、质量、track、历史事件、RGB-D/TF、地图、Nav2路径和动态资源 | 四状态与Episode稳定事件；三维落点；形成安全区、服务点、语义边和事件任务DAG | 可供机器人使用的稳定event ID、SemanticEvent3D、任务、目标位姿、资源和安全约束 | V2事件稳定已实现；S0合同和S1时间/path接口已完成；3D/zone/service/edge运行链未实现 |
| 3. 单/多机器人协同分配、排程与局部计划修复 | 稳定事件任务、机器人能力/状态、服务点、路径代价、资源、deadline、旧计划和执行反馈 | 单/多机器人MILP分配与排程；影响传播和LocalRepair；Full-Replan/HOLD_SAFE回退；医院场景实验 | TaskPlan、RepairStatus、ExecutionFeedback、安全停止状态和单/多机器人实验结果 | V2离线MILP/LocalRepair已实现；S1真实导航未过；V3在线修复和双机器人实验未开始 |

上述三项研究内容内部所需的支撑模块关系如下。这里的“支撑模块”不增加论文研究内容
数量：

| 支撑模块 | 归属研究内容 | 作用 |
|---|---|---|
| 原始时间戳、RGB-D落点和协方差 | 研究内容二 | 把二维视觉结果转换为带空间依据的任务事件 |
| 动态安全区和角色服务点 | 研究内容二 | 把事件转换为可安全执行的目标位姿与约束 |
| 语义边和path-cost adapter | 研究内容二 | 把导航可达性和持续阻塞转换为任务层资源状态 |
| 事件任务模板和任务DAG | 研究内容二 | 把稳定事件转换为任务、前驱、目标、deadline和安全约束 |
| 序列MILP | 研究内容三 | 完成单/多机器人任务分配、排序和资源预约 |
| LocalRepair和Full-Replan | 研究内容三 | 在动态变化后修复受影响计划并保证可行性 |
| Nav2执行、HOLD_SAFE和实验日志 | 研究内容三 | 执行并验证分配、排程、修复与安全边界 |

## 7. 当前阶段成果总览

### 7.1 已经可靠完成

按三项研究内容归纳，当前已经可靠完成的是：

1. **研究内容一：视觉检测。** 已形成训练—推理—评估—可视化闭环；完成Rule、LSTM、
   TCN同口径比较和hard-negative实验；默认LSTM开发口径F1为0.7979；
2. **研究内容二：事件稳定与任务层形成。** V2四状态、EventEpisode、去重和任务工厂已有
   实现；S0已固化96个参数、4个任务模板、状态—动作表、schema、revision/reason规则；
   S1已完成原始图像时间戳/frame ID贯通以及结构化path-cost接口；
3. **研究内容三：分配、排程与局部修复。** V2序列MILP、validator、五类动态扰动和离线
   LocalRepair已有可复现实验；S1已建立单车连续导航runner、地图—world—waypoint—costmap
   诊断链和执行日志，但真实连续三轮尚未通过。

横跨三项研究内容的工程基础还包括ROS2最小感知—监督—任务请求骨架、S0安全检查器、
20-seed manifest模板、V2/house 13项资产hash保护和分组回归测试。

### 7.2 测试与证据

截至S1正式关闭报告：

| 测试组 | 结果 |
|---|---:|
| S0专项 | 19 passed |
| 根目录既有Python | 33 passed |
| ROS执行契约 | 4 passed |
| S1新增/基线 | 25 passed |
| V2 planning smoke | `passed: true` |
| dynamic repair matrix | 五类场景均返回预期结构化结果 |
| V2/house保护hash | 13/13 unchanged |
| `git diff --check` | passed |

S0检查点为`8d0e6a0033c9121969598e36d722339fe3340d16`。当前分支为
`feat/public-space-v3-s1`，S1改动仍在工作区，尚未提交。

### 7.3 尚未完成或未通过

| 项目 | 状态 | 原因/边界 |
|---|---|---|
| S1连续导航三轮 | **FAIL** | D→S反复恢复后失败，尚未完成第一轮 |
| Orbbec与D2C | NOT STARTED | 必须等待S1关闭后进入S2 |
| Robust RGB-D | NOT STARTED | S3 |
| 医院语义区域、动态zone、服务点 | NOT STARTED | S3/S4 |
| persistent edge与路径缓存 | NOT STARTED | S5 |
| V3在线LocalRepair/HOLD_SAFE | NOT STARTED | S6 |
| 双机器人医院仿真 | NOT STARTED | S7 |
| 正式论文消融和统计 | NOT STARTED | S8 |

因此当前总状态应表述为：

```text
感知主线：已有可用原型和开发集结果
V2规划/修复原型：已完成离线验证
S0协议固化：PASS
S1代码、path-cost、时间戳：PASS
S1真实连续导航：FAIL
S1总体：FAIL
S2-S8：未启动
```

## 8. 当前主要问题及计划中的解决方案

| 编号 | 当前问题 | 直接影响 | 解决方案 | 所属阶段 |
|---|---|---|---|---|
| P1 | 公共空间遮挡/慢跌倒数据不足 | 感知结果可能不能泛化 | 冻结独立test，补远距离、遮挡和hard negative，报告event-level指标 | S8 |
| P2 | confirmed但3D无效 | 无法安全生成zone和交付目标 | 保留episode、reobserve、provisional最大区，禁止deliver | S3/S4 |
| P3 | R1可能在新安全区内部 | zone创建瞬间违规 | 冻结2.5–3.0米观测距离和确认净空前提 | S4/S7 |
| P4 | 定位不确定性未进入导航 | 固定安全半径可能过小或过大 | 协方差驱动动态半径和服务点 | S3/S4 |
| P5 | 短时行人与持续阻塞混淆 | 重规划过频或阻塞不响应 | 5秒确认、10秒释放的语义edge迟滞 | S5 |
| P6 | 路径失败时可能使用旧YAML距离 | 规划代价失真 | 结构化path adapter，失败返回reason并禁止静默回退 | S1已完成 |
| P7 | LocalRepair在小任务集中可能被比例门禁禁用 | 核心方法无法实际运行 | 剩余任务不少于5时才使用0.60比例门禁 | S0已固化/S6实施 |
| P8 | 单机器人基线可能因角色硬编码不公平 | 双机器人必要性结论不可信 | 单机拥有全部能力，仅保留物理持续留场约束 | S0已固化/S8实验 |
| P9 | 求解期间world更新 | 旧计划可能覆盖新安全状态 | solve revision捕获、stale结果拒绝、ACK和plan revision | S6 |
| P10 | HOLD_SAFE只停止派发、不取消旧目标 | 机器人仍可能运动 | cancel、ACK、速度阈值和dispatch lock四重判据 | S6/S7 |
| P11 | D→S全局有路但执行失败 | S1不能关闭 | 审计cmd_vel、local costmap、DWB、恢复行为和Create3安全仲裁 | 当前S1 |
| P12 | 20个种子不足以证明方法优越 | 统计结论不稳定 | 20-seed只做工程门禁；论文用每扰动每方法20–30个配对种子 | S7/S8 |

## 9. 研究假设、实验和验收指标

### 9.1 研究假设

- H1：四状态+EventEpisode相对单阈值减少false task、重复episode和plan churn；
- H2：Robust RGB-D相对区域中心、2D地面投影和单点深度提高落点、区域和服务点有效率；
- H3：同等安全和任务约束下，LocalRepair比Full-Replan少修改计划且成功率非劣；
- H4：持续监护与异地取送的并发占位使能力完备单机器人仍结构性不可行，而双机器人可行。

### 9.2 研究内容一实验：视觉检测

比较Rule、LSTM、TCN；后续可加入轻量Transformer。报告frame/window/event-level
Precision、Recall、F1、触发延迟、误报任务、重复episode、状态翻转以及遮挡/慢跌倒子集。
P0 event-level F1目标为不低于0.75，但未达标不伪装成功，也不阻断系统安全闭环验证。

### 9.3 研究内容二实验：事件稳定与任务层形成

首先比较single threshold、hysteresis、four-state、four-state+Episode，统计false task、
重复episode、状态翻转、确认延迟、degraded后事件丢失和stale revision覆盖。目标包括：
confirmed后重复episode不超过0.05/event，相比single threshold的false task至少降低30%，
从32帧窗口ready后计算的确认延迟p95不超过5秒。

三维落点比较以下四种方法，并使用完全相同的样本：

1. Zone centroid；
2. 2D ground projection；
3. Single-depth；
4. Robust RGB-D。

目标为平面误差median不超过0.25米、p90不超过0.50米、region accuracy不低于95%，且无效
深度被错误发布为valid的次数为0。

还要验证service pair生成成功率不低于95%、服务点进入核心区次数为0、两服务点间距小于
0.75米的次数为0、未收到当前zone revision ACK就派发任务的次数为0，以及短时行人误触发
任务级修复的比例不超过1%。这些指标共同证明研究内容二确实形成了可供机器人采用的任务
层，而不只是输出一个分类标签。

### 9.4 研究内容三实验：单/多机器人分配、排程与局部修复

首先在完全相同的事件位置、任务时长、路径、deadline和随机种子下比较能力完备单机器人
与R1/R2双机器人。单机器人保留持续监护硬约束；同时增加“去掉持续监护约束”的sanity
check。主要报告可行性、响应时间、交付完成时间、R1留场、路径长度和资源冲突，以验证
双机器人协同的必要性来自任务并发语义。

在双机器人条件下进一步比较动态扰动处理方法：

1. Nav2-only/No-Repair；
2. Full-Replan；
3. LocalRepair；
4. LocalRepair without change penalty。

主要扰动包括persistent blocked、zone/service更新、navigation failure、perception degraded
和求解中world revision更新。报告任务成功率、计划变化数、runtime、deadline、安全失败、
fallback和HOLD_SAFE。

LocalRepair runtime p95目标不超过2.2秒，Full-Replan不超过5.5秒；可局部修复场景中，
LocalRepair比Full-Replan少改计划的run比例不低于70%，任务成功率非劣界为-5个百分点。

### 9.5 工程门禁与论文统计分开

S7的20个固定种子只验证端到端闭环、安全、日志和复现：目标至少18/20成功、碰撞为0、
核心区侵入为0、R1提前离场为0、日志/revision链20/20完整。

正式方法结论对每个主要扰动、每个方法至少使用20–30个相同配对种子，报告95%置信区间、
配对差值、McNemar或配对bootstrap以及seed级原始数据。不能把20次中的一次成败直接当作
稳定的5个百分点证据。

## 10. 预期创新点与准确表述

### 10.1 可以主张的研究贡献

1. 带观测质量、三维位置协方差、TTL和revision的规划语义事件；
2. 由视觉位置不确定性驱动的共享硬安全区和角色服务点；
3. 从短时局部避障到持续语义边阻塞的时间分层；
4. 基于world revision、影响传播和冻结计划的最小扰动LocalRepair；
5. 从感知误差到false task、无效导航和plan churn的跨层评价；
6. 通过持续监护与异地取送语义建立公平的单双机器人可行性对照。

### 10.2 不能主张的内容

不得声称：

- 提出了新的YOLO、LSTM、MILP或Nav2；
- V3双机器人系统已经完成；
- 已实现完整三维动态语义SLAM；
- 已接入PlanSys2进行任务规划；
- 已实现人群疏导、跨摄像头ReID或三机器人协同；
- 当前开发集F1代表医院公共空间最终泛化结果；
- 当前离线LocalRepair已经完成ROS在线闭环；
- S1已经通过。

## 11. 实施阶段与当前下一步

| 阶段 | 内容 | 当前状态 |
|---|---|---|
| S0 | 参数、schema、测试向量、hash、安全检查器、manifest | **PASS，已建立Git检查点** |
| S1 | source stamp、单车连续导航、path-cost、V3 smoke | **总体FAIL：连续导航未过** |
| S2 | Orbbec、D2C、CameraInfo、同步和TF台架 | 禁止启动 |
| S3 | Robust RGB-D、协方差和语义区域 | 未启动 |
| S4 | DynamicZone、shared keepout、ACK和服务点 | 未启动 |
| S5 | semantic edge、迟滞和路径缓存 | 未启动 |
| S6 | 在线LocalRepair、Full-Replan和HOLD_SAFE | 未启动 |
| S7 | 双机器人医院仿真和20-seed门禁 | 未启动 |
| S8 | 感知、3D、规划和跨层正式实验 | 未启动 |

进入S2前唯一合理的近期工作是继续完成S1真实运行门禁：

1. 对D→S失败区段同步记录`cmd_vel_nav`、平滑后`cmd_vel`、底盘输入和odom；
2. 保存local costmap和DWB候选轨迹；
3. 区分controller无进展、局部障碍/膨胀、恢复行为和Create3安全层限速/禁退；
4. 不先减小机器人半径、关闭inflation或移动语义航点；
5. 修复后重新执行四对路径查询和A→B→C→D→S连续三轮；
6. 真实门禁通过、用户检查diff后才能关闭S1。

## 12. 汇报时建议采用的主线

汇报必须始终围绕三个研究内容展开，而不是按工程模块逐个介绍：

1. **研究内容一——视觉检测。** 先说明医院公共空间中跌倒、坐下、弯腰和遮挡的视觉
   难点，再介绍YOLO Pose、32帧LSTM、规则法/TCN对照、hard negative和当前检测结果；
2. **研究内容二——事件稳定和任务层形成。** 说明单帧结果为什么不能直接触发机器人，
   再讲四状态、EventEpisode、RGB-D落点、安全区、服务点和语义边如何共同把视觉结果变成
   “任务是什么、在哪里执行、有哪些安全与资源约束”；
3. **研究内容三——单/多机器人分配、排程和局部修复。** 说明单机器人与双机器人任务
   模型、MILP联合分配排程、LocalRepair/Full-Replan/HOLD_SAFE，以及如何在医院仿真中用
   持续监护、异地配送、走廊阻塞和导航失败验证这些方法。

每个研究内容都按“问题—输入—方法—输出—已经完成—尚未完成—实验设计”讲述。RGB-D、
安全区、服务点、Nav2和HOLD_SAFE在汇报中应被称为实现研究内容二、三所必需的支撑方法，
不能另起为第四到第十项研究内容。

一段可直接使用的汇报摘要：

> 本研究面向医院公共空间人员跌倒事件，目标不是只提高检测精度，而是建立从视觉证据到
> 多机器人安全处置的完整闭环。系统首先通过YOLO Pose和32帧LSTM识别跌倒，再用观测质量
> 四状态与EventEpisode抑制误触发和重复任务；随后利用RGB-D和TF估计map坐标中的人体位置
> 与协方差，据此生成所有机器人共享的核心安全区以及边界外可达的核验、交付服务点。事件
> 任务由序列MILP进行分配和排序；当走廊阻塞、服务点变化或导航失败时，通过world revision
> 和影响传播只修复受影响子计划，局部不可行则回退Full-Replan，仍不可行则HOLD_SAFE并
> 验证Nav2取消和物理停止。当前感知原型、V2离线规划修复、S0协议固化、S1时间戳与路径
> 代价接口已经完成；真实连续导航仍在D到S区段失败，因此S1尚未关闭，三维落点、动态安全
> 区、在线LocalRepair和双机器人医院仿真均未提前启动。

## 13. 演示内容与证据文件

### 13.1 跌倒检测

- 现成OSD视频：`outputs/vis_debug/bili_fall_debug.mp4`；
- 推理入口：`scripts/run_pose_infer.py`；
- 默认配置：`configs/infer_pose_stream.yaml`；
- 结果依据：[Rule/LSTM/TCN对比](../../reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md)；
- hard-negative依据：[FallVision抽样实验](../../reports/benchmarks/fallvision_nofall_sampling_sweep_2026-04-13.md)。

### 13.2 规划与LocalRepair

- 动态重规划：[Dynamic Replan](../../reports/benchmarks/dynamic_replan_2026-06-22.md)；
- 最小扰动对比：[Local Repair Comparison](../../reports/benchmarks/local_repair_comparison_2026-06-23.md)；
- 可运行入口：`scripts/run_planning_smoke.py`、`scripts/run_dynamic_repair_matrix.py`。

### 13.3 S1时间与路径

- 100帧图像header：
  [image_header_100_frame_real.json](../../reports/s1/image_headers/image_header_100_frame_real.json)；
- 真实path-cost：
  [path_cost_20260729_s1_real_nav2.json](../../reports/s1/path_cost/path_cost_20260729_s1_real_nav2.json)；
- 地图、costmap和TF诊断：
  [nav2_diagnostics_20260729_s1_world_aligned.json](../../reports/s1/diagnostics/nav2_diagnostics_20260729_s1_world_aligned.json)；
- 2026-07-29连续导航：
  [round_01.json](../../reports/s1/continuous_navigation/20260729_s1_world_aligned_three_rounds/round_01.json)；
- 2026-09-14最新连续导航：
  [latest round_01.json](../../reports/s1/continuous_navigation/latest_run/round_01.json)。

## 14. 核心代码、配置和文档入口

| 类型 | 位置 | 作用 |
|---|---|---|
| 冻结研究计划 | [research_plan_v3_0_1.md](../research_plan_v3_0_1.md) | P0研究问题、参数、接口、安全和门禁的唯一依据 |
| S0协议说明 | [public_space_v3_s0_protocol.md](../public_space_v3_s0_protocol.md) | S0机器可读合同和验证方式 |
| S1关闭报告 | [public_space_v3_s1_closure_2026-07-29.md](public_space_v3_s1_closure_2026-07-29.md) | 当前S1真实结论 |
| 感知runner | `src/yolopose/pipeline/runner.py` | 姿态推理、记录与source metadata |
| 时序检测 | `src/yolopose/temporal/sequence_fall_detector.py` | LSTM/TCN窗口推理 |
| ROS感知节点 | `ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py` | ROS图像输入、事件和debug图像 |
| V3配置 | `configs/public_space_v3.yaml` | 96个冻结参数和4个任务模板 |
| V3协议validator | `src/kaiti_planning/public_space_v3_protocol.py` | 完整对象、枚举、reason、revision与stale检查 |
| V3安全检查器 | `src/kaiti_planning/public_space_v3_safety.py` | 13条仿真安全规则接口 |
| S1 path adapter | `src/kaiti_planning/nav2_path_cost.py` | Nav2路径结构化查询 |
| S1导航runner | `src/kaiti_planning/s1_navigation_baseline.py` | 连续导航和逐目标日志 |
| V2序列MILP | `src/kaiti_planning/sequence_milp.py` | 分配、排序与约束求解 |
| V2动态修复 | `src/kaiti_planning/dynamic_repair.py` | 影响传播、冻结和局部修复 |

## 15. 当前结论

目前项目已经从“单纯跌倒检测”发展为一套有明确输入输出、状态语义、任务模型、安全边界、
动态修复策略和阶段门禁的多机器人研究方案。感知和V2离线规划原型为可复用基础，S0把
V3规则完整固化为机器可读合同，S1已解决原始时间戳和路径代价接口问题，并发现了真实
导航执行层的D→S阻塞。

当前最重要的研究态度是保持结果边界清晰：已有证据足以说明技术路线和基础模块成立，但
不足以宣称医院双机器人端到端系统完成。只有先关闭S1，再按S2到S8依次验证三维落点、
安全区、动态边、在线LocalRepair和双机器人系统，最终创新点才会由完整实验链支撑。
