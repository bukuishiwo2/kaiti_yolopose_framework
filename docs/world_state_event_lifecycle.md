# WorldState 与事件任务生命周期

正式 v2 路线使用 `src/kaiti_planning/world_state.py` 统一维护 robot、resource、task、event registry，以及 world/plan revision。旧的 `planner_minimal_experiment.yaml` 继续用于历史 benchmark；正式事件驱动配置是 `configs/planner_graduation_v2.yaml`。

## 关键规则

- 初始正式问题只有 `T1/T2/T5`，不存在预置 `T3/T4`；
- 首次 uncertain 创建稳定 episode ID 和 `observe:{event_id}`；
- confirmed 通过 track/location 找回同一 episode，取消未开始 observe，幂等创建 `verify:{event_id}`；
- degraded 只更新感知状态，不删除 active episode，也不创建新任务；
- verify 的导航或动作失败会增加 attempt 并回到 `verify_pending`；
- `no_fall` 才关闭事件；确认跌倒后创建 `pickup:{event_id}`、`deliver:{event_id}`；
- event close 时 pending task 直接取消，active task 只设置 `cancel_requested`，由执行层安全停止；
- 重复输入不增加 world revision，只有有效状态变化触发 revision。

## 运行 demo

```bash
.venv/bin/python scripts/replay_world_state_case.py
```

输出 timeline 依次展示：初始问题、uncertain、degraded、confirmed、verify retry、supply task 创建和事件完成。可用以下命令确认正式初始计划不含事件任务：

```bash
.venv/bin/python scripts/run_milp_planner.py \
  --config configs/planner_graduation_v2.yaml
```

当前 WorldState 已完成事件生命周期和规划问题装配；直接后继 arc、pickup-deliver 同机与逐任务电量属于第 3–4 周 MILP 重构，不在本模块重复实现。
