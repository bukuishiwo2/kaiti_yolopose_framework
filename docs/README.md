# Docs Index

- [Clinic小影响范围配对与Fast/Standard/Benchmark实测（2026-11-17）](../reports/benchmarks/clinic_sparse_repair_and_modes_2026-11-17.md)

- [Clinic统一入口完整闭环复验与同快照对照（2026-11-17）](../reports/benchmarks/clinic_unified_full_loop_recheck_2026-11-17.md)

- [Clinic基础设施复用、单入口与预检收敛（2026-11-17）](reviews/clinic_runtime_reuse_convergence_2026-11-17.md)

- [Clinic实体床扰动、承诺保持修复与热启动全量对照实测](../reports/benchmarks/clinic_active_bed_repair_2026-11-16.md)

- [Clinic实体床扰动、活动监护/携货承诺与修复契约（2026-11-17验收）](reviews/clinic_active_bed_repair_contract_2026-11-16.md)

- [Clinic局部三机巡逻—应急—恢复闭环实测（2026-11-16）](../reports/benchmarks/clinic_dense_loop_2026-11-16.md)
- [独立闭环运行契约](reviews/clinic_dense_loop_contract_2026-11-16.md)

- [Clinic共享资源与反馈修复契约（2026-11-12）](reviews/clinic_resource_alignment_and_repair_contract_2026-11-12.md)
- [Clinic占用对齐与动态修复实测（2026-11-12）](../reports/benchmarks/clinic_resource_alignment_2026-11-12.md)

本目录用于长期维护项目说明文档，不再作为临时记录的平铺存放区。

当前研究范围与下一步工作统一入口：[三项研究内容重新确认（2026-11-09）](reviews/research_scope_and_completion_plan_2026-11-09.md)。

当前文档信息架构说明见：

- [documentation_information_architecture.md](documentation_information_architecture.md)

## 1. 稳定文档

建议优先阅读：

1. [项目总览](../README.md)
2. [项目约定](project_conventions.md)
3. [多代理协作说明](agents.md)
4. [医院公共空间硕士学位论文研究计划 V3.0.1（P0 冻结）](research_plan_v3_0_1.md)
5. [医院公共空间 V3.0.1 S0 配置与测试协议](public_space_v3_s0_protocol.md)
6. [毕业设计研究方案 v2（house 回归基线）](graduation_research_plan_v2.md)
7. [毕业设计执行计划 v2](graduation_execution_plan_v2.md)
8. [毕业设计实施计划（历史冻结基线）](graduation_design_implementation_plan.md)
9. [成熟技术复用与 Demo 手册](technology_reuse_demo_runbook.md)
10. [LTLf 工具门禁](ltlf_tool_gate.md)
11. [WorldState 与事件生命周期](world_state_event_lifecycle.md)
12. [动态重规划与 LocalRepair v2](dynamic_repair_v2.md)
13. [MILP 模型规范](milp_model_spec.md)
14. [最小实验规范](minimal_experiment_spec.md)
15. [规划 ROS2 接口契约](ros2_interface_contract.md)
16. [仿真搭建计划](simulation_bringup_plan.md)
17. [PlanSys2 与 Nav2 接入计划](plansys2_nav2_integration_plan.md)
18. [局部修复方法说明](local_repair_method_note.md)
19. [局部修复图注草稿](local_repair_figure_captions.md)
20. [第5章实验结果草稿](chapter5_experiment_results_draft.md)
21. [开题目标对齐](kaiti_alignment.md)
22. [系统架构说明](system_architecture.md)
23. [ROS2 最小骨架](system_bringup_skeleton.md)
24. [系统接口契约](system_interface_contract.md)
25. [数据集定位与外部验证策略](dataset_positioning.md)
26. [ROS2 工作区说明](../ros2_ws/README.md)
27. [DUCT 独立研究串流与三维显示](system_duct_research_stream.md)
28. [DUCT 可回退运动实验与左脚接近](system_duct_motion_experiment.md)

研究补充文档：

- [Clinic医院新路线实际执行、服务反馈与事件—MILP接入](../reports/benchmarks/clinic_hospital_execution_2026-11-12.md)

- [Clinic医院语义点位、常态路线及视线/路径验收](../reports/benchmarks/clinic_hospital_semantics_2026-11-10.md)
- [Clinic医院语义、动态障碍与协同修复研究设计](reviews/clinic_dynamic_hospital_research_design_2026-11-10.md)
- [Clinic脚本跌倒事件、协议到MILP及三机实际重分配](../reports/benchmarks/clinic_fall_milp_2026-11-10.md)
- [Clinic L1三台TurtleBot4/Nav2与共享服务点互斥实测](../reports/benchmarks/clinic_l1_three_tb4_2026-11-10.md)
- [Clinic L1单机Nav2与服务反馈实测](../reports/benchmarks/clinic_l1_nav2_services_2026-11-10.md)
- [Clinic协同规划接入步骤与对比实验方案](reviews/clinic_cooperative_planning_integration_plan_2026-11-10.md)
- [Clinic demo图形启动等待诊断与修复](reviews/rmf_clinic_gui_startup_diagnosis_2026-11-09.md)
- [Open-RMF Clinic安装与启动验收](reviews/rmf_clinic_installation_2026-11-09.md)
- [独立事件到任务协议 event-task/v1](event_task_protocol.md)
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

- [Clinic执行承诺保留与非全体等待修复实测（2026-11-13）](../reports/benchmarks/clinic_execution_prefix_repair_2026-11-13.md)

- [Clinic六阶段事件—协同—修复—周期巡逻设计（2026-11-16）](reviews/clinic_six_stage_incident_patrol_design_2026-11-16.md)
