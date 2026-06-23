# Chapter 5 Experiment Results Draft

## 1. Chapter Positioning

本章用于验证冻结版毕业设计主线的三项核心能力：

- 动态空间状态向规划层的有效传递
- 时序/资源/电量约束下的 MILP 多机器人分配与重规划能力
- 扰动条件下的最小扰动局部修复能力

为避免实验目标混淆，本章将实验分为两类：

- 主最小实验：验证静态规划、动态重规划和状态接口主链路
- 扩展对比实验：验证 `LocalRepair` 相对 `Full-Replan` 的最小扰动效果

## 2. Experiment Setup

主最小实验配置为 `configs/planner_minimal_experiment.yaml`。场景包含三台机器人 `R1~R3`、五个任务 `T1~T5` 和四类共享资源 `corridor_H`、`charger_D`、`event_zone_B`、`supply_point_S`。其中，`T3` 和 `T4` 为事件相关任务，满足前驱约束 `T3 -> T4`。动态扰动脚本保持冻结版设定，即 `t=30` 触发 `fall_confirmed@B`，`t=45` 使 `corridor_H` 进入 `temporary_occupied`，`t=80` 恢复为 `free`。

为贴近后续 ROS2 接入路径，空间扰动不再通过手写资源事件直接注入，而是通过 `configs/planner_regions.yaml` 与 `configs/planner_spatial_replay.yaml` 将 OccupancyGrid 回放转换为规划器可消费的 `corridor_*` 状态、`available_from` 与 `wait_time` 字段。

扩展局部修复对比实验配置为 `configs/planner_local_repair_comparison.yaml`。该场景在主最小实验基础上增加两个未来常规任务 `T6` 和 `T7`，二者都占用 `supply_point_S`，其目的不是改变主研究问题，而是构造一个“未来任务顺序存在对称自由度”的最小可区分样例，用于观察 `Full-Replan` 是否会改动未受直接扰动的未来任务。

## 3. Static Planning Result

静态阶段比较了 MILP 与三类启发式基线。结果表明，在当前三机器人五任务最小主场景中，`nearest_robot`、`request_response` 与 MILP 都得到 `event_response_start = 38.0`、`makespan = 78.0`、`total_delay = 0.0` 的可行结果，而 `priority_greedy` 虽然将事件任务起始时间提前到 `30.0`，但使整体 `makespan` 增大到 `110.0`。MILP 的目标值为 `108.2`，并且满足走廊、充电位和电量安全约束。

这一结果说明，在小规模静态场景中，MILP 与启发式之间的宏观指标差距尚不明显，因此论文的核心优势不应停留在静态分配本身，而应重点转向动态资源扰动与局部修复阶段。

## 4. Dynamic Replanning Result

动态重规划实验的关键在于验证：空间状态抽象是否能够真正改变规划解，而不是只停留在感知层输出。实验结果显示，`t=30` 的语义确认不会改变既有可行计划；真正引起计划变化的是 `t=45 corridor_H -> temporary_occupied`。回放得到的关键空间状态为 `occupancy_ratio = 0.6667`、`occupancy_ratio_ema = 0.4`、`min_width = 0.5`、`available_from = 65.0`、`wait_time = 20.0`。在此条件下，`T4` 的开始时间由原静态计划中的 `53.0` 延后到 `65.0`，系统 `makespan` 由 `78.0` 增加到 `90.0`。

为了确认该变化确实由资源时间窗触发，而不是其他隐含约束造成，实验进一步输出了任务开始时间分解表。对 `T4` 而言，`resource earliest = 65.0`，`predecessor earliest = 53.0`，`robot sequence earliest = 40.0`，`event zone earliest = 53.0`，最终 `final start = 65.0`。这说明 `T4` 的延后直接由 `corridor_H.available_from = 65.0` 决定，而不是前驱、机器人顺序或事件区互斥决定。

当 `t=80` 走廊恢复为 `free` 时，`T4` 已在 `65.0 -> 90.0` 执行中，因此系统不会主动重新提前该任务。这一行为符合“执行前缀冻结”的工程常识，不应视为缺陷，而应视为规划层与执行层边界的合理体现。

## 5. Local Repair Comparison Result

主最小实验可以验证“动态状态 -> 完整重规划”链路，但不足以稳定区分 `Full-Replan` 与 `LocalRepair`。因此，扩展对比实验被用于验证最小扰动修复能力。该场景中，静态基线计划为：`T3(R2): 40 -> 55`、`T7(R1): 50 -> 75`、`T4(R2): 75 -> 100`、`T6(R1): 100 -> 125`。在 `t=45 corridor_H -> temporary_occupied` 后，系统识别得到 `affected_tasks = [T3, T4, T6]`，`frozen_tasks = [T1, T2, T5, T3, T7]`。

实验结果表明，`Full-Replan` 会把 `T6` 提前到 `50.0 -> 75.0`，并将 `T7` 推迟到 `100.0 -> 125.0`；而 `LocalRepair` 保持 `T7` 不变，仅让 `T6` 留在 `100.0 -> 125.0`。从指标上看，`Full-Replan` 相对静态基线修改了 `2` 个任务，`LocalRepair` 修改了 `0` 个任务，且两者在资源冲突、截止时间和 validator 检查上都保持 `0` 违例。

该结果具有两层意义。第一，它说明仅依靠“冻结已执行前缀”还不足以体现局部修复优势；只有进一步冻结未受影响的未来任务，才能体现最小扰动特性。第二，它验证了当前实现中的 `affected task propagation + frozen prefix + validator` 已形成闭环，即：先从受扰动任务生成种子集合，再沿前驱、同机器人未来链和共享资源未来链进行传播，最后只允许受影响子集在 MILP 中重新调整。

## 6. Validator Result

为避免只看 `makespan` 或任务顺序而忽略可行性，本研究在静态规划、动态重规划和局部修复三个阶段都统一接入 validator。validator 检查的内容包括：任务唯一分配、能力匹配、前驱约束、同机器人任务不重叠、共享资源不冲突、动态资源时间窗、电量安全、事件响应时间和冻结约束。当前主最小实验与扩展对比实验中的关键结果均满足 `is_valid = true`。

这一机制的价值在于，它使“局部修复减少了多少改动”不再只是表面现象，而是建立在可行性未被破坏的前提之上。因此，validator 不只是工程调试工具，也是本章实验结论成立的必要支撑。

## 7. Result Discussion

综合上述结果，可以得出三点结论。首先，研究内容一与研究内容三之间的接口已经被打通：动态 OccupancyGrid 回放可被稳定映射为 `corridor_free / corridor_temporary / corridor_blocked` 等规划状态，并进一步转化为 MILP 中的资源时间窗约束。其次，MILP 规划器在小规模静态场景中未必显著优于启发式，但在动态资源扰动下能够稳定维持前驱、共享资源和电量安全的统一可行性。最后，局部修复的价值不在于“重新算得更快”这一单一口径，而在于“在保持可行性的前提下尽量少改未来计划”，这一点已在扩展对比实验中得到直接验证。

## 8. Suggested Figure References

正文可配套引用以下图表：

- 主最小实验动态重规划：
  - `reports/figures/planning_2026-06-22/dynamic_replan_gantt.svg`
  - `reports/figures/planning_2026-06-22/corridor_H_state_timeline.svg`
  - `reports/figures/planning_2026-06-22/corridor_H_occupancy_curves.svg`
- 扩展局部修复对比实验：
  - `reports/figures/local_repair_comparison_2026-06-23/local_repair_vs_full_replan_gantt.svg`
  - `reports/figures/local_repair_comparison_2026-06-23/local_repair_resource_timeline.svg`

## 9. Suggested Citation Bundle

若第 5 章需要统一引用实现和结果，建议配套引用：

- `docs/milp_model_spec.md`
- `docs/minimal_experiment_spec.md`
- `docs/local_repair_method_note.md`
- `docs/local_repair_figure_captions.md`
- `reports/benchmarks/planner_static_baselines_2026-06-22.md`
- `reports/benchmarks/dynamic_replan_2026-06-22.md`
- `reports/benchmarks/local_repair_comparison_2026-06-23.md`
