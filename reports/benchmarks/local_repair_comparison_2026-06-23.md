# Local Repair Comparison 2026-06-23

## Task Goal

在不改变冻结主研究方向的前提下，补一个能稳定区分 `Full-Replan` 与 `LocalRepair` 的最小扩展场景。

本对比使用：

- `configs/planner_local_repair_comparison.yaml`
- `configs/planner_regions.yaml`
- `configs/planner_spatial_replay.yaml`
- `reports/figures/local_repair_comparison_2026-06-23/local_repair_vs_full_replan_gantt.svg`
- `reports/figures/local_repair_comparison_2026-06-23/local_repair_resource_timeline.svg`
- `docs/local_repair_method_note.md`
- `docs/local_repair_figure_captions.md`

触发条件仍保持冻结版主场景：

- `t=30`: `fall_confirmed@B`
- `t=45`: `corridor_H -> temporary_occupied`
- `t=80`: `corridor_H -> free`

## Scenario Change

相对主最小实验，新增两个未来常规任务：

- `T6`: `patrol@A`, `release=50`, `duration=25`, `resources=[supply_point_S]`
- `T7`: `patrol@A`, `release=50`, `duration=25`, `resources=[supply_point_S]`

设计目的不是改变主线，而是制造一个“未受 corridor_H 直接扰动、但在未来调度上存在对称自由度”的局部修复判别样例。

## Static Baseline

静态最优计划：

- `T1(R1): 0 -> 20`
- `T2(R2): 0 -> 20`
- `T5(R3): 0 -> 40`
- `T3(R2): 40 -> 55`
- `T7(R1): 50 -> 75`
- `T4(R2): 75 -> 100`
- `T6(R1): 100 -> 125`

静态 validator：

- `is_valid = true`
- 所有唯一分配、前驱、同机互斥、共享资源、电量和时间窗检查均为 `0` 违例

## Trigger Summary

- `trigger_source: spatial_replay`
- `trigger_time: 45.0`
- `trigger_resource: corridor_H`
- `trigger_state: temporary_occupied`
- `affected_tasks: [T3, T4, T6]`
- `frozen_tasks: [T1, T2, T5, T3, T7]`

这里 `T6` 被纳入受影响集合，不是因为它直接依赖 `corridor_H`，而是因为它位于同一未来调度链上，会受到扰动传播影响；`T7` 则被保留为未受影响未来任务，用于检验局部修复的冻结效果。

## Comparison

| Method | Modified Vs Baseline | Shifted Vs Baseline | Resource Conflict | Deadline Violation | Validator |
|---|---:|---:|---:|---:|---:|
| `Full-Replan` | `2` | `2` | `0` | `0` | `true` |
| `LocalRepair` | `0` | `0` | `0` | `0` | `true` |

`Full-Replan` 输出：

- `T6(R1): 50 -> 75`
- `T4(R2): 75 -> 100`
- `T7(R1): 100 -> 125`

`LocalRepair` 输出：

- `T7(R1): 50 -> 75`
- `T4(R2): 75 -> 100`
- `T6(R1): 100 -> 125`

因此：

- `local_vs_full.modified_task_count = 2`
- `local_vs_full.shifted_task_count = 2`

## Structural Conclusion

- 阶段4现在有了一个可复现实验：`Full-Replan` 会在没有最小扰动约束时改动未受影响未来任务，而 `LocalRepair` 会保留冻结前缀和未受影响子计划。
- 这说明当前 `affected task propagation + frozen prefix + validator` 三件套已经形成闭环。
- 原 `configs/planner_minimal_experiment.yaml` 仍作为主链路验收场景保留；`configs/planner_local_repair_comparison.yaml` 只承担“区分局部修复收益”的角色，不替代主实验。

## Figure

推荐直接查看：

- [Local Repair Vs Full Replan Gantt](../figures/local_repair_comparison_2026-06-23/local_repair_vs_full_replan_gantt.svg)
- [Local Repair Resource Timeline](../figures/local_repair_comparison_2026-06-23/local_repair_resource_timeline.svg)

## Acceptance Command

```bash
python3 scripts/eval_local_repair.py \
  --config configs/planner_local_repair_comparison.yaml \
  --backend pulp \
  --regions configs/planner_regions.yaml \
  --spatial-replay configs/planner_spatial_replay.yaml

python3 scripts/generate_local_repair_comparison_figures.py \
  --config configs/planner_local_repair_comparison.yaml \
  --backend pulp \
  --regions configs/planner_regions.yaml \
  --spatial-replay configs/planner_spatial_replay.yaml
```
