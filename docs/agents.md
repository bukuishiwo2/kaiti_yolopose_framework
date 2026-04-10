# Multi-Agent Collaboration

本文件是本项目的长期协作手册，用于配合仓库根目录的 [AGENTS.md](../AGENTS.md) 使用。

它回答三个问题：

1. 这个项目有哪些长期角色
2. 每个角色应该改哪些文件
3. 结果应该去哪里看

## 1. 当前长期角色

### 1.1 主代理

负责：
- 收口项目结论
- 决定默认配置
- 更新 `README` / `docs` / `reports`
- 合并多条主线的阶段结果

典型输出：
- `README.md`
- `reports/benchmarks/*.md`
- `docs/worklog_*.md`

### 1.2 感知代理

负责：
- 跌倒检测算法实现
- `LSTM / TCN` 训练与评估
- 调参与模型对比
- 感知推理与语义事件稳定

典型输出：
- `src/yolopose/temporal/`
- `configs/train_fall_sequence*.yaml`
- `configs/infer_pose_stream*.yaml`
- `data/eval/fall_grid_*.yaml`
- `reports/benchmarks/*comparison*.md`

### 1.3 数据代理

负责：
- 数据集接入
- 标签 CSV 构建
- hard negative 管理
- 数据格式统一与文档化

典型输出：
- `scripts/build_*.py`
- `scripts/merge_label_csvs.py`
- `docs/fallvision_integration.md`
- `docs/hard_negative_plan.md`
- `data/eval/*.csv`

### 1.4 系统代理

负责：
- `ROS2` 工作区骨架
- 感知桥接、系统监督节点
- `RTAB-Map / Nav2 / LTL / PlanSys2` 的系统级接口预留
- launch / config 组织

典型输出：
- `ros2_ws/`
- `docs/system_architecture.md`
- `docs/system_bringup_skeleton.md`
- `docs/kaiti_alignment.md`

## 2. 目录责任边界

| 目录 / 文件 | 默认责任角色 |
| --- | --- |
| `src/yolopose/pipeline/` | 感知代理 |
| `src/yolopose/temporal/` | 感知代理 |
| `scripts/run_fall_sequence_train.py` | 感知代理 |
| `scripts/eval_fall_batch.py` | 感知代理 |
| `scripts/tune_fall_grid.py` | 感知代理 |
| `scripts/build_*.py` | 数据代理 |
| `data/eval/` | 数据代理 + 感知代理 |
| `ros2_ws/` | 系统代理 |
| `docs/system_*.md` | 系统代理 |
| `docs/*integration*.md` | 数据代理 |
| `README.md` | 主代理 |
| `reports/benchmarks/` | 主代理收口，感知代理供稿 |

## 3. 查看其他代理进展的方法

### 3.1 看感知代理

优先看：
- [UR Fall Rule / LSTM / TCN 对比摘要](../reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md)
- [TCN 定位说明](tcn_positioning.md)
- `data/eval/fall_grid_*.yaml`
- `outputs/eval_*` 中的结果目录

### 3.2 看系统代理

优先看：
- [系统架构说明](system_architecture.md)
- [ROS2 最小骨架](system_bringup_skeleton.md)
- [ROS2 工作区说明](../ros2_ws/README.md)
- `ros2_ws/src/yolopose_ros/launch/`

### 3.3 看主代理收口结果

优先看：
- [项目总览](../README.md)
- [开题目标对齐](kaiti_alignment.md)
- `docs/worklog_YYYY-MM-DD.md`

## 4. 什么时候应该开子代理

适合开子代理的任务：

1. 写入范围清楚
2. 任务可独立完成
3. 结果能直接落到文件
4. 不阻塞主代理当前动作

不适合开子代理的任务：

1. 需要频繁修改同一文件
2. 任务定义本身还不清楚
3. 当前主线决策还没定

## 5. 当前推荐协作方式

当前项目推荐长期保持：

1. 主代理
2. 感知代理
3. 系统代理

数据代理在数据集接入密集阶段再单独开启，平时可以由感知代理兼带。

## 6. 当前阶段默认主线

1. 感知主线：
- `LSTM` 作为综合主模型
- `TCN` 作为低误报候选分支

2. 系统主线：
- `ROS2` 骨架先行
- 逐步接 `RTAB-Map`、`Nav2`、`PlanSys2/LTL`

3. 数据主线：
- `UR Fall` 继续作为主评估集
- `FallVision` 更适合作为增强和 hard negative 来源

