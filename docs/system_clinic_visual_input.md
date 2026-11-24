# Clinic独立真实视频输入模式

实际部署依赖仍来自`/home/yhc/clinic_planning_ws`；仓库`experiments/clinic`不是部署位置。本模式不修改原MILP、Nav2、服务worker、Benchmark/Fast/Standard入口或旧S1。

## 数据流与唯一所有者

`run_clinic_video_ros.py`解码既有视频，经`sensor_msgs/Image`发布至`/clinic_visual/rgb`。独立子类只隔离原PoseStreamNode的模型配置和输出路径；解码、ROS图像推理、发布继续使用现有节点实现。仍为原YOLO Pose、32帧LSTM及阈值0.6。默认输出候选事件和编译任务用于离线门禁；连接执行器时必须启用`--perception-only`，由执行器唯一持有EventTaskProtocol，不能同时启用两套任务拥有者。

`/clinic_visual/replay_metadata`包含视频标识、回放轮次、帧号、源视频秒数、发布时单调钟、ROS时间戳和区域注册方式。图像Header使用发布ROS时间，视频原始时间另存，不能将视频第3秒直接视为Clinic仿真第3秒。回放按源帧率尽力定速，逐帧等待推理收据，落后时延长回放，不静默丢帧；不是实机实时吞吐测试。

每次重播和显式图像中断后重置原模型的时序缓存，事件身份继续保持。没有图像时仅推进协议时钟/有效期，心跳不能续期位置或充当新的阳性。注册视频身份不等于跨相机人体重识别，同一桥仅接受一个登记来源，不做无依据多源同步融合。

## 事件、核验与承诺

`src/kaiti_task_sim/clinic_visual.py`将真实模型稳定阳性转换为协议候选。协议原有`confirmed`字段在此意为“模型候选达到稳定条件”，不代表服务核验已经证实跌倒；score、stable、样本ID与此含义写入因果日志。只有核验任务可以先生成，`verified`仍为false。模型非阳性不等于明确否定，本适配层以保守观测退化处理，不静默关闭事件。

核验服务succeeded与核验结论分开。`feedback()`必须取得带event_id、result、source、evidence_id的明确复核凭据；不会从服务成功、视频文件名或执行器计时推断fall。支持`operator_review`或`independent_sensor_review`，复用同一模型证据不得声称独立核验。负例复核为no_fall时关闭事件，不生成监护/取送；未知结论不能当成功。

协议保留取消请求、执行revision/attempt、owner和取消ACK；位置变更不会悄悄覆盖execution_target。纯协议测试覆盖取消ACK前仍保留承诺、过期success拒绝和合法ACK后attempt递增。第一版实际执行器对持续观测失效会安全终止并报告需要取消/恢复流程，不宣称已完成在线取消ACK、监护交接或携货恢复验收。

## 空间编译和执行门禁

`video_source_registered`区域A沿用V1/M1/H1，B候选采用DL/CDL/ADL，取货仍为G1。B是显式新区域注册，不是此前相机走廊候选坐标的自动沿用。编译同时选择服务锚点、实际坐标、entry/clear阶段、共享资源和原旅行时间表；坐标不匹配会拒绝，不能回退V1。区域改变会经同一个协议产生space/task revision，已发执行目标在ACK前保持。

导航证书绑定完整配置SHA256。只有实际导航、稳定到达、资源阶段及服务ACK证明支持的角色才能放行；核验角色的单点证书不放行监护/取送。三个机器人具备相同移动模型不等于所有并发停靠已安全，路径查询或顺序访问不构成并发资源验收。

`qualify_clinic_visual_regions.py`先要求实际模型因果门禁通过，再复用原运行静态/在线门禁、原Nav2 ComputePathToPose＋FollowPath、0.20米/0.30弧度/稳定0.7秒/新鲜0.5秒和服务ACK。资格检查单次访问使用1秒专用测试服务，未缩短既有研究算例服务时长。资格检查不是新的算法性能实验。

`run_clinic_visual_execute.py`是独立受门禁保护的真实视频执行入口：不调用旧Episode.tick/inject_event/observe；重写本模式Bot反馈，关闭旧核验成功自动fall旁路。第一版只验收真实误报→核验→显式no_fall闭环，正常短任务用于证明三机实际执行。正例核验后监护/取送需进一步并发证书和完整执行适配，目前明确阻断，不冒充完整应急或床扰动恢复闭环。

`clinic_visual_launch.py`导入原Clinic launch，保留机器人、Nav2、资源worker及床组件，仅替换一个keepout进程为`clinic_visual_keepout.py`。该进程继承原Masks，仅调整视觉事件语义：候选不直接创建已确认倒地人体的几何占用；核验确认为fall后按事件space.event_xy更新，显式CLOSED/COMPLETED时移除，遮挡不清除已确认占用。原生Clinic/Fast/Standard仍使用原keepout。独立supervisor复用原PID/partition清理；本模式额外保存自身源码哈希并在派发前核对。

`certify_clinic_visual_regions.py --allow-partial-verify`仅从已经完成原到达守卫、资源阶段及服务ACK的单项证据签发VERIFY证书；保留整体资格检查FAIL，不能用局部证书掩盖G1路径阻断。它不会放行并发监护/取送。

## 复现顺序

所有目录必须新建，先source现有环境。模型、数据和outputs不应被本模式改写。

```bash
cd /home/yhc/kaiti_yolopose_framework
source /home/yhc/clinic_planning_ws/support/clinic_runtime/environment.sh
export ROS_DOMAIN_ID=96
.venv/bin/python scripts/run_clinic_video_ros.py \
  --videos fall-01-cam0 adl-01-cam0 --regions A B --solve \
  --out /home/yhc/clinic_planning_ws/verification/visual_ros_NEW
.venv/bin/python scripts/gate_clinic_visual.py \
  --replay /home/yhc/clinic_planning_ws/verification/visual_ros_NEW \
  --out /home/yhc/clinic_planning_ws/verification/visual_gate_NEW
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q \
  tests/test_clinic_visual.py tests/test_event_task_protocol.py
```

四片段重复/中断实验：在回放命令指定`--videos fall-01-cam0 adl-01-cam0 fall-02-cam0 adl-02-cam0 --regions A --repeats 2 --gap-at-frame 70 --gap-seconds 1.2`。所选URFall样本均为联调/历史开发域，不能称独立测试；实际NPZ划分随每轮input_manifest保存。

## 2026-11-18 A区正例扩展（独立模式）

后续实施以A区为优先，B区与Gazebo人物/相机分支不再作为前置门禁。新增`qualify_clinic_visual_a.py`，先检查锚点、原旅行时间、资源entry/clear与M1/H1间距，再实际执行三机首项常态服务、R1 V1/M1、R2 G1取货/H1交付/返回以及R1/R3返回。R1保持M1占位时检查R2整条服务序列，原Nav2、资源worker和到达/新鲜度/稳定守卫不变。该阶段是空间服务排练，不能称真实跌倒或持续监护服务闭环。

`audit_clinic_visual_positive.py --qualification`独立检查保存的路径、服务ACK、顺序、租约清空、M1占位、返回和源文件/清理证据；只有审计通过才签发A区证书，限定R1核验/监护和R2取送。所有机器人/所有并发占位的通用安全资格不在该证书范围。正例执行器检查证书证据文件SHA与审计PASS，不能只手填并发标志。

正例仍使用唯一VisualEventBridge/EventTaskProtocol和实际模型候选。明确fall复核后，使用原`bed_initial_solver.py`、原MILP和约束验证器生成响应计划；独立短模式只追加既有R3第二个常态任务，不加入900秒后的第二周期，不修改Benchmark/Fast/Standard。提交计划前按任务revision/attempt/target/required_owner与位置有效性校验；实际派发仍要求协议READY以及空间证书匹配。取货ACK改变交付required_owner/revision后重新编译，不能复用旧执行版本。

复核来源新增`controlled_visual_review`，用于保存原帧后的显式AI图像复核；必须标注reviewer、human_review=false和非独立传感器，不得称人工确认或独立临床证据。它与operator_review、independent_sensor_review区别保留，只有verify succeeded携带单独复核凭据；其余服务成功没有fall结论。

`--cancel-verify-once`只测试核验服务开始前的一次真实FollowPath取消：等待同一goal UUID的cancel响应及CANCELED终态后才能释放运动预约并重试。它不等于活动监护取消、携货交接或证据失效后的完整恢复验收。在线记录正常执行中的监护保护、物理携货/协议所有者及任务版本；任何CANCEL_REQUESTED仍停止本模式，不制造取消ACK。**在活动服务失效/取消/恢复尚未实际验收时，禁止直接进入床扰动阶段。**

新证据根目录：`/home/yhc/clinic_planning_ws/verification/visual_positive_2026-11-18_c1/`。原始失败和独立审计分别保留。资格首轮驱动的汇总布尔值存在循环依赖，原summary为FAIL；10项实际服务均成功，独立25项审计通过。修复只影响新驱动后续运行，不回写原summary。正例首轮在ROS UUID日志序列化时失败，诊断后转换为普通int并增加回归测试，保留失败再作有依据重跑。

命令见该目录`commands.md`，实际结果以独立审计和本轮实验摘要为准。新增阶段不改变既有Fast/Standard“功能通过、时间目标未达”结论。

## 独立三维定位分支的接口与测试计划（继续保留）

`sensor_position_contract()`保留`human-spatial-evidence/v1`接口：RGB、Depth、CameraInfo、TF各自时间戳，光学/地图frame、内参、深度编码与单位、位置、有效性原因、协方差和仅评测使用的真值误差。无输入时valid=false；不能用Gazebo actor脚本真值填map_xyz充当估计。

下一批独立测试必须覆盖：已知相机内参/深度投影数值；Depth单位与无效像素；RGB/Depth时间差和过期；CameraInfo分辨率匹配；TF缺失/过期/坐标方向；静态已知点的地图误差；遮挡和关键点缺失；不同source/track没有关联证据时拒绝融合。实际RGB-D采集和误差实验本轮NOT_RUN。区域注册只是当前视频模式的可控空间前提，不替代或删除该研究分支。


A区扩展的本轮最终状态：空间25项独立审计及正例36项执行审计通过，实际8任务/6552帧；监护与取送原ACK完整。详见`reports/benchmarks/clinic_visual_positive_2026-11-18.md`。正常706次在线检查及真实导航取消ACK通过，但活动服务失效/取消/恢复尚未验收，任务3 BLOCKED，床扰动NOT_RUN。不要从正例完整功能闭环推断动态修复或学术创新已通过。

## 2026-11-18后续：取货前床扰动独立模式

本节是上述正例阶段之后的新范围，不回写历史验收。用户后续指令允许先运行**不取消活动服务、不释放监护、不改变携货所有者**的取货前床扰动；完整活动服务撤销/交接工作流仍未放行。

`run_clinic_visual_execute.py --bed-repair --repair-budget 5`使用独立`clinic_visual_bed.py`适配器；原Clinic部署源码、研究MILP、Nav2、资源/服务worker及Benchmark/Fast/Standard入口不改。只回放一次原`fall-01-cam0`，候选仍必须来自真实YOLO/LSTM；核验后仍需独立保存的显式复核来源。新增有限cycle0常态后缀，用于观察应急延迟对后续任务的传播；不是重复900秒周期。

`RegisteredVideoProtocol`将两类时效分离：真实模型的`last_seen_at`保持原样，tick不刷新；区域位置来自显式、配置绑定、几何一致且有限有效期的`video-region-registration/v1`。这是行政/场景注册证据，不是RGB-D三维估计。注册撤销或过期仍产生取消请求并保留活动owner/token；不会伪造取消ACK或恢复。现有默认协议的传感器观测TTL不变。

触发条件为R1监护已RUNNING、R2取货导航中且尚未服务/携货、R3常态任务执行中。只通过原`bed_driver.py`创建真实床对象。实际激光命中、新全局障碍与剩余路径相关性触发FollowPath取消，必须收到相同UUID的cancel响应和CANCELED终态，才进入BED_WAIT。持续15秒后保存机器人/任务/资源/计划/token快照；旧计划通过原约束验证器则记NO_INVALIDATION，不强制修复。

`project_before_pickup`保持R1监护和R2已发取货目标/归属，后续交付同车；复用原30秒滚动可用时间预测、原旅行表、G1预约和正常前缀投影，仅将未派发常态后缀交给既有修复器。预测不是服务完成ACK，也不读取床的隐藏移除时刻。`clinic_visual_pair.py`给local_impact和full_warm传同一个保存的problem与相同预算，分别由原验证器复查。**full_warm是同样硬承诺投影下的全自由后缀求解，不是允许破坏监护/携货约束的全任务任意改派。**在线只提交local_impact；当前测量总耗时包含顺序执行两个对照求解器的开销，不能当独立局部算法的实时优势。

提交前检查原约束、活动任务身份/目标/服务起点、未来任务revision/attempt/target/required_owner、监护执行token、plan revision、资源租约和时序窗口。等待期间仍保持实际监护和原资源守卫。之后沿用原激光/全局/局部清空及稳定守卫恢复；Nav2到达/稳定/新鲜度/服务ACK条件不变。

**范围严格为BEFORE_PICKUP_ONLY。**首例误把原`injection_stage`设为2，额外启用了原交付阶段床实验：床已经移除后，CG1视角仍产生35个床区域激光命中，旧无床成功日志也有相同现象，最终BED_WAIT_LIMIT失败。证据与原源码保留在`visual_bed_2026-11-18_d1/bed_before_pickup_01`。修正只是不再激活这条未请求的交付阶段实验及其高层修复路径；**不把不适用解释为路径安全，不改变任何原Nav2碰撞/路径/到达守卫。**通用床区域分类的视角混淆仍是未解决问题，不能宣称持货阶段床检测/修复已通过。

启动时原完整运行门禁必须PASS。如仅生命周期/参数RPC类`live:*`检查失败，独立模式允许同一world内另存目录、重新启动一次原完整检查进程，最多60秒；任何传感器、TF、动作或freshness失败直接终止，第二次全门禁仍失败也终止。首次失败报告不覆盖；没有强制激活节点或放松判据。

新证据根目录：`/home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/`。独立审计、证据退化、轨迹动画分别用下列入口，不启动新world：

```bash
cd /home/yhc/kaiti_yolopose_framework
.venv/bin/python scripts/audit_clinic_visual_bed.py --run /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_before_pickup_04 --out /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_audit_NEW
.venv/bin/python scripts/check_clinic_evidence_degradation.py --source /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_before_pickup_04/before_bed.json --out /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/degradation_NEW
.venv/bin/python scripts/render_clinic_visual_bed.py --run /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/bed_before_pickup_04 --out /home/yhc/clinic_planning_ws/verification/visual_bed_2026-11-18_d1/trajectory_NEW
```

渲染器使用实际Gazebo位姿、任务状态和床对象ACK，不插值生成未来轨迹；图中床为示意轮廓。输出是可复核的轨迹动画，不冒充机器人相机录屏。实际分项结果以新实验摘要、原始summary和独立审计为准。

### 监护结束后的真实区域清空

`bed_before_pickup_03`完成四项应急服务并关闭事件，但整场为FAIL：R2交付后恢复常态任务时R1仍停在M1，原局部控制器连续碰撞/耐心超时。全局路径查询通过不等于局部可执行。未增加重试或删除同伴keepout。新增独立`qualify_clinic_monitor_clearance.py`，将三机受控初始化至保存的完成位姿，R2保持H1，R1实际通过原ETL→TL服务→V3清空与资源释放流程；该探针不生成跌倒或伪造恢复ACK。`clearance_probe_02`签发配置与原始证据SHA绑定证书，01门禁失败保持原样。

床模式现强制传入`--clearance-certificate`。`project_initial_clearance`在原response提交后、派发前，固定原应急和R3第二项常态安排，用原full_warm MILP重排五项未派发常态后缀，并排入`E1_monitor_clear`。它是本场的初始策略，不是再次运行无扰动基线。未来预测不写入completed或协议ACK，不声称尚未执行的任务已有硬承诺。床修复保留相同清空策略与TL预约，避免把事后新增空间政策当成床扰动的算法收益。

`E1_monitor_clear`为辅助清空任务，依赖实际监护完成，R1经原TL资源worker执行后清到V3。R2所有后续常态派发还必须等待实际clear/release和任务完成记录。修复中不取消监护服务，不改变取货/交付归属，不要求携货交接；现有活动服务撤销恢复仍BLOCKED。完整启动命令见该证据根目录`commands.md`，必须换新输出目录及空闲ROS域，不覆盖04。轨迹视频是实际位姿日志动画，不冒充Gazebo GUI录屏。
