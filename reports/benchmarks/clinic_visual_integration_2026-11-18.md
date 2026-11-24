# Clinic真实视频驱动集成实测（2026-11-18）

## 目标与最终判断

保持既定三个研究内容。实际完成真实视频RGB发布、原YOLO Pose＋32帧LSTM、唯一event-task/v1、区域任务编译及受限三机执行，保留原MILP、Nav2、服务ACK和研究修复后端，不改旧S1或原有模式。

**已完成一个真实误报驱动的系统闭环：adl-01真实推理→稳定候选→核验任务→原MILP分配→实际Nav2及服务ACK→有来源的no_fall复核→事件关闭。三台机器人均实际完成常态任务。不是完整正例应急、监护/取送或床扰动修复验收。**

证据根目录：`/home/yhc/clinic_planning_ws/verification/visual_integration_2026-11-18_b1/`。全部为新目录；没有覆盖历史成功/失败结果、导入大体积历史日志或自动提交推送。

| 任务 | 状态 | 严格范围 |
| --- | --- | --- |
| A 限定相机诊断 | BLOCKED | 完成唯一一组有/无actor对照；原生帧连续，ROS接收不稳定；停止该分支，不作为主线前提 |
| B 真实视频ROS回放 | PASS | 4条联调视频、重复/中断/静默测试，真实模型；不代表独立准确率或实时吞吐验收 |
| C 唯一协议接入 | BLOCKED | 最小候选/核验/明确否定关闭已实际通过；取消/交接协议单测通过，在线取消ACK、监护与携货恢复未验收 |
| D 空间编译 | FAIL | A/B目标、entry/clear、旅行表、资源映射已变化；21次实际路径查询、6个点实际停靠成功；B布局占用后通往G1失败，不能宣布双区完整安全 |
| E 离线＋三机 | BLOCKED | 离线26项通过；A区真实负例核验闭环16项独立审计通过；正例监护/取送和床扰动NOT_RUN |
| F 三维分支接口/计划 | PASS | 两种位置来源隔离，接口及测试计划落代码/手册；实际RGB-D估计与误差实验NOT_RUN |

## A：限定相机对照

仅运行一组相同相机/简单场景的无actor、有actor对照，均加入原生transport计数。无actor：原生485帧、时间推进15.93秒，ROS仅1帧；有actor：原生422帧、ROS411帧，采集通过。原生传感/渲染均能连续产图，因此当前优先定位桥接/DDS/接收链不稳定，不能断言actor必然卡死，也未证明精确根因已修复。保留native_counts、ROS计数、仿真统计与cleanup；不再为此修改安装库或重复主线世界。

## B：真实ROS图像及模型证据

`run_clinic_video_ros.py`实际解码、发布`sensor_msgs/Image`，复用原PoseStreamNode的ROS图像解码/推理/发布方法，独立子类仅关闭outputs写入并指定原权重。源视频时间、发布单调钟、发布ROS时间戳、轮次与处理延迟分别保存。逐帧等待推理收据，回放尽力按30Hz定速，处理落后则延长回放；不是丢帧后假称实时30Hz。

首批`ros_replay_a1`共620帧（fall-01/adl-01各在A/B运行），4次原MILP均OPTIMAL、独立验证通过。每个案例只生成E1_verify：

| 视频 | 单次帧数 | 单次稳定阳性帧 | 首次稳定阳性/源秒 | 任务结果 |
| --- | ---: | ---: | ---: | --- |
| fall-01-cam0 | 160 | 61 | 3.300 | 核验任务，未直接扩展全部应急 |
| adl-01-cam0 | 150 | 5 | 4.833 | 如实保留误报，进入核验 |

扩展`ros_replay_repeat_gap_a1`：4条视频各重复2次，每次第70帧前中断1.2秒，重置模型缓存但保持事件身份；每案例末尾11秒无新观测。共1200帧、8次实际中断；10项行为审计通过。

| 视频 | 两次帧数 | 合计稳定阳性帧 | 任务 |
| --- | --- | ---: | --- |
| fall-01 | 160＋160 | 114 | 同一E1、仅核验 |
| adl-01 | 150＋150 | 10 | 同一E1、保留误报 |
| fall-02 | 110＋110 | 76 | 同一E1、仅核验 |
| adl-02 | 180＋180 | 0 | 无应急任务 |

这些计数是本次中断/缓存重置条件，不能与无中断数据拼成识别性能提升。静默时心跳没有续期位置，已有位置在TTL后失效。

**四条视频在本地urfall_pose_sequences.npz均为train划分**，且URFall是历史评估/调参域；input_manifest保存视频SHA和划分，全部明确independent_test=false。未把它们称独立测试集。

误报诊断：已实际查看adl-01采样图，人物从走入到下蹲，并非已标注跌倒。源MP4是左侧深度渲染＋右侧RGB拼接帧；沿用原完整输入、原最大bbox选择，未暗中裁图。逐帧日志发现主框在两侧切换36次，5个稳定阳性帧中也发生切换。它与下蹲姿态混淆是待检验原因，尚不能判定唯一根因。证据`adl01_review_contact.jpg`、`adl01_false_alarm_diagnosis.json`。没有修改0.6阈值、模型或训练数据。

## C/D：协议与位置一致编译

唯一桥接器把稳定且窗口有效的真实模型输出转换为候选；协议原`confirmed`表示候选稳定，不等于服务核验fall。score、stable、样本ID、来源与源时间保存在因果日志。模型非阳性按证据退化处理，不作为明确no_fall。重复播放不重复生成身份；不把不同来源拼成人体融合。

核验succeeded必须另有复核凭据。实际负例使用`adl01_explicit_review.json`：`operator_review`、`assistant_visual_review`、保存的原帧接触表以及既有ADL标签交叉核对。不是执行器按时间/服务成功自动判fall，也不是临床或独立新传感器诊断。

区域A复用V1/M1/H1；区域B新注册为DL/CDL/ADL；取货G1。B不是前轮相机点净空候选的自动沿用。编译精确匹配协议目标和服务锚点，同时改变MILP几何、原旅行表、资源、entry/clear；未知坐标拒绝而非覆盖V1。A/B两种位置都声明`video_source_registered`，不是RGB-D定位。

`offline_gate_a2`直接消费真实ROS模型日志：关闭语义、有效正例A/B、无效空间、真实负例候选，以及显式标记为离线ACK夹具的正/负核验后续，26项检查通过，7次原MILP调用均独立校验。离线ACK夹具不是实际服务反馈，不能用它证明正例执行。

空间资格检查失败完整保留：

- a1：21次实际Nav2路径查询通过；V1实际停靠/ACK成功后因测试驱动遗漏finishes字段终止。只修复测试驱动，不改原后端/守卫。
- a2：21次路径查询通过；V1、M1、H1、DL、CDL、ADL实际到达、服务ACK及相应资源阶段完成。之后R2前往G1的entry AG1持续无路径，原180秒路径等待到期报PATH_WAIT_TIMEOUT；清图恢复未解决，没有放松条件或凑通过。
- 失败时R1留在CDL，原keepout会保护静止同伴0.5米范围；初始路径查询通过、该占用状态下失败，与通道被静止同伴/清空位占用一致。尚无消融证明其唯一根因。一次只读costmap采样赶在清理后未取到数据（0样本），保留失败，不能声称已测得完整代价层因果。
- 驱动存在“完成当前job的同一tick可能派发下一个job”问题，已加完成检查修正；a2不能冒充严格逐项隔离实验，未重跑第三次资格世界。不能从a2推断所有并发停靠都安全。

仅从已成功的单项到达/资源/ACK证据签发A/B的VERIFY证书，绑定完整配置SHA，保留`overall_qualification_passed=false`、`concurrent_resource_qualification=false`。没有给monitor/pickup/deliver授权，未伪造双区总通过。

## E：实际三机负例核验闭环

`visual_false_alarm_a1`实际功能通过，接收2805帧，原始首轮记录保留。随后发现旧keepout不区分模型候选与核验成立，且CLOSED仍可能保留人体占用。此轮不作为修正后的完整口径。

新增独立视觉launch，仅替换一个keepout进程，原生Clinic不改：候选不会直接建立已确认人体几何占用；核验fall后使用事件坐标；CLOSED/COMPLETED移除；遮挡保持已确认占用。纯逻辑测试、22项launch动作构造检查及实际复验均完成。

最终使用`visual_false_alarm_a2`与`execution_audit_a2`：

| 实际任务 | 机器人 | 派发/仿真秒 | 完成/仿真秒 |
| --- | --- | ---: | ---: |
| C0_r1_W1 | R1 | 35.04 | 135.56 |
| C0_r2_W1 | R2 | 35.04 | 134.17 |
| C0_r3_W1 | R3 | 35.04 | 186.12 |
| E1_verify | R1 | 147.01 | 172.34 |

实际链：源视频4.833秒的真实稳定误报在Clinic约46.04秒创建候选；原MILP生成verify分配（R1），保留三机已发常态前缀；R1完成原常态后派发V1核验，真实Nav2守卫通过，服务started/succeeded ACK关联同一执行token（attempt=1、revision=1），显式no_fall复核关闭事件。最终协议只有E1:verify，无monitor/pickup/deliver；全程接收2810条模型观测，事件身份保持E1，结束186.12仿真秒。

**16项独立执行审计通过**：真实模型样本到候选的关联、无旧注入、三机真实执行、原到达/新鲜度/稳定及服务ACK、MILP任务目标与实际Nav2目标一致、MILP所有者一致、独立约束验证、token匹配、明确核验来源、负例无后续全应急及自有进程清理。

`visual_mask_a2`是另一个只读ROS订阅器：OPEN未核验和CLOSED时实际mask事件中心值均为0，审计通过，支持本次没有候选/关闭后的幽灵人体占用。只证明该单元格与本案例，不替代全局碰撞验证。

此处常态任务为既有首项4秒服务，核验保持原3秒。是独立4任务短集成，不是Fast/Standard计时实验；186.12不能用于声称原模式时间目标达成。正例全部应急、持续监护/携货在线取消ACK、B区并发资源与床扰动均未运行，**不得称完整123正例闭环已完成**。

## F、保护与交付

RGB-D分支未删除或被注册位置取代。`sensor_position_contract()`及[操作手册](../../docs/system_clinic_visual_input.md)保存Depth/CameraInfo/TF/各自时间戳、frame、有效性、协方差/误差字段，以及同步、单位、投影、过期、TF缺失、遮挡和身份关联测试计划。actual RGB-D NOT_RUN，无Gazebo真值冒充估计。

新增/修改代码：

- `src/kaiti_task_sim/clinic_visual.py`、`tests/test_clinic_visual.py`。
- `scripts/run_clinic_video_ros.py`、`gate_clinic_visual.py`。
- `scripts/qualify_clinic_visual_regions.py`、`certify_clinic_visual_regions.py`。
- `scripts/run_clinic_visual_execute.py`、`clinic_visual_world.py`、`clinic_visual_launch.py`、`clinic_visual_keepout.py`。
- `scripts/audit_clinic_visual_execution.py`、`audit_clinic_visual_mask.py`。
- `scripts/clinic_camera_counts.cc`；扩展既有`probe_clinic_visual_fall.py`的无actor/原生计数控制参数。
- 上述操作手册、本文及当天工作日志追加。

最终专项33项测试通过；没有运行全仓回归或修复旧S1两项已知失败。保护清单核对、模型哈希及进程清理结果见证据根目录`protected_workspace_integrity.json`。本轮原部署源码/配置、原生world、MILP、Nav2、原有模式和成功结果未改；只有已声明的探针扩展与日志追加属于原文件有意变化。未提交/推送。

工程功能、性能与创新分别判断：本轮支持真实误报驱动的受限功能闭环，不支持识别泛化、算法性能增益或学术创新成立。既有Fast/Standard仍为功能通过但时间目标未达；稀疏局部修复仍只是条件性收益。

## 下一步

先修复B区静止占用/清空位/取货通路的空间资源关系，复用已有路径与同伴keepout诊断，离线检查后再做针对性短测；不要重跑已知失败的完整序列或强行授权并发证书。随后补正例的monitor/pickup/deliver在线适配、取消ACK和承诺投影，再启动视觉正例＋既有床扰动闭环。

当前可安全复核已完成因果链的下一步命令（新目录，无Gazebo）：

```bash
cd /home/yhc/kaiti_yolopose_framework
python3 scripts/audit_clinic_visual_execution.py \
  --run /home/yhc/clinic_planning_ws/verification/visual_integration_2026-11-18_b1/visual_false_alarm_a2 \
  --mask /home/yhc/clinic_planning_ws/verification/visual_integration_2026-11-18_b1/visual_mask_a2 \
  --out /home/yhc/clinic_planning_ws/verification/visual_integration_audit_NEW
```
