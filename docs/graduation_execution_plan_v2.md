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
- [ ] 拆分 replay/house region 配置
- [ ] 新增 planning smoke 与 pytest 门禁
- [ ] blocked resource 结构化结果
- [ ] LTLf 独立环境一日 spike

## 4. 验收命令基线

```bash
.venv/bin/python scripts/check_graduation_plan_sync.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/run_planning_smoke.py
```

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install
colcon test --event-handlers console_direct+
colcon test-result --verbose
```

## 5. 变更控制

- 数据、模型、地图和 outputs 默认不删除；
- 不覆盖未审计的用户修改；
- benchmark 必须记录 commit、dirty flag、配置 hash、数据 manifest hash 和随机种子；
- 正式接口变更必须同步研究方案、接口文档和测试；
- 每个阶段形成一个可回滚提交，不把多个研究阶段混为一个提交。
