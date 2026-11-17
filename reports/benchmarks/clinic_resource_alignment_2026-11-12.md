# Clinic共享服务区占用对齐、状态反馈与局部修复实测

日期：2026-11-12。本轮目标：对齐MILP与真实执行的资源占用定义，核查旧148秒排队；在独立Clinic入口中验证“变化反馈→原计划失效→影响范围→MILP修复→实际恢复执行”。原生Clinic、已有hospital_execution入口/验收结果和项目规划主链保留，不接实车。

## 模型和执行口径

旧入口在远程导航出发前即获取目的服务点租约，MILP却主要约束服务区间。旧算例r2_N3在400.40s申请DR，548.36s才获准出发，排队147.96s；实际交付开始697.10s，晚于计划598.14s。

新入口把任务j的服务开始/结束记为s_j、f_j，局部接近/驶离预算记为A_j、E_j，资源占用定义为 **[s_j−A_j, f_j+E_j]**。相邻机器人任务使用 **E_u+T(驶离点_u,等待点_v)+A_v** 行驶先验；资源停用窗口用“完整占用在窗口前或后”的二选一约束。所有方法共享同一模型、输入、变化代价和独立约束检查。

实际执行依次为：无租约导航至等待点→等待计划准入时间→现场申请租约→局部接近→稳定到达→独立服务启动/完成反馈→导航至驶离点→归还确认。实际租约不会因计划时间已到就自动失效。服务位置/角度验收仍为0.20m/0.30rad；虚拟等待/驶离点采用0.30m区域，另核查真值距服务中心≥1.50m、离散静态障碍/机器人间距。本报告下方三轮采用**显式的仿真真值定位条件**：由Gazebo实际位姿与实时轮式里程计计算map→odom，AMCL不广播TF；Nav2仍驱动物理机器人，雷达、导航、租约及服务反馈照常运行，没有传送机器人。此条件隔离定位误差，用于研究内容三的已知状态规划实验，不证明AMCL或实车定位性能。几何审计与控制使用同一真值来源，独立的是检查代码和反馈链，不能声称测量来源独立。

首次响应预留30仿真秒计算缓冲，修复快照中机器人可用时间来自反馈。为产生明确的状态变化，初次受控延误将r3可用时刻在原计划基础上推迟30秒；实际静止时间还包含原规划等待。后续另在一次真实巡检服务期间，延迟下一段导航90秒，验证执行偏差能否触发再次修复。上述等待均单独计入，不当成求解性能收益。

动态v6到达流程：在线TF/里程计/雷达新鲜，距离≤0.12m持续≥0.7秒→明确取消导航（状态5保留）→实际停稳→复用Nav2 Spin校正朝向→原0.20m/0.30rad、稳定0.7秒守卫。Spin失败/超时拒绝服务；不把取消重写为导航成功。额外Spin与导航目标分开计数。

在线预算可行解提交是v4起的扩展，必须独立完整校验并重验提交时状态，保留FEASIBLE_BUDGET和界差。旧v3解均为OPTIMAL，不触发该分支。另补显式监护结束期限，已有10份见证均仍可行；已证最优解在收紧后仍可行，故同输入/范围最优值保持。源版本分别留存，不声称全部源码哈希一致。[期限补充](/home/yhc/clinic_planning_ws/verification/hospital_alignment/monitor_deadline_addendum.json)。

详见[数学与执行契约](/home/yhc/kaiti_yolopose_framework/docs/reviews/clinic_resource_alignment_and_repair_contract_2026-11-12.md)。本轮没有改进SLAM、Nav2、底盘控制或真实人体识别。

## 三类实际运行

|条件：理想定位|服务数|导航目标数（不含Spin）|仿真秒|运行墙钟秒|最大服务位置误差m|累计求解流程墙钟秒|完整审计|
|---|---|---|---|---|---|---|---|
|常态|16|37|838.38|934.40|0.0992|2.814|通过|
|跌倒|20|43|1075.61|1221.50|0.0990|6.383|通过|
|跌倒＋状态/资源/后续延误|20|43|1269.15|1372.53|0.1001|22.719|通过|

AMCL条件单独保留：`aligned_normal_final`通过16项服务/37次导航，766.15仿真秒；`aligned_event_final`虽完成20项服务/43次导航，但PW7最大误差0.238855m超出0.20m，**完整审计失败**，不计入本表通过轮。

三轮服务任务、地图和基础机器人参数相同，但不是完全相同执行条件：常态/跌倒v3使用原终点和直接Nav2到达；动态v6采用XL/PDR/PR分离终点及位置交接＋Spin。v4在20项服务后返场会车失败，v5因M1振荡错过启动期限，均未计为通过。分离终点是场景修正，位置交接是执行适配，不能当作通道算法或创新；三轮总耗时不能作匹配效率对照。各轮按独立域/分区串行冷启动，原始输入、源文件哈希、协议、动作、服务、健康与资源反馈均保存在各轮目录。导航数量包含等待、服务、驶离和终端动作，不能与旧版19/23次动作按次数直接比较。仿真时间与客户端墙钟时间分开记录。

|运行|到达方式|明确位置交接取消数|额外Spin动作数|
|---|---|---|---|
|aligned_reference_v3_normal|nav2|0|0|
|aligned_reference_v3_event|nav2|0|0|
|aligned_reference_v6_dynamic|pose_handoff|32|30|

## 原148秒排队与等待分类

|运行|申请后最大资源排队s|最大入口等待s|累计入口等待s（跨机器人）|累计任务前空闲s（跨机器人）|
|---|---|---|---|---|
|aligned_reference_v3_normal|0.000|47.02|206.07|37.83|
|aligned_reference_v3_event|0.000|47.09|226.84|113.55|
|aligned_reference_v6_dynamic|0.000|46.03|154.46|593.82|

资源申请后的排队、到入口后的计划等待、上一事务清空后的出发前等待分开统计。旧轮与新轮的接近/驶离路线、停车及初始计划口径不同，历史数字用于追溯旧故障，不是严格配对的算法加速比。总任务耗时同时报告；减少某类排队不能替代整体效率证明。

|运行|完整租约数|最大提前进入s|最大超出计划清空s|最小机器人中心距m|最小静态障碍中心净空m|
|---|---|---|---|---|---|
|aligned_reference_v3_normal|9|0.010|0.000|0.748|0.500|
|aligned_reference_v3_event|10|0.000|0.000|0.737|0.500|
|aligned_reference_v6_dynamic|10|0.000|0.000|0.935|0.500|

实际共享资源间隔逐对满足2秒缓冲；所有服务先稳定到达再启动、驶离后释放。上述净空来自离散采样/圆形近似，不是连续时间形式化碰撞证明；提前或迟清空为对任务出发时接受包络的偏差。

## 局部修复具体改了什么

首次受控变化后的任务数为13；种子为`{"r3_N2": ["actual_ready_or_source_infeasible"], "r3_N5": ["resource_availability_overlap"], "r2_N3": ["resource_availability_overlap"]}`。最终释放7项，保留6项；扩展次数0。

释放：`r2_N2, r2_N3, r2_N4, r3_N2, r3_N3, r3_N4, r3_N5`；范围外固定开始时刻：`E1_deliver, E1_monitor, E1_pickup, r1_N2, r1_N3, r1_N4`。

实际已完成常态任务相对初始归属的换机数为2：`r3_N5, r2_N4`。事件新角色分配与既有任务换机分别统计；零换机不能称为已验证跨机器人移交。

实际提交局部解已证明当前范围最优，目标值1585.402800、范围内最优性界差为0；

在线预算25秒，输入完整校验与提交时状态/时效校验均须通过。范围内最优不等于全范围最优。

`repair_plan`原计划完整约束检查失败：

|任务|原因|旧计划与新边界|违例|
|---|---|---|---|
|r3_N2|r3源状态|旧开始317.45，最早可达347.45|缺口30.00s|
|r3_N5|DR不可用|旧占用[721.45,776.45]，停用[719.45,866.45]|重叠55.00s|
|r2_N3|DR不可用|旧占用[778.45,838.45]，停用[719.45,866.45]|重叠60.00s|

`feedback_repair_1`原计划完整约束检查失败：

|任务|原因|旧计划与新边界|违例|
|---|---|---|---|
|r1_N4|r1源状态|旧开始767.45，最早可达1115.24|缺口347.79s|
|r3_N4|r3源状态|旧开始492.45，最早可达1007.24|缺口514.79s|

`local_impact`以实际源状态无法兑现的旧开始时刻、资源占用与新增停用窗口的冲突为种子，沿任务依赖、原机器人顺序、共享资源先后传播，并闭合取送对。范围外固定执行者、相对顺序及开始时刻；持续监护的可变结束仍受覆盖约束约束。范围不是最小影响集的证明，必要时会扩展。

首次事件响应仍使用已有结构保留策略：保持普通任务归属/相对顺序，允许整体调整时刻。它与后续“范围外开始时刻固定”的局部修复不同。OPTIMAL仅是当前求解范围内的最优状态，不能写成全范围最优或最优实际执行。

|阶段|释放任务数|剩余任务总数|范围外固定开始数|
|---|---|---|---|
|normal_plan|0|16|0|
|verify_plan|1|1|0|
|response_plan|3|13|0|
|repair_plan|7|13|6|
|feedback_repair_1|4|4|0|

后续独立执行延误在r3_N2实际服务期间注入，阻止下一段导航至预定出发时刻后90秒。请求仿真时刻347.71，解除时刻453.45；健康ACK、停止里程计、物理位置和后续迟到/再次失效均由完整审计检查。修复后剩余任务全部完成。若反馈阶段释放了全部剩余任务，它属于范围扩展后的重规划，不包装成“小范围仍保持”。

本轮明确的代价是：TR完成迟到79.20s在488.65s发现，直到921.24s才取得安全快照，中间等待**432.59s**。这是当前全体安全边界造成的等待，不能掩盖为求解时间；其中包含已取货配送等待DR窗口的执行承诺。下一步应冻结仍在执行的承诺前缀，允许其余机器人同时修复，而非全体等待。

当前安全边界会等待各机器人完成当前承诺，已取货的普通任务先完成交付；空载巡检机器人必须离开共享驶离区再等待。该规则避免挡住另一台机器人的交付出口，也可能扩大影响范围。没有验证任意行进位置或持续监护中途的抢占修复。

本轮物理闭环的释放范围使用单体MILP求解；分解求解只做下述同快照离线对照。下列五流程及热启动流程没有分别执行完整Nav2场景，不能从这些时间推导各策略的实际导航总耗时。

## 同一实际快照上的算法对照

|方法|三轮状态|三轮目标值|求解墙钟中位数s|释放数|归属改变数|开始时刻改变数|
|---|---|---|---|---|---|---|
|full_replan|FEASIBLE_BUDGET,FEASIBLE_BUDGET,FEASIBLE_BUDGET|2587.410800/2587.410800/2587.410800|28.1822|13/13/13|5/5/5|10/10/10|
|legacy_local_repair|FEASIBLE_BUDGET,FEASIBLE_BUDGET,FEASIBLE_BUDGET|2587.410800/2587.410800/2587.410800|28.1621|13/13/13|5/5/5|10/10/10|
|local_impact|OPTIMAL,OPTIMAL,OPTIMAL|1585.402800/1585.402800/1585.402800|11.1634|7/7/7|1/1/1|5/5/5|
|same_scope_monolithic|OPTIMAL,OPTIMAL,OPTIMAL|1585.402800/1585.402800/1585.402800|11.1188|7/7/7|1/1/1|5/5/5|
|same_scope_decomposition|OPTIMAL,OPTIMAL,OPTIMAL|1585.402800/1585.402800/1585.402800|8.9664|7/7/7|1/1/1|5/5/5|

|方法/轮次|目标下界（含常数）|相对界差|
|---|---|---|
|full_replan/0|1418.810900|0.4516|
|legacy_local_repair/0|1418.810900|0.4516|
|legacy_local_repair/1|1418.810900|0.4516|
|full_replan/1|1418.810900|0.4516|
|full_replan/2|1418.810900|0.4516|
|legacy_local_repair/2|1418.810900|0.4516|

全部返回incumbent完整校验：`True`；有效返回数`15`；未返回有效解的轮次`[]`。原始求解日志/完整逐轮指标见[同快照比较](/home/yhc/clinic_planning_ws/verification/hospital_alignment/reference_v6_comparison/summary.json)。算法时间不含机器人运动；不以不同范围目标值差异证明求解器更优。

全量MILP释放全部任务；旧local_repair只以新增任务作为初始种子，本轮无新增任务的状态/资源快照可能使其范围为空，随后全量回退；新影响域修复显式处理状态/资源违例。此差异针对当前项目实现，不声称Calvo或TAPF-PC也只支持任务插入。

同范围单体/分解使用完全相同的模型、范围和目标，分开观察结构保留与分解求解。三轮交错计时是同一快照上的计时重复，不是三个独立场景或统计显著性证明。本节每方法每轮预算30墙钟秒，在线入口预算25秒；有限预算的可行incumbent必须通过完整约束校验，并与已证明OPTIMAL的结果区分。

|补充流程|三轮状态|目标值|墙钟中位数s|换机数|时刻改变数|热启动接收且校验通过|
|---|---|---|---|---|---|---|
|免费提供局部解的诊断|FEASIBLE_BUDGET,FEASIBLE_BUDGET,FEASIBLE_BUDGET|1558.407600/1558.407600/1558.407600|28.091|1/1/1|9/9/9|True|
|实际局部构造＋剩余预算全量搜索|FEASIBLE_BUDGET,FEASIBLE_BUDGET,FEASIBLE_BUDGET|1558.407600/1558.407600/1558.407600|28.120|1/1/1|9/9/9|True|

第一行免费使用已知局部解，时间不含该解获取，只作搜索设置诊断。第二行每轮实际先构造局部解，再用30秒总预算的余量进行全量热启动，计入局部构造、建模和全量搜索；未做物理执行。两项均记录全矩阵可行MIP start与独立语义检查。[端到端完整结果](/home/yhc/clinic_planning_ws/verification/hospital_alignment/reference_v6_warm_e2e/summary.json)。

补充全量热启动获得比局部1585.4028更低的目标值，但仍为预算可行解，并改变更多开始时刻。未热启动全量CBC的差解不能当成全局最优基准；本例呈现保留承诺、目标质量与求解时间的折中，不证明局部方法普遍优于全量方法。

资源约束反例：仅服务区间互斥时，两任务完整占用可为[0,25]与[7,32]，仍相互重叠；完整模型改为[0,25]与[27,52]，满足2秒间隔。[原始反例](/home/yhc/clinic_planning_ws/verification/hospital_alignment/phase_counterexample/result.json)。这说明原项目模型缺项，不代表现有研究普遍忽略该问题，也不能单独作为创新点。

## 动画和时间证据

- `aligned_reference_v3_normal`：[动画MP4](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_normal/trajectory_replay.mp4)、[GIF](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_normal/trajectory_preview.gif)、[实际路线](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_normal/actual_routes.png)、[资源时间图](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_normal/resource_occupancy.png)、[完整审计](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_normal/independent_audit.json)。
- `aligned_reference_v3_event`：[动画MP4](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_event/trajectory_replay.mp4)、[GIF](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_event/trajectory_preview.gif)、[实际路线](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_event/actual_routes.png)、[资源时间图](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_event/resource_occupancy.png)、[完整审计](/home/yhc/clinic_planning_ws/runs/aligned_reference_v3_event/independent_audit.json)。
- `aligned_reference_v6_dynamic`：[动画MP4](/home/yhc/clinic_planning_ws/runs/aligned_reference_v6_dynamic/trajectory_replay.mp4)、[GIF](/home/yhc/clinic_planning_ws/runs/aligned_reference_v6_dynamic/trajectory_preview.gif)、[实际路线](/home/yhc/clinic_planning_ws/runs/aligned_reference_v6_dynamic/actual_routes.png)、[资源时间图](/home/yhc/clinic_planning_ws/runs/aligned_reference_v6_dynamic/resource_occupancy.png)、[完整审计](/home/yhc/clinic_planning_ws/runs/aligned_reference_v6_dynamic/independent_audit.json)。

动画为Gazebo实测位姿二维回放、实际服务/资源/健康反馈；不插值规划路径。动态轮在原计划失效与修复提交处加入定格说明，字幕明确标示，真实仿真时刻不变。资源时间图同时展示任务出发时接受的计划占用包络、实际租约、停用窗口和失效旧预约；不是仅用空间路线代替资源验证。

## 保留的失败记录

- `aligned_normal_a1`：16项服务反馈返回，但末次G1发生定位偏差，终端导航失败，真值条件不通过；未计为通过。移开占用后续服务通路的停车点，增加AMCL束数/粒子数，将驶离朝向沿通道设置。
- `aligned_event_a1`、`aligned_dynamic_a1`：为修正初始清空区等待会挡住后续交付的问题，提前停止；保留记录。现采用统一清空区退出规则。
- `aligned_dynamic_a2`：局部数学解有效；旧提交检查把时钟推进导致的目标常数变化当作失效。修正为“原快照解/目标校验＋提交时可行性校验”。[实际失败快照回归](/home/yhc/clinic_planning_ws/verification/hospital_alignment/commit_clock_diagnosis.json)
- `aligned_dynamic_a3`：三机控制器已激活，但r3雷达3秒观测为0条，map→odom未形成，就绪超时；未当作规划失败。改为串行冷启动、新域/分区。[诊断](/home/yhc/clinic_planning_ws/verification/hospital_alignment/startup_dynamic_a3_scan_diagnosis.json)。并发渲染原因未被单独隔离证明。
- `aligned_event_a2`：r3返向PW3停车与r2配送在窄口迎面，Nav2未恢复，17项服务后失败。最终r3停车改到右侧服务区南侧PDR，避开该返场冲突。**这不是共享通道算法已经解决的证据。**
- `aligned_event_a3`：协调器READY先于执行器收到相应状态，取货被protocol_guard_not_ready拒绝；增加执行器的协议接收ACK后，才允许发送启动请求。保留[ACK回归](/home/yhc/clinic_planning_ws/verification/hospital_alignment/protocol_ack_regression.json)。

这些是实验/执行适配修正，不能把接口修复、参数调整或场景安装写成算法创新。所有预检、失败轮与正式验收轮目录分开。

## 六项问题的边界

|问题|本轮证据|尚未覆盖|
|---|---|---|
|局部与全量区别|释放/冻结变量及任务范围明确，同快照对照|多规模、多种子、多扰动的普遍质量/时间结论|
|动态性仅任务插入|任务事件＋可用时刻变化＋资源停用＋执行器延误|硬件故障、人员动态障碍、未知时长阻塞|
|共享通道不足|共享服务区进入/清空、实际租约和时间图|共享通道/交叉口弧段预约；已保留窄口失败|
|缺执行反馈|独立健康ACK、实际迟到、旧计划失效检查及再次求解|任意运动位置、活动监护中的承诺投影与修复|
|缺消融对照|同模型五流程、同范围求解、资源缺项反例|各策略在多次Gazebo闭环的公平统计比较、外部最近方法|
|状态展示不完整|机器人等待/接近/服务/清空、事件状态、资源窗口、修复范围|真实识别、真实取放与不同硬件能力|

本轮足以支持一个有边界的系统证据：在已知定位的Clinic任务级导航实验中，状态/资源变化使原计划违反明确约束，显式影响范围修复保留部分开始承诺，调整后恢复实际执行；后续执行偏差又能经反馈触发再次修复。它仍不足以单独成立普遍算法创新或优于最新工作的结论：尚需多实例/多扰动的闭环公平对照、共享通道建模与外部近似范围方法比较。价值应落在受影响承诺的建模、修复范围与可执行性恢复，而非安装仿真、使用MILP或接口修复。

## 变更及复现

独立工作区新增文件清单与手动命令见[README_CLINIC_ALIGNED.md](/home/yhc/clinic_planning_ws/README_CLINIC_ALIGNED.md)。主入口分别为AMCL的run_clinic_aligned.sh、理想定位的run_clinic_reference.sh，运行器为run_aligned_episode.sh；模型/校验是aligned_contract.py、aligned_tasks.py、aligned_solver.py；运行反馈是aligned_resources.py、aligned_health.py、aligned_service_worker.py；另有审计、动画、资源时间图和对照脚本。原医院入口保留。

项目内只增补本报告、契约评审、索引与工作日志。保护快照包含465个原文件，哈希变化为0；三轮基础配置/服务任务一致、运行时终点变体检查通过。

```bash
cd /home/yhc/clinic_planning_ws
./run_clinic_reference.sh
# 另一终端，使用新的输出目录：
./run_aligned_episode.sh --localization reference --arrival pose_handoff --parking separate_bays --mode event --changes none --reference runs/aligned_reference_v3_normal/result.json --out runs/my_event
# 受控动态轮用 --changes hold_resource，并在该域的另一终端运行：
./run_aligned_delay.sh runs/my_dynamic --delay 90
./stop_clinic_reference.sh
```

最终批量入口run_reference_suite_v6.py复用已审计v3常态/跌倒并单独重跑v6动态；postprocess_reference_suite_v6.py处理三轮证据。使用固定正式目录防止覆盖；重做需先使用新输出命名。G1的routine_ready目前是可改派的1秒点位服务，不等于原配送车完成回补；若要求原车返回，应另加执行者绑定。分离终点是有限回合临时终点，未验证长期停车与未来任务共存。本轮未启用电量消耗、SOC/充电、硬件故障或移动行人；能力差异是任务层配置，三台物理模型相同。没有启动实车或修改现有规划主链。最终实验进程按所属分区关闭。

补充失败保留：`aligned_reference_v3_dynamic`在25秒预算内已有可行incumbent但旧入口只接受OPTIMAL，因而停止；不能说该快照不可行。离线复核的206项约束通过、最大残差约2.3e-13，仍有约4.88%日志界差。该失败轮还在PW2经历了目标附近停滞，Nav2自行恢复后才到达301秒；不能据另外轮次成功宣称末端停滞已完全排除。v4仅提交独立校验与提交时效检查均通过的可行解，并保留FEASIBLE_BUDGET状态。[兼容性核查](/home/yhc/clinic_planning_ws/verification/hospital_alignment/budget_acceptance_compatibility.json)。reference_v2在约0.05m的到达边界附近持续旋转，保留端点/命令诊断并停止；最终reference_v3将Nav2到达容差设为0.10m/0.10rad，独立服务标准不变。首轮reference在根命名空间发布各机器人TF，未通过严格节点命名空间审计；现为每机器人独立节点，原检查不变。最终通过记录为`aligned_reference_v3_normal`、`aligned_reference_v3_event`和`aligned_reference_v6_dynamic`。动态v4完成20项服务后，两机返场在左窄廊迎面停滞并NAV_TIMEOUT，未通过整轮验收；见[失败诊断](/home/yhc/clinic_planning_ws/verification/hospital_alignment/terminal_v4_diagnosis.json)。v5更换终端点后又在M1目标附近发生导航振荡，监护启动期限已过，主动停止并保留[诊断](/home/yhc/clinic_planning_ws/verification/hospital_alignment/arrival_stall_v5_diagnosis.json)。v6进一步采用显式位置交接和Nav2 Spin，不放宽服务守卫；不能声称分离终点解决了通道算法问题。AMCL跌倒轮定位超限已在上文单独报告。
