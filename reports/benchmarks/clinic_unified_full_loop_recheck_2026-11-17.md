# Clinic统一入口完整闭环复验（2026-11-17）

本轮目标是验证工程收敛后，三机“巡逻—跌倒—监护/取送—实体病床短阻挡与持续占道—在线修复—关闭事件—恢复延期任务—下一周期巡逻”仍能完整执行，并与相同变化代价的热启动全量重规划对照。两组各运行一次，均通过预检、控制器验收、独立约束审计及自有进程清理；未因中断对话而重新启动实验。没有修改运行源码、配置、MILP模型或现有规划主链。

## 实际结果与重构一致性

时间均为各自运行的仿真秒；服务包括18项常态任务和4项应急任务，资源区间覆盖接近、服务、驶离的实际预约。

| 策略/版本 | 完成服务/资源区间 | 审计通过项 | 事件关闭 | 最后任务完成 | 相对名义计划换机数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| local 旧A13 | 22 / 19 | 549 | 629.29 | 1352.39 | 1 |
| local 新统一入口 | 22 / 19 | 554 | 629.06 | 1330.91 | 1 |
| full 旧A13 | 22 / 19 | 557 | 632.18 | 1329.18 | 1 |
| full 新统一入口 | 22 / 19 | 551 | 630.77 | 1371.42 | 10 |

两个新运行均由R3核验并持续监护，R2同车取送；活动事件中各调用3次修复，R1未受影响的90秒常态服务继续执行。局部策略保留1项未受影响的未来任务、开放10/11项后缀任务；全量策略开放11/11项。此算例的局部范围仍很大，不能据此宣称显著缩小了搜索问题。

新局部运行：跌倒187.20、事件关闭629.06、下一周期900.01释放；短床实际存在10.04秒，长床77.14秒；R2停车93.48秒后恢复。新全量运行：跌倒187.60、关闭630.77、下一周期900.02释放；短床10.09秒、长床77.04秒；R2停车93.47秒后恢复。实际存在时间含床的置入、转向、移除操作，不等于脚本静止保持时长。两组等待段采样漂移为0，床表面最小采样净距分别1.158米和0.950米；这些是离散采样证据，不是连续安全证明。

短阻挡只等待，没有触发任务层修复；持续阻挡使旧来源/旅行时间约束失效后才修复。各次解均通过模型完整约束检查和提交时承诺检查；监护、已取货的机器人/交付目标以及已下发常态服务得到保持。床清除后的恢复有实际激光与代价地图观测，未以脚本移除时刻直接当作通行恢复。

| 策略/修复轮次 | 请求→提交/仿真秒 | 端到端墙钟秒 | 自由任务/后缀任务 | 此快照加权目标值 | 完整约束及承诺 |
| --- | ---: | ---: | ---: | ---: | --- |
| local/1 | 493.84→514.35 | 23.997 | 10/11 | 448.2685 | 通过 |
| local/2 | 523.85→543.69 | 23.413 | 10/11 | 468.6903 | 通过 |
| local/3 | 553.86→573.55 | 23.811 | 10/11 | 470.7901 | 通过 |
| full/1 | 495.53→516.81 | 23.858 | 11/11 | 447.9613 | 通过 |
| full/2 | 525.56→546.79 | 23.912 | 11/11 | 403.6891 | 通过 |
| full/3 | 555.60→576.43 | 24.231 | 11/11 | 427.8158 | 通过 |

全部为CBC接收MIPStart的预算内可行解（FEASIBLE_BUDGET），不是已证明最优解。局部三次修复未进一步换机；全量第一次修复更换9项未承诺常态任务的执行机器人，后两次没有继续换机。因此新全量结果的10项名义归属变化包含响应阶段的1项必要变化及其后的9项变化。

与旧A13比较，场景、三机展开Nav2参数、22项任务的角色/位置/依赖/能力/期限/服务/资源语义、变化权重、研究后端、严格到达条件保持一致；每组18项行为/输入/约束一致性检查均通过。局部新旧实际任务归属相同，全量新旧9项归属不同。**一致的是模型语义、执行边界和验收条件，不是每次优化解、轨迹和时刻逐位相同。**快照不同及预算内搜索会影响输出，本轮没有证明差异仅由某一种数值原因导致。审计项数随实际导航尝试变化，不代表约束标准更换。

旧两组曾并行运行，新两组顺序运行；主机负载和实际状态不同，不把总时长差归因于策略或重构性能。新控制器墙钟分别1516.25/1480.98秒，也不作为算法速度排名。

## 同一新快照的交错求解

取新局部运行首次修复快照，复用既有对照工具，3轮交错求解。每对输入SHA256相同，目标权重、共同25秒预算、承诺、热启动种子一致；全部6次解通过独立检查且CBC接受热启动。下面是同一快照的重复，不是3个独立实例。

| 轮次 | 局部目标值 | 全量目标值 | 局部墙钟秒 | 全量墙钟秒 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 444.0765 | 448.2685 | 24.451 | 24.049 |
| 2 | 444.0765 | 448.2685 | 24.247 | 24.044 |
| 3 | 444.0765 | 448.2685 | 24.227 | 24.106 |

局部目标444.0765，全量448.2685，差4.1920（约0.935%）；但局部换机2项、累计开始时移481.19秒，全量换机0项、时移218.39秒。局部墙钟中位24.247秒，全量24.049秒，**本轮没有速度优势，也没有更少改动优势**。较低加权目标来自旅行/延期等代价与改动代价的权衡。

这组离线局部解没有回写并执行于上述物理闭环。离线计时期间有报告渲染负载，仅作实际记录，不作专用性能基准。精确求解时全量可行域包含局部域，全量最优值应不劣于局部；这里局部较低只能说明给定预算下的搜索结果，不能证明局部模型的全局最优性或普遍优势。

## 证据、动画与复现

- [两组持续占道对齐回放](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/comparison_replay.mp4)
- [局部完整实际位姿动画](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/local_report/mission_replay.mp4)
- [全量完整实际位姿动画](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/full_report/mission_replay.mp4)
- [局部审计](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/local_report/independent_audit.json)
- [全量审计](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/full_report/independent_audit.json)
- [重构前后语义一致性](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/behavior_consistency.json)
- [同快照对照](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/paired/summary.json)
- [机器摘要](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/summary.json)
- [原文件完整性](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/integrity.json)
- [视频元数据与抽帧核查](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/media_verification.json)
- [局部前后计划](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/local_report/repair_plan_before_after.png)
- [全量前后计划](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/full_report/repair_plan_before_after.png)
- [逐任务计划变化](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/full_report/task_plan_changes.csv)

回放15倍速，使用真实Gazebo离散位姿采样，不插值补造路线；床的位置来自脚本操作的确认记录。对齐视频分别以各自长床置入时刻为零，不假装两次物理输入完全一致。计划图是预测排程，与实际执行时间线分开。原始传感器保存在[/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/local_sensors](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/local_sensors)和[/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/full_sensors](/home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/full_sensors)，含LaserScan、局部代价地图与坐标变换。

查看动画：

```bash
xdg-open /home/yhc/clinic_planning_ws/verification/runtime_full_recheck_2026-11-17/comparison_replay.mp4
```

只重新审计已有结果、不重跑Gazebo（输出目录必须新建）：

```bash
cd /home/yhc/clinic_planning_ws
./clinic_experiment.sh report runs/unified_bed_local_r1 --out verification/clinic_runtime/unified_local_review_02 --no-render
```

## 变更范围与结论边界

变更仅为本报告、两个文档索引、11月17日工作日志、独立工作区当前入口说明及新批次证据。完整列表和哈希见本批次change_manifest.json。53项当前运行源及两组新冻结副本、旧两组各47项冻结源、752个受保护文件、旧原始result.json均核对未变。原生Clinic、旧算例、现有规划主链及用户本地资产保持原状。

本轮支持“工程收敛后完整闭环仍可执行；执行失效可触发修复；承诺得到保护；未受影响工作可以继续；延期与周期任务能恢复”的受控仿真证据。没有增加新功能，也没有证明局部修复普遍优于热启动全量重规划。当前范围仍为参考定位、脚本事件/床、有限布局与执行护栏；未包含人员、真实视觉、抓取、电量充电或实车。

后续研究最缺的是多个独立扰动/规模实例上的配对统计：在同快照、同预算、同变化代价下联合报告恢复可行率、首次可行解延迟、完整求解时间、任务延期、改动和实际执行失败；尤其需要局部影响明显小于全体后缀的实例。本轮不新增这些实验，也不把一次成功闭环当作长期可靠性或学术创新成立的充分证明。
