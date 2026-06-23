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
