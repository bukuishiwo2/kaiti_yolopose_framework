# Dynamic Replan 2026-06-22

## Task Goal

验证冻结主场景中的三个关键动态时刻：

- `t=30 fall_confirmed@B`
- `t=45 corridor_H -> temporary_occupied`
- `t=80 corridor_H -> free`

并检查四状态语义与空间状态是否能驱动完整重规划。
本次结果基于 `configs/planner_regions.yaml + configs/planner_spatial_replay.yaml` 的 OccupancyGrid 回放，而不是手写资源状态注入。

## Key Observations

- 语义示例已覆盖：
  - `event_uncertain`
  - `event_confirmed`
  - `perception_degraded`
- `t=30` 输出 `event_confirmed / fall_confirmed / FALL_B_001`
- `t=45` 输出 `corridor_temporary`
- `t=80` 输出 `corridor_free`

## Replan Summary

| Time | Trigger | Event Response Start | Makespan | Modified Tasks |
|---|---|---:|---:|---:|
| `0` | initial | `38.0` | `78.0` | `-` |
| `30` | semantic | `38.0` | `78.0` | `0` |
| `45` | resource temporary | `38.0` | `90.0` | `1` |
| `80` | resource free | `65.0` | `90.0` | `0` |

`t=45` 时，回放障碍使 `corridor_H` 被判为 `temporary_occupied`，其状态字段为：

- `occupancy_ratio=0.6667`
- `occupancy_ratio_ema=0.4`
- `min_width=0.5`
- `available_from=65.0`
- `wait_time=20.0`

在该资源扰动下，`T4` 从原计划的 `53.0` 延后到 `65.0`，对应 `makespan` 从 `78.0` 增加到 `90.0`。这满足冻结版方案要求的“动态空间状态 -> 规划层时间窗约束 -> 完整重规划”链路。

对 `T4` 的开始时间分解结果如下：

| Task | Resource Earliest | Predecessor Earliest | Robot Sequence Earliest | Event Zone Earliest | Final Start |
|---|---:|---:|---:|---:|---:|
| `T4@t=45` | `65.0` | `53.0` | `40.0` | `53.0` | `65.0` |

因此，`T4=65.0` 的直接决定因素是 `corridor_H.available_from=65.0`，而不是前驱、机器人序列或事件区互斥。

`t=80` 时，走廊恢复 `corridor_free`，但 `T4` 已经在 `65.0 -> 90.0` 执行中，因此重规划不再产生新的调整。

## Validator

- `initial / t=30 / t=45 / t=80` 的 validator 结果均为 `is_valid = true`
- 约束检查覆盖：
  - 任务唯一分配
  - 能力匹配
  - 前驱约束
  - 同机器人不重叠
  - 共享资源不冲突
  - 动态资源可用时间窗
  - 电量安全
  - 事件响应
  - 冻结前缀约束

## Structural Conclusion

- 阶段3最小链路已成立：语义状态、空间状态和完整重规划之间存在明确 handoff。
- 当前链路已从“手写 resource event”推进到“区域配置 + OccupancyGrid 回放 + 资源状态生成”，更贴近后续接入 `Nav2 costmap` 的落地路径。
- 首帧 OccupancyGrid 现在只用于建立资源基线，不再错误触发 `t=0` 资源重规划。
- 主场景恢复到 `t=80 corridor_free` 后，当前实现不会自动把已在执行的 `T4` 再提前；这是合理的执行前缀冻结行为，不属于本阶段缺陷。
- 配套图表已生成到 `reports/figures/planning_2026-06-22/`，可直接支撑论文中的时序图、曲线图和甘特图。
