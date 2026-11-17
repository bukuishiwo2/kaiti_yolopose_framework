# Clinic L1医院新路线实际执行与事件—MILP接入

日期：2026-11-12。目标：让三台TurtleBot4沿冻结医院语义方案实际导航、稳定到达并完成服务，再接入已有脚本事件、event-task/v1和独立MILP，保存真实执行轨迹动画。原生RMF演示、旧算例、项目规划主链均保留。

## 执行范围

此前的[语义点位验收](clinic_hospital_semantics_2026-11-10.md)证明了几何、视线和全局路径条件；本轮额外启动Gazebo物理、官方底盘控制器、各机AMCL/Nav2与服务执行器，验证真正运动后的反馈。

运行入口独立位于 `/home/yhc/clinic_planning_ws`，ROS_DOMAIN_ID=79、Ignition分区 `clinic_hospital_tb4_yhc`。使用原Clinic静态碰撞体及官方TurtleBot4 Lite/Create3，三机各有隔离的TF、定位、导航和控制器。没有重新建图或改造机器人模型。

|机器人|常态路线|服务语义|
|---|---|---|
|r1|DL→PW2→TL→PW1→DL|左护理站、候诊/诊疗通道巡检|
|r2|G1→DL→G1→DR→G1|准备交接位取货，分别送至左右护理站，再返回准备位|
|r3|DR→PW3→PR→TR→PW7→DR|右护理站、候诊/诊疗通道巡检|

机器人直接生成在DL/G1/DR工作起点；每轮结束分别驶至XL/XG/XR，实际离开共享服务点后才释放资源。这次不包含从车库出发、回库和充电。G1是BOH ADMIN邻近的研究性交接接口，不将原清洁物资间当作医疗物资库；服务时间为缩短的实验停留时长。

## 导航和反馈设计

- 定位使用含家具的原碰撞地图；全局和局部代价地图另外接收医院语义禁止穿越区域，避免穿诊疗室抄近路。
- 复用Navfn和Nav2 Regulated Pure Pursuit（RPP）路径跟踪。它们是部署组件，不作为本文运动规划创新。
- Nav2成功之后，还须在目标位置误差≤0.20m、角度误差≤0.30rad、线速度<0.04m/s、角速度<0.06rad/s及TF/里程计/雷达新鲜度<0.5s下连续稳定≥0.7s。
- 由独立服务节点再次检查条件，返回唯一启动/完成反馈；执行器不能用“发送了导航目标”替代“已到达/已完成”。若Nav2成功后实际停稳的定位姿态仍超出服务守卫，最多向同一目标重新导航2次，逐次记录动作；仍不满足就明确超时报错。此处在线使用定位/里程计，Gazebo真值只用于事后审计，未用真值作弊闭环。
- G1、DL、DR采用逐点FIFO资源租约。实际接近前获取资源，服务完成并驶离后释放。其他机器人代价地图临时屏蔽被占用服务点。
- 普通取送及事件取送均要求同一机器人、直接相邻的取/送服务，不能在中间执行另一项服务。服务是任务级交接，不包含实体抓取。

## 事件与MILP边界

E1位于第二候诊区，t=15s注入抽象确认跌倒观测，无摔倒动画。事件存续期间向代价地图发布人体区域安全屏蔽。

流程是：常态运行→完成当前承诺（已取货先交付）→三机在实际服务位静止形成快照→核验分配MILP→实际到达V1并取得脚本核验反馈→联合响应MILP→监护M1、G1取货、H1交付及剩余常态任务→事件结束、完成后续路线。

第一阶段只分配核验任务，常态积压暂时保持；第二阶段才联合分配并排程全部待执行常态任务和响应任务。输入使用各机器人实际到达的锚点，提交时再次检查当前时间、协议版本及完整MILP约束。服务实际启动仍由到达、依赖和协议反馈门控。

独立求解进程复用既有MILP后端，并额外加入普通/事件取送同机器人及相邻弧约束。未修改原后端和项目规划主链。这里没有启用电量消耗，也不声称由LTL自动合成任务。结构保留策略的`OPTIMAL`仅表示当前保留/扩展范围内最优，不是同范围以外的全局最优保证。三台底盘型号相同；camera/carry等差异是任务层能力可用性设置，并非验证了三种不同硬件。

这是稳定服务位边界上的动态任务重分配，尚不支持任意行进边上的抢占式重规划。资源实际占用包含接近/驶离时间，MILP中的资源区间与估计行驶时间仍是任务层近似；执行租约与反馈负责安全门控，计划时刻不等于实际时刻。

## 实际结果

**最终验收：`hospital_normal_v6`与`hospital_event_v2`均通过。两轮15份运行源文件/配置哈希完全一致；373份受保护的旧入口、旧算例和项目主链文件未改变。** [保护与配置一致性记录](/home/yhc/clinic_planning_ws/verification/hospital_execution/final_preservation.json)

|指标|常态整轮|事件整轮|
|---|---:|---:|
|实际服务完成|16/16|20/20（常态16＋事件4）|
|实际NavigateToPose动作|19/19|23/23|
|其中离开最终共享点的导航|3|3|
|同目标到达修正次数|0|0|
|全过程仿真时间|469.28s|877.46s|
|客户端墙钟时间，含等待就绪|499.62s|961.81s|
|稳定到达时最大Gazebo真值位置误差|0.143642m|0.134226m|
|稳定到达时最大真值角度误差|0.061161rad|0.065526rad|
|共享服务点最大同时占用数|1|1|
|实际获取/归还资源租约|9/9|10/10|
|抽样机器人中心最小间距|1.117667m|0.381886m|
|抽样语义障碍中心最小间距|0.350000m|0.390512m|
|抽样机器人0.17m圆盘至人体矩形最小间距|不适用|0.665364m（验收≥0.35m）|
|r1/r2/r3实际累计行驶距离|77.35/101.21/86.28m|86.50/135.69/86.00m|

导航动作数量包含原地目标的Nav2动作及最后驶离动作，并非每个动作都代表一段长距离行驶。实际位置/角度误差用于独立审计，在线导航与服务守卫没有读取Gazebo真值。两轮均未触发到达重试，因此重试分支未完成专门故障注入验收。

[常态完整结果](/home/yhc/clinic_planning_ws/runs/hospital_normal_v6/result.json)、[常态独立审计](/home/yhc/clinic_planning_ws/runs/hospital_normal_v6/independent_audit.json)；[事件完整结果](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/result.json)、[事件独立审计](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/independent_audit.json)、[逐服务反馈与误差表](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/actual_services.csv)。审计计数13837/26105包含逐位姿采样检查，不是同等数量的独立算例。最小间距是离散样本和圆盘近似，不等同于连续时间全3D碰撞证明。

### 事件过程、实际角色和约束

15.00s触发时，r1/r3正在导航，r2正在取货。到76.85s完成当前承诺后，6项普通服务已完成，三机停在PW2/DL/PW3；核验MILP在77.24s提交。核验实际于136.15–139.15s执行；随后响应MILP在141.67s提交，联合处理10项未完成普通任务及3项新响应任务。

|事件服务|机器人/点位|实际开始—结束（仿真s）|
|---|---|---|
|核验|r1 / V1|136.15–139.15|
|持续监护|r1 / M1|197.70–293.45|
|应急取货|r2 / G1|197.95–200.95|
|应急交付|r2 / H1|290.40–293.40|

监护与取送由不同机器人承担；实际监护覆盖完整取货至交付过程。所有普通前驱、取送同机器人及直接相邻关系、任务释放/期限/启动期限、协议反馈和实际共享服务点互斥通过审计；事件最终为COMPLETED，4项协议任务均为SUCCEEDED。

|机器人|事件前已执行的普通前缀|事件后接受计划（其后驶离共享点）|
|---|---|---|
|r1|DL→PW2|V1核验→M1监护→TL→PW1→DL|
|r2|G1取货→DL交付|G1应急取货→H1交付→G1普通取货→DR交付→G1准备|
|r3|DR→PW3|PR→TR→PW7→DR|

**本例普通任务换机数为0。** 结构保留范围保持普通任务的机器人归属及相对顺序，释放执行时间，分配新事件任务；未触发范围扩展。因此本例展示事件任务插入、角色分配和时间重排，不能称为“已展示普通任务跨机器人改派”或结构扩展优势。[完整计划前后与实际执行顺序](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/plan_comparison.md)

核验、响应求解完整流程墙钟时间分别0.510659s、2.766762s，总3.277421s；当前范围内目标值分别23.9、1586.2175。两阶段任务不同，不能比较其目标值大小来说明改进。完整原始数学约束、附加取送相邻约束与提交时版本/时间校验通过；该结果不是全范围单体MILP最优性或速度对照。[核验输入与结果目录](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/verify_plan)、[响应输入与结果目录](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/response_plan)

### 实测暴露的计划—执行偏差

r2普通右区交付在400.40s申请DR，因r3正在持有DR的接近/服务/驶离租约，直到548.36s才获准出发，排队147.96s。实际交付服务697.10s开始，而MILP计划598.14s，晚98.96s；最终返回准备位也晚53.36s。响应计划估计整轮结束829.14s，实际877.46s，晚48.32s。

原因是运行侧在出发前就申请共享点租约，覆盖完整接近和驶离；模型中的资源占用区间主要覆盖服务，两个范围不完全一致。运行门控维持了互斥，但产生额外等待；本轮期限充裕，所以没有硬期限违约。这是当前接入限制，不应包装成“已实现最优执行排程”。下一轮须加入安全接近/等待锚点或让资源区间与真实租约一致，并将阻塞与实际行驶时间更新返回任务规划。

### 实际轨迹动画

[事件实测MP4，73.25秒，12倍速](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/trajectory_replay.mp4) · [事件GIF预览](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/trajectory_preview.gif) · [常态实测MP4，39.25秒](/home/yhc/clinic_planning_ws/runs/hospital_normal_v6/trajectory_replay.mp4) · [常态GIF](/home/yhc/clinic_planning_ws/runs/hospital_normal_v6/trajectory_preview.gif)。视频1280×800、12fps；源数据哈希和采样说明保存在各轮animation_manifest.json，媒体核验见[media_verification.json](/home/yhc/clinic_planning_ws/verification/hospital_execution/media_verification.json)。

![事件响应过程的实测轨迹帧](/home/yhc/clinic_planning_ws/runs/hospital_event_v2/event_midframe.png)


## 失败记录与修正

1. `runs/hospital_normal_pilot`：地图服务器与生命周期激活后，代价地图尚未收到地图。相对topic被解析到costmap命名空间，手动结束试运行，0项服务完成。改为显式`/rX/semantic_map`，并将收到非空全局代价地图加入就绪条件。
2. `runs/hospital_normal_v2`：完成13项服务后，配送车在跨区直角转弯反复触发DWB“无进展”，最终NAV_FAILED。定位估计与Gazebo真值吻合，问题是路径跟踪局部停滞。保留失败日志；仅在新入口复用标准RPP并重跑，不放宽服务到达验收阈值。

3. `runs/hospital_event_v1`：核验MILP最优解通过任务层约束，但实际Navfn路径贴近人体Keepout边缘，RPP足迹碰撞检查拒绝通行，最终NAV_FAILED。为全局/局部Keepout追加标准InflationLayer（半径0.55m，衰减4），并用最终相同配置重新跑常态和事件。Nav2官方也说明了[Keepout与足迹检查需要配合膨胀层](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_filters/keepout_filter/)。本机Humble插件实际加载与后续运行是兼容性的验收依据。

4. `runs/hospital_normal_v4`：Keepout膨胀插件正常运行，但PW7定位估计误差约0.097m，实际真值误差约0.202m，超过预先设置的0.20m真值验收线。中止试运行，收紧Nav2自身xy_goal_tolerance从0.12m到0.05m；独立服务/真值验收阈值保持0.20m。保留该段轨迹和失败记录。

5. `runs/hospital_normal_v5`：收紧xy后，PW7导航返回成功时仍有约0.77rad/s转动，停稳后定位角误差约0.38rad，服务守卫拒绝启动并返回ARRIVAL_NOT_STABLE。收紧Nav2角容差到0.05rad、转向参考速度0.35rad/s、平滑器角速度上限0.5rad/s，增加最多2次同目标到达修正；没有放宽服务守卫。

`hospital_normal_v3`曾完成16项服务/19次导航（427.20s），但后续Keepout与停靠配置发生修正，因此不作为最终事件轮的同配置对照；最终采用v6/v2。

失败试验、正式试验与离线数学预检目录分开，未删除或覆盖失败记录。`math_preflight`仅用于检查模型可解，不能作为运动执行证据。

## 文件与复现

新入口及详细运行命令见 [README_HOSPITAL_EXECUTION.md](/home/yhc/clinic_planning_ws/README_HOSPITAL_EXECUTION.md)。本轮新增独立配置`config/hospital_execution/`、启动文件`launch/clinic_l1_hospital.launch.py`、运行/停止脚本、`tools/*hospital*.py`执行与审计/动画工具；原生及旧入口不变。

```bash
cd /home/yhc/clinic_planning_ws
./run_clinic_hospital.sh --headless
# 另一终端；输出目录必须不存在
./run_hospital_episode.sh --mode normal --out runs/my_hospital_normal
# 完成后停止并冷启动同一世界，再运行：
./run_hospital_episode.sh --mode event --reference runs/my_hospital_normal/result.json --out runs/my_hospital_event
/home/yhc/kaiti_yolopose_framework/.venv/bin/python tools/audit_hospital_execution.py runs/my_hospital_event
python3 tools/render_hospital_animation.py runs/my_hospital_event
./stop_clinic_hospital.sh
```

动画使用Gazebo真实位姿样本与服务/计划时间戳，二维地图上回放实际行进，非规划路径插值，也不是Gazebo三维录像。每帧选择已有真实样本，默认12倍速。

## 结论的适用范围与下一步

本轮验证新医院点位上的实际导航、到达—服务反馈、任务协议和MILP执行连接，属于研究内容三的系统可执行性证据；不能单独支持结构保留/分解求解优于对照方法。此前旧场景的策略比较不能直接当作本场景公平对比。

没有新增行人、移动病床或突发通道封堵；尚未证明人员密集环境的动态避障性能、临床适用性、真实人体识别、物资抓取或SOC/充电。本轮人体事件是脚本，核验结论也是脚本；巡检是导航停留服务，没有接入视觉检测。

后续先在相同新路线、控制器、事件与随机种子下跑同变化代价的全量重规划、局部修复、结构保留，以及“相同保留/扩展＋单体MILP”对照，再加入可控动态障碍及实际通行延误反馈；记录成功率、响应/完成时间、改派/改序、求解与全过程时间、实际到达偏差和阻塞恢复。当前部署不替代这组创新性实验。
