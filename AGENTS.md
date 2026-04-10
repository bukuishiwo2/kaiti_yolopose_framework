# AGENTS

本仓库是面向动态家居场景移动机器人任务系统的研究仓库，当前重点是：
1. 感知主线：跌倒检测、时序模型、语义事件稳定化
2. 系统主线：ROS2 骨架、感知到任务层桥接、后续 RTAB-Map / Nav2 / PlanSys2 / LTL 接口预留

## Working conventions

推荐按以下职责分工：
- architect：项目收口、默认配置、文档和跨模块协调
- perception：感知模型、训练评估、调参、语义稳定化
- system_planner：ros2_ws、系统骨架、接口设计、架构文档

是否实际启动子代理，由当前任务决定。

## Directory boundaries

perception 主要工作目录：
- src/yolopose/pipeline/
- src/yolopose/temporal/
- scripts/
- configs/
- data/eval/
- reports/benchmarks/

system_planner 主要工作目录：
- ros2_ws/
- docs/system_*.md
- docs/kaiti_alignment.md

architect 主要维护：
- README.md
- AGENTS.md
- docs/
- reports/
- .codex/

## Do-not-touch

默认不要直接覆盖：
- data/urfall/
- data/processed/
- data/Fall Detection Video Dataset/
- models/*.pt
- outputs/
- .venv/

## Output requirements

任何完成的任务至少需要给出：
1. 任务目标
2. 变更文件列表
3. 指标或结构性结论
4. 未解决风险
5. 下一步命令

不接受只给口头建议、不落文件的“完成”。

## Verification and progress

优先查看：
- README.md
- docs/README.md
- reports/benchmarks/
- docs/system_architecture.md
- docs/system_bringup_skeleton.md
- docs/kaiti_alignment.md
- docs/worklog_YYYY-MM-DD.md

## Current defaults

- 主学习模型：LSTM
- TCN：低误报候选，不是默认主模型
- 规则法：baseline
- 系统主线已启动，但仍处于 ROS2 骨架阶段