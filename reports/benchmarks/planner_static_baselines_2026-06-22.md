# Planner Static Baselines 2026-06-22

## Task Goal

在冻结版三机器人最小主场景上，验证静态离线 MILP 与三类基线的可运行性，并记录统一口径下的响应时间与 makespan。

## Results

| Method | Event Response Start | Makespan | Total Delay | Notes |
|---|---:|---:|---:|---|
| `nearest_robot` | `38.0` | `78.0` | `0.0` | 最近机器人可行，但不优于 MILP |
| `priority_greedy` | `30.0` | `110.0` | `0.0` | 高优先级任务更早，但常规任务整体拖后 |
| `request_response` | `38.0` | `78.0` | `0.0` | 与最近机器人结果一致 |
| `milp` | `38.0` | `78.0` | `0.0` | 当前最优解与启发式相同，但目标值可扩展到动态/修复阶段 |

`milp` 当前输出目标值为 `108.2`。在该冻结主场景中，`T1~T5` 全部可行，`corridor_H` 与 `charger_D` 未发生容量冲突，`R3` 充电后满足安全电量。

## Structural Conclusion

- 阶段2最小验收已满足：静态 MILP 与三类基线均可运行。
- 当前主场景规模较小，静态阶段尚未拉开 MILP 与启发式差距；差异主要将在动态资源与局部修复阶段体现。
- `priority_greedy` 虽然能更早触发事件任务，但显著推迟常规任务收尾，不适合作为主方法。
