# Graduation Design Execution Plan v2

本文件由研究方案 v2 的冻结内容派生，是后续实现和验收的执行基线。任何范围变化必须先修改 `graduation_research_plan_v2.md`、重新生成 DOCX/manifest，再更新本文件。

## 1. 当前基线

- 保护分支：`backup/july-house-20260710`
- 正式开发分支：`feat/graduation-v2`
- July house/Nav2 保护提交：`b9f5a2a`
- 审计与复用边界提交：`4087256`
- 仓库外备份：`/home/yhc/kaiti_yolopose_framework_backups/2026-07-10/`

## 2. 顺序化阶段

| 阶段 | 目标 | 必须通过的门禁 |
|---|---|---|
| W1 | 方案同步、region 拆分、测试入口、LTLf spike、blocked 状态 | DOCX sync；历史规划命令退出正常；ROS build/test |
| W2 | WorldState、EventEpisode、动态任务工厂、revision | 事件前无事件任务；重复事件幂等；degraded 保留 episode |
| W3-W4 | arc MILP、同机配送、逐任务电量、资源预约、validator | 正确计划零违规；错误计划反例全部被捕获 |
| W5 | Full-Replan、LocalRepair、五类扰动、LTLf monitor | 过期 revision 不发布；local infeasible 可靠回退 |
| W6 | 独立感知 split、校准、tracker/状态机消融 | manifest/hash/结果可复现；test 不参与开发 |
| W7 | `kaiti_interfaces`、事件驱动 ROS planner、Nav2 path adapter | 无 PlanSys2 时单车任务序列闭环 |
| W8 | 中央 PlanSys2 Executor 与单车 performers | 不调用 PlanSys2 Planner；执行顺序与 MILP 一致 |
| W9-W10 | 3 车 namespaced Nav2、共享资源、批量仿真 | 20 次冻结场景；零资源冲突/碰撞 |
| W11 | 2 车实物 M1/M2，M3 增强 | M2 至少 8/10 端到端成功 |
| W12 | 正式实验、图表、论文、演示 | 一键验收；交付 hash 完整；论文第 3-6 章收口 |

## 3. Week 1 任务

- [x] 仓库外 binary patch、untracked archive 和 SHA256 备份
- [x] July house/Nav2 受控提交
- [x] 审计与复用边界受控提交
- [x] 创建 `feat/graduation-v2`
- [x] 建立 Markdown→DOCX→manifest 生成与同步检查
- [x] 拆分 replay/house region 配置
- [x] 新增 planning smoke 与 pytest 门禁
- [x] blocked resource 结构化结果
- [x] LTLf 独立环境一日 spike

## 4. Week 2 任务

- [x] robot/task/resource/event registry
- [x] `EventEpisode` 与 task lifecycle
- [x] event/world/plan revision
- [x] observe/verify/pickup/deliver 动态任务工厂
- [x] event close、degraded、retry 与幂等规则
- [x] 正式 v2 初始问题不预置事件任务

门禁结果：事件前无事件任务；重复输入不重复创建；degraded 保留 active episode；verify 执行失败不关闭事件。

## 5. Week 3–4 任务

- [x] 虚拟起点/终点与直接后继 arc
- [x] flow/MTZ 子回路消除
- [x] pickup-deliver 同机约束
- [x] 逐任务电量、充电上限与返航储备
- [x] 路径/服务资源预约区间
- [x] planning horizon 自动 Big-M
- [x] 路径相关 wait/change objective
- [x] CBC time limit/gap/status/runtime/bound 输出
- [x] validator 跨车配送、预约重叠和电量反例

门禁结果：正式 v2 demo 为 `OPTIMAL`，solver/validator 零违规；手工跨车配送、资源重叠和电量篡改均被捕获。六月 legacy benchmark 保留原求解路径，不与最终模型结果混写。

## 6. Week 5 任务

- [x] 五类扰动 seed 与受影响任务传播
- [x] completed/active prefix 状态推进
- [x] LocalRepair 与 Full-Replan fallback
- [x] world revision 过期结果丢弃
- [x] LTLf 三值运行时 monitor

门禁结果：五类扰动均产生非空 affected set；persistent blocked 的 local infeasible 进入结构化 fallback；temporary corridor 的选中计划 validator 零违规；过期 revision 不发布。

## 7. 验收命令基线

### Week 7 当前实现状态（运行门禁尚未签字）

- [x] ROS planner 改为 world revision 变化触发，health timer 不再周期重求解；
- [x] plan 增加 planner instance、plan ID、plan/world revision 与有效期；
- [x] executor 拒绝重复/过期 revision，并把执行中到达的新 revision 延迟到完整队列边界；
- [x] 动态 `verify/pickup/deliver:{event_id}` 可直接展开，不依赖静态任务表；
- [x] 完成 step key 防止同一任务步骤被 revision 重复派发；
- [x] 单车 v2 可视化配置、trace recorder 和重复目标机器检查；
- [x] house 门洞、事件区、跌倒标记和 waypoint 的配置对齐；
- [x] 现场发现并记录旧 saved map 的 C/D 覆盖不足；增加 Nav2 waypoint path audit；
- [ ] Gazebo + RViz 现场运行并保存 trace/截图；
- [ ] 重新覆盖 C/D 建图，冻结新 map hash，并通过 A→B/C/D/S path audit；
- [ ] Nav2 path-cost adapter；
- [ ] `kaiti_interfaces` 正式消息替换 `String + JSON`。

在最后三项完成前，W7 总门禁仍标记为未完成。

```bash
.venv/bin/python scripts/check_graduation_plan_sync.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_planning_smoke.py
.venv/bin/python scripts/replay_world_state_case.py
.venv/bin/python scripts/run_sequence_milp_demo.py
.venv/bin/python scripts/run_dynamic_repair_matrix.py
```

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install
colcon test --event-handlers console_direct+
colcon test-result --verbose
```

## 8. 变更控制

- 数据、模型、地图和 outputs 默认不删除；
- 不覆盖未审计的用户修改；
- benchmark 必须记录 commit、dirty flag、配置 hash、数据 manifest hash 和随机种子；
- 正式接口变更必须同步研究方案、接口文档和测试；
- 每个阶段形成一个可回滚提交，不把多个研究阶段混为一个提交。
