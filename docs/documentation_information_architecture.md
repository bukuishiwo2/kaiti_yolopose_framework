# Documentation Information Architecture

本文件定义仓库中文档的长期分层规则，避免 `README`、`docs/`、`reports/` 与 `worklogs/` 再次混写。

## 1. 目标

文档体系需要同时满足四件事：

1. 让新读者快速理解项目定位与默认主线
2. 让长期维护者能找到稳定规则、接口与系统边界
3. 让阶段性审计与 benchmark 结果可以长期追溯
4. 让开发过程记录不污染长期稳定文档

## 2. 文档分层

### 2.1 根目录 `README.md`

只负责项目总览与进入路径，不负责承载全部细节。

应保留：

- 项目定位
- 当前默认主线与阶段结论
- 仓库结构
- 快速开始
- 感知主线与系统主线概览
- 关键文档导航

不应长期堆积：

- 大段阶段性实验过程
- 多轮 audit 细节
- 被替代的接口草案

### 2.2 `docs/` 根目录

只放长期稳定说明文档。

适合放在这里的内容：

- 项目约定
- 系统架构
- 系统接口契约
- 开题目标对齐
- 数据集定位与外部验证策略
- 文档信息架构
- 环境搭建与参考资料

### 2.3 `docs/reviews/`

只放阶段审计、接口评审、阶段汇总。

适合放在这里的文件：

- `*_audit_YYYY-MM-DD.md`
- `*_summary_YYYY-MM-DD.md`
- 某一轮阶段收口评审

### 2.4 `docs/worklogs/`

只放按日期记录的开发过程。

适合放在这里的内容：

- 当天完成了什么
- 做了哪些验证
- 当前阻塞与下一步

### 2.5 `docs/archive/`

只放已被替代但仍需保留的历史文档。

适合放在这里的内容：

- 旧架构稿
- 已被稳定版替代的 dated snapshot
- 被新方案替换但仍需追溯的历史说明

### 2.6 `reports/benchmarks/`

只放长期保留的实验摘要与对比结论。

适合放在这里的内容：

- benchmark 摘要
- 模型对比结论
- 数据策略实验摘要

不适合放在这里的内容：

- 当天临时调参过程
- 尚未收口的实验流水账

## 3. 当前推荐阅读路径

新读者建议按以下顺序阅读：

1. `README.md`
2. `docs/project_conventions.md`
3. `docs/kaiti_alignment.md`
4. `docs/system_architecture.md`
5. `docs/system_interface_contract.md`
6. `docs/dataset_positioning.md`
7. `ros2_ws/README.md`
8. `reports/benchmarks/`
9. `docs/worklogs/`

## 4. 当前术语口径

为避免文档间出现同义反复或冲突，当前统一用法如下：

- `默认主线`：当前仓库推荐默认使用的技术路径
- `baseline`：保留用于对照、诊断或历史参考的方法，不作为默认主决策
- `debug`：联调用的辅助字段、调试图像或状态，不属于冻结核心契约
- `system skeleton`：ROS2 骨架与接口占位实现，不等于最终完整系统
- `planner placeholder`：占位任务层节点或占位规划模式，不等于真实 `PlanSys2 / LTL`
- `external validation`：不一定进入主训练，但用于验证域外泛化能力的外部数据集或视频集

## 5. 维护规则

1. 根 `README.md` 负责总览，不负责堆积所有细节。
2. 若某一带日期文档已经成为长期稳定结论，应升格为无日期文档。
3. 若某一稳定文档被替代，旧版本应移动到 `docs/archive/` 或明确标注为 snapshot。
4. 任何关键 benchmark 结论都应落到 `reports/benchmarks/`，而不是只留在 `outputs/`。
5. 任何当天工作推进都应落到 `docs/worklogs/`，而不是继续回写到稳定文档正文。
