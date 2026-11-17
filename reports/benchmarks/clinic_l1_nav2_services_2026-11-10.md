# Clinic L1独立单机Nav2与服务执行实测

日期：2026-11-10。任务：在独立Clinic L1入口设置三个服务点，验证真实仿真导航、稳定到达、任务启动/完成与超时反馈；保留原生演示、不接实车、不修改现有规划主链。

## 实际结果

**已完成独立入口和真实Gazebo/Nav2闭环。最终六条任务尝试符合预期，独立审计520项全部通过。**

- 工作区：[clinic_planning_ws](/home/yhc/clinic_planning_ws/README.md)，ROS域74、Ignition partition=`clinic_l1_nav2_yhc`，原生Clinic域73与入口保留。
- L1实验world保留405个静态include，复用原素材。移除原生受控车辆、动态门/电梯相关model及RMF调度链，加入一台简化物理差速底盘；不是直接给原slotcar机器人发送任务。
- 机器人有物理碰撞、轮式驱动、10Hz/360束GPU激光、里程计和TF，实际运行AMCL与Nav2。Gazebo真值仅用于验证，不替代AMCL、不参与运行时到达门禁。
- 最终S1/S2/S3均经真实Nav2成功、稳定到达、独立服务执行桩started/succeeded反馈后完成。三个故障尝试分别得到ARRIVAL_NOT_STABLE、ACTION_START_TIMEOUT、NAV_TIMEOUT，没有误记服务启动或完成。
- 独立审计重读原始日志/实际位姿，不导入执行器判断函数；最终**520/520通过**，包含稳定窗口原始数据、实际位置、服务期间位置保持、ACK顺序与取消确认。
- 81个既有ROS/独立规划/相关配置文件哈希前后相同；上游rmf_demos已跟踪源码diff为空。未安装新系统依赖、未清理用户资产或旧实验输出。

这证明单机执行接口已具备后续三机常态任务的基础，不代表已完成跌倒事件、MILP协同分配或动态障碍算法比较。

## 原始证据

| 内容 | 文件 |
|---|---|
| 最终六条执行、运行内检查 | [result.json](/home/yhc/clinic_planning_ws/runs/final_verified/result.json) |
| 独立520项审计、逐任务指标 | [independent_audit.json](/home/yhc/clinic_planning_ws/runs/final_verified/independent_audit.json)、[metrics.csv](/home/yhc/clinic_planning_ws/runs/final_verified/metrics.csv) |
| 原始状态、动作反馈、门禁数据 | [trace.jsonl](/home/yhc/clinic_planning_ws/runs/final_verified/trace.jsonl) |
| Gazebo实际位姿 | [ground_truth.json](/home/yhc/clinic_planning_ws/runs/final_verified/ground_truth.json) |
| 地图上实际轨迹与定位轨迹 | [PNG](/home/yhc/clinic_planning_ws/runs/final_verified/trajectory.png)、[SVG](/home/yhc/clinic_planning_ws/runs/final_verified/trajectory.svg) |
| 实际查看的Clinic L1与蓝色机器人画面 | [clinic_l1_gui.png](/home/yhc/clinic_planning_ws/verification/clinic_l1_gui.png) |
| 版本、场景和保护检查 | [versions.json](/home/yhc/clinic_planning_ws/verification/versions.json)、[scene_manifest.json](/home/yhc/clinic_planning_ws/verification/scene_manifest.json)、[protected_after.json](/home/yhc/clinic_planning_ws/verification/protected_after.json) |

最终运行目录的`source/`和`source_manifest.json`保存运行开始时的源码、world、地图和配置；独立后处理实际使用的源码/哈希另保存在`audit_source.py`及审计JSON中，不能把后处理版本变更误当作当时运行版本。

## 服务点与真实计量

坐标为Clinic地图原生米制坐标，未照搬旧DES示例坐标。初始spawn为`(13.31,-31.72,yaw=0)`；三个服务点为：

| 服务点 | x/m | y/m | yaw/rad |
|---|---:|---:|---:|
| S1 | 13.46 | -33.78 | -1.50 |
| S2 | 15.04 | -36.80 | 0.00 |
| S3 | 13.31 | -31.72 | 1.57 |

下表来自最终`final_verified`运行。它是同一GUI会话内的重复执行，实际初始位姿在上次运行返回S3并取消后的附近；不是再次按spawn冷启动，不能与前两组直接作性能比较。

| 任务 | 导航时间/s | Nav2成功至稳定到达/s | 请求至started/s | 模拟服务/s | 真值位置误差/m | 结果 |
|---|---:|---:|---:|---:|---:|---|
| S1 | 10.66 | 0.86 | 0.28 | 1.50 | 0.113 | SUCCEEDED |
| S2 | 14.57 | 0.74 | 0.29 | 1.50 | 0.061 | SUCCEEDED |
| S3 | 20.26 | 0.87 | 0.27 | 1.50 | 0.101 | SUCCEEDED |

真值朝向误差分别0.140、0.068、0.123rad；真值位置和朝向误差均满足本轮服务门限。独立审计还核对服务期间的Gazebo位姿，避免仅在到达瞬间合法。

六条尝试执行区间共61.30仿真秒、61.298单调墙钟秒，区间仿真/墙钟比约1.000；完整验证进程约63.327墙钟秒，包含就绪检查等开销。离散时钟和日志采样会影响最后几位，不能据此声称硬实时保证。

本轮底盘修正后做了三组六条尝试：headless冷启动的`axis_fixed`、GUI冷启动的`final_gui`、同GUI会话复执行的`final_verified`。18次尝试均返回预期结果；**只有最后一组使用最终接收顺序证据完成520项独立审计**。这些是功能复验，不是18个随机场景、可靠性统计或算法对照。

## 稳定到达与服务反馈如何判定

导航必须由Nav2 action真正返回成功，不能按预计时刻记完成。此后连续至少0.7仿真秒同时满足：

- 位置误差≤0.20m、朝向误差≤0.30rad。
- 平面速度<0.04m/s、角速度<0.06rad/s。
- TF、odom和laser新鲜度均<0.5仿真秒。

Nav2 goal checker与DWB位置门限统一为0.12m，Nav2朝向门限0.18rad。这些是本轮仿真配置，不是通用机器人安全标准或实车标定结果。

执行器稳定到达后发出带run作用域task_id、attempt的服务请求。另一个进程`service_worker.py`再次检查到位、低速与位姿新鲜度，在至少0.25秒后明确返回started；执行1.5秒模拟服务后明确返回succeeded。机器人到点不自动等于服务成功，也没有机械臂装卸或人体视觉核验。

正常导航上限120仿真秒，到达稳定检查上限4秒，启动ACK上限3秒，服务完成上限5秒；另有单调墙钟看门狗防止仿真时钟停滞时无限等待。`/clinic_experiment/execution_feedback`发布JSON状态与原因，原始记录可重建整个过程。本轮还没有把这套服务消息接入event-task/v1或生产`/planning/*`。

## 三条主动注入的超时轨迹

| 注入 | 实际反馈 | 核对结果 | 不应扩大解释为 |
|---|---|---|---|
| 到达后保持启动门禁不放行 | ARRIVAL_NOT_STABLE，4.00秒后返回 | Nav2成功，但未发送服务启动请求、未开始服务 | 已测试实际定位噪声/抖动分布 |
| 服务桩不执行服务、也不返回started | ACTION_START_TIMEOUT，3.00秒后返回 | 已稳定到达并请求；超时后取得取消确认，无服务成功 | 已解决“服务实际启动但ACK丢失”的不确定状态恢复 |
| 给远端S1导航仅0.15秒期限 | NAV_TIMEOUT，约0.17秒返回 | cancel被接受且Nav2最终状态CANCELED；未请求服务 | 自然导航失败率或最短可行导航预算 |

故障测试用于检查反馈和禁止假成功，不是通过人为故障制造性能指标。导航结果、服务启动和服务完成分别计量。

## 调试失败记录与修正

没有只保留成功输出：

1. `runs/initial/error.json`：就绪检查只查一次生命周期，planner_server尚未完成激活即被误判失败。改为有上限地等待实际ACTIVE，不用固定延时假设就绪。
2. `runs/first_navigation/`：初始Nav2最终位置门限0.12m，DWB仍在0.25m内提前转向，机器人在约0.19m处难以结束导航。定点取消后保留了NAV_FAILED记录；统一两处位置门限后重测。
3. `runs/calibrated/`：简化底盘轮轴方向定义不正确，Gazebo实际运动与轮式里程计预测不一致；S1估计到位但真值偏离，后续S2规划/恢复失败。修正SDF轮轴坐标并从初始状态重启，不把该轮S1服务成功当作物理到位验收。
4. `runs/final_gui/independent_audit.json`：第一版独立审计按仿真时间戳选稳定窗口，遇到同一时刻先后多个回调，误纳入边界处上一条未稳定样本。没有直接删除该失败记录；执行器改为记录全部guard决策和单调接收边界，另跑`final_verified`，独立审计按实际接收顺序还原后通过。

头部日志仍有非阻断的OBJ材质与EGL警告；本轮激光、定位、实际GUI和导航都已验证，但不声称所有图形后端均兼容。

## 变更范围与剩余风险

独立工作区新增：

- `run_clinic_l1.sh`、`verify_clinic_l1.sh`、`README.md`。
- `launch/clinic_l1.launch.py`。
- `tools/prepare_scene.py`、`sensor_tf.py`、`service_worker.py`、`start_gui.py`、`verify_services.py`、`audit_run.py`。
- `config/navbot.sdf`、`nav2.yaml`、`services.yaml`；生成的L1 world、地图、原始运行与verification证据。

论文仓库新增本报告，更新benchmark/docs索引及接入方案的已实现状态。没有修改ROS主链、旧规划器、感知模型、旧配置、数据集、旧outputs或原生Clinic入口。

地图来自L1建筑碰撞网格，仅含墙/地板；家具由激光障碍层处理。没有验证全医院每个目标、动态人群、自动门、电梯、失定位恢复、完整碰撞统计或导航算法优越性。当前服务是有位置守卫的模拟服务，不能称真实核验/取放。还未接入跌倒事件、MILP、多机器人、共享通道预约或电量；这些按[既定接入方案](../../docs/reviews/clinic_cooperative_planning_integration_plan_2026-11-10.md)后续推进。

本轮结束保留独立L1 GUI/导航进程供用户查看，机器人在S3附近停止；原生Clinic demo及其RViz进程已按授权关闭，随时可用原命令重新启动。切换演示时建议先停止当前实例以释放GPU/CPU。

## 复现与下一步

当前场景已运行；如需重启，先在其启动终端Ctrl-C停止。两个终端分别执行：

```bash
cd /home/yhc/clinic_planning_ws
./run_clinic_l1.sh
```

```bash
cd /home/yhc/clinic_planning_ws
./verify_clinic_l1.sh
# 将下面路径替换为刚打印的新run目录，避免误读本次已归档结果。
/usr/bin/python3 tools/audit_run.py runs/<新run目录>
```

只看三点正常执行可用`./verify_clinic_l1.sh --success-only`，不包含三个故障。完整命令、参数、版本和独立范围见[工作区README](/home/yhc/clinic_planning_ws/README.md)。

下一步应先复制验证第二/第三台机器人的命名空间、TF与Nav2，跑无跌倒的三机常态任务；通过后再把event-task/v1和独立MILP接上。单机通过是接入门槛，不替代第三项算法的公平对照。

技术参考：[Fortress差速驱动](https://gazebosim.org/docs/fortress/moving_robot/)、[Fortress传感器](https://gazebosim.org/docs/fortress/sensors/)。本机Nav2组件版本1.1.20、ros_gz_bridge 0.244.26、Gazebo Fortress6.18.0；不使用Rolling接口假设。
