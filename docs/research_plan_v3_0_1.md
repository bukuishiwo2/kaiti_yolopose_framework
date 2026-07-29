# 医院公共空间不确定视觉事件驱动的双机器人协同响应与局部计划修复研究

硕士学位论文研究计划 V3.0.1

- 学生：叶豪成
- 版本：v3.0.1
- 日期：2026-07-29
- P0 范围状态：**FROZEN_FOR_IMPLEMENTATION**
- V3 代码状态：尚未开始；必须按 S0、S1 顺序实施
- 冻结清单统计：96 个配置参数 + 4 个任务模板；13 项规划触发；9 项 Full-Replan
  顶层回退条件
- 评审依据：
  - [公共空间技术路线评审](reviews/public_space_technical_route_review_2026-07-29.md)
  - [实现差距审计](reviews/implementation_gap_audit_2026-07-29.md)
  - [文献方法矩阵](reviews/literature_method_matrix_2026-07-29.md)
  - [二次评审采纳决策](reviews/secondary_review_adoption_2026-07-29.md)

## 0. 文档权威性与变更控制

本文件是医院公共空间研究主线的 P0 唯一冻结依据。V3.0.1 已完成实施前的小型逻辑修订，
因此本文定义的 P0 研究问题、角色、状态、接口、参数名、安全硬约束、验收指标与 S0/S1
顺序从 2026-07-29 起正式冻结。后续如有冲突，以本文件为准。

V3.0.1 相比 V3.0 只修正 LocalRepair 小任务集判据、公平单机器人基线、事件确认安全前提、
HOLD_SAFE 物理停止、目标归一化、实验统计层级、两项规划消融和文档统计；研究场景、P0
边界、接口架构以及 S0→S8 顺序不变。

`graduation_research_plan_v2.md` 不删除、不覆盖，继续承担 house 场景回归基线。V3 新资产
必须使用独立名称和目录，不得覆盖：

- house world、地图和 waypoint；
- `configs/planner_graduation_v2*.yaml`；
- v2 benchmark、报告和演示结果；
- 用户本地数据、模型、输出和未提交资产。

变更等级：

| 等级 | 示例 | 规则 |
|---|---|---|
| 参数校准 | validation 上调整感知阈值、阻塞迟滞时间 | S0/S2 记录旧值、新值、依据和配置 hash，不改变研究问题 |
| P0 接口变更 | 删除 revision、改变安全区含义、改变任务 DAG | 必须先修改本文件并重新评审 |
| 范围扩张 | R3、Tiny Transformer、RTAB-Map 主链、PlanSys2 | 只能进入 P1/P2，不得挤占 P0 |
| 安全边界放宽 | 缩小核心区、允许机器人进入核心区 | 必须重新做全部安全实验，不允许静默修改 |

本文的数值是**工程仿真与研究实验初始值，不是临床处置标准**。deadline 和安全距离必须
在正式 test 前冻结，不得根据最终结果反向调整。

## 1. 研究定位

### 1.1 研究场景

场景冻结为：

> 医院门诊大厅—候诊区—连接走廊中，由巡检机器人视觉发现跌倒事件后触发的双机器人
> 协同核验、持续监护和急救物资取送。

P0 只有两台机器人：

| 机器人 | P0 角色 | 传感器/能力 | 事件确认后的硬职责 |
|---|---|---|---|
| R1 | `patrol_verifier` | Orbbec Gemini 336L、camera、move、patrol、verify | 到核验服务点并持续留场，直至交付完成或事件明确关闭 |
| R2 | `courier` | move、carry | 到物资点 pickup，再到交付服务点 deliver |

事件只由 R1 移动视觉产生。固定摄像头、跨摄像头 ReID 和 R3 人群疏导不进入 P0。

### 1.2 核心研究问题

1. 如何把有遮挡、深度缺失和分类波动的视觉证据转换为稳定、带 3D 位置协方差和版本号
   的规划事件？
2. 如何由事件位置不确定性生成对所有机器人强制生效的核心安全区，以及边界外、角色相关
   且 Nav2 可达的服务点？
3. 如何把短时行人避障与持续通道阻塞分层，并让后者通过世界版本触发任务级修复？
4. 如何在保持已完成、执行中和未受影响任务稳定的前提下，只修复受影响任务，并在局部
   不可行时可靠回退 Full-Replan？
5. 如何用持续留场和异地取送的任务语义，而不是事后收紧期限，证明双机器人不可被单机
   串行等价替代？

### 1.3 核心方法与假设

方法名称暂定为：

> **面向不确定视觉事件的三维语义落点与版本驱动的多机器人局部任务修复方法**

研究假设：

- H1：四态稳定机 + EventEpisode 相比单阈值减少 false task、重复 episode 和 plan churn；
- H2：Robust RGB-D 相比区域中心、2D 地面投影和单点深度，提高区域判断与服务点有效率，
  并降低路径和安全距离违规；
- H3：在相同安全、能力、期限和资源硬约束下，LocalRepair 相比 Full-Replan 减少计划
  修改，且不降低任务成功率；
- H4：`verify_and_monitor` 与 `pickup_and_deliver` 的并发语义使单机器人结构性不可行，
  两机器人可行。

### 1.4 明确不做

P0 不包含：

- 第三台引导机器人；
- Tiny Transformer、ST-GCN；
- RTAB-Map 作为定位主链或完整稠密 3D 地图；
- Hydra、Khronos、HOV-SG；
- PlanSys2 正式接入；
- 固定监控摄像头、跨摄像头 ReID；
- 自动语义区域分割、开放词汇导航；
- 通用人群轨迹预测和真实人群疏散；
- 机械臂真实取物。

## 2. P0 系统边界与数据流

### 2.1 P0 数据流

```text
R1 Orbbec RGB + aligned depth + CameraInfo + source stamp
  -> YOLO11 Pose track
  -> 32-frame LSTM + observation quality
  -> four-state semantic event
  -> EventEpisode
  -> Robust RGB-D person center + covariance in map
  -> dynamic core keepout + role service points
  -> Event-to-Task DAG
  -> sequence MILP
  -> Nav2 execution
  -> execution / path / edge feedback
  -> world_revision
  -> LocalRepair
  -> Full-Replan fallback when required
```

### 2.2 地图与 TF

- P0 使用已知 2D 栅格地图、AMCL 和 Nav2；
- 每台机器人拥有独立命名空间 `/r1`、`/r2`；
- TF 使用 `r1/odom`、`r1/base_link`、`r1/camera_link` 等前缀；
- AMCL 是 P0 唯一 `map→<robot>/odom` 发布者；
- RTAB-Map 不得与 AMCL 同时发布同一 TF；
- 人体地图坐标只依赖 aligned depth、CameraInfo、相机外参和机器人地图位姿；
- 所有几何计算使用原始 Image `header.stamp`，禁止使用推理完成时刻替代。

### 2.3 四层轻量世界模型

| 层 | P0 内容 | 规划消费 |
|---|---|---|
| L1 2D 导航 | map、AMCL、Nav2 costmap、路径长度/时间 | 路径代价、可达性、执行 |
| L2 局部 3D | 人体中心、地面点、协方差 | 区域、安全区、服务点 |
| L3 语义图 | 人工多边形、拓扑边、护士站、物资点、充电点 | 任务位置、通道资源 |
| L4 动态层 | event、zone、service point、edge state、robot state、TTL/revision | DAG、MILP、LocalRepair |

## 3. 冻结参数总表

本节参数应在 S0 写入计划中的 `configs/public_space_v3.yaml`。正式 test 开始后参数只能通过
变更记录修改。

### 3.1 感知与状态参数

| 参数 | P0 初始值 | 单位 | 来源/说明 |
|---|---:|---|---|
| `pose_mode` | `track` | — | P0 必须提供 track ID |
| `pose_input_hz` | 10 | Hz | 仿真/回放目标输入频率 |
| `seq_len` | 32 | frame | 继承当前 LSTM |
| `keypoint_conf_threshold` | 0.30 | probability | 继承当前配置 |
| `theta_low` | 0.45 | probability | 继承 v2 |
| `theta_high` | 0.75 | probability | 继承 v2 |
| `quality_min` | 0.55 | score | 继承 v2；低于该值进入 degraded |
| `visible_keypoint_threshold` | 6 | count | 继承 v2 |
| `min_confirm_windows` | 2 | window | 连续确认门槛 |
| `min_clear_windows` | 2 | window | 候选清除门槛；不得自动关闭已确认 episode |
| `hold_windows` | 3 | window | confirmed 最小保持 |
| `cooldown_windows` | 2 | window | 关闭后的重复触发冷却 |
| `event_dedup_time_sec` | 10.0 | s | 同一 track/邻近事件去重窗口 |
| `event_dedup_distance_m` | 1.0 | m | 无可靠 track 时的空间去重门槛 |
| `candidate_ttl_sec` | 15.0 | s | 未确认候选超时 |
| `event_pose_stale_sec` | 2.0 | s | 超过后位置标记 stale 并膨胀协方差 |
| `event_pose_expire_sec` | 5.0 | s | 超过后停止新派发并触发 reobserve |
| `perception_debounce_sec` | 0.30 | s | 合并同一状态突发更新 |

状态判定初始逻辑：

```text
quality < 0.55
  -> perception_degraded

quality >= 0.55 and score >= 0.75 for 2 windows
  -> event_confirmed

quality >= 0.55 and 0.45 < score < 0.75
  -> event_uncertain

quality >= 0.55 and score <= 0.45 for 2 windows
  -> normal/candidate_clear
```

已确认 episode 不因模型短时回到 normal 自动关闭，只能由 `verify_no_fall`、明确
`scene_clear`、人工 supervisor close 或超时升级策略关闭。

### 3.2 RGB-D 与 TF 参数

| 参数 | P0 初始值 | 单位 | 说明 |
|---|---:|---|---|
| `rgb_depth_sync_slop_sec` | 0.05 | s | RGB 与对齐深度最大时间差 |
| `max_source_age_sec` | 0.20 | s | 在线处理允许的源帧年龄 |
| `tf_lookup_timeout_sec` | 0.10 | s | 原图时间戳 TF 查询超时 |
| `depth_min_m` | 0.30 | m | 有效深度下限 |
| `depth_max_m` | 8.00 | m | P0 有效深度上限，S2 台架可收紧 |
| `depth_window_radius_px` | 2 | pixel | 每关键点使用 5×5 窗口 |
| `depth_window_min_samples` | 5 | sample | 有效深度最小数量 |
| `depth_mad_scale` | 3.0 | MAD | 局部深度异常剔除 |
| `stable_keypoints` | `[5,6,11,12]` | COCO index | 左右肩与左右髋 |
| `min_valid_stable_keypoints` | 2 | count | 少于该值不发布有效 3D 位置 |
| `position_std_floor_m` | 0.05 | m | 平面位置标准差下限 |
| `position_std_max_m` | 0.50 | m | 超过后位置无效，触发 reobserve |
| `stale_std_growth_mps` | 0.05 | m/s | stale 期间不确定性增长 |
| `ground_plane_z_m` | 0.00 | m | 仿真 map 地面高度 |
| `localization_publish_hz` | 5.0 | Hz | 3D 事件最大发布率 |

鲁棒落点步骤冻结为：

1. 选择可见的肩/髋关键点；
2. 读取对齐深度小窗口；
3. 删除零值、越界和 MAD 异常；
4. 使用 CameraInfo 反投影；
5. 按关键点置信度和深度离散度加权聚合；
6. 在 source stamp 查询 TF 转换到 `map`；
7. 投影到地面；
8. 输出 `PoseWithCovariance`；失败时输出原因码并生成 `reobserve`。

平面协方差至少包含：

```text
Σ_xy =
  Σ_keypoint / n_eff
  + J_depth * σ_depth² * J_depth^T
  + σ_tf² * I
```

若误差无法可靠建模，必须增大协方差或输出 invalid，不得发布零协方差。

### 3.3 Nav2 与机器人安全参数

| 参数 | P0 初始值 | 单位 | 来源/说明 |
|---|---:|---|---|
| `robot_radius_m` | 0.175 | m | 继承当前 TurtleBot4 配置 |
| `inflation_radius_m` | 0.45 | m | 继承当前 Nav2 配置 |
| `max_linear_speed_mps` | 0.22 | m/s | 继承当前 Nav2 配置 |
| `max_angular_speed_rps` | 0.90 | rad/s | 继承当前 Nav2 配置 |
| `xy_goal_tolerance_m` | 0.25 | m | 继承当前 Nav2 配置 |
| `yaw_goal_tolerance_rad` | 0.25 | rad | 继承当前 Nav2 配置 |
| `min_robot_center_distance_m` | 0.60 | m | 仿真双机器人安全下限 |
| `collision_distance_m` | 0.35 | m | 两倍机器人半径；低于即碰撞 |
| `min_single_passage_width_m` | 0.80 | m | 继承空间状态门槛 |
| `corridor_capacity` | 1 | robot | P0 窄走廊资源容量 |
| `keepout_apply_timeout_sec` | 2.0 | s | 等待所有活动机器人应用 zone revision |
| `keepout_update_p95_target_sec` | 0.50 | s | 仿真验收目标 |
| `safe_stop_timeout_sec` | 0.50 | s | cancel ack 后速度降到停止阈值的最大时间 |
| `hold_cancel_issue_timeout_sec` | 0.50 | s | 收到 HOLD_SAFE 后发出 Nav2 cancel 的最大时间 |
| `hold_cancel_ack_timeout_sec` | 0.50 | s | HOLD_SAFE 发出 cancel 后等待 Nav2 确认 |
| `hold_linear_speed_threshold_mps` | 0.02 | m/s | 物理停止线速度阈值 |
| `hold_angular_speed_threshold_rps` | 0.05 | rad/s | 物理停止角速度阈值 |
| `event_detection_distance_min_m` | 2.50 | m | P0 场景事件确认时的 R1 观测距离下限 |
| `event_detection_distance_max_m` | 3.00 | m | P0 场景事件确认时的 R1 观测距离上限 |
| `event_confirm_clearance_margin_m` | 0.10 | m | R1 与新核心区边界的额外确认余量 |

### 3.4 动态核心安全区参数

事件平面位置为 `p_e=(x_e,y_e)`，协方差为 `Σ_xy`。核心安全半径：

```text
r_safe =
  clamp(
    r0 + robot_radius_m + k_sigma * sqrt(lambda_max(Σ_xy)),
    r_safe_min_m,
    r_safe_max_m
  )
```

| 参数 | P0 初始值 | 单位 |
|---|---:|---|
| `r0_m` | 0.60 | m |
| `k_sigma` | 2.0 | — |
| `r_safe_min_m` | 0.90 | m |
| `r_safe_max_m` | 2.00 | m |
| `zone_polygon_vertices` | 24 | count |
| `zone_position_update_m` | 0.25 | m |
| `zone_radius_update_m` | 0.10 | m |
| `zone_update_debounce_sec` | 0.50 | s |
| `zone_clear_hold_sec` | 5.0 | s |
| `service_standoff_m` | 0.50 | m |

规则：

- 核心区对 R1、R2 都是硬 keepout；
- P0 场景生成器只接受 R1 在 2.50–3.00 m 距离确认事件的样本，并在创建正式 zone 前验证
  `distance(R1,event_center) >= r_safe + xy_goal_tolerance_m +
  event_confirm_clearance_margin_m`；
- 上述确认前提不满足时判为 `SCENARIO_PRECONDITION_FAILED`，不得先创建包住 R1 的
  keepout，也不得将该样本计入方法成功率；P0 不实现“区内安全退出”；
- keepout mask 使用 `map` 坐标，携带 `zone_revision`；
- zone 创建、中心移动超过 0.25 m、半径变化超过 0.10 m、region 变化或撤销时递增
  `world_revision`；
- zone 未被两台活动机器人确认应用前，不发布依赖该 zone 的新计划；
- `event_pose_stale_sec` 后按 `stale_std_growth_mps` 膨胀；
- `event_pose_expire_sec` 后保持现有安全区，停止 R2 新目标派发，并让 R1 reobserve；
- zone 只在 `verify_no_fall`、`scene_clear` 或 supervisor close 后等待 5 s 撤销；
- deliver 完成不自动撤销安全区。

### 3.5 服务点生成参数

候选点位于半径 `r_service = r_safe + service_standoff_m` 的圆周上。

| 参数 | P0 初始值 | 单位 |
|---|---:|---|
| `candidate_angle_step_deg` | 15 | degree |
| `service_candidates_per_ring` | 24 | count |
| `min_static_clearance_m` | 0.35 | m |
| `min_service_pair_distance_m` | 0.75 | m |
| `verifier_view_angle_max_deg` | 30 | degree |
| `max_path_candidates_per_role` | 6 | count |
| `path_query_timeout_sec` | 0.30 | s/candidate |
| `service_generation_timeout_sec` | 4.00 | s/pair |
| `service_radius_retry_step_m` | 0.15 | m |
| `service_radius_retry_count` | 3 | count |
| `service_point_shift_trigger_m` | 0.25 | m |

生成顺序：

1. 在初始圆周以及最多 3 个、每次增加 0.15 m 的外扩圆周上，每 15° 生成候选位姿；
2. 所有候选 yaw 指向事件中心，且目标中心距必须满足
   `distance >= r_safe + xy_goal_tolerance_m + 0.10 m`；
3. 删除落在静态障碍、地图外、核心区或 clearance 小于 0.35 m 的候选；
4. 分别按直线启发式距离保留每个角色最多 6 个候选；
5. 使用 Nav2 `getPath()` 删除 R1/R2 不可达候选，单次查询超时 0.30 s；
6. R1 候选必须满足相机朝向误差不超过 30°；
7. 枚举满足点间距离至少 0.75 m 的可行 `(verifier,courier)` 组合；
8. 选择 `R1 path length + R2 path length` 最小的组合，不先贪心固定 R1；
9. 全部圆周和查询共用 4 s 总预算；超时返回结构化失败，不继续使用旧服务点；
10. 没有有效组合则发布 `SERVICE_POINT_UNAVAILABLE`，保持 keepout，R1 reobserve，R2 hold，
   并触发 LocalRepair/Full-Replan 判定。

P0 不通过人为指定服务点绕过生成失败。人工点只作为 Zone centroid baseline。

### 3.6 持续阻塞与路径缓存参数

| 参数 | P0 初始值 | 单位 |
|---|---:|---|
| `path_probe_hz` | 1.0 | Hz |
| `block_confirm_sec` | 5.0 | s |
| `block_cost_ratio` | 1.80 | ratio |
| `release_confirm_sec` | 10.0 | s |
| `release_cost_ratio` | 1.30 | ratio |
| `edge_state_cooldown_sec` | 10.0 | s |
| `path_cache_ttl_sec` | 5.0 | s |
| `path_start_shift_m` | 0.50 | m |
| `path_goal_shift_m` | 0.25 | m |
| `nav_failure_retry_count` | 2 | count |
| `nav_failure_window_sec` | 10.0 | s |

状态解释：

- 短时动态行人：只进入 Nav2 local costmap，不改变 `world_revision`；
- `TEMPORARY_OCCUPIED`：路径仍存在，但代价比基线连续 5 s 不低于 1.80；
- `BLOCKED`：路径连续 5 s 不存在；
- `FREE`：路径连续 10 s 可达且代价比不高于 1.30；
- 每次状态变化都带 `reason_code`、时间戳和新 `world_revision`；
- 单次路径查询失败不触发 LocalRepair。

路径缓存以下任一条件发生时立即失效：

- map/costmap revision 变化；
- edge/zone/world revision 变化；
- 起点移动超过 0.50 m；
- 目标/服务点移动超过 0.25 m；
- Nav2 连续失败达到 2 次；
- plan revision 变化或缓存超过 5 s。

### 3.7 任务与求解参数

P0 任务模板：

| 任务 | service duration | deadline offset | capability | 说明 |
|---|---:|---:|---|---|
| `reobserve:E` | 10 s | 60 s | camera, move | 只由 R1 执行 |
| `verify_and_monitor:E` | 15 s + hold | start ≤ 60 s | camera, verify | R1 到位后持续到 deliver/close |
| `pickup:E` | 8 s | 90 s | carry, move | R2 在 supply point |
| `deliver:E` | 15 s | 120 s | carry, move | R2 到 courier service point |

deadline 是仿真工程规范。正式实验固定主值 120 s，并对 deliver deadline
`{90,120,150}` s 做敏感性分析。

P0 任务 DAG：

```text
event_confirmed
  ├─> verify_and_monitor:E ───────────────┐
  └─> pickup:E -> deliver:E -> monitor_end:E
                                         └─ requires active monitor until delivery finishes
```

`pickup` 与 `verify_and_monitor` 在 event confirmed 且 zone/service pair 有效后并发释放，
不要求 R1 先结束 monitor；否则会削弱双机器人并发语义。

持续留场硬约束：

```text
robot(verify_and_monitor:E) = R1
robot(pickup:E) = robot(deliver:E) = R2
start_monitor <= start_pickup
end_monitor >= finish_deliver
R1 location = verifier_service_point during monitor interval
```

求解参数：

| 参数 | P0 初始值 |
|---|---:|
| `local_repair_time_limit_sec` | 2.0 |
| `full_replan_time_limit_sec` | 5.0 |
| `mip_gap` | 0.01 |
| `planning_horizon_sec` | 300.0 |
| `replan_debounce_sec` | 0.50 |
| `min_replan_interval_sec` | 1.00 |
| `affected_ratio_full_replan` | 0.60 |
| `affected_ratio_min_remaining_tasks` | 5 |
| `max_local_failures_in_window` | 2 |
| `local_failure_window_sec` | 10.0 |
| `plan_change_start_shift_sec` | 5.0 |

目标函数使用无量纲分量。令 `H=planning_horizon_sec`、`N_task` 为进入本次求解的任务数、
`N_remaining` 为触发时未完成任务数：

```text
Cmax_bar = Cmax / H
L_bar = sum(priority_i * lateness_i) / (N_task * H)
Nchange_bar = N_plan_change / max(1, N_remaining)
Rwait_bar = (resource_wait + detour_time) / H
Erisk_bar = normalized_energy_risk in [0, 1]

min J =
  1.0 * Cmax_bar
  + 4.0 * L_bar
  + 2.5 * Nchange_bar
  + 1.5 * Rwait_bar
  + 3.0 * Erisk_bar
```

一个任务发生以下任一变化时，`N_plan_change` 对该任务计 1 次；同一任务同时发生多项变化
仍只计 1 次，另在日志中记录变化位掩码：

- 机器人重分配；
- 与任一同机器人剩余任务的相对顺序变化；
- verifier/courier 服务点 ID 或位姿变化；
- 计划开始时间偏移严格大于 `plan_change_start_shift_sec=5.0 s`。

已完成任务不计变化；安全覆盖造成的强制取消单独标记 `safety_override=true`，在安全统计
中报告，但不把它伪装成优化器的无意义震荡。

安全区、能力、持续留场、pickup-deliver 同机器人、前驱、电量下限和资源互斥全部是
硬约束，不得用目标权重交换。

## 4. 状态—动作映射

### 4.1 感知/事件到系统动作

| 输入状态 | Episode 操作 | R1 动作 | R2 动作 | Zone/服务点 | 是否触发规划 |
|---|---|---|---|---|---|
| `normal`，无 active episode | 不创建事件 | 继续 patrol | standby/常规任务 | 无 | 否 |
| `event_uncertain`，位置质量有效 | 创建/刷新 candidate，保持同一 ID | `reobserve`，调整视角 | 不派发 | 可发布 debug zone，不进入 keepout | 首次 candidate 可触发 R1 局部任务 |
| `event_uncertain`，位置无效 | 刷新 candidate | 原地/小范围 reobserve | hold | 不创建正式 zone | 否或只更新 R1 |
| `event_confirmed`，3D 有效且确认距离前提通过 | Episode 转 confirmed | 前往 verifier point 并 monitor | pickup + deliver | 创建硬 keepout 和两服务点 | 是，`NEW_CONFIRMED_EVENT` |
| `event_confirmed`，3D 有效但确认距离前提失败 | 保留 confirmed；标记场景无效 | cancel 后物理停止，不进入新 zone | cancel 后物理停止 | 不创建包住 R1 的正式 zone | `HOLD_SAFE`，原因 `SCENARIO_PRECONDITION_FAILED` |
| `event_confirmed`，3D 无效 | 保留 confirmed，位置 pending | reobserve，禁止离场 | hold | 保持旧 zone；无旧 zone 时用最大保守半径临时区 | 是，生成/刷新 reobserve，不派发 deliver |
| `perception_degraded`，无 confirmed episode | 保留 candidate 到 TTL | reobserve/hold | 不派发 | 无正式 zone | 状态首次变化时 |
| `perception_degraded`，已有 confirmed episode | 保持 episode 和旧任务，不新建 ID | 保持 monitor，尝试 reobserve | 已派发任务仅在服务点仍有效时继续，否则安全停止 | 协方差随 stale 时间膨胀 | zone/服务点变化达到阈值时 |
| `verify_no_fall` | 关闭 episode，取消未开始 supply task | 恢复 patrol | 取消未开始任务 | clear hold 5 s 后撤销 | 是，`EVENT_CLOSED` |
| `deliver_completed` | 标记 supply completed | monitor 可结束，等待 scene clear | 退出交付点 | zone 继续存在 | 任务生命周期更新 |
| `scene_clear`/supervisor close | episode completed/closed | 恢复 patrol | 恢复 standby | clear hold 后撤销 | 是 |

`event_confirmed` 但 3D 无效且没有历史 zone 时，临时区中心按以下顺序选择：

1. 有效的 2D ground projection；
2. 当前人工语义区域 centroid；
3. 两者都不存在时不发布几何 zone，直接 `HOLD_SAFE + reobserve`。

使用前两种 fallback 时必须设置 `provisional=true`，半径固定为 `r_safe_max_m=2.0 m`，
且不得派发 R2 deliver 目标。

### 4.2 动态空间与执行反馈到动作

| 输入 | 世界动作 | 规划动作 |
|---|---|---|
| 短时行人 | 只更新 local costmap | 不触发任务重规划 |
| edge `TEMPORARY_OCCUPIED` | edge revision + wait/detour estimate | LocalRepair |
| edge `BLOCKED` | edge revision，相关 route unavailable | LocalRepair；局部不可行则 Full-Replan |
| edge 恢复 `FREE` | edge revision，缓存失效 | LocalRepair，只有收益且不增加 churn 时改计划 |
| zone 创建/移动/膨胀/撤销 | zone revision，等待 keepout apply ack | LocalRepair |
| service point 变化/失效 | service revision，路径缓存失效 | LocalRepair |
| R1 navigation failure | 记录失败；2 次/10 s 后升级 | reobserve/新 verifier point，LocalRepair |
| R2 navigation failure | 记录失败；2 次/10 s 后升级 | 新 courier point/绕行，LocalRepair |
| robot low battery | robot revision | LocalRepair；能力/返航储备仍为硬约束 |
| action failure | task attempt + reason | LocalRepair；verify failure 不关闭 episode |
| 新 world revision 发生在求解中 | 标记结果 stale | 丢弃结果，只求解最新 revision |

## 5. LocalRepair 触发、影响传播与回退

### 5.1 触发类型

冻结触发枚举：

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

只有输入值跨过本文件阈值、任务生命周期变化或 revision 变化时触发。原始模型分数抖动、
单次 Nav2 查询失败和 local costmap 的短时障碍不触发。

### 5.2 受影响任务集合

```text
A(ΔW) =
  tasks_using_changed_resource
  ∪ tasks_whose_selected_or_candidate_route_uses_changed_edge
  ∪ tasks_bound_to_changed_event_zone_or_service_point
  ∪ tasks_assigned_to_changed_robot
  ∪ descendants_in_task_DAG
  ∪ downstream_tasks_in_same_robot_sequence
```

冻结集合：

- completed；
- active non-preemptible；
- R1 active monitor；
- 未受影响 future task 的 robot/start/order；
- 已经获得外部资源且释放会造成安全风险的动作。

安全覆盖规则：若冻结动作与新 keepout 冲突，安全优先。系统先发布 `HOLD_SAFE`，取消危险
导航目标，并把该任务加入 affected set；这不计为错误的计划震荡。

### 5.3 LocalRepair 正常路径

1. 聚合 0.5 s 内 trigger；
2. 捕获 `solve_world_revision`；
3. 计算 affected/frozen 集；
4. 按以下规模与结构判据选择 LocalRepair 或 Full-Replan；
5. 选择 LocalRepair 时，在 2 s、1% gap 下求解；
6. validator 检查所有硬约束、冻结集和 keepout revision；
7. world revision 未变化且 validator 通过才发布；
8. 计划发布记录修改任务、重分配、顺序变化、时间偏移和归一化 objective components。

```text
affected_ratio = |affected_tasks| / max(1, |remaining_tasks|)

if remaining_tasks >= affected_ratio_min_remaining_tasks
   and affected_ratio > affected_ratio_full_replan:
    Full-Replan
elif all_active_robots_affected:
    Full-Replan
elif global_resource_or_safety_structure_changed:
    Full-Replan
else:
    LocalRepair
```

其中：

- `all_active_robots_affected=true`：每台当前 active robot 都至少有一个执行中或剩余任务
  进入 affected set；
- `global_resource_or_safety_structure_changed=true`：共享走廊连通性、全局 map/costmap、
  所有可用服务点或跨机器人共享安全结构发生变化，使原局部边界不再成立；
- 单一 edge、单一 zone 的常规位姿/半径更新，以及只影响一台机器人的导航失败默认不是
  global change；
- `remaining_tasks < 5` 时不使用 affected ratio；小任务集只有触及全部 active robots
  或全局资源/安全结构时才直接 Full-Replan。

### 5.4 Full-Replan 回退条件

出现任一条件必须回退：

- LocalRepair 为 `INFEASIBLE` 或 `ERROR`；
- 2 s 内没有 feasible incumbent；
- validator 任一硬约束失败；
- frozen set 与新安全区冲突且无法安全释放；
- 没有有效服务点对；
- 规模/结构回退成立：`remaining_tasks>=5 && affected_ratio>0.60`，或全部 active robots
  受影响，或全局资源/安全结构变化；
- 10 s 内连续 2 次 LocalRepair 失败；
- robot unavailable 破坏持续留场或 pickup-deliver 能力；
- 多个 edge/zone 同时变化导致局部边界不再可信。

Full-Replan 使用 5 s、1% gap。回退结果仍须通过 validator。

### 5.5 Full-Replan 仍失败

不得发布旧 revision 计划。系统发布：

```text
planner_state = HOLD_SAFE
reason = FULL_REPLAN_INFEASIBLE | NO_SERVICE_POINT | NO_CAPABLE_ROBOT
```

动作：

- R1 保持当前安全 monitor 位姿；
- 对每台存在 active Nav2 goal 的机器人在
  `hold_cancel_issue_timeout_sec=0.50 s` 内发送 cancel；
- 在 `hold_cancel_ack_timeout_sec=0.50 s` 内收到 cancel ack；
- cancel ack 后 `safe_stop_timeout_sec=0.50 s` 内实测
  `|linear_speed|<=0.02 m/s` 且 `|angular_speed|<=0.05 rad/s`；
- R2 仅在已经物理停止且存在经当前 revision 验证的安全等待点时，才允许后续新计划将其
  移到该点；HOLD_SAFE 本身不继续旧导航；
- keepout 保持；
- 未开始动作不派发；
- supervisor/操作者获得结构化原因；
- 新 world revision 到达后允许再次求解。

cancel 未确认、停止超时或速度超过阈值均发布 `HOLD_STOP_FAILED` 并判本次 run 失败。

## 6. P0 逻辑接口冻结

P0 传输层继续允许 `std_msgs/String + JSON`，避免自定义消息阻塞 S0/S1；但下列 schema、
类型、单位、revision 和原因码冻结。P1 可迁移为 `kaiti_interfaces`，字段语义不得改变。

统一规则：

- 几何 frame 固定为 `map`；
- 时间使用 ROS source stamp，JSON 表示为 `stamp_ns: int64`；
- revision 使用非负 `uint64` 语义；
- JSON 禁止 NaN/Inf；
- 所有状态使用本文枚举；
- producer 每次只发布完整 object，不发 partial patch；
- consumer 必须拒绝比当前 revision 旧的消息。

### 6.1 Topic 总表

| Topic | 逻辑消息 | Producer | Consumer | QoS |
|---|---|---|---|---|
| `/perception/semantic_event_3d` | `SemanticEvent3D` | R1 event localizer | WorldState、RViz/logger | reliable, depth 10 |
| `/world/dynamic_zone` | `DynamicZone` | zone manager | R1/R2 keepout adapter、planner | reliable + transient local, depth 1 |
| `/world/role_service_points` | `RoleServicePointArray` | service point generator | planner、RViz/logger | reliable + transient local, depth 1 |
| `/world/semantic_edge_state` | `SemanticEdgeState` | edge monitor | WorldState、planner | reliable, depth 10 |
| `/world/zone_apply_ack` | `ZoneApplyAck` | 每机器人 keepout adapter | zone manager、planner | reliable, depth 10 |
| `/planning/trigger` | `PlanningTrigger` | WorldState | planner | reliable, depth 20 |
| `/planning/plan` | `TaskPlan` | MILP planner | executor、logger | reliable + transient local, depth 1 |
| `/planning/execution_feedback` | `ExecutionFeedback` | executor/Nav2 adapter | WorldState、planner | reliable, depth 20 |
| `/planning/repair_status` | `RepairStatus` | planner | logger/supervisor | reliable, depth 20 |
| `/planning/hold_safe` | `HoldSafeCommand` | planner/safety supervisor | R1/R2 executor | reliable + transient local, depth 1 |
| `/execution/safety_stop_status` | `SafetyStopStatus` | R1/R2 executor | planner/safety supervisor/logger | reliable, depth 20 |

### 6.2 `SemanticEvent3D`

| 字段 | 类型 | 单位/枚举 | 必填 |
|---|---|---|---|
| `stamp_ns` | int64 | source ROS time | 是 |
| `frame_id` | string | `map` | 是 |
| `event_id` | string | stable episode ID | 是 |
| `track_id` | string | tracker ID，可空 | 是 |
| `event_type` | string | `fall` | 是 |
| `semantic_state` | string | normal/event_uncertain/event_confirmed/perception_degraded | 是 |
| `confidence` | float32 | [0,1] | 是 |
| `observation_quality` | float32 | [0,1] | 是 |
| `pose_valid` | bool | — | 是 |
| `position` | float64[3] | m, map | pose_valid 时 |
| `covariance` | float64[36] | m²/rad² | pose_valid 时 |
| `observer_robot_id` | string | P0 固定 `R1` | 是 |
| `observer_pose_map` | float64[3] | x/y/yaw，source stamp | confirmed 时 |
| `observation_distance_m` | float32 | observer 到 event center 平面距离 | confirmed 且 pose_valid 时 |
| `region_id` | string | semantic polygon ID | 是 |
| `region_probability` | float32 | [0,1] | 是 |
| `valid_until_ns` | int64 | ROS time | 是 |
| `perception_revision` | uint64 | monotonic | 是 |
| `reason_code` | string | snake_case | 是 |

拒绝条件：stamp 过期、TF 无效、协方差缺失、revision 倒退、confirmed 但 event ID 为空。

### 6.3 `DynamicZone`

| 字段 | 类型 | 说明 |
|---|---|---|
| `stamp_ns/frame_id` | int64/string | source time，`map` |
| `zone_id/event_id` | string/string | `zone:{event_id}` |
| `center_xy` | float64[2] | m |
| `covariance_xy` | float64[4] | m² |
| `safe_radius` | float32 | m |
| `polygon_xy` | float64[][2] | 24 顶点 |
| `hard_keepout` | bool | P0 固定 true |
| `provisional` | bool | 2D/region fallback 时为 true |
| `zone_revision` | uint64 | monotonic |
| `source_perception_revision` | uint64 | 对应事件版本 |
| `valid_until_ns` | int64 | stale 管理 |
| `lifecycle` | string | active/clearing/cleared |
| `reason_code` | string | created/moved/inflated/cleared/stale |

### 6.4 `RoleServicePointArray`

数组顶层必须包含：

```text
event_id
pair_valid
generation_status = SUCCESS | TIMEOUT | UNREACHABLE | CLEARANCE_FAILED
generation_runtime_sec
zone_revision
service_revision
failure_reason
points[]
```

每个 service point 包含：

```text
service_point_id
event_id
role = verifier | courier
pose_map = (x, y, yaw)
clearance_m
path_exists
path_length_m
estimated_time_sec
zone_revision
service_revision
valid_until_ns
reason_code
```

必须同时发布 verifier/courier 点；任何一点无效时，整组 `pair_valid=false`。

### 6.5 `SemanticEdgeState`

```text
edge_id
from_region / to_region
state = FREE | TEMPORARY_OCCUPIED | BLOCKED
path_exists
path_length_m
baseline_length_m
cost_ratio
state_since_ns
valid_until_ns
edge_revision
reason_code
```

### 6.6 `ZoneApplyAck`

```text
robot_id
zone_id
zone_revision
applied = true | false
applied_at_ns
reason_code
```

planner 只有收到 R1、R2 对当前 `zone_revision` 的 `applied=true` 后才允许发布依赖该 zone
的新计划；2 s 超时进入 `HOLD_SAFE`。

### 6.7 `PlanningTrigger`

```text
stamp_ns
trigger_type
changed_entity_ids[]
world_revision
source_revision
reason_code
```

### 6.8 `TaskPlan`

```text
planner_instance_id
plan_id
plan_revision
source_world_revision
source_zone_revision
generated_at_ns
valid_from_ns
plan_epoch_ns
solver_status
plan_kind = INITIAL | LOCAL_REPAIR | FULL_REPLAN_FALLBACK
assignments[]
resource_reservations[]
affected_tasks[]
frozen_tasks[]
objective_components = {
  Cmax_bar, L_bar, Nchange_bar, Rwait_bar, Erisk_bar,
  raw_values, normalization_denominators
}
runtime_sec
mip_gap
validator_passed
```

每个 assignment 至少包含：

```text
robot_id
task_id
event_id
task_type
target_pose_map
start_offset_sec / finish_offset_sec
deadline_ns
predecessors[]
resources[]
required_zone_revision
```

### 6.9 `ExecutionFeedback`

```text
stamp_ns
robot_id
plan_id / plan_revision / source_world_revision
task_id / attempt
state = ACCEPTED | EXECUTING | COMPLETED | FAILED | CANCELED | HOLDING
failure_class = NONE | NAVIGATION | ACTION | SAFETY | TIMEOUT | STALE_PLAN
actual_pose_map
nav2_error_code
reason_code
```

旧 plan/world revision 的反馈只进入日志，不得覆盖当前 episode 或完成新计划任务。

### 6.10 `RepairStatus`

```text
stamp_ns
trigger_type
solved_world_revision
selected_kind
affected_tasks[]
frozen_tasks[]
remaining_task_count
affected_task_count
affected_ratio
affected_ratio_gate_applied
all_active_robots_affected
global_resource_or_safety_structure_changed
local_solver_status
full_solver_status
fallback_used
fallback_reason
local_changes / full_changes
change_records[] = {task_id, change_flags[]}
runtime_sec
validator_passed
published
reason_code
```

### 6.11 `HoldSafeCommand` 与 `SafetyStopStatus`

`HoldSafeCommand`：

```text
stamp_ns
command_id
world_revision
plan_revision
target_robot_ids[]
cancel_active_nav = true
dispatch_lock = true
reason_code
```

`SafetyStopStatus`：

```text
stamp_ns
command_id
robot_id
world_revision
command_received_at_ns
cancel_requested_at_ns
cancel_acknowledged
cancel_ack_at_ns
active_nav_goal
linear_speed_mps
angular_speed_rps
dispatch_locked
state = CANCELING | DECELERATING | STOPPED | FAILED
reason_code
```

每台目标机器人只有同时满足以下条件才可报告 `STOPPED`：

```text
cancel_acknowledged = true
active_nav_goal = false
abs(linear_speed_mps) <= hold_linear_speed_threshold_mps
abs(angular_speed_rps) <= hold_angular_speed_threshold_rps
dispatch_locked = true
```

`command_id` 用于关联 cancel、ack 和速度记录；旧 command/revision 的 `STOPPED` 不得解除
当前 dispatch lock。只有 supervisor 或更新 revision 上通过 validator 的新计划可以解锁。
executor 以收到 `HoldSafeCommand` 的时间为起点校验 cancel issue timeout，并以
`cancel_requested_at_ns` 为起点校验 cancel ack timeout。

## 7. 仿真安全边界

### 7.1 环境边界

- 单层医院简化世界；
- 至少包含候诊区、连接走廊、护士站、物资点、等待点和两个机器人起点；
- 窄走廊可通行宽度不小于 0.80 m，并建模为容量 1；
- 动态行人不得瞬移到机器人 footprint 内；
- P0 不模拟真实人群疏导，只用行人产生 local obstacle 或持续 edge blockage；
- world、map、semantic polygon 使用同一坐标原点和版本 manifest。

### 7.2 硬安全规则

以下任一情况均判本次 run 失败：

1. 机器人中心进入当前 `r_safe`；
2. 任意机器人中心距离小于 0.35 m；
3. 非计划共享走廊占用重叠；
4. plan 依赖的 zone revision 尚未 ack 就派发；
5. stale plan 被执行；
6. Full-Replan 不可行后仍继续旧导航；
7. TF 不可用时发布零协方差 3D 事件；
8. R1 在 deliver 完成前离开 verifier service point 容差范围；
9. R2 进入核心安全区；
10. 事件确认时 R1 不满足
    `distance >= r_safe + xy_goal_tolerance_m + event_confirm_clearance_margin_m`，但仍创建
    正式 zone 或将其作为有效实验样本；
11. HOLD_SAFE 后仍派发新目标，或超过 0.50 s 才向 active Nav2 goal 发送 cancel；
12. cancel 发出后 ack 超过 0.50 s，或 ack 后 0.50 s 内速度没有降到
    `|v|<=0.02 m/s`、`|ω|<=0.05 rad/s`；
13. 未收到符合当前 `command_id/world_revision` 的 `STOPPED` 就解除 dispatch lock。

R1 留场容差：

```text
distance(R1, verifier_service_point) <= xy_goal_tolerance_m
```

### 7.3 安全记录频率

- robot pose 与人/机器人距离：至少 20 Hz；
- zone/ack/revision：事件驱动并完整记录；
- collision/contact：仿真物理引擎原始 topic；
- Nav2 path 与执行结果：每目标一条完整记录；
- 所有 run 输出随机种子、配置 hash、map hash 和 git dirty flag。

## 8. 验收指标

### 8.1 感知与 Episode

| 指标 | P0 门槛 |
|---|---:|
| event-level F1 | 目标 ≥ 0.75；未达不阻断系统闭环，但必须如实报告 |
| confirmed 后重复 episode | ≤ 0.05 / event |
| 相比 single-threshold 的 false task | 至少降低 30% |
| confirmation latency p95 | ≤ 5.0 s（从 32 帧窗口 ready 后计） |
| degraded 后 active episode 丢失 | 0 |
| stale/旧 revision 覆盖当前事件 | 0 |

### 8.2 3D 落点、区域与服务点

| 指标 | P0 门槛 |
|---|---:|
| Robust RGB-D 平面误差 median | ≤ 0.25 m |
| Robust RGB-D 平面误差 p90 | ≤ 0.50 m |
| region accuracy | ≥ 95% |
| 无效深度被错误发布为 valid | 0 |
| 真实误差落入报告的 95% ellipse | ≥ 90% 样本 |
| 有效场景 service pair 生成成功率 | ≥ 95% |
| service point 位于核心区内 | 0 |
| service pair 距离 < 0.75 m | 0 |
| 四种定位 baseline 使用相同样本 | 100% |

### 8.3 动态区与边状态

| 指标 | P0 门槛 |
|---|---:|
| keepout update latency p95 | ≤ 0.50 s |
| 未 ack zone revision 的计划派发 | 0 |
| core-zone penetration | 0 |
| 短时行人误触发任务级修复 | ≤ 1% transient events |
| blocked 确认时间误差 | `block_confirm_sec + 1 s` 内 |
| release 确认时间误差 | `release_confirm_sec + 1 s` 内 |
| 单一阻塞 episode 的 blocked/free 抖动 | ≤ 1 次非预期翻转 |
| 过期 path cache 被使用 | 0 |

### 8.4 规划与 LocalRepair

| 指标 | P0 门槛 |
|---|---:|
| validator 硬约束违规 | 0 |
| stale solver result 发布 | 0 |
| LocalRepair runtime p95 | ≤ 2.2 s |
| Full-Replan runtime p95 | ≤ 5.5 s |
| 可局部修复场景中 LocalRepair plan changes < Full-Replan | ≥ 70% runs |
| LocalRepair 任务成功率 | 不低于 Full-Replan 超过 5 个百分点的差距，即 `LocalRepair ≥ Full-Replan - 5pp` |
| local infeasible 正确 fallback | 100% |
| Full-Replan infeasible 后进入 HOLD_SAFE | 100% |
| HOLD_SAFE cancel 发出 | 100% 在命令后 0.50 s 内 |
| HOLD_SAFE cancel ack | 100% 在 0.50 s 内 |
| HOLD_SAFE 物理停止 | 100% 在 ack 后 0.50 s 内达到速度阈值 |
| HOLD_SAFE 停止失败仍继续执行 | 0 |
| 共享资源冲突 | 0 |
| deadline violation | ≤ 10% runs，并报告敏感性 |

### 8.5 工程验收：20 个固定种子

20 个固定种子只用于 S7 系统闭环、安全和复现门禁，不用于单独支撑 LocalRepair
非劣性或优越性结论。种子清单在 S0 写入 benchmark manifest，覆盖：

- 无扰动；
- 短时行人；
- persistent blocked；
- zone 更新；
- service point 失效；
- R2 navigation failure；
- perception degraded；
- 新 world revision 在求解中到达。

门槛：

| 指标 | P0 门槛 |
|---|---:|
| 端到端成功 | ≥ 18/20 |
| 碰撞 | 0 |
| 人体核心区侵入 | 0 |
| robot-robot 最小中心距离 < 0.60 m | 0 |
| R1 提前离场 | 0 |
| R2 物资按期送达 | ≥ 18/20 |
| 日志、配置和 revision 链完整 | 20/20 |

### 8.6 公平的单机器人基线

单机器人对照使用 `R_single`，不得沿用“只有 R1 能 verify、只有 R2 能 carry”的角色拆分：

```text
capabilities(R_single) = {camera, verify, carry, move, patrol}
speed/battery/Nav2/controller/map = 双机器人中单台机器人的同一配置
start_monitor <= start_pickup
end_monitor >= finish_deliver
location(R_single) = verifier_service_point during monitor interval
remote_camera_substitution = false
```

对照方法使用同一事件位置、服务点候选、任务时长、deadline、障碍序列和随机种子。单机器人
允许执行全部任务类型，但同一物理机器人不能在 monitor interval 内离开 verifier point
前往异地 supply/delivery point。若因此不可行，结论是持续监护与异地取送的并发占位语义
造成结构性不可行，而不是能力名称或 R1/R2 硬编码造成。

双机器人主实验仍可把 R1 固定为 verifier、R2 固定为 courier；单机公平性分析必须使用
上述能力完备模型，并同时报告去掉持续监护约束后的可行性 sanity check。若去掉持续监护
后仍不可行，应先检查场景或求解器，不得用于论证双机器人必要性。

### 8.7 正式论文实验与统计

正式论文方法结论与 20-seed 工程门禁分开。对每个主要扰动类型、每个对照方法使用至少
30 个相同的配对随机种子；若资源受限可降至 20 个，但必须报告统计功效限制，不得只报告
百分点。

主要扰动至少包括：

- persistent blocked；
- zone/service point 更新；
- navigation failure；
- perception degraded 或求解中 world revision 更新。

比较方法：

1. `Full-Replan`；
2. `LocalRepair`；
3. `Nav2-only/No-Repair`：任务计划固定，任务层不修复，只允许 Nav2 按相同 retry 配置处理；
4. `LocalRepair without change penalty`：令 `Nchange_bar` 权重为 0，其余约束和权重不变。

所有方法必须使用同一 seed 的事件位置、障碍轨迹、感知输入、初始状态和 deadline，记录
paired success、plan changes、runtime、deadline violation、安全失败和 HOLD_SAFE。报告：

- 配对成功率差及 95% 置信区间；
- plan changes/runtime 的配对差值及 95% bootstrap 置信区间；
- `LocalRepair - Full-Replan >= -5pp` 的非劣性区间判断；
- 二元配对结果使用 McNemar 或配对 bootstrap，不把单次成败等同稳定的 5pp 证据；
- seed 级原始表、排除原因和配置 hash。

### 8.8 方法消融

必须完成：

1. single threshold / hysteresis / four-state / four-state + Episode；
2. Zone centroid / 2D ground projection / Single-depth / Robust RGB-D；
3. 公平的能力完备单机器人 / 两机器人；
4. Nav2-only/No-Repair / Full-Replan / LocalRepair；
5. LocalRepair without change penalty / 完整 LocalRepair；
6. 只有任务授权 / 共享导航 keepout；
7. deliver deadline 90/120/150 s 敏感性。

## 9. P0 阶段与顺序门禁

正常工期 10–14 周，包含约 2 周缓冲。稳定真实双机器人实验可能超过 14 周，不作为 P0
仿真冻结门槛。

### S0：V3 配置与测试协议固化

目标：把本文件转为机器可读配置、schema 和测试向量，不实现新算法。

必须交付：

- `configs/public_space_v3.yaml`；
- `configs/public_space_regions_v3.yaml`；
- 新逻辑消息 JSON schema 或等价 dataclass validator；
- 状态—动作表的表驱动测试向量；
- zone/service point/edge/repair 参数 hash；
- 仿真安全规则检查器接口；
- P0 benchmark manifest 模板。

S0 门禁：

- 本文所有 P0 参数在配置中一一对应，无未解释 magic number；
- 96 个配置参数与 4 个任务模板分别进入配置/schema，不把任务模板误计为参数；
- 所有枚举和 reason code 可被 schema 拒绝/接受测试覆盖；
- 13 项规划触发与 9 项 Full-Replan 顶层回退条件逐项有正反测试；
- 小任务集回退、公平单机基线、事件确认距离前提和 HOLD_SAFE cancel/ack/速度状态均有
  可执行测试向量；
- 关键状态映射至少覆盖 12 个正例和 12 个反例；
- 配置、schema、测试向量本地链接和 hash 完整；
- 不修改或覆盖 v2/house 配置；
- 用户确认 S0 diff 后才能进入 S1。

### S1：现有基线收口

目标：在增加医院算法前，确保时间戳、单车连续执行和 Nav2 路径代价接口可靠。

实施顺序：

1. 保留原始 Image stamp、frame_id、处理时刻与处理延迟；
2. 完成单机器人 `A→B→C→D→S` 连续 NavigateToPose；
3. 完成 Nav2 path-cost adapter；
4. 输出 path exists、length、estimated time、source map/costmap revision 和 reason；
5. 保持 v2 planning/LocalRepair regression；
6. 为 V3 新 topic 建立空实现/schema smoke，不接 Orbbec。

S1 门槛：

| 门槛 | 要求 |
|---|---|
| Python regression | 不低于当前基线 37 passed |
| ROS2 regression | 不低于当前基线 4 passed，0 failures |
| v2 planning smoke | `passed: true` |
| dynamic repair matrix | 5 类场景全部通过 |
| 连续 NavigateToPose | `A→B→C→D→S` 连续 3 次成功 |
| named-pair getPath | 100% 返回结构化结果；可达 pair 长度 > 0 |
| path adapter runtime p95 | ≤ 1.0 s |
| source stamp 贯通 | 100% ros_image record 含 source stamp/frame_id |
| 过期/空路径 | 100% 返回结构化 reason，不静默用 YAML 旧值 |
| house 资产 | hash 不被覆盖 |

S1 未通过时不得开始 Orbbec、医院世界或双机器人并行开发。

### S2：Orbbec 与时间同步台架

- 驱动、D2C、CameraInfo、外参、TF；
- 静态标志点近/中/远误差；
- RGB-depth sync 与 source stamp；
- 通过 3.2 参数和接口门禁。

### S3：Robust RGB-D 与语义区域

- 四种定位方法；
- map 地面点与协方差；
- 人工语义多边形；
- region accuracy 与 calibration 报告。

### S4：安全区与服务点

- DynamicZone；
- shared keepout 与 ack；
- RoleServicePointArray；
- 安全边界检查器。

### S5：动态边与路径缓存

- edge 状态迟滞；
- path-cost cache；
- transient vs persistent 数据流；
- world revision。

### S6：在线 LocalRepair

- ROS planner 调用真实 `repair_after_disturbance`；
- affected/frozen 集；
- validator；
- Full-Replan/HOLD_SAFE 回退；
- RepairStatus。

### S7：双机器人仿真

- `/r1`、`/r2` AMCL/Nav2/TF；
- R1 patrol-verifier；
- R2 courier；
- 20 个固定工程门禁种子和安全边界。

### S8：感知、规划与跨层实验

- P0 感知对比；
- 3D baseline；
- LocalRepair 消融；
- deadline 敏感性；
- 论文图表、失败案例和复现 manifest。

## 10. 计划代码与配置位置

以下是冻结的责任边界，不代表本轮已经创建实现：

| 位置 | P0 责任 |
|---|---|
| `src/yolopose/pipeline/runner.py` | source stamp/frame metadata |
| `ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py` | ROS Image header 贯通 |
| `ros2_ws/src/yolopose_ros/yolopose_ros/event_localizer_3d_node.py` | RGB-D、CameraInfo、TF、协方差 |
| `src/kaiti_planning/semantic_map.py` | polygon、region、edge、point-in-polygon |
| `src/kaiti_planning/service_points.py` | zone 与角色服务点生成 |
| `src/kaiti_planning/models.py` | 事件、zone、service/edge/repair 数据结构 |
| `src/kaiti_planning/world_state.py` | 状态—动作、Episode、revision |
| `src/kaiti_planning/sequence_milp.py` | monitor interval、角色、期限、资源 |
| `src/kaiti_planning/dynamic_repair.py` | V3 trigger、影响传播、回退 |
| `ros2_ws/.../dynamic_keepout_node.py` | zone→Nav2 mask 与 ack |
| `ros2_ws/.../semantic_edge_monitor_node.py` | path anomaly→edge revision |
| `ros2_ws/.../milp_planner_node.py` | online LocalRepair 优先 |
| `configs/public_space_v3.yaml` | 本文参数唯一机器可读源 |
| `configs/public_space_regions_v3.yaml` | polygon、edge、service/supply/wait points |
| `ros2_ws/.../public_space_nav2.yaml` | 双机器人 AMCL/Nav2/keepout |
| `tests/` 与 ROS package tests | schema、映射、几何、安全和回归 |

## 11. P1/P2 边界

### P1

- R3 人群引导；
- Tiny Transformer；
- RTAB-Map 点云展示/辅助建图；
- 双事件、3–6 机器人压力测试；
- 自定义 `kaiti_interfaces`；
- 只有确有角色入核心区需求时的 per-robot filter mask。

### P2/P3

- ST-GCN；
- PlanSys2 正式执行；
- 随机任务完成时间；
- Hydra/Khronos/HOV-SG；
- 自动 3D 语义图、开放词汇和通用人群预测。

任何 P1/P2 工作只有在 S7 安全闭环通过后才可启动。

## 12. 预期创新与论文证据

### 12.1 创新点

1. 带观测质量、3D 位置协方差、TTL 和 revision 的规划语义事件；
2. 由视觉位置不确定性驱动的硬安全区与角色服务点生成；
3. 短时局部避障到持续语义边阻塞的时间分层；
4. 基于世界版本、影响传播和冻结计划的最小扰动 LocalRepair；
5. 从感知误差到 false task、无效导航和 plan churn 的跨层评价。

### 12.2 不能使用的创新表述

不得声称：

- 提出了新的 YOLO、LSTM、MILP、Nav2 或 RTAB-Map；
- 已实现 LTLf 任务规划；
- 已实现完整三维动态语义 SLAM；
- 已完成人群疏导；
- 使用了尚未进入 P0 的 PlanSys2、Hydra 或 ST-GCN。

### 12.3 最终交付

- 本研究计划与冻结参数 manifest；
- P0 机器可读配置和 schema；
- 状态—动作与安全边界测试；
- 3D 定位和服务点 benchmark；
- online LocalRepair 与 Full-Replan 对照；
- 双机器人 20-seed 工程门禁日志；
- 每个主要扰动/方法至少 20–30 个配对种子的正式统计、置信区间和 seed 级原始表；
- 感知、3D、规划和跨层消融报告；
- 论文图表、失败案例、演示视频和复现命令。

## 13. 风险与降级

| 风险 | 触发 | P0 降级 |
|---|---|---|
| Orbbec D2C/TF 不稳定 | S2 门禁失败 | 使用录制 RGB-D/仿真真值做 3D 方法，实机只作增强；不伪称实机闭环 |
| 公共空间感知 F1 未达 0.75 | 冻结 test 结果 | 保留 LSTM，如实报告；用 false task/plan churn 跨层证据 |
| 服务点生成率不足 95% | S4 | 扩展地图 clearance/候选半径，但不使用核心区内人工点 |
| shared keepout 延迟超标 | S4 | 降低机器人速度、增大 apply timeout；不取消 ack 门禁 |
| LocalRepair 不稳定 | S6 | 保留 Full-Replan fallback；若计划改动无优势，不声称局部修复贡献 |
| 双机器人 TF/命名空间冲突 | S7 | 不进入 P1；先修复命名空间，不回退成假多机器人单进程演示 |
| 工期不足 | 预计超过 14 周 | 删除全部 P1/P2；保留 S0–S7 和最小消融 |

## 14. P0 冻结声明与下一步

以下 P0 内容现已冻结：

- 医院公共空间场景；
- R1 移动视觉发现/核验/留场，R2 物资取送；
- Rule/LSTM/TCN；
- 已知地图 + AMCL/Nav2；
- Robust RGB-D + 四种定位 baseline；
- DynamicZone + shared keepout + 两个边界外服务点；
- 持续阻塞迟滞和路径缓存；
- MILP + online LocalRepair + Full-Replan/HOLD_SAFE；
- 本文参数名、逻辑接口、安全边界和验收门槛；
- S0→S1→S2… 的顺序门禁。

下一步只启动 S0，不并行启动 S2–S8。S0 完成并由用户检查 diff 后，才进入 S1。

建议首个命令：

```bash
cd /home/yhc/kaiti_yolopose_framework
sed -n '1,280p' docs/research_plan_v3_0_1.md
```
