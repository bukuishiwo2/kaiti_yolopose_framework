# Benchmarks Index

当前研究内容与结论边界见[当前研究范围](../../docs/clinic_current_research_scope.md)。最新Clinic实验摘要：

- [A区真实视频正例三机应急闭环（2026-11-18）](clinic_visual_positive_2026-11-18.md)
- [真实视频误报核验与视频回放集成（2026-11-18）](clinic_visual_integration_2026-11-18.md)
- [动态协同任务分配四策略强基线（离线）（2026-11-18）](clinic_dynamic_assignment_2026-11-18.md)
- [动态修复方法对照（条件性离线证据）（2026-11-18）](clinic_repair_methods_2026-11-18.md)
- [实体床扰动功能闭环（2026-11-18）](clinic_visual_bed_2026-11-18.md)
- [视觉源可行性与仿真相机诊断（2026-11-18）](clinic_visual_source_feasibility_2026-11-18.md)
- [误报语义任务的反事实分析（2026-11-18）](clinic_semantic_counterfactual_2026-11-18.md)

配套的数学模型和实验设计审查见[reviews索引](../../docs/reviews/README.md)。报告中的绝对路径指向本机保护数据；GitHub不包含原始视频、模型、ROS历史日志或仿真运行目录。

- [Clinic小影响范围配对与三种实验配置实测（2026-11-17）](clinic_sparse_repair_and_modes_2026-11-17.md)

- [Clinic统一入口完整闭环复验与同快照对照（2026-11-17）](clinic_unified_full_loop_recheck_2026-11-17.md)

- [Clinic活动监护/携货期间实体床扰动与保持承诺修复（11月17日验收）](clinic_active_bed_repair_2026-11-16.md)

- [Clinic20×25米三机巡逻—事件—恢复与下一周期实测（2026-11-16）](clinic_dense_loop_2026-11-16.md)

- [Clinic共享服务区占用对齐、实际反馈修复与对照（2026-11-12）](clinic_resource_alignment_2026-11-12.md)

本目录存放适合长期引用的 benchmark 摘要与模型对比文档。

命名规则：

- `reports/benchmarks/<topic>_YYYY-MM-DD.md`

放置原则：

- 这里只保留摘要和结论
- 原始 `csv/json` 继续留在本地 `outputs/`
- 需要跨阶段比较的结果，应优先整理成这里的 Markdown 文档

当前文档：

- [Clinic医院新路线实际执行与事件—MILP接入（2026-11-12）](clinic_hospital_execution_2026-11-12.md)

- [Clinic医院语义点位、常态路线与事件观察位静态验收（2026-11-10）](clinic_hospital_semantics_2026-11-10.md)

- [Clinic脚本跌倒事件、event-task/v1与三机MILP重分配实测（2026-11-10）](clinic_fall_milp_2026-11-10.md)

- [Clinic L1三台TurtleBot4/Nav2与共享服务点互斥实测（2026-11-10）](clinic_l1_three_tb4_2026-11-10.md)
- [Clinic L1独立单机Nav2与服务执行实测（2026-11-10）](clinic_l1_nav2_services_2026-11-10.md)
- [统一事件到任务协议：四类独立回放实测（2026-11-09）](event_task_protocol_replay_2026-11-09.md)
- [相同保留/扩展策略单体MILP与分解完整流程交错计时（2026-11-09）](task_repair_ablation_2026-11-09.md)
- [常态任务中突发跌倒：独立任务级离散事件仿真实测（2026-11-09）](task_level_simulation_2026-11-09.md)
- [固定随机种子多机器人逐结构等价性与计时实测（2026-11-09）](random_repair_equivalence_2026-11-09.md)
- [独立小规模修复模型等价性实测（2026-11-09）](repair_equivalence_2026-11-09.md)
- [UR Fall 基准摘要](urfall_comparison_2026-04-09.md)
- [UR Fall Rule / LSTM / TCN 对比摘要](urfall_rule_lstm_tcn_comparison_2026-04-10.md)
- [Planner Static Baselines](planner_static_baselines_2026-06-22.md)
- [Dynamic Replan](dynamic_replan_2026-06-22.md)
- [Local Repair Vs Full Replan](local_repair_vs_full_replan_2026-06-22.md)
- [Local Repair Comparison](local_repair_comparison_2026-06-23.md)

- [Clinic执行承诺保留、非全体等待修复与热启动全量对照（2026-11-13）](clinic_execution_prefix_repair_2026-11-13.md)

- [Clinic20×25米候选密集区：静态Nav2预检（2026-11-16）](clinic_dense_area_preflight_2026-11-16.md)
