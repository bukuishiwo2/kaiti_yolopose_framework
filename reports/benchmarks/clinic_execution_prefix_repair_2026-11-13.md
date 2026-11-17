# Clinic执行承诺保留、非全体等待修复及同条件实际对照

日期：2026-11-13。目标：保留在途/服务/携货承诺，让其余机器人继续工作并及时修复后缀，解决历史432.59秒全体等待。原生Clinic、旧成果和项目规划主链不改；本轮不接实车。

## 条件与公平边界

三策略**实际重跑**相同地图、任务、参考正常计划、能力、变化权重、仿真真值定位、XL/PDR/PR终点及Nav2位置交接＋Spin。服务守卫保持0.20m/0.30rad/0.7秒，新鲜度0.5秒；没有放宽。执行源文件哈希、运行时配置和参考文件均核对相同，只有反馈策略以及隔离域/分区不同。各轮串行冷启动，求解与绘图离线阶段等物理仿真完全停止。

主对照使用相同90秒延迟规则；实际ROS/Gazebo反馈时刻不是逐位相同，不能宣称相同瞬间状态或统计显著性。每个实际捕获快照另外做同输入局部/热启动全量对照。当前物理模型三台相同，能力差异在任务层设置；真值定位结果不是AMCL部署结论。

[条件和源哈希核对](/home/yhc/clinic_planning_ws/verification/clinic_prefix/conditions_a2.json)。三策略各一轮，并非三个独立随机样本。

## 主要实际结果

|策略|服务数|导航目标|Spin数|完成/返场sim秒|运行墙钟秒|最大服务误差m|申请后最大排队s|全部审计|
|---|---|---|---|---|---|---|---|---|
|全体等待＋局部|20|43|31|1270.45|1402.74|0.1017|0.00|通过|
|承诺投影＋局部|20|43|30|1127.43|1222.36|0.1043|0.00|通过|
|承诺投影＋热启动全量|20|43|31|1127.21|1234.28|0.0994|0.00|通过|

每轮均检查任务数/唯一反馈、稳定服务、真实前序清空ACK、同车相邻取送、监护覆盖、期限、实际完整租约、2秒资源缓冲、关闭区排除及采样几何净空。导航取消仅允许有记录的位置交接，必须有Spin成功或无需旋转和最终稳定守卫，不能将取消伪装成导航成功。

## 等待是否真正消除

|策略|发现迟到sim时刻|发现→请求sim秒|发现→有效提交sim秒|求解流程墙钟秒|发现→首个后缀派发sim秒|其他承诺结束前完成的后缀服务|
|---|---|---|---|---|---|---|
|全体等待＋局部|488.55|432.53|434.33|2.23|435.53|无|
|承诺投影＋局部|488.70|0.00|0.44|0.56|35.00|r3_N4, r1_N4|
|承诺投影＋热启动全量|487.99|0.00|1.24|1.47|35.00|r3_N4, r1_N4|

这里“全体等待”指协调器等待全部承诺结束才释放新后缀，并非三台机器人在432秒内始终静止；原取送前缀仍执行，已空闲机器人被屏障限制。

本轮全体等待实际为432.53秒；局部投影在0.44秒内有效提交，首个新后缀派发仍需35.00秒。这包含预先声明的35仿真秒投影计算/提交余量，不包装成“立即开始导航”。全体等待旧入口是在全空闲后使用3秒准备余量，异步策略更保守的35秒余量已单独报告。

最重要的执行证据不是仅完成20项服务，而是：r3_N4, r1_N4在最后一个受保护前缀实际清空前已经完成。原导航/服务/取送前缀保持命令身份与执行者，物资仍由实际取货机器人交付。局部较全体等待的总完成/返场时间缩短143.02秒（11.26%）；局部与热启动全量只差0.22秒，不能认为局部在执行效果上胜过全量。两者都采用不全体等待，本例主要执行收益归于承诺投影/执行机制，不能全部归于缩小MILP。

## 释放范围与实际变化

|策略|发现时承诺任务数|释放后缀数|后缀总数|保留开始窗口±s|实际后续换机数|实际开始时移绝对和s|实际旧邻接破坏数|加权实际改动|
|---|---|---|---|---|---|---|---|---|
|全体等待＋局部|3|4|4|无保留窗口|1|1332.00|1|336.00|
|承诺投影＋局部|3|2|4|2.0|1|419.00|1|107.75|
|承诺投影＋热启动全量|3|4|4|无保留窗口|1|418.40|1|107.60|

实际改动相对延误发现前最后接受的repair_plan，统计当时尚未完成任务，并非相对初始常态计划的全程变化。开始窗口承诺不是精确固定原时刻；实际开始时刻另行测量。加权实际改动按相同owner/shift/adjacency权重，比较发现迟到时仍未完成任务的真实执行，包含不可改派前缀的实际时序偏差；它不是MILP目标值。模型优化的变化项仅针对后缀参考子图，不含前缀最后任务到后缀首任务跨边；实际邻接指标则包含发现时全部未完成任务，边界不得混淆。G1 routine_ready是可改派1秒点位服务，不是原配送车回补证明。

## 承诺怎样进入模型

本轮仍是MILP协同分配与排程：局部策略在受影响作用域内解单体MILP，热启动全量解同范围后缀MILP；没有将本轮物理执行称为分解算法已部署，也不把Nav2本身的避障当成本文创新。

集合D为真实已完成，C为当前动作至清空与携货/正在取货至同车交付清空的前缀，U为可修复后缀。前缀不是伪造完成事实：`actual_known_finishes`保持实际ACK；预测单列`committed_finishes`，用于后缀源状态/依赖预测；协议完成状态不提前改变。

对机器人i，后缀起始锚点为前缀最后清空锚点，r_i为可撤销的清空预测；后缀满足源到达、期限、能力与取送约束。前缀资源区间K与后缀完整区间[s−A,f+E]二选一互斥，2秒缓冲；真实租约只能物理清空后释放。预测不是物理保证，过期要拒绝/重投影，不强制清租约。服务ACK余量1秒、资源清空余量5秒，非前缀可用时间预留35秒。

局部保留未受影响后缀归属/顺序及原开始±2秒窗口。热启动全量释放全部U，但同样保留C；25墙钟秒总预算包含局部可行种子、建模和全量搜索。提交验证输入目标、当前时钟、前缀身份/清空预测、没有快照外派发和协议版本。求解期间只允许固定前缀继续，不声称所有未发出任务无锁派发。

当前修复限定事件结束后的常态积压；活动监护中途、电量消耗与不可执行前缀不在本轮保证内。非零前缀能耗被明确拒绝。原模型依赖按服务结束预测，控制器等待更强的清空ACK；本例另外核查所有跨前缀依赖计划开始不早于清空上界。紧依赖推广需正式区分事实类型，不能从本例外推一般可执行性保证。

[模型/执行契约](/home/yhc/kaiti_yolopose_framework/docs/reviews/clinic_execution_prefix_repair_contract_2026-11-13.md)。

## 已经携货的补充实际验证

载货由取货服务回执产生的任务级cargo状态表示，没有仿真抓取机构或物品搬运物理验证；这里验证同车实际导航、到达、取送ACK与承诺连续性。

主90秒场景在取货导航期间触发，保留整个取货—交付前缀；不能称修复时已经载货。因此单独增加180秒扰动，仅执行承诺投影局部策略：实际触发时载货状态`{"r2": "E"}`。该轮20项服务及返场通过，完成时间1127.84sim秒；发现→有效提交0.44sim秒。它不混入主三策略效率表，未给出180秒扰动的三策略物理统计对照。

[已载货状态及审计](/home/yhc/clinic_planning_ws/verification/clinic_prefix/carry_actual_state_a3.json)。

## 每个实际快照上的同输入求解

|实际快照|求解流程|三轮状态|三轮目标|墙钟中位数s|释放数|
|---|---|---|---|---|---|
|prefix_barrier_a2|local_impact|OPTIMAL,OPTIMAL,OPTIMAL|842.542000/842.542000/842.542000|1.3438|4/4/4|
|prefix_barrier_a2|full_warm|OPTIMAL,OPTIMAL,OPTIMAL|842.542000/842.542000/842.542000|2.5429|4/4/4|
|prefix_local_a2|local_impact|OPTIMAL,OPTIMAL,OPTIMAL|526.567500/526.567500/526.567500|0.0836|2/2/2|
|prefix_local_a2|full_warm|OPTIMAL,OPTIMAL,OPTIMAL|526.567500/526.567500/526.567500|0.5585|4/4/4|
|prefix_full_warm_a2|local_impact|OPTIMAL,OPTIMAL,OPTIMAL|526.313500/526.313500/526.313500|0.0711|2/2/2|
|prefix_full_warm_a2|full_warm|OPTIMAL,OPTIMAL,OPTIMAL|526.313500/526.313500/526.313500|0.7792|4/4/4|
|prefix_carry_a3|local_impact|OPTIMAL,OPTIMAL,OPTIMAL|456.932000/456.932000/456.932000|0.0573|2/2/2|
|prefix_carry_a3|full_warm|OPTIMAL,OPTIMAL,OPTIMAL|456.932000/456.932000/456.932000|0.1402|3/3/3|

局部OPTIMAL只指当前保留窗口/作用域下最优，全量OPTIMAL才是对应全部后缀域的最优；不把状态标签直接当作一般等价证明。每组两流程共享完全相同输入、权重和25秒预算；热启动包含种子获取，不免费提供解。三轮为同快照计时重复，无统计显著性。不同策略的实际快照时间/源状态不同，不跨快照比较目标值；不能把物理等待改善说成数学求解器必然更优。

[完整逐轮结果](/home/yhc/clinic_planning_ws/verification/clinic_prefix/comparison_a2/summary.json)。

## 动画与执行时间线

三面板回放按各轮实际发现迟到时刻对齐，用先前实测Gazebo位姿采样，不插值计划路径。每轮已有任务区间包括导航、计划等待、服务和清空，不意味着区间内一直移动；深色段是实际服务。

[三策略动画MP4](/home/yhc/clinic_planning_ws/verification/clinic_prefix/media_a2/comparison_replay.mp4) · [GIF](/home/yhc/clinic_planning_ws/verification/clinic_prefix/media_a2/comparison_preview.gif) · [执行时间线](/home/yhc/clinic_planning_ws/verification/clinic_prefix/media_a2/execution_comparison.png)

- `prefix_barrier_a2`：[完整动画](/home/yhc/clinic_planning_ws/runs/prefix_barrier_a2/trajectory_replay.mp4)、[资源区间](/home/yhc/clinic_planning_ws/runs/prefix_barrier_a2/resource_occupancy.png)、[独立审计](/home/yhc/clinic_planning_ws/runs/prefix_barrier_a2/independent_audit.json)。

- `prefix_local_a2`：[完整动画](/home/yhc/clinic_planning_ws/runs/prefix_local_a2/trajectory_replay.mp4)、[资源区间](/home/yhc/clinic_planning_ws/runs/prefix_local_a2/resource_occupancy.png)、[独立审计](/home/yhc/clinic_planning_ws/runs/prefix_local_a2/independent_audit.json)。

- `prefix_full_warm_a2`：[完整动画](/home/yhc/clinic_planning_ws/runs/prefix_full_warm_a2/trajectory_replay.mp4)、[资源区间](/home/yhc/clinic_planning_ws/runs/prefix_full_warm_a2/resource_occupancy.png)、[独立审计](/home/yhc/clinic_planning_ws/runs/prefix_full_warm_a2/independent_audit.json)。

- `prefix_carry_a3`：[完整动画](/home/yhc/clinic_planning_ws/runs/prefix_carry_a3/trajectory_replay.mp4)、[资源区间](/home/yhc/clinic_planning_ws/runs/prefix_carry_a3/resource_occupancy.png)、[独立审计](/home/yhc/clinic_planning_ws/runs/prefix_carry_a3/independent_audit.json)。

## 失败和审计数据来源

180秒补充首轮prefix_carry_a2发现空闲已携货状态残留上一项取货record，误把其服务时刻用于未派发交付，发生非预期预测过期重投影。发现后主动中止并保留部分结果，不记成功。修正为仅使用身份匹配的当前任务记录，未派发交付按后缀源位置、可用时刻和行驶时间预测；新增审计即使预测撤销也禁止未派发任务携带旧服务证据。修正版prefix_carry_a3重新冷启动，不与主三轮混合计时。载货轮最终派生指标也补齐空闲携货的交付承诺，采用最终独立审计的两项承诺集合；不改原始执行记录。三个主快照修正前后投影逐字段一致，原三轮源哈希及执行记录保持原样。见[修正与差分回放](/home/yhc/clinic_planning_ws/verification/clinic_prefix/idle_cargo_fix/replay_checks.json)及[补丁](/home/yhc/clinic_planning_ws/verification/clinic_prefix/idle_cargo_fix/prefix_contract.patch)。

离线历史快照检查确认原后缀存在行驶/返回约束残差，投影局部和热启动全量均得到通过约束校验的最优解；预测没有写入实际完成字典，过期候选被拒绝，完成记录的执行者异常被识别。另有前缀合并/过期拒绝测试。见[快照检查](/home/yhc/clinic_planning_ws/verification/clinic_prefix/preflight_v2/summary.json)和[运行器合并检查](/home/yhc/clinic_planning_ws/verification/clinic_prefix/preflight/runtime_merge_checks.json)；这些离线拒绝测试不能写成现场发生过预测过期。

首轮`prefix_local_a1`在投影提交后出现TF时效0.65–0.82秒，到达守卫正确拒绝。主要嫌疑是每个回调重复深拷贝/TF查询造成队列积压，未独立证明所有传输根因。修正为10Hz轻量检查，未改变0.5秒时效、定位发布器或服务守卫。失败原始日志保留；正式三策略执行源哈希一致。

`prefix_local_a2`初次审计因历史对象共享引用失败，物理运行实际完成。控制器当前计划重定时会改动其历史视图；每阶段原始worker输出及提交追加日志均未修改且严格一致。`prefix_result_io.load_result`只读物化不可变求解见证用于审计/画图，记录`witness_reconstruction.json`哈希与变更字段。原始结果/轨迹/初次审计保留，不放宽数学约束来通过。

[TF失败诊断](/home/yhc/clinic_planning_ws/verification/clinic_prefix/tf_lag_a1_diagnosis.json) · [历史见证重建](/home/yhc/clinic_planning_ws/runs/prefix_local_a2/witness_reconstruction.json)。

## 结论与仍需完成

本轮能支持：执行状态改变使接受计划失效后，保留当前动作/取送承诺，在其继续执行时投影并修复后缀，且使修复任务实际完成。是否更局部以实际释放集/窗口为准；扰动变大时范围可以扩到全部后缀，不能强求始终很小。

尚不足以宣称普遍算法优越或新颖性已经成立：只有一个主场景三策略各一轮与一个更大扰动载货补充轮，没有多规模/多种子/外部最近方法统计；共享通道/终端资源、活动监护中途、真实定位/识别、能耗/充电、预测失效的一般可恢复性仍待研究。35秒准备余量及前缀预测保守度也需消融。

## 变更、保护和复现

项目内变更：本benchmark、`docs/reviews/clinic_execution_prefix_repair_contract_2026-11-13.md`、文档/benchmark索引、`docs/worklogs/worklog_2026-11-13.md`。独立工作区新增prefix运行器、模型/校验、只读结果物化、审计、批次/恢复、同输入对照和绘图工具；新增源码与辅助脚本哈希清单见[变更清单](/home/yhc/clinic_planning_ws/verification/clinic_prefix/new_files_manifest.json)；完整说明见[README_CLINIC_PREFIX.md](/home/yhc/clinic_planning_ws/README_CLINIC_PREFIX.md)。

保护快照711个原文件哈希0变化。原生Clinic、旧验收和项目规划主链未改。

[最终验收清单](/home/yhc/clinic_planning_ws/verification/clinic_prefix/final_acceptance.json)，包含全部约束审计、24次同输入求解、媒体校验、链接和进程清理。

```bash
cd /home/yhc/clinic_planning_ws
./run_clinic_reference.sh
# 另一个终端（新输出目录）：
./run_prefix_episode.sh --strategy prefix_local --localization reference --parking separate_bays --arrival pose_handoff --mode event --changes hold_resource --reference runs/aligned_reference_v3_normal/result.json --out runs/my_prefix_trial
# 同一轮第三终端：
./run_aligned_delay.sh runs/my_prefix_trial --delay 90
```
