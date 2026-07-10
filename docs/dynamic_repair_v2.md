# 动态重规划与 LocalRepair v2

`dynamic_repair.py` 在正式 sequence-arc MILP 上实现受影响任务传播、执行前缀冻结和 Full-Replan fallback。

- completed/active prefix 从后续优化问题中移除，并把机器人起点、电量推进到前缀末端；
- resource、robot low-battery、navigation/action failure 和 new semantic event 分别生成 seed；
- seed 沿任务前驱和 incumbent 机器人序列向后传播；
- 未受影响 future task 固定 robot/start，affected task 才允许变化；
- LocalRepair 非可行状态统一选择 Full-Replan；fallback 仍不可行时保留结构化原因；
- `RevisionPlanningCoordinator` 在发布前比较 world revision，过期结果直接丢弃并设置 pending trigger。

运行五类扰动 demo：

```bash
.venv/bin/python scripts/run_dynamic_repair_matrix.py
```

当前脚本用于确定性回归；第 9–10 周批量仿真会冻结随机种子、扰动次数与统计 CSV。
