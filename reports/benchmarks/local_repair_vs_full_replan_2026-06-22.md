# Local Repair Vs Full Replan 2026-06-22

## Task Goal

在 `t=45 corridor_H -> temporary_occupied` 的扰动下，对比：

- `Full-Replan`：冻结已执行/在执行前缀，对受影响剩余任务完整重规划
- `LocalRepair`：在上述基础上继续冻结未受影响任务，只重排受影响子集

## Comparison

| Method | Event Response Start | Makespan | Total Delay | Modified Task Count |
|---|---:|---:|---:|---:|
| `Full-Replan` | `38.0` | `90.0` | `0.0` | `1.0` vs baseline |
| `LocalRepair` | `38.0` | `90.0` | `0.0` | `1.0` vs baseline |

额外比较：

- `trigger_source = spatial_replay`
- `trigger_time = 45.0`
- `trigger_resource = corridor_H`
- `trigger_state = temporary_occupied`
- `affected_tasks = [T3, T4]`
- `frozen_tasks = [T1, T2, T5, T3]`
- `local_vs_full.modified_task_count = 0.0`
- `resource_conflict_count = 0.0`
- `deadline_violation_count = 0.0`
- `validator.is_valid = true`

在该最小场景下，`Full-Replan` 与 `LocalRepair` 的输出一致：唯一被修改的任务是 `T4`，其开始时间由 `53.0` 延后到 `65.0`。这是因为除 `T4` 外，剩余任务要么已完成、要么已在执行、要么不存在额外未受影响的未来任务可供冻结。

## Structural Conclusion

- 阶段4链路已打通：`spatial_replay -> trigger_event -> affected_task_set -> frozen_prefix -> validator`
- 当前主场景较小，局部修复与完整重规划在结果上重合，这说明冻结规则和验证逻辑是一致的。
- 若后续扩展到 `4~6` 台机器人或增加并发常规任务，局部修复优势会更明显。
