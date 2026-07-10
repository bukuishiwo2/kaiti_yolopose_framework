# Graduation Design Implementation Plan

## 1. Goal

本文件将冻结版毕业设计方案转成仓库内可执行实施基线。后续实现必须遵守以下固定主线：

- 空间层只做任务相关区域状态估计，不改 `RTAB-Map` 核心。
- 语义层只做基于现有 `YOLOPose + tracking + LSTM` 的四状态规划语义生成，不重做感知大模型。
- 规划层以 `co-safe LTL/LTLf + 任务前驱图 + MILP + 局部修复` 为核心，`PlanSys2` 只负责动作生命周期，`Nav2` 只负责导航执行。

## 2. Frozen Research Spine

- 研究内容一：将 `RTAB-Map / Nav2 costmap` 转为 `corridor_free`、`corridor_temporary`、`corridor_blocked`、`charger_available`、`region_reachable` 等规划谓词和时间窗。
- 研究内容二：将现有感知输出转为 `normal`、`event_uncertain`、`event_confirmed`、`perception_degraded` 四状态。
- 研究内容三：实现三机器人最小主场景上的静态 MILP、动态事件完整重规划和局部修复。

固定最小主实验：

- 机器人：`R1@A(80%)`、`R2@C(70%)`、`R3@D(35%)`
- 任务：`T1~T5`
- 资源：`corridor_H`、`charger_D`、`event_zone_B`、`supply_point_S`
- 动态脚本：`t=30 fall_confirmed@B`、`t=45 corridor_H temporary`、`t=80 corridor_H free`

## 3. Implementation Stages

### Stage 1

- 冻结文档、MILP 变量命名、接口契约和最小实验 YAML。
- 仅新增文档和配置，不改动现有感知与 ROS2 行为。

### Stage 2

- 实现离线静态 MILP 与三类基线。
- 验证 `T1~T5` 可行性、资源互斥和电量安全。

### Stage 3

- 实现四状态语义生成、空间资源状态生成和动态事件完整重规划。
- 允许以脚本化状态回放替代在线 costmap 作为第一版输入。

### Stage 4

- 实现受影响任务识别、冻结未受影响任务前缀、局部修复和 `Full-Replan` 对比。

### Stage 5

- 在 `ros2_ws` 中新增 `semantic_state`、`spatial_state`、`milp_planner` 和 `execution_feedback` 四类节点。
- 保留现有 `/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status` placeholder 链路。

## 4. Acceptance Baseline

- 阶段1：文档和 `configs/planner_minimal_experiment.yaml` 完整存在。
- 阶段2：`scripts/run_milp_planner.py` 和 `scripts/eval_planner_baselines.py` 可运行。
- 阶段3：`scripts/replay_dynamic_planning_case.py` 可在 `t=30/45/80` 触发完整重规划。
- 阶段4：`scripts/eval_local_repair.py` 可输出 `LocalRepair` 与 `FullReplan` 差异。
- 阶段5：`planning_stack.launch.py` 可发布 `/planning/semantic_state`、`/planning/spatial_state`、`/planning/plan`、`/planning/execution_feedback`。

## 5. Explicit Non-Goals

- 不引入 `TWTL` 作为主线。
- 不把核心求解改成乘积自动机全局搜索。
- 不加入 `Petri Net` 作为第二套正式规划主线。
- 不做完整 `TAMP` 或连续空间多机器人联合运动优化。
- 不新做 SLAM 后端。
- 不新做大型感知网络。
- 不要求 3 台以上实车闭环作为最低毕业目标。

## 6. Reuse Guardrails（防止重复造轮子）

后续实现必须按以下标记执行：

### 6.1 `[必须复用]`

- 人体姿态检测与目标跟踪：复用 Ultralytics Pose 的 `track` 模式和内置 tracker；不自写 Kalman、ReID 或匈牙利匹配框架。
- 建图与定位：复用 `RTAB-Map` 官方 ROS2 包和 TurtleBot4 demo；不修改 SLAM 后端。
- 路径规划与避障：复用 `Nav2` 的 `NavigateToPose / ComputePathToPose` 或 Simple Commander；不自写全局/局部导航器。
- 动作生命周期：复用 `PlanSys2` action performer、controller 和 Nav2 action 示例；PlanSys2 不重新做 MILP 全局分配。
- LTLf 转换：若论文保留可执行自动机，复用 Spot 等成熟 translator；不自写公式解析器和自动机构造算法。
- 数学求解：继续使用 PuLP/CBC（可增加 Gurobi 对照）；不实现自有 MILP 求解器。

### 6.2 `[允许自研/论文贡献]`

- 质量门控四状态语义事件生成；
- 静态地图与动态 costmap 到任务相关资源状态/时间窗的转换；
- 时序、资源、电量、优先级联合约束的多机器人 MILP；
- 事件 ID、影响传播、冻结前缀和最小扰动局部修复；
- 感知稳定性对任务误触发与计划扰动影响的跨层实验。

### 6.3 `[降级或删除]`

- 若没有实际 LTLf parser/automaton/monitor，只能表述为“LTLf 需求规格 + 任务前驱图”，不能声称完成了 LTL 自动机规划。
- 概率校准若没有 ECE/Brier/reliability 实验，应从正式方法中删除“校准后概率”表述。
- 未实现三车 namespace 闭环前，系统实验统一称“单车执行链 + 离线三机器人调度”，不能称为三机器人在线闭环。
- 不把自主探索、新 SLAM、新 tracker、新导航插件、POMDP、TAMP 或多车实物全闭环加入最低毕业目标。

## 7. Mandatory Corrections And Acceptance Notes

### 7.1 能力约束统一

正式文档和代码统一采用：

```text
x_ij = 0, if C_j is not a subset of C_i
```

即任务需求 `C_j` 不是机器人能力 `C_i` 的子集时禁止分配。DOCX 第 8.2 节当前把集合方向写反，必须在下一版修正。

### 7.2 动态事件必须是真插入

`fall_confirmed` 前，事件任务不得作为 `must_complete` 任务预先存在于活动问题中。验收标准：

- 初始计划不含 `verify_fall/deliver_supply`；
- 新 event ID 到达后创建事件任务；
- 相同 event ID 重复输入不重复创建任务；
- `event_closed` 能取消未执行事件任务并恢复巡检。

### 7.3 实验口径

- UR Fall 必须冻结视频级 train/val/test manifest；
- 参与训练、fine-tune、阈值选择的视频不能再作为正式 test；
- 四状态语义方法必须报告误触发、重复事件、状态翻转和触发延迟；
- benchmark 必须记录配置 hash、数据 manifest、随机种子与 Git commit。

### 7.4 当前回归

2026-07-10 审计时，静态 MILP 和三类 baseline 仍通过，但动态 replay 与 local repair 因当前 house region 标定把 `corridor_H` 判为 `blocked` 而失败。必须将冻结 replay region 与 house 实图 region 分文件维护，不能让在线标定破坏历史验收。

完整证据与优先计划见：

- [毕业设计研究方案与仓库现状审计（2026-07-10）](reviews/graduation_plan_repo_audit_2026-07-10.md)
- [成熟技术复用与官方 Demo 运行手册](technology_reuse_demo_runbook.md)
