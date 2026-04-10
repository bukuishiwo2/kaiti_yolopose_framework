# AGENTS

本仓库是面向动态家居场景移动机器人任务系统的研究仓库。当前阶段有两条主线：

1. 感知主线：跌倒检测、时序模型、语义事件稳定化
2. 系统主线：ROS2 骨架、感知到任务层桥接、后续 `RTAB-Map / Nav2 / PlanSys2 / LTL` 接口预留

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

`architect` 主要维护：

- `README.md`
- `AGENTS.md`
- `docs/`
- `reports/`
- `.codex/`

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
