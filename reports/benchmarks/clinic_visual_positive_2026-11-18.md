# Clinic A区真实视觉正例完整应急执行（2026-11-18）

## 目标、结论与范围

论文题目和三个研究内容保持不变。本轮优先完成A区服务资格及`fall-01-cam0`正例实际执行，不修改原生Clinic、规划主链、MILP、Nav2、资源/服务worker、Benchmark/Fast/Standard、旧S1或既有实验结果。

**本轮完成一次受控真实视频正例功能闭环：实际ROS RGB→原YOLO Pose＋32帧LSTM→稳定候选E1→核验→带保存原帧来源的显式fall复核→monitor/pickup/deliver→原MILP→实际三机Nav2与服务ACK→交付/交接后监护结束。**A区空间资格独立审计25项通过，正例独立审计36项通过。不是独立泛化性能或学术创新结论。

实际证据根目录：`/home/yhc/clinic_planning_ws/verification/visual_positive_2026-11-18_c1/`。实际命令、模型输入、因果摘要、分项验收和保护清单分别为`commands.md`、`model_input.json`、`causal_ledger.json`、`acceptance.json`、`protected_workspace_integrity.json`。所有结果使用新目录，历史失败原样保留；没有提交或推送。

| 工作项 | 状态 | 严格结论 |
| --- | --- | --- |
| 任务1 A区服务资格 | PASS | R1核验/监护，R2取送；实际服务序列、G1 entry/clear/租约、M1占位及三机返回；不是所有机器人任意组合的通用资格 |
| 任务2 真实正例执行 | PASS | 6552条实际模型观测、8项实际任务完成，四项应急任务均有原服务ACK，事件COMPLETED |
| 任务3 在线承诺合法性 | BLOCKED | 正常执行706次检查通过，真实导航取消ACK/重试通过，监护/携货身份保持；活动服务证据失效→取消ACK→恢复、携货交接/重新分配尚未实际验收 |
| 任务4 床阻挡与修复比较 | NOT_RUN | 任务3总门禁未通过，未进入床短/长阻挡；旧计划/全量/局部对比未运行 |
| B区控制变量诊断 | NOT_RUN | 保留已知占用条件下R2→G1无路径证据，没有重跑或修改配置 |
| RGB-D三维定位 | NOT_RUN | 接口分支继续保留；本轮只用video_source_registered，未冒充sensor_estimated |

## 输入与复核来源

- 视频：`data/urfall/cam0_mp4/fall-01-cam0.mp4`，SHA256 `5fcb77e5b5a35d73ab8cda856ea58bd9e6acd7552e16fc6d22a623556bee76bc`。本地划分train，历史训练/开发及调参域，independent_test=false。
- YOLO：原`yolo11n-pose.pt`，SHA256 `869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0`。
- 时序模型：原`fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`，SHA256 `bca4411d5a75d171e4fbfb09784f719d8099be1622cdeaa5748fd0d675a1a762`；seq_len=32，阈值0.6，原稳定化参数，不裁图、不训练、不调阈值。
- 保持原视频左深度渲染/右RGB拼接完整帧，真实解码并经ROS图像接口推理。视频源时间、ROS发布戳、单调钟和Clinic仿真时间分别记录；未把视频第3.3秒当Clinic第3.3秒。
- 保存并实际查看第0/45/75/100/130/155帧：可见站立、下落及倒地。`fall01_review.jpg`和`fall01_explicit_review.json`绑定图像SHA、事件E1及来源视频。
- **fall核验结论为controlled_visual_review，reviewer=assistant_visual_review、human_review=false、independent_sensor=false。它是显式AI原帧复核，不是人类复核、机器人相机二次观测、独立传感器或临床诊断。**若后续要求严格人工复核，应由操作员提供带来源的复核输入，不能把本次AI记录改名成人工证据。
- 只有核验succeeded接收上述单独复核凭据；其他服务反馈没有fall结论。不从服务成功、文件名或执行器定时产生fall。无真实模型候选便不会有核验或后续应急链。

ROS回放为维持实际观测而重复同一短片，保持单一源注册事件身份E1，不能把6552帧/2494稳定阳性帧当独立样本或准确率。回放逐帧等待推理回执，不能用它宣称30Hz实时吞吐。机器人定位沿用Gazebo参考位姿，不验证SLAM性能。

## A区空间服务资格

复用V1/M1/H1/G1、AG1/CG1与原旅行时间表/共享资源。新增独立A区排练入口，不调用旧事件注入或定时confirmed。

1. `a_offline/offline.json`：6项锚点、有限有向旅行时间、G1 entry/clear、原阶段时长、能力和M1/H1间距检查通过。另复跑当前代码的视觉离线门禁26项通过，7次原MILP验证通过；其中ACK仍是明确离线夹具。
2. `a_qualification_01`：9次实际Nav2路径查询通过后，严格顺序执行10项真实服务及返回。R1在M1的4054条占位记录覆盖299.86–525.14仿真秒，最大离站距离0.0972m；期间R2完成G1取货、H1交付及返回。保留原同伴keepout、走廊预约、资源租约和导航恢复。
3. 10项完成时间/仿真秒：R1首项72.46、R2首项144.28、R3首项255.32、V1核验277.36、M1站位299.81、G1取货352.62、H1交付435.68、R2返回525.14、R1返回582.51、R3返回671.21。G1执行AG1入场、服务、CG1清空及释放，不是仅查询G1点位净空。
4. **原始驱动summary是FAIL，原因是到达审计把初始化的passed=false作为自身前提，实际没有导航/服务异常。**原summary不回写。修正新驱动的循环布尔条件后，另运行保存证据独立审计`a_qualification_audit`：25项全部通过，逐项检查实际ACK、到达稳定/新鲜度、严格顺序、资源清空、M1占位、返回、原部署源文件及清理。
5. 只由独立审计签发配置SHA绑定的A证书，限定R1核验/监护、R2取送，不授权未测机器人换位。实际持续监护生命周期由正例实验再验收，不用站位排练代替。

原0.20m、0.30rad、稳定0.7s、TF/scan/odom freshness≤0.5s和服务ACK守卫均未放松。路径查询通过、实际服务可执行、特定并发占位可满足分别记录；不宣称任意动态环境下全局碰撞安全已获证明。

## 正例实际因果链与任务执行

最终运行：`positive_02`；独立审计：`positive_02_audit/summary.json`，36项通过。

首个候选原因是`fall-01-cam0:A:0:99`：源视频3.3秒，真实score=0.9089867、stable=true、window_ready=true；Clinic候选时间44.15秒。只有E1:verify，不能从一次阳性直接扩展全部服务。原verify MILP在44.61秒提交，保留三机已发常态前缀。

| 实际任务 | 机器人 | 派发 | 服务开始 | 服务结束 | 完成（含清空） | 执行revision |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| C0_r1_W1 | R1 | 35.00 | 113.29 | 117.29 | 136.02 | 常态 |
| C0_r2_W1 | R2 | 35.00 | 120.99 | 124.99 | 136.18 | 常态 |
| C0_r3_W1 | R3 | 35.00 | 163.29 | 167.29 | 186.08 | 常态 |
| E1_verify | R1 | 147.02 | 169.29 | 172.29 | 172.30 | 1 |
| E1_monitor | R1 | 207.33 | 240.59 | 399.79 | 399.84 | 1 |
| C0_r3_W2 | R3 | 207.33 | 286.64 | 290.64 | 323.86 | 常态 |
| E1_pickup | R2 | 240.64 | 271.54 | 279.54 | 294.59 | 1 |
| E1_deliver | R2 | 294.59 | 390.59 | 396.59 | 396.66 | 2 |

时间单位均为本次运行的相对仿真秒，不是壁钟实时性能指标。

核验独立fall凭据生效后，原`bed_initial_solver.py`使用同一原MILP/约束验证器，172.83秒提交响应：R1持续监护、R2取送同车、R3继续真实常态任务。独立短模式使用既有R3第二项任务，不插入900秒后的第二周期；原模式不变。

normal/verify/response均OPTIMAL，分别58/34/78项约束检查通过；本次单次端到端求解壁钟约0.635/0.599/0.840秒。这些只是单例记录，不支持局部修复收益或总体性能比较。

实际监护240.59–399.79，持续159.20秒，覆盖取货、清空和交付；交付服务396.59结束，实际任务396.66完成，场景收货方在399.68给出交接ACK，随后才请求结束监护。交接ACK明确为受控场景服务接收方，不是视觉/临床推理。最终事件COMPLETED，四项应急协议任务全部SUCCEEDED、资源清空、三机IDLE。

G1取货成功后协议携货所有者为R2，交付required_owner=R2、revision=2；执行端重新编译并使用当前revision派发服务，原MILP给出的R2归属及H1几何不变。日志包含协议任务ID、执行task_id、attempt、revision、plan_revision、服务ACK、实际目标和MILP输入。`causal_ledger.json`提供紧凑可追踪索引，完整证据仍为原始trace/模型causal日志。

## 在线承诺证据与未通过的门禁

- 真实核验导航取消请求147.24秒，147.30秒收到同一个FollowPath goal UUID的cancel ACK及CANCELED终态；ACK前不释放运动预约，随后重试同一核验任务并成功。服务未开始，故不伪造服务cancelled ACK，也不无故增加协议attempt。
- 正常在线状态检查706次全部通过，其中313次明确拒绝在交付/交接前释放监护；实际R1监护身份、R2物理携货与协议所有者一致。模块测试检查旧任务版本/失效位置不能提交、没有ACK不释放承诺、携货不得换机。
- **以上不等于完整在线取消/恢复能力。**视觉执行器当前对CANCEL_REQUESTED仍采取安全停止，尚无活动监护/携货任务的取消ACK、补偿/交接及恢复工作流。原worker要求RUNNING；不能通过放松其守卫把失效监护假称持续有效。
- 长期视觉证据失效、活动服务取消/恢复、实际携货交接/重新分配，以及真实异步求解期间状态变化导致的旧结果拒绝，仍为NOT_RUN。任务3整体BLOCKED，不能凭协议单测或正常闭环宣布通过。
- 因此未启动床短/持续阻挡，没有本轮局部修复结果，也没有旧计划/全量/局部的时间、影响范围、保留比例和完成时间对比。下一轮先实现并实际验收上述在线状态路径，再启用已有床扰动、原投影和原局部/全量后端。

## 失败、代码与保护

`positive_01`在取消请求的日志保存处失败：ROS UUID数组元素为numpy.uint8，不能直接JSON序列化。原始summary、traceback、1959条模型观测及清理记录保留；未将其称通过。修正为16字节普通int列表，增加numpy UUID回归测试后才运行`positive_02`。没有盲目重复相同完整场景，也没有借重跑修改守卫或模型。

变更文件：

- `src/kaiti_task_sim/clinic_visual.py`：显式复核来源、JSON安全UUID、任务提交fence、承诺释放/携货保护辅助检查、证书角色约束。
- `scripts/run_clinic_visual_execute.py`：原响应MILP短模式接入、版本fence、限定机器人资格、真实导航取消/ACK/重试、显式复核与在线因果日志、异常证据保存。
- 新增`scripts/qualify_clinic_visual_a.py`、`scripts/audit_clinic_visual_positive.py`、`tests/test_clinic_visual_positive.py`。
- 更新`docs/system_clinic_visual_input.md`、本文、当日工作日志。

最终专项39项测试通过，未运行全仓/S1测试，旧S1两项已知失败未改。所有三次自有world清理通过，无该partition残余；正例运行源码manifest未变化。494项已有文件保护核验见保护清单：部署原源码/配置、原模型、既有成功失败证据及旧S1保持；只有明确列出的本轮文件有意变化。

## 研究结论边界与下一步

模块测试、离线验证、真实三机功能、定量性能收益和学术创新分别报告：前三类在上述限定范围有证据；后两类本轮未验证。既有Fast/Standard仍是功能通过但时间目标未达；既有局部修复只有条件性收益。

本次不把内容一、二包装成新算法。后续独立方法实验仍需同一观测/状态条件下比较：语义核验机制对误报无效任务数的影响；TTL/空间有效性与承诺保护对错误目标和非法取消数的影响；语义依赖相对无依赖分配的实际可执行率变化。控制输入、机器人快照、后端与预算，分别报告任务数、错误派发、取消完成/请求差异、约束违规及任务完成率；不把本次集成通过直接作为这些研究假设的支持。

安全复核下一步命令（新输出目录，不启动Gazebo）：

```bash
cd /home/yhc/kaiti_yolopose_framework
python3 scripts/audit_clinic_visual_positive.py \
  --run /home/yhc/clinic_planning_ws/verification/visual_positive_2026-11-18_c1/positive_02 \
  --out /home/yhc/clinic_planning_ws/verification/visual_positive_2026-11-18_c1/positive_02_audit_review_NEW
```

下一项开发是活动监护/携货状态下的证据失效和安全取消/恢复入口及在线短测，不是再次重跑正例基线或直接启动床扰动。
