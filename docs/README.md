# Docs Index

本目录用于长期维护项目说明文档，不再作为临时记录的平铺存放区。

当前文档信息架构说明见：

- [documentation_information_architecture.md](documentation_information_architecture.md)

## 1. 稳定文档

建议优先阅读：

1. [项目总览](../README.md)
2. [项目约定](project_conventions.md)
3. [多代理协作说明](agents.md)
4. [毕业设计研究方案 v2](graduation_research_plan_v2.md)
5. [毕业设计执行计划 v2](graduation_execution_plan_v2.md)
6. [毕业设计实施计划（历史冻结基线）](graduation_design_implementation_plan.md)
7. [成熟技术复用与 Demo 手册](technology_reuse_demo_runbook.md)
8. [LTLf 工具门禁](ltlf_tool_gate.md)
9. [MILP 模型规范](milp_model_spec.md)
10. [最小实验规范](minimal_experiment_spec.md)
11. [规划 ROS2 接口契约](ros2_interface_contract.md)
12. [仿真搭建计划](simulation_bringup_plan.md)
13. [PlanSys2 与 Nav2 接入计划](plansys2_nav2_integration_plan.md)
14. [局部修复方法说明](local_repair_method_note.md)
15. [局部修复图注草稿](local_repair_figure_captions.md)
16. [第5章实验结果草稿](chapter5_experiment_results_draft.md)
17. [开题目标对齐](kaiti_alignment.md)
18. [系统架构说明](system_architecture.md)
19. [ROS2 最小骨架](system_bringup_skeleton.md)
20. [系统接口契约](system_interface_contract.md)
21. [数据集定位与外部验证策略](dataset_positioning.md)
22. [ROS2 工作区说明](../ros2_ws/README.md)

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
