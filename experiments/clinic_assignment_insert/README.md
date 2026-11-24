# Clinic已接受计划插入与严格双因素实验

本目录是独立离线实验，不替换部署规划器，不启动ROS/Gazebo，不修改旧B0–B3或局部修复后端。研究内容三仍为语义事件驱动的动态协同分配与排程，执行承诺为硬保障。运行结果和原始求解日志使用`/home/yhc/clinic_planning_ws/verification/assignment_insert_2026-11-18_h1/`新目录。

## 历史已接受计划与时间边界

固定选择`runs/dense_loop_a13`与`runs/unified_bed_local_r1`，不按新算法结果选择。各运行trace第8行真实`plan_committed(stage=normal)`，分别在Clinic episode .64/.56秒，接受全部9项常态owner、顺序及开始时间；与保存`00_normal/result.json`逐项一致，并经原完整约束检查。

历史事件分别在185.57/187.20秒，由旧脚本触发，不是视觉推理。本轮不会改变这个来源。以对应`01_verify/problem.json`和`02_response/problem.json`的真实机器人/资源状态为固定条件；插入当前视觉模式已验证角色模板的语义任务图，是**离线事件图拼接**，没有新图像、显式复核或执行记录。response阶段的confirmed_at是假设在保存response快照时接受明确fall复核，不将旧verify成功自动fall当作真实复核。

verify与response是两个条件阶段，不把各策略verify计划与共享历史response状态串成一条新闭环。response指标中的verify开始来自共享历史ACK，明确注明来源。

历史trace仅流式读到首次response planning_requested，抽取计划接受、导航下发、完成及事件/规划请求行，约1500行内停止；保存小摘录和完整原文件SHA，不复制历史大日志。

`accepted_reference`始终是事件前真实已接受计划在未派发任务上的精确裁剪，不用release=0或首次名义分工替代。历史verify提交没有重新接受常态计划，保留事件前常态参考；旧执行器此时暂停常态派发，不意味着旧开始时间被重新承诺为必达。

任务分区由原actual_known_finishes、prefix/snapshot_states及trace navigation_requested交叉确定：

- 已完成任务不重入优化。
- 已下发/正在执行的任务整体留在prefix，包括服务完成后仍在驶离的clear导航；不能因service_finished已有值就释放。
- 只把未派发常态后缀与新语义角色送入优化；原source_anchor、ready、阻塞/租约和记录ID保留。额外hold只能延长ready，不提前释放。

## 同一目标、约束与预算

完全保留上一轮独立分配目标及权重：

`J = 4*阶段响应 + .1*(Cmax-now) + .1*常态释放等待 + 2*accepted换机数 + .05*accepted绝对时移 + .1*phase旅行`。

没有新增目标、权重、负载或紧急度模块。普通等待不称逾期；原硬deadline保留。核验从candidate起，monitor从confirmed起，同时记录交付与candidate端到端指标。每项任务release首次固定，360秒开始截止不因重复求解移动。

复用原完整phase-aware模型/约束检查、货物同车相邻、监护覆盖交付+4秒、资源entry/service/clear与能量检查。执行版本/token留在原快照；本轮无在线提交、取消或新的ACK。

复用上轮worker计时与CBC：每法5秒算法墙钟，含构造、建模、求解及验证；同seed17、单线程、单CPU、BLAS线程1，方法顺序轮转。每种MILP使用相同构造程序在自身政策内产生初解，不借用其他方法最后的解；B1失败不回退MILP。first_feasible是首个完成验证的可用解时间，CBC内部首整数秒数另列。

## 严格2×2与四方法映射

| 方法 | 第三角色政策T | 常态开放O | 用途 |
|---|---|---|---|
| F00 | 放宽 | 仅necessary_normal可换机 | 离线政策反事实 |
| F01 | 放宽 | 全部未派发常态可换机 | 离线政策反事实 |
| F10 | 保留 | 仅necessary_normal可换机 | 当前受限MILP，B2 |
| F11 | 保留 | 全部未派发常态可换机 | 本轮合法联合MILP，B3 |

necessary_normal固定为原政策中的C0_r3_W2，不由结果选择。T要求它与monitor/courier不同owner。实际执行器将此作为硬提交约束，因此T=0永远标`OFFLINE_POLICY_RELAXATION_ONLY`，不能在运行时删除此业务约束；原物理模型可行与业务合法分开。

B0全部常态保持真实accepted owner，应急沿用r1监护/r2取送（verify为r1），优化排序与时间；B1固定accepted普通owner和顺序，合法最早服务bundle贪心插入，保留T。F10/F11只优化合法未派发后缀。

四个F单元共享**完全相同的problem文件与SHA**；只添加policy_owner/policy_third行。去掉这两类被测行后，全部数学约束、变量域及目标的签名必须相同；专项测试进一步验证切换T只增加三条第三角色行，切换O只减少相应owner锁。不能把预算内incumbent差称全局最优的因素因果效应。

## 预先固定的输入

每个历史run的response阶段五条件：

1. observed：保存真实机器人/资源状态，拼接语义事件图，无额外环境变化。
2. r1_hold：r1在其投影source处额外不可中断等待160秒，仅延长ready，显式反事实占用。
3. g1_reservation：G1从snapshot.now起额外预约240秒，与取货和常态巡检竞争，显式反事实资源输入。
4. routine_window：C0_r3_W3设硬服务截止`max(now+240, accepted_finish+90)`，属于显式SLA假设，不冒充历史真实截止或软逾期。
5. role_restricted：应急owner限原A角色组合，观察资格域限制；只为模型敏感性，不自动继承整个新时序/源配置的实体资格。

两run×五response条件×六策略=60次；另两verify条件×四合法策略=8次；两run×observed/G1条件的reference-erased诊断×F10/F11=8次，共16输入76调用。没有重新抽种子筛结果，也不把同一run、stage或共享参考的条件当独立实体样本。

Reference-erased是独立的代价诊断：只将objective使用的reference置空，accepted_reference及政策锁、真实改派评价保持。原目标权重未变，但优化问题的变更代价参考范围改变，故不能直接比较原始J。审计将两组方案统一重新按真实accepted_reference算`true_reference_evaluation`，同时报告实际换机、时移、应急与常态代价。

## 文件和复现

- adapter.py：两个政策开关、合法域、实际接受顺序的bundle构造、MILP添加行与真实接受变更指标。
- run.py：来源提取、分区/实例生成、冻结、复用原worker实际求解。
- audit.py：原完整约束+原始来源/分区/参考/政策独立复核，2×2因素和代价参考配对CSV。
- context.py：同状态、不插入本阶段任务束的固定accepted归属重排，区分背景与新增时移。
- summarize.py：逐任务及逐机器人前后计划、域缺口、计算耗时和指标取舍汇总。
- test_insert.py：专项测试。
- report_2026-11-18.md：实际结果与方法判断。

从项目根目录，所有NEW输出目录必须不存在：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q experiments/clinic_assignment_insert/test_insert.py
.venv/bin/python experiments/clinic_assignment_insert/run.py generate --output /home/yhc/clinic_planning_ws/verification/insert_NEW
.venv/bin/python experiments/clinic_assignment_insert/run.py run --output /home/yhc/clinic_planning_ws/verification/insert_NEW
.venv/bin/python experiments/clinic_assignment_insert/audit.py /home/yhc/clinic_planning_ws/verification/insert_NEW --output /home/yhc/clinic_planning_ws/verification/insert_audit_NEW
```

输出为新目录，已有文件拒绝覆盖。预算与主机负载可能影响incumbent，复现输入/规则不保证每次预算内同解。该目录依赖原项目适配器和实际Clinic tools，不是新的部署主链。

本轮实测：16输入76次正式调用，2154项审计通过；另12次无新增任务束背景重排，99项审计通过；33项专项与相关回归通过。10个response条件中F11的冻结J均低于F10，但observed两来源交付分别晚44/151秒，accepted换机更多。T=OFF仅反事实，20份放宽解中7份违反现行业务政策。没有新增实体资格或执行收益结论，没有新增算法模块。详细数据、局限与后续判断见[实测报告](report_2026-11-18.md)。

背景与汇总命令（新目录）：

```bash
.venv/bin/python experiments/clinic_assignment_insert/context.py run /home/yhc/clinic_planning_ws/verification/insert_NEW --output /home/yhc/clinic_planning_ws/verification/context_NEW
.venv/bin/python experiments/clinic_assignment_insert/context.py audit /home/yhc/clinic_planning_ws/verification/insert_NEW --context /home/yhc/clinic_planning_ws/verification/context_NEW --output /home/yhc/clinic_planning_ws/verification/context_audit_NEW
```

`summarize.py`使用本轮证据根下固定formal_01、audit_01、context_audit_01子目录名；本轮命令记录见证据根`commands.sh`。最终验收、保护核对和源码快照见该根目录的acceptance.json、protection_check.json、delivery_manifest.json及source_snapshot.tar.gz。
