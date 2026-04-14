# Multi-Agent Collaboration

本文件用于配合仓库根目录的 [AGENTS.md](../AGENTS.md) 使用，回答三个问题：

1. 项目有哪些长期角色
2. 每个角色默认改哪些文件
3. 阶段结果应该去哪里看

## 1. 当前长期角色

### 1.1 `architect`

负责：

- 项目结论收口
- 默认配置切换
- 目录规范与文档分层
- 根 README、阶段总结与跨模块一致性

典型输出：

- `README.md`
- `AGENTS.md`
- `docs/README.md`
- `docs/project_conventions.md`
- `docs/reviews/*.md`

### 1.2 `perception`

负责：

- 跌倒检测算法实现
- `LSTM / TCN` 训练与评估
- 感知调参与 hard negative 策略
- 感知事件语义稳定化

典型输出：

- `src/yolopose/pipeline/`
- `src/yolopose/temporal/`
- `configs/train_fall_sequence*.yaml`
- `configs/infer_pose_stream*.yaml`
- `data/eval/*.yaml`
- `reports/benchmarks/*comparison*.md`

### 1.3 `system_planner`

负责：

- `ros2_ws/` 系统骨架
- 感知到任务层的接口设计
- launch / config 组织
- 系统接口、系统架构、bringup 文档

典型输出：

- `ros2_ws/`
- `docs/system_architecture.md`
- `docs/system_bringup_skeleton.md`
- `docs/system_interface_contract_*.md`
- `docs/kaiti_alignment.md`

## 2. 目录责任边界

| 目录 / 文件 | 默认责任角色 |
| --- | --- |
| `src/yolopose/pipeline/` | `perception` |
| `src/yolopose/temporal/` | `perception` |
| `scripts/run_fall_sequence_train.py` | `perception` |
| `scripts/eval_fall_batch.py` | `perception` |
| `data/eval/` | `perception` |
| `ros2_ws/` | `system_planner` |
| `docs/system_*.md` | `system_planner` |
| `docs/kaiti_alignment.md` | `system_planner` |
| `README.md` | `architect` |
| `AGENTS.md` | `architect` |
| `docs/README.md` | `architect` |
| `docs/project_conventions.md` | `architect` |
| `docs/reviews/` | `architect` 收口 |
| `reports/benchmarks/` | `architect` 收口，`perception` 供稿 |

## 3. 阶段结果放置位置

阶段结果必须按类型落到正确位置：

- benchmark 摘要：`reports/benchmarks/`
- 审计、接口评审、汇总：`docs/reviews/`
- 过程日志：`docs/worklogs/`
- 历史方案：`docs/archive/`

不要继续把阶段性文档直接平铺在 `docs/` 根目录。

## 4. 查看其他角色进展的方法

### 4.1 看 `perception`

优先看：

- [UR Fall Rule / LSTM / TCN 对比摘要](../reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md)
- [TCN 定位说明](tcn_positioning.md)
- [Hard Negative 方案](hard_negative_plan.md)
- `configs/infer_pose_stream*.yaml`

### 4.2 看 `system_planner`

优先看：

- [系统架构说明](system_architecture.md)
- [ROS2 最小骨架](system_bringup_skeleton.md)
- [系统接口契约](system_interface_contract.md)
- [ROS2 工作区说明](../ros2_ws/README.md)

### 4.3 看 `architect`

优先看：

- [项目总览](../README.md)
- [项目约定](project_conventions.md)
- [阶段评审索引](reviews/README.md)
- [开发日志索引](worklogs/README.md)

## 5. 什么时候适合开子代理

适合：

1. 写入范围清楚
2. 任务可独立完成
3. 结果能直接落到文件
4. 不阻塞主代理当前动作

不适合：

1. 需要频繁修改同一文件
2. 任务定义还不清楚
3. 当前主线决策还没定

## 6. 当前推荐协作方式

当前长期保持三类角色即可：

1. `architect`
2. `perception`
3. `system_planner`

数据整理工作默认由 `perception` 协带，只有当数据接入本身成为独立任务时再拆角色。

## 7. 当前阶段默认主线

感知主线：

- `LSTM` 作为综合主模型
- `TCN` 作为低误报候选分支

系统主线：

- 先维持 `ROS2` 骨架和最小桥接闭环
- 先做接口收敛，再接 `RTAB-Map / Nav2 / PlanSys2`
