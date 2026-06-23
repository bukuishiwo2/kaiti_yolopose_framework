# Local Repair Method Note

## 1. Purpose

本文档只解释冻结版毕业设计中的局部修复实现边界，不改变研究主线。

局部修复的目标是：

- 在动态空间/语义扰动到来后，不直接重做整张计划
- 先识别受影响任务集合
- 冻结已完成前缀、执行中前缀和未受影响未来任务
- 只对受影响子集做 MILP 重优化

这与开题冻结版中的“最小扰动局部修复”保持一致。

## 2. Input And Trigger

当前实现支持两类触发源：

- `dynamic_script`
- `spatial_replay`

当前主实验和对比实验都使用：

- `trigger_source = spatial_replay`
- `trigger_resource = corridor_H`
- `trigger_state = temporary_occupied`

## 3. Affected Task Rule

受影响任务集合不是只看“是否直接使用受扰动资源”，而是分两步构造：

1. 种子集合

- 资源扰动：直接命中该资源的任务
- 语义扰动：直接命中事件任务

2. 扰动传播

从种子集合出发，沿以下关系做闭包传播：

- 前驱关系：`before -> after`
- 同机器人未来执行链
- 同共享资源未来占用链

这样做的目的，是把“虽然不直接用到 corridor_H，但其排程位置会因受扰动任务移动而变化”的任务也纳入可修复范围。

## 4. Frozen Task Rule

局部修复时冻结三类任务：

- 已完成任务
- 正在执行的任务
- 未受影响的未来任务

其中：

- 已完成和执行中任务用于保证执行前缀一致性
- 未受影响未来任务用于体现“最小扰动”

当局部修复无可行解时，理论上应回退到完整重规划；当前实现已保留 `Full-Replan` 作为对照路径。

## 5. Full-Replan And LocalRepair Difference

`Full-Replan`：

- 冻结已完成/执行中前缀
- 对剩余任务整体重规划

`LocalRepair`：

- 在 `Full-Replan` 的基础上，继续冻结未受影响未来任务
- 只允许受影响子计划调整

因此：

- `Full-Replan` 追求剩余全局最优
- `LocalRepair` 追求可行且改动最小

## 6. Validator Scope

局部修复和完整重规划都统一经过 validator，检查：

- 任务唯一分配
- 能力匹配
- 前驱约束
- 同机器人任务不重叠
- 共享资源不冲突
- 动态资源时间窗约束
- 电量安全
- 事件响应时间
- 冻结约束

## 7. Why The Comparison Case Is Needed

主最小实验 `configs/planner_minimal_experiment.yaml` 足以验证：

- 语义状态
- 空间状态
- 完整重规划

但它通常不足以稳定拉开 `Full-Replan` 与 `LocalRepair` 的差异。

因此增加 `configs/planner_local_repair_comparison.yaml`：

- 保持主触发脚本不变
- 只补少量未来对称任务
- 用于观察 `Full-Replan` 是否会改动未受影响未来任务

这个对比场景只是阶段4验证工具，不替代主实验。
