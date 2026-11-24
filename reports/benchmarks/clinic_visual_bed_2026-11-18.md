# Clinic真实视觉正例后的实体床扰动与局部修复（2026-11-18）

## 目标与严格结论

论文题目《动态环境下融合语义感知的多智能体协同规划研究》及三个研究内容保持不变。本轮直接进入研究内容三，不重新跑无扰动正例基线，不以B区或Gazebo人体动画为前提。

**完成一例真实视频驱动的取货前实体床阻挡与合法三机恢复：14/14项实际任务成功，事件COMPLETED，全部资源释放；独立执行审计93项通过，在线承诺检查1707次通过。实际最后任务于897.84仿真秒完成。**

这是一个有限场景的工程功能结果。三份滚动修复快照来自同一物理实例，不是三次独立试验。只有local_impact在线执行；full_warm仅作同状态快照求解对照。未建立稳定性能收益、跨场景泛化或学术创新结论。

证据根目录：`/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1`。[分项验收](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/delivery_04/acceptance.json)；[完整因果索引](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/delivery_04/causal_ledger.json)；[原始实测summary](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_before_pickup_04/summary.json)；[93项独立审计](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_audit_04/summary.json)；[实际命令](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/commands.md)。

| 交付项 | 状态 | 证据与边界 |
|---|---|---|
| 在线前置条件与限定取消路径 | PASS | 仅取货服务前FollowPath取消；不取消活动监护、不变更携货者 |
| 真实实体床与旧计划失效 | PASS | Gazebo对象ACK、激光/新增全局与局部占用、同UUID取消终态、旧约束残差 |
| 同状态局部/全量比较 | PASS | 每策略相同5秒预算、同problem SHA、原MILP与原独立验证器 |
| 局部方案实际恢复与常态后缀 | PASS | 14项原Nav2/服务ACK、监护后TL/V3清空、最终无租约/队列 |
| 实际EOF、有效区域注册 | PASS | 只播放160帧一次；行为TTL过期但已确认事件及有效注册不被伪造刷新 |
| 独立证据退化协议实验 | PASS | 从真实监护快照离线分叉8项通过；未发服务命令或假ACK |
| 活动服务撤销后的实体恢复 | BLOCKED | 仍需合格取消/接管/恢复工作流，本例不调用 |
| 携货交接、全量实体对照、无修复实体对照 | NOT_RUN | 不从同快照求解推断实体完成时间差 |
| 多种子性能优势、学术创新、独立泛化、RGB-D定位 | NOT_RUN | 作为下一阶段独立研究任务，不与本次集成验收混用 |

## 在线状态审查与本例授权范围

先读取仓库AGENTS、最新视觉正例报告、原始因果日志、实际工作区运行手册及既有床/局部修复评审。实际部署来自`/home/yhc/clinic_planning_ws`，仓库`experiments/clinic`不作为运行工作区。

R1监护必须保留原owner、空间M1、服务开始时间及执行token，直至实际交付成功和显式受控收货方交接ACK。M1的空间保持由实测驻留、同伴keepout与原运动准入见证；不把它说成MILP已实现一般空间驻留容量预约。R2服务前尚未携货，允许取消真实FollowPath，但保持任务身份、目标与归属；必须同UUID的cancel响应与CANCELED(5)终态均成立才进入BED_WAIT。取货后配送required_owner仍为R2，不做携货换机。

原worker没有合格暂停/恢复入口，本例不尝试暂停RUNNING服务。提交修复前检查原模型约束、活动记录/目标/监护开始时间、future task revision/attempt/target/required owner、活动执行token、plan revision、已有租约及开始时间窗口。任何失配拒绝提交。预测释放时刻仅为可撤销承诺投影，不写成实际完成或服务ACK。

行为观测时效与视频源注册时效分别记录。新增有限、配置SHA与几何绑定的`video-region-registration/v1`；EOF不再续造模型观测，`last_seen_at`保持真实最后观测。注册撤销/过期会CANCEL_REQUESTED并保留owner/token，恢复注册也不会抹掉待处理取消；实际活动服务撤销恢复仍BLOCKED。默认传感器观测TTL逻辑保持。

## 先诊断失败，再限定修正

所有失败目录保留，没有覆盖或将局部成功改名为整场PASS：

- `bed_before_pickup_01`：FAIL BED_WAIT_LIMIT。独立适配器误设原injection_stage=2，意外启用旧交付阶段床实验；床删除后CG1视角仍有35个ROI回波，旧无床成功日志也有同样现象。保存对象查询、传感器诊断、源码冻结与失败动画；修正为BEFORE_PICKUP_ONLY，不将ROI不适用当成路径安全，不修改Nav2碰撞守卫。通用携货阶段床分类并未修好。
- `bed_before_pickup_02`：原运行门禁r2 live:controller_server失败，任务/视频/床NOT_RUN；清理PASS。
- `bed_before_pickup_03`：四项应急任务完成、事件关闭，但整场FAIL NAV_FAILED。R1仍停M1时R2恢复常态导航，原局部控制器连续collision ahead/patience exceeded；全局路径通过不足以保证局部可执行。见`failure_diagnosis_03.json`，没有增加重试、删除keepout或改成功判据。
- `clearance_probe_01`：原live:behavior_server预检失败，移动NOT_RUN；保存原cleanup身份竞态失败，随后只读归属检查确认无残留。未用单个新查询替代全量预检。
- `clearance_probe_02`：PASS。受控放置至03真实监护/交付完成位姿，R2保持H1，R1实际经ETL→TL服务→V3清空，原服务/资源/到达守卫不改；无fall事件、无伪恢复ACK。TL服务39.79–40.79、清空56.79、释放/完成56.84秒，签发证据SHA绑定资格。该探针不是无扰动正例基线或通用碰撞安全证明。
- 两次离线初始投影构造错误分别涉及丢失R3活动依赖和历史夹具未合并W1时间；修正后保存`offline_initial_clearance_03`双后端通过。具体见`offline_initial_clearance_construction_errors.json`，没有据此重复启动完整world。

本轮启动时原全量运行门禁必须PASS；仅RPC类live:*失败允许同一world内另存结果、最多一次fresh-process全量复查，不能放行传感器/TF/动作/freshness失败。04首次全量预检通过。

新增监护后清空约束必须在床之前就存在，防止不公平比较。原response完成后，固定原应急分工与R3 W2，调用原full_warm后端排入`E1_monitor_clear`及五项常态后缀；177.86秒通过提交。它不是实际ACK，也不虚构尚未执行的硬承诺。后续旧计划、local/full都含同一个TL/V3清空策略。R2后续常态除排程时间外还必须等待R1真实clear/release与完成记录。

## 实际因果链

视频为历史训练/开发域`fall-01-cam0`，原YOLO Pose、32帧LSTM、阈值0.6与原稳定化参数不变。[模型/输入SHA清单](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/model_input.json)。真实解码、ROS发布、真实模型推理，仅160帧一次，不无限重播维持观测。第99帧（源3.3秒）score=0.9089867、stable/window_ready=true，在Clinic43.87秒生成唯一候选。视频源时钟、ROS发布戳与Clinic仿真时间分别保存，未混为同一时钟。

唯一event-task/v1先生成verify，核验服务后才接收原保存帧的显式复核凭据，再生成monitor/pickup/deliver。复核来源保持`controlled_visual_review / assistant_visual_review / human_review=false / independent_sensor=false`，不是人类、临床或独立传感器确认，不从服务succeeded推断fall。位置来源仅`video_source_registered`，没有冒充RGB-D三维定位或跨源同步人物融合。

关键时间（相对仿真秒；求解耗时另用壁钟）：

| 事实 | 时间 / 结果 |
|---|---|
| 原response提交 / 同策略清空排程提交 | 173.42 / 177.86 |
| R1监护服务 | 240.57–546.57，306.00秒 |
| 床请求 / 实际inserted ACK | 241.93 / 241.94 |
| 同UUID取消ACK及CANCELED终态 | 243.48，ACK前不释放运动预约 |
| 实际持久障碍失效快照 | 258.47 / 288.52 / 318.52 |
| 局部修复提交 | 264.52 / 297.28 / 326.96 |
| 对象移除ACK / 原观测清空恢复 | 318.97 / 322.79 |
| R2取货服务 / G1清空完成 | 399.37–407.37 / 422.33 |
| R2交付服务 / 交付完成 | 537.42–543.42 / 543.47 |
| 受控收货方交接ACK | 546.47，之后才允许监护结束 |
| R1 TL清空服务 / V3清空并释放完成 | 616.42–617.42 / 634.16 |
| R2常态任务重新派发 | 647.12，晚于实际清空ACK |
| 全部14项服务/清空完成 | 897.84，三机IDLE、事件COMPLETED、资源清空 |

监护位姿见证1377个采样，最大距M1约0.09736米，覆盖取货和交付。1707次在线检查全部通过，其中612次明确拒绝提前释放监护。所有实际任务通过原0.20米、0.30弧度、0.7秒稳定、TF/scan/odom freshness≤0.5秒及原worker ACK条件；没有放松守卫。

完整实际任务：

| 任务 | 实际机器人 | 派发 | 服务开始 | 服务结束 | 完成（含清空） |
|---|---|---:|---:|---:|---:|
| C0_r1_W1 | R1 | 35.03 | 113.27 | 117.27 | 135.11 |
| C0_r2_W1 | R2 | 35.03 | 119.42 | 123.47 | 134.56 |
| C0_r3_W1 | R3 | 35.03 | 163.27 | 167.27 | 185.37 |
| E1_verify | R1 | 147.01 | 169.27 | 172.27 | 172.29 |
| E1_monitor | R1 | 207.32 | 240.57 | 546.57 | 546.59 |
| C0_r3_W2 | R3 | 207.32 | 286.12 | 290.12 | 322.79 |
| E1_pickup | R2 | 240.60 | 399.37 | 407.37 | 422.33 |
| C0_r2_W2 | R3 | 353.55 | 411.82 | 415.82 | 444.27 |
| E1_deliver | R2 | 437.12 | 537.42 | 543.42 | 543.47 |
| C0_r2_W3 | R3 | 453.57 | 574.67 | 578.67 | 593.59 |
| E1_monitor_clear | R1 | 548.14 | 616.42 | 617.42 | 634.16 |
| C0_r1_W2 | R1 | 647.12 | 700.42 | 704.42 | 720.58 |
| C0_r3_W3 | R2 | 647.12 | 797.42 | 801.42 | 813.42 |
| C0_r1_W3 | R3 | 720.58 | 786.42 | 876.42 | 897.84 |

## 同快照修复对照与归因边界

首快照真实LaserScan命中75、新全局致命单元87、新局部致命单元59；从243.43至258.47秒持续超过15秒，R2已处BED_WAIT且无货物/无服务开始。快照保留三机实际状态、任务、资源、计划、协议、执行token及真实观测。床真值只作证据，修复输入不读取隐藏移除时刻；继续使用既有30秒滚动不可用预测和原旅行表。

旧计划在更新后的来源/可用时刻约束下最大残差87.77、30.05、30.00秒，三份均未通过原约束验证器。首份主要是R1/R2后缀来源—旅行残差87.77秒，另有R3常态预测约1秒残差；不能把所有普通执行偏差都归于床。这里恢复的是高层后缀排程时间可行性，不是已实现动态走廊容量联合优化或多机器人联合路径规划。实际几何恢复仍由原Nav2、观测清空及共同准入护栏完成。

两策略每次使用同problem SHA、任务/机器人快照、承诺/旅行代价、失效条件与5秒预算，原后端与独立验证器未改。full_warm释放全部未承诺后缀结构，仍受相同监护/取货/同车交付承诺约束，不是允许打破承诺的全任务重分配。

| 快照 | 策略 | 状态 | 原目标J | 求解秒（壁钟） | 自由范围 | 改归属数 | 预测路线末端（仿真秒） |
|---|---|---:|---:|---:|---:|---:|---:|
| 00 | local_impact | OPTIMAL | 386.0360 | 1.513 | 4/5 | 4 | 768.29 |
| 00 | full_warm | FEASIBLE_BUDGET | 386.0360 | 4.769 | 5/5 | 4 | 768.29 |
| 01 | local_impact | FEASIBLE_BUDGET | 376.1158 | 4.844 | 5/5 | 0 | 792.11 |
| 01 | full_warm | FEASIBLE_BUDGET | 376.1158 | 4.878 | 5/5 | 0 | 792.11 |
| 02 | local_impact | FEASIBLE_BUDGET | 387.6888 | 4.753 | 5/5 | 0 | 822.11 |
| 02 | full_warm | FEASIBLE_BUDGET | 387.6888 | 4.736 | 5/5 | 0 | 822.11 |

共享对照管线的实际请求—提交总耗时（包含顺序local＋full两次求解，不是local独立发布时延）：

| 快照 | 请求（仿真秒） | 提交（仿真秒） | 总耗时（壁钟秒） |
|---|---:|---:|---:|
| 00 | 258.47 | 264.52 | 7.536 |
| 01 | 288.52 | 297.28 | 10.974 |
| 02 | 318.52 | 326.96 | 10.784 |

所有解与在线提交独立约束/栅栏检查通过；R1监护、R2取送与R3已派发W2身份/token均保持。第一次四项未派发常态任务换机，两策略结果一致；其余快照不再换机。闭包外的时间允许原±2秒窗口，不能把它称为所有时间完全不变。

首份local在受限子问题1.513秒获得OPTIMAL，full在预算内返回相同J的FEASIBLE_BUDGET；这不证明全问题最优或稳定加速。首份共同种子J=402.2224，两策略均改善至386.036；后两份最终目标等于共同重定时种子，尚未证明结构搜索必要。第二/三份local范围均扩至5/5，没有稀疏范围收益。全部三对最终J相同，不支持局部解质量优于全量。

在线适配器顺序等待两个对照求解器后才提交local，端到端修复耗时包含两次求解、建模/进程/验证，不能当局部算法自身发布时延优势。预测末端与实际897.84也不能混用；后续依赖等待、导航与服务清空产生实际延迟。没有跑full实体组或无修复实体组，不能给出两者实际完成时间差；旧计划模型失效也不等于已证明原运行守卫不可能通过被动等待完成。

## 独立证据退化与未放行机制

[8项离线分叉证据](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/evidence_degradation_04/summary.json)使用本次真实RUNNING监护快照，不增加任何模型样本、不发worker命令、不伪造ACK。EOF后行为过期/有效注册保留已确认监护；注册撤销/期限过期分别请求取消、保持owner及执行target/revision/attempt；恢复注册不会抹掉取消。主实测同时验证真实EOF下有效注册与承诺保持。

实际活动服务取消/ACK/接管/恢复尚BLOCKED，携货交接NOT_RUN。本例既不要求也不绕过这些机制。RGB-D、CameraInfo、Depth、TF、误差与sensor_estimated接口继续保留，独立定位实验NOT_RUN。B区已知路径问题未重跑、未改配置。

## 变更、保护与复现

实际变更及原因见[文件清单](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/change_manifest.json)。主要代码：

- `src/kaiti_task_sim/event_protocol.py`：提取可覆盖的位置有效性方法，默认TTL语义不变。
- `src/kaiti_task_sim/clinic_visual.py`：独立模式可注入RegisteredVideoProtocol。
- `src/kaiti_task_sim/clinic_visual_repair.py`：有限区域注册、取货前投影、初始共同清空策略及租约栅栏。
- `scripts/run_clinic_visual_execute.py`与`clinic_visual_bed.py`：独立bed入口、单次视频、真实床/取消ACK、版本栅栏、初始清空排程与实际清空等待；原注入旁路继续禁用。
- `scripts/clinic_visual_pair.py`：同输入同预算调用原研究修复器；`qualify_clinic_monitor_clearance.py`：实际清空资格短测。
- `scripts/audit_clinic_visual_bed.py`、`check_clinic_evidence_degradation.py`、`summarize_clinic_visual_bed.py`、`render_clinic_visual_bed.py`：独立审计、退化测试、因果索引与真实位姿动画。
- `tests/test_clinic_visual_repair.py`：TTL/注册/取消承诺、取货前scope、资源与活动前缀投影回归。专项47项通过，不运行/改动旧S1套件。
- 更新本报告、实际视觉手册及当日worklog。所有新实验独立目录；既有成功/失败、旧S1与本地修改保留。499项保护核对结果见[完整性清单](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/protected_workspace_integrity.json)。

未修改实际Clinic部署源码、原MILP/研究后端、Nav2、资源/服务worker、Benchmark/Fast/Standard、模型或旧S1；没有提交或推送。Fast/Standard历史结论仍为功能通过、时间目标未达。

[轨迹MP4（18倍速）](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/trajectory_04/trajectory.mp4)；[预览](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/trajectory_04/preview.png)；[渲染元数据](/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/trajectory_04/render.json)。轨迹来自实际Gazebo位姿及真实任务/对象ACK，没有未来插值；床轮廓为示意，不冒充机器人相机录像。

已执行命令、各次失败和运行参数保存于commands.md。重新实跑必须使用新目录/空闲ROS域；当前优先只读复核，不默认再开完整Gazebo：

```bash
cd /home/yhc/kaiti_yolopose_framework
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_event_task_protocol.py tests/test_clinic_visual.py tests/test_clinic_visual_positive.py tests/test_clinic_visual_repair.py
.venv/bin/python scripts/audit_clinic_visual_bed.py --run /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_before_pickup_04 --out /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_audit_review_NEW
```

## 下一阶段研究任务

本例先交付了真实失效与合法恢复，不能将工程链路直接改写成新算法贡献。后续先离线做“固定结构重定时即可恢复 / 必须少量改派 / 时序传播广但结构变化少 / 全局耦合不可恢复”见证实例，再按预定规模、扰动时机与种子做同预算配对，并将共同重定时种子作为强基线。性能统计应分开首次可发布时延、建模/求解/验证/提交总耗时、目标、结构变化、硬约束违规和实际完成率，不能将三次滚动快照当三例样本。

研究内容一/二仍需独立实验：固定相同观测与后端，对照直接触发与语义核验的无效任务数；对照位置有效性/承诺保护的错误目标与非法取消；对照有无依赖的可执行率。当前历史URFall联调不作为识别泛化性能，JSON协议和任务管理功能本身不构成已获支持的创新。
