# AGENTS

本仓库当前服务于《动态环境下融合语义感知的多智能体协同规划研究》。多智能体协同规划是论文核心，人体行为识别是语义事件来源，事件驱动任务生成是两者之间的桥梁，Clinic医院场景仅作为典型动态环境验证。统一研究收口见`docs/research_scope_and_completion_plan.md`。三个研究内容为：

1. 动态环境下的语义事件感知；
2. 面向动态事件的机器人任务生成；
3. 面向动态语义事件的多机器人协同分配与反馈重规划。

旧 house / public-space V3 研究计划仅作为历史方案或回归资产，不代表当前主线。默认研究边界是已知先验地图、现有定位或仿真真值、Nav2底层导航和高层任务协同规划。不新增SLAM、机器人定位、完整人体三维重建、独立底层路径规划、PlanSys2/LTL替代规划器、强化学习或新的复杂识别网络。Clinic实际运行工作区是`/home/yhc/clinic_planning_ws`，仓库内`experiments/clinic`是上传用源码快照。实际运行前先读当前研究范围与当轮Clinic实验手册。

空间站位按两阶段验收。先记录 Nav2 查询的可达性和终点误差，再对代表点记录真实跟踪、稳定到达及同一派发身份的服务回执。涉及共享工位时另核验许可、驶离及释放。结论绑定机器人、起点、目标和占用条件。

## Working Conventions

推荐长期按以下职责分工：

- `architect`：项目收口、默认配置、目录规范、跨模块文档协调
- `perception`：感知模型、训练评估、调参、事件稳定化
- `system_planner`：`ros2_ws`、系统骨架、接口契约、系统架构文档

是否实际启动子代理，由当前任务决定。没有明确写入边界时，不应同时修改同一文件。

## Directory Boundaries

`perception` 主要工作目录：

- `src/yolopose/pipeline/`
- `src/yolopose/temporal/`
- `scripts/`
- `configs/`
- `data/eval/`
- `reports/benchmarks/`

`system_planner` 主要工作目录：

- `ros2_ws/`
- `docs/system_*.md`
- `docs/kaiti_alignment.md`
- `src/kaiti_task_sim/clinic_*.py`
- `src/kaiti_planning/`
- `experiments/clinic_*/`
- `web/clinic/` 与 `src/kaiti_review/`

`architect` 主要维护：

- `README.md`
- `AGENTS.md`
- `docs/`
- `reports/`
- `.codex/`

近期本地独有或未提交的改动必须先检查来源和当前分支，不要未经筛选全部加入共享提交。特别保护旧S1、用户本地模型/数据/输出以及原始Clinic运行证据。

## Documentation Rules

文档分层必须保持清晰：

- `docs/` 根目录：长期稳定说明文档
- `docs/reviews/`：阶段审计、接口评审、架构汇总
- `docs/worklogs/`：按日期记录的开发日志
- `docs/archive/`：被新方案替代但仍需保留的历史文档
- `reports/benchmarks/`：长期保留的实验摘要

默认不要再把以下内容直接放回 `docs/` 根目录：

- `worklog_*.md`
- `*_audit_*.md`
- `*_summary_*.md`
- 已被替代的旧架构稿

## Do-Not-Touch

默认不要直接覆盖：

- `data/urfall/`
- `data/processed/`
- `data/Fall Detection Video Dataset/`
- `models/*.pt`
- `outputs/`
- `.venv/`

如确需清理这些目录，必须先确认它们不是用户本地资产或实验结果。

## Output Requirements

任何完成的任务至少需要给出：

1. 任务目标
2. 变更文件列表
3. 指标或结构性结论
4. 未解决风险
5. 下一步命令

不接受只给口头建议、不落文件的“完成”。

## Verification And Progress

优先查看：

- `README.md`
- `docs/README.md`
- `docs/project_conventions.md`
- `reports/benchmarks/`
- `docs/system_architecture.md`
- `docs/system_bringup_skeleton.md`
- `docs/kaiti_alignment.md`
- `docs/worklogs/worklog_YYYY-MM-DD.md`

## Current Defaults

- 主学习模型：`LSTM`
- `TCN`：低误报候选，不是默认主模型
- 规则法：baseline
- ROS2 默认输入模式：`mock`
- 系统主线已启动，但仍处于 ROS2 骨架与接口收敛阶段
