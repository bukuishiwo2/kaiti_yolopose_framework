# Clinic活动监护与携货期间实体床占道：完整闭环与同输入对照（2026-11-16）

批次于2026-11-16启动，完整执行及人工验收于2026-11-17完成。

任务目标：把常态巡逻—跌倒核验—监护/取送—事件关闭—恢复与下一周期，与实体床引起的观测等待和承诺保持修复合并。仅新增独立入口；不接实车、不加行人、不改原生Clinic、旧算例或规划主链。

## 实际闭环结果

| 指标 | 局部影响范围修复 | 同变化代价热启动全量重规划 |
|---|---:|---:|
| 真实完成服务 | 22 | 22 |
| 完整独立审计检查 | 549 | 557 |
| 完整站点租约事务 | 19 | 19 |
| 最后完成仿真时间/s | 1352.39 | 1329.18 |
| 跌倒触发/s | 187.31 | 187.07 |
| 事件关闭/s | 629.29 | 632.18 |
| 活动事件期间实际提交修复次数 | 3 | 3 |
| 采样中心位于20×25m区域的比例 | 1.00 | 1.00 |

本轮两次物理执行的结束时间不同，不能把23.21秒差直接归因于策略性能；实际资源到达/排队状态也不同。

两组均实际执行18项常态与4项应急服务；R3核验/持续监护、R2取货及交付、R1承担必要常态任务。监护保持至真实交付及脚本接管ACK后才停止；下一周期固定900秒释放。求解期间已下发动作继续，新派发仍受共同快照栅栏约束。

## 短时等待与持续扰动修复

| 策略 | 短床实际存在/s | 长床实际存在/s | 停车等待/s | 最大采样停车漂移/m | 最小采样床表面净距/m |
|---|---:|---:|---:|---:|---:|
| local_impact | 10.06 | 77.08 | 93.07 | 0.0000 | 0.9738 |
| full_warm | 10.19 | 77.05 | 93.21 | 0.0000 | 1.0649 |

短段未调用任务修复；持续观测满15秒且旧后缀来源/旅行或机器人释放预约约束失效后才请求修复。模型使用30秒滚动不可用视界，不读床实际剩余占用时间。激光和全局代价地图共同判断，局部Costmap另有原始证据；取消FollowPath不冒充到达。床不写入人工keepout。

| 策略/修复 | 请求→提交/仿真s | 墙钟/s | 自由任务/后缀任务 | 目标值 | 证明状态 | CBC接收MIPStart |
|---|---|---:|---:|---:|---|---|
| local_impact #1 | 494.98→506.91 | 24.14 | 10/11 | 448.5710 | FEASIBLE_BUDGET | True |
| local_impact #2 | 524.99→536.60 | 23.12 | 10/11 | 468.8661 | FEASIBLE_BUDGET | True |
| local_impact #3 | 555.04→566.03 | 23.23 | 10/11 | 470.9641 | FEASIBLE_BUDGET | True |
| full_warm #1 | 497.79→509.46 | 23.98 | 11/11 | 451.5865 | FEASIBLE_BUDGET | True |
| full_warm #2 | 527.82→539.63 | 23.90 | 11/11 | 470.6921 | FEASIBLE_BUDGET | True |
| full_warm #3 | 557.83→568.95 | 24.23 | 11/11 | 472.4329 | FEASIBLE_BUDGET | True |

每次修复前的旧计划独立检查均失败：局部组两条来源—旅行约束的最大时间残差依次为86.69、30.01、30.05秒；全量组为86.78、30.03、30.01秒。提交后的同一问题完整约束全部通过。R1的原90秒检查贯穿首次求解，R3监护未重启，R2保持同一包裹/目标。

本轮病床后的三次实际修复均未换机，主要调整后继开始时刻；跌倒响应阶段有将原R3常态任务改派给R1的协同分工。本轮不证明机器人故障后的跨机任务接管。

上述两轮捕获状态不同，表中跨轮目标值不可用于判定优劣。活动监护/携货任务固定身份、机器人、目标、服务起始ACK和包裹；只更新可撤销释放预测，未伪装成可换机normal任务。后缀包含全部已知未来常态任务。两种策略均使用相同MILP、变化权重、共同固定结构重定时初解和25秒预算；随后分别在影响范围/全部未承诺后缀内进行真实CBC热启动搜索。

两策略均直接调用同一单体MILP，区别为影响范围与外部冻结；本轮不验证分解求解优越性。ETA为直线距离/标称速度加余量的可撤销预测，不是最坏情形时间上界。
本轮失效主要是配送和监护延后使后继任务的机器人可用时刻预约与来源—旅行约束失效；不把它称为已实现MILP动态走廊容量预约或联合时空路径规划。实际走廊、站点租约和路径交叉仍使用共同执行护栏。

## 同一捕获问题的交错对照

原始输入：[捕获问题](/home/yhc/clinic_planning_ws/runs/bed_local_a13/03_active_repair/problem.json)。3轮同快照重复＋10个固定种子的离线ETA扰动，每对输入SHA相同，合计26次求解。十个ETA扰动不是十次Gazebo稳定性试验。完整记录：[逐实例结果](/home/yhc/clinic_planning_ws/verification/active_bed_2026-11-16/snapshot_comparison_a13/summary.json)。

| 同快照轮次 | 局部目标 | 全量目标 | 局部墙钟/s | 全量墙钟/s | 局部/全量换机数 |
|---|---:|---:|---:|---:|---|
| actual_repeat_0 | 448.5710 | 448.5710 | 23.85 | 23.84 | 0/0 |
| actual_repeat_1 | 448.5710 | 448.5710 | 23.82 | 23.93 | 0/0 |
| actual_repeat_2 | 448.5710 | 448.5710 | 23.85 | 23.79 | 0/0 |

同一实际快照重复：3对中局部目标较低0、全量较低0、相同3；局部减全量墙钟差中位数0.014秒。相同目标只表示返回的预算内可行解成本相同，不证明最优值相同。

离线ETA扰动：10对中局部目标较低1、全量较低0、相同9；局部减全量墙钟差中位数0.078秒。相同目标只表示返回的预算内可行解成本相同，不证明最优值相同。

全部输入下的可行性、完整约束及热启动接收情况见JSON。所有FEASIBLE_BUDGET仅是预算内可行解，不是最优性或等价最优值证明。局部自由范围可能接近整个后缀，不能由“局部”名称推出效率优势。两组物理仿真并行，同快照策略按交错顺序串行求解；时间结果包含当时机器负载，非空载微基准。

## 实际证据与动画

- [两策略实测回放对比](/home/yhc/clinic_planning_ws/verification/active_bed_2026-11-16/final_a13/comparison_replay.mp4)（各轮按持续床置入时刻对齐，状态不同）。
- local_impact：[完整实测动画](/home/yhc/clinic_planning_ws/runs/bed_local_a13/mission_replay.mp4)、[实际服务时间线](/home/yhc/clinic_planning_ws/runs/bed_local_a13/execution_timeline.png)、[修复前后预测计划](/home/yhc/clinic_planning_ws/runs/bed_local_a13/repair_plan_before_after.png)、[逐任务变化](/home/yhc/clinic_planning_ws/runs/bed_local_a13/task_plan_changes.csv)、[激光/局部地图原始证据图](/home/yhc/clinic_planning_ws/verification/active_bed_2026-11-16/bed_local_a13/sensor_evidence.png)、[独立审计](/home/yhc/clinic_planning_ws/runs/bed_local_a13/independent_audit.json)。
- full_warm：[完整实测动画](/home/yhc/clinic_planning_ws/runs/bed_full_a13/mission_replay.mp4)、[实际服务时间线](/home/yhc/clinic_planning_ws/runs/bed_full_a13/execution_timeline.png)、[修复前后预测计划](/home/yhc/clinic_planning_ws/runs/bed_full_a13/repair_plan_before_after.png)、[逐任务变化](/home/yhc/clinic_planning_ws/runs/bed_full_a13/task_plan_changes.csv)、[激光/局部地图原始证据图](/home/yhc/clinic_planning_ws/verification/active_bed_2026-11-16/bed_full_a13/sensor_evidence.png)、[独立审计](/home/yhc/clinic_planning_ws/runs/bed_full_a13/independent_audit.json)。

动画使用实际Gazebo位姿采样回放，不插值编造机器人运动；床框来自Gazebo服务确认的脚本姿态，不是连续运动测量。预测计划图与实际执行时间线分开。

## 失败记录、保护范围和适用边界

历史24轮是跨版本开发、失败及主动停止记录，全部保留在[逐轮目录与状态](/home/yhc/clinic_planning_ws/verification/active_bed_2026-11-16/earlier_trials.json)，不能合并成固定版本成功率：

- a1–a4：检测窗口、scan订阅链、旧动态足迹、阶段误触发及预算内无初解。
- a5–a7：床驱动重复set_pose超时、未确证的ROS context中断、CBC约-4.5e-12数值边界触发PuLP严格校验。只在1e-7内归整边界后重查原矩阵，不放宽模型约束。
- a8：三次修复后R1驻留CDL阻断配送；负探针确认180秒无路径。两策略共同改为侧边BDL停靠，原服务点/地图/a13保留；正探针验证三项实际导航。布局修正不算算法自动解决停车冲突。
- a9：局部图残留与驶过区域后的无关回波；复用标准双清图、重新观测及剩余路径相关性检查，实体床探针通过。
- a10：全量组床前路径恢复被无关回波抑制；源位短探针验证共同恢复入口。局部组已关闭事件、释放下一周期，但第17项后共用CPW2产生依赖—驻留死锁。
- a11–a12：主动停止未完成对比，先分离名义任务通道的PW2清空位；12条驻留路径、5条DL占用路径及4项真实服务—清空—依赖探针通过。A12局部组仍因4个静态采样单元误计新增障碍而BED_WAIT_LIMIT，A12全量组未完成时停止。A13仅在任务层解释原静态图一格采样边界，并保留原始计数和原生碰撞检测；121帧真实记录回放保留真实床占用。该布局与检测口径修正是共同实验前提，不是规划创新，也不代表模型解决一般停车预约。

A13首次后处理审计也保留了两项报错：跨节点时钟相差0.01秒，而原审计链式相加使已有0.06秒容差抵消；短段的“当前清除”标志在下一段占用时被更新，不能当作历史记录。修正后处理为逐边时钟容差＋同控制器清空→释放ACK因果顺序，以及由实际激光/全局/局部图重建的短段清除证据。原始result/trace/NPZ与运行代码均未改；初次审计见各轮`initial_independent_audit.json`，[诊断记录](/home/yhc/clinic_planning_ws/verification/active_bed_2026-11-16/a13_audit_diagnosis.json)。运行中的位置、朝向、驻留及新鲜度守卫没有放宽。


复用Nav2标准ClearEntireCostmap处理无可见障碍时残留的动态单元，并重新观测后恢复；驻留床不再反复下发相同姿态，只有转向时调用Gazebo标准服务，对幂等set_pose有限重试。任何场景API未确认则失败，不把床未移开当成算法成功。新实验绝对/rid/scan配置和六订阅检查修正了真实传感器接入；a13原配置保持，不能追认为其已验证动态床避障。

受保护的752个原生/旧实验/主链文件SHA无变化；两组运行源文件均有各自冻结副本与哈希，数量以source_manifest为准。完整新增/变更列表见[change_manifest.json](/home/yhc/clinic_planning_ws/verification/active_bed_2026-11-16/final_a13/change_manifest.json)。

当前只支持这个固定走廊、两组受控物理功能验收与同输入离线对照，尚不能证明长期稳定性、全局联合最优或学术创新已经成立。需后续增加多初始位姿、多扰动位置/持续时间及故障实例，完整保留失败率。无行人、实车、视觉跌倒识别、机械抓取、AMCL定位误差、电量/充电验证；能耗仍为0。床为现成CC0 NormalBed通用代理，脚本置入/转向/移除，不模拟人员推行动力学；安全几何为离散采样，不是连续零接触证明。

本轮只在活动应急阶段注入一次短段＋一次持续段扰动；尚未验证周期巡逻任意时刻的故障修复、严格硬实时求解或预测最坏情形保证。实际新任务派发在求解期间仍有快照栅栏，持续执行的是已经下发的动作。

独立价值是形成并检验“真实观测变化→旧计划约束失效→保持执行承诺→恢复后缀可行性→真实执行、关闭事件与恢复周期”的证据链。策略性能优劣需逐实例数据支持，不由视频或完成服务数量推出。

## 复现

```bash
cd /home/yhc/clinic_planning_ws
python3 tools/run_bed_acceptance.py --name bed_local_repeat_01 --domain 124 --policy local_impact --static-delta
python3 tools/postprocess_bed.py --name bed_local_repeat_01
```

全量对照使用不同新运行名/ROS域及`--policy full_warm`。手册：[独立入口说明](/home/yhc/clinic_planning_ws/README_CLINIC_ACTIVE_BED.md)；[运行与数学契约](/home/yhc/kaiti_yolopose_framework/docs/reviews/clinic_active_bed_repair_contract_2026-11-16.md)。
