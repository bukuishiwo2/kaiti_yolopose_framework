# Docs Index

本目录用于长期维护项目说明文档，不再作为临时记录的平铺存放区。

当前文档信息架构说明见：

- [documentation_information_architecture.md](documentation_information_architecture.md)

## 1. 稳定文档

建议优先阅读：

1. [项目总览](../README.md)
2. [项目约定](project_conventions.md)
3. [多代理协作说明](agents.md)
4. [开题目标对齐](kaiti_alignment.md)
5. [系统架构说明](system_architecture.md)
6. [ROS2 最小骨架](system_bringup_skeleton.md)
7. [系统接口契约](system_interface_contract.md)
8. [数据集定位与外部验证策略](dataset_positioning.md)
9. [ROS2 工作区说明](../ros2_ws/README.md)

研究补充文档：

- [FallVision 接入说明](fallvision_integration.md)
- [Hard Negative 方案](hard_negative_plan.md)
- [方法路线图](method_roadmap.md)
- [文档信息架构](documentation_information_architecture.md)
- [推理测试资源](inference_resources.md)
- [TCN 定位说明](tcn_positioning.md)
- [外部参考链接](references.md)
- [新机器环境说明](setup_new_machine.md)

## 2. 阶段文档分层

`docs/` 根目录之外，当前还维护三个子区：

- [reviews/README.md](reviews/README.md)：阶段审计、接口评审、汇总结论
- [worklogs/README.md](worklogs/README.md)：按日期记录的开发日志
- [archive/README.md](archive/README.md)：已被替代但仍需保留的历史文档

## 3. 文档类别

当前仓库中的文档可分为四类：

- 长期稳定文档：`README.md`、`docs/` 根目录、`ros2_ws/README.md`
- 阶段审计文档：`docs/reviews/`
- benchmark 摘要：`reports/benchmarks/`
- worklog：`docs/worklogs/`

## 4. 放置规则

文档应按以下规则放置：

- 长期有效的说明文档：放 `docs/` 根目录
- 带日期的阶段审计和汇总：放 `docs/reviews/`
- 开发过程记录：放 `docs/worklogs/`
- 历史版本或被替代方案：放 `docs/archive/`
- benchmark 结果摘要：放 `reports/benchmarks/`
- 已冻结但仍需追溯的 dated snapshot：保留原文件，并在稳定文档中提供统一入口

不要继续把 `worklog_*.md`、`*_audit_*.md`、`*_summary_*.md` 直接放到 `docs/` 根目录。
