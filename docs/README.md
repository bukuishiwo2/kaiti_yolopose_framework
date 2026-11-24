# Docs Index

当前论文和Clinic状态以[当前研究范围与证据边界](clinic_current_research_scope.md)为准。旧的house毕业方案和医院公共空间双机器人V3文档保留为历史版本，不作为当前实施计划。

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

当前Clinic页面与实验入口的审查：

- [研究内容三的MILP模型审查](reviews/clinic_dynamic_assignment_model_audit_2026-11-18.md)
- [内容一/二/三串联准备度审查](reviews/clinic_semantic_end_to_end_readiness_2026-11-18.md)
- [工作台解释性与历史运行归类](reviews/clinic_workbench_explainability_2026-11-24.md)
- [节点、旅行代价与路径来源](reviews/clinic_node_path_sources_2026-11-24.md)
- [动态修复滚动更新诊断](reviews/clinic_three_repairs_diagnosis_2026-11-24.md)

当前Clinic研究范围、三项内容的串联状态与未完成证据：

- [当前研究范围与证据边界（2026-11-24）](clinic_current_research_scope.md)
- [研究实验目录与任务规划说明](clinic_research_experiment_guide.md)
- [面向前端展示的实验目录数据](clinic_research_catalog.json)
- [较早的三项研究内容审查（2026-11-09，历史阶段快照）](reviews/research_scope_and_completion_plan_2026-11-09.md)

当前文档信息架构说明见：

- [documentation_information_architecture.md](documentation_information_architecture.md)

## 1. 稳定文档

按当前研究定位建议优先阅读：

1. [项目总览](../README.md)
2. [项目约定](project_conventions.md)
3. [多代理协作说明](agents.md)
4. [动态任务规划数学模型](milp_model_spec.md)
5. [动态重规划与LocalRepair方法说明](dynamic_repair_v2.md)
6. [独立语义事件到任务协议](event_task_protocol.md)
7. [数据集定位与外部验证策略](dataset_positioning.md)
8. [当前研究范围与证据边界](clinic_current_research_scope.md)
9. [Clinic研究实验与任务规划说明](clinic_research_experiment_guide.md)
10. [Clinic研究实验目录数据](clinic_research_catalog.json)
11. [历史家居场景毕业方案（不作为当前路线）](graduation_research_plan_v2.md)
12. [历史医院公共空间V3双机器人方案（不作为当前路线）](research_plan_v3_0_1.md)
13. [历史执行计划v2](graduation_execution_plan_v2.md)
14. [成熟技术复用与 Demo 手册](technology_reuse_demo_runbook.md)
15. [LTLf 工具门禁](ltlf_tool_gate.md)
16. [WorldState 与事件生命周期](world_state_event_lifecycle.md)
17. [最小实验规范](minimal_experiment_spec.md)
18. [规划 ROS2 接口契约](ros2_interface_contract.md)
19. [仿真搭建计划（旧实现背景）](simulation_bringup_plan.md)
20. [PlanSys2 与 Nav2 接入计划（接口参考，非当前主线）](plansys2_nav2_integration_plan.md)
21. [局部修复方法说明](local_repair_method_note.md)
22. [局部修复图注草稿](local_repair_figure_captions.md)
23. [第5章实验结果草稿](chapter5_experiment_results_draft.md)
24. [开题目标对齐（早期范围映射，历史参考）](kaiti_alignment.md)
25. [系统架构说明](system_architecture.md)
26. [ROS2 最小骨架](system_bringup_skeleton.md)
27. [系统接口契约](system_interface_contract.md)
28. [ROS2 工作区说明](../ros2_ws/README.md)
29. [DUCT 独立研究串流与三维显示](system_duct_research_stream.md)
30. [DUCT 可回退运动实验与左脚接近](system_duct_motion_experiment.md)

Clinic早期接入和资格报告（历史执行记录；不是当前研究范围定义）：

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


## Clinic动态协同分配实验（2026-11-18）

- [统一时间、数学模型与离线运行契约](clinic_dynamic_assignment_contract.md)
- [原MILP动态分配因素与时间口径审查](reviews/clinic_dynamic_assignment_model_audit_2026-11-18.md)
- [四策略强基线、逐例对照与能力敏感性实测](../reports/benchmarks/clinic_dynamic_assignment_2026-11-18.md)
- [多事件规划表达能力验证](../experiments/clinic_multievent/README.md)
- [五类任务耦合必要性实验](../experiments/clinic_coupling_necessity/README.md)

## Clinic真实视频与任务执行实验（2026-11-18）

- [视觉正例三机核验/监护/取送闭环](../reports/benchmarks/clinic_visual_positive_2026-11-18.md)
- [真实视频误报核验集成](../reports/benchmarks/clinic_visual_integration_2026-11-18.md)
- [执行扰动床阻挡实测](../reports/benchmarks/clinic_visual_bed_2026-11-18.md)
- [感知到任务链串联准备度](reviews/clinic_semantic_end_to_end_readiness_2026-11-18.md)

## Clinic 实验工作台与任务解释（2026-11-24）

- [面向普通用户的实验目录与任务规划说明](clinic_research_experiment_guide.md)
- [节点、旅行代价与路径来源审查](reviews/clinic_node_path_sources_2026-11-24.md)
- [工作台解释性与证据边界审查](reviews/clinic_workbench_explainability_2026-11-24.md)
- [三次滚动修复诊断](reviews/clinic_three_repairs_diagnosis_2026-11-24.md)
- [工作台启动与使用手册](../web/clinic/README.md)
- [GitHub范围整理与本次发布核验](reviews/clinic_github_scope_cleanup_2026-11-24.md)
- [本次发布的浏览器/目录检查收据与截图](../reports/demos/2026-11-24_clinic_research_release/README.md)
