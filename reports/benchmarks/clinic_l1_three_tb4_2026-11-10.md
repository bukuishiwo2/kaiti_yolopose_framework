# Clinic L1三台TurtleBot4/Nav2：常态任务与共享服务点互斥实测

日期：2026-11-10。目标：按用户要求直接复用TurtleBot4/Nav2及既有Clinic地图、碰撞体和坐标，验证三机命名空间、TF隔离、导航、服务反馈和共享点互斥。无跌倒事件、无实车、不修改既有规划主链。

## 实际结论

**三台官方TurtleBot4 Lite完成9段真实仿真导航、6次有启动/完成确认的服务，3次共享点占用全部正确释放。独立审计18,636项通过。**

- 工作区仍为`/home/yhc/clinic_planning_ws`，新增独立三机入口；旧单机原型保留但本轮不使用其自定义小车。
- 完整GUI运行原始目录：[three_verified](/home/yhc/clinic_planning_ws/runs/three_verified/result.json)。不是DES回放或仅发布计划，实际运行Gazebo物理、官方轮式控制、AMCL与三套Nav2。
- 合计26项命名空间/图检查通过。每机独立TF流、地图服务、scan、odom、cmd_vel、action与服务反馈；无全局`/tf`、`/tf_static`、`/cmd_vel`发布者。
- 先只驱动R1四秒，Gazebo真值位移0.894m；R2/R3无观测位移。随后三台常态导航区间实际重叠5.02仿真秒。
- 三台分别完成私人服务，再按FIFO依次使用共享点。三次在点内提前释放均被拒绝；一次非持有者启动共享服务被明确拒绝，无错误started/succeeded。
- 共享圆区（中心距离<0.6m）的采样占用最多1台；机器人间最小采样中心距离2.028m。
- 最终完整运行包含9个到达点，Gazebo真值位置误差0.032–0.154m；六次服务均有独立进程的started/succeeded反馈。
- 原有地图/旧场景/规划及原生入口等86个保护文件未变；官方模型每机39个link、38个joint定义逐项核对一致，Clinic的405个静态include一致。没有重新建图，也没有改官方安装包。

18,636项大部分是同一轮轨迹中的位姿、占用和门禁采样检查，**不是18,636个独立场景，也不是可靠性或算法优越性统计**。

## 入口、模型与复用边界

启动：[run_clinic_three.sh](/home/yhc/clinic_planning_ws/run_clinic_three.sh)；验证：[verify_clinic_three.sh](/home/yhc/clinic_planning_ws/verify_clinic_three.sh)；完整说明：[README_THREE_TB4.md](/home/yhc/clinic_planning_ws/README_THREE_TB4.md)。

本轮采用安装包中的TurtleBot4 Lite xacro、Create3 `ign_ros2_control`和`diff_drive_controller`，保持原官方link/joint几何、惯量、传感器位姿、轮距与轮半径。生成的独立URDF只做命名空间相关控制参数引用、世界级传感器/接触系统去重、传感器更新率配置等适配；不另建小车几何，不使用上一轮自定义DiffDrive机器人。

`maps/clinic_l1.pgm`、`maps/clinic_l1.yaml`直接复用、哈希未变。三机world从已验证的L1副本中移除旧`clinic_navbot`；405个静态include的URI、pose、碰撞素材等结构与原L1副本完全相同。原有门梯简化保持，没有新增裁剪建筑或地图重投影。

三台型号相同，本轮不是硬件/能力异构实验。为减少不研究的传感器开销，RPLIDAR配置10Hz，辅助传感器/相机配置1Hz；底盘控制更新100Hz。完整TurtleBot4 HMI、充电坞、Create3安全应用节点没有启动，不能写成其全部功能验收。轮式控制使用真实关节反馈而非open-loop；真值仅供核对，不代替AMCL或服务门禁。

资产证据：[three_tb4_asset_audit.json](/home/yhc/clinic_planning_ws/verification/three_tb4_asset_audit.json)、[官方包校验输出](/home/yhc/clinic_planning_ws/verification/three_official_package_check.txt)、[three_tb4_scene.json](/home/yhc/clinic_planning_ws/verification/three_tb4_scene.json)。官方包`dpkg -V`输出为空；没有改`/opt/ros`、shell启动文件或原生Clinic演示。

## 命名空间与TF隔离

| 每机独立部分 | R1示例 | 检查依据 |
|---|---|---|
| 底盘控制 | `/r1/controller_manager`、`diffdrive_controller` | 官方控制器均为active |
| 感知与速度 | `/r1/scan`、`/r1/odom`、`/r1/cmd_vel` | 发布者namespace及实际消息 |
| 定位/导航 | `/r1/amcl`、`/r1/navigate_to_pose`及costmap | lifecycle ACTIVE、实际action结果 |
| TF | `/r1/tf`、`/r1/tf_static` | 独立buffer，map→odom→base_link连通 |
| 任务服务 | `/r1/experiment/service_request`和`service_feedback` | 正确robot/task/attempt身份 |

R2/R3采用对应`/r2`、`/r3`。每套隔离TF内部仍使用官方`map/odom/base_link/rplidar_link`等名称，不宣称已全局改名成`r1/base_link`。底盘自动frame prefix在各隔离图内关闭，以与官方描述一致；TF不向全局流混合。以后若要在单一全局TF树显示全部机器人，需显式适配frame前缀，不能直接拼接三个原始流。

结果：[namespace_audit.json](/home/yhc/clinic_planning_ws/runs/three_verified/namespace_audit.json)。隔离检查也包括实际运动：前4秒只有R1收到导航，R2/R3保持原位，避免只看topic名称就宣称隔离有效。

## 常态任务及实际时刻

同一个Clinic map米制坐标下的固定场景：

| 机器人 | 初始位置(x,y,yaw) | 私人服务点(x,y,yaw) |
|---|---|---|
| R1 | (13.31,-31.72,0) | (13.21,-28.00,-1.57) |
| R2 | (15.71,-38.07,0) | (16.89,-40.32,1.57) |
| R3 | (12.83,-38.55,1.57) | (12.716,-37.265,1.57) |

共同服务点：`(13.46,-33.78,-1.50)`。每机流程为私人点导航/服务→申请共享点→持有者导航/服务→返回私人点并稳定到达→确认资源释放。返回段不是额外服务任务。

| 机器人/阶段 | 导航耗时/s | 稳定到达等待/s | 模拟服务/s | 真值位置误差/m |
|---|---:|---:|---:|---:|
| R1 常态私人点 | 19.45 | 0.86 | 1.50 | 0.032 |
| R2 常态私人点 | 14.79 | 0.81 | 1.50 | 0.071 |
| R3 常态私人点 | 5.02 | 0.85 | 1.50 | 0.154 |
| R1 共享点 | 18.41 | 0.83 | 3.00 | 0.110 |
| R1 退出返回 | 26.68 | 0.82 | — | 0.050 |
| R2 共享点 | 28.35 | 0.80 | 3.00 | 0.105 |
| R2 退出返回 | 27.59 | 0.83 | — | 0.038 |
| R3 共享点 | 17.47 | 0.78 | 3.00 | 0.094 |
| R3 退出返回 | 16.92 | 0.80 | — | 0.117 |

首个导航时刻17.52，到最后释放189.67，共172.15仿真秒；完整验证进程175.91单调墙钟秒，含就绪与记录开销。不将它与其他方法耗时比较，也不据此声明硬实时保证。

到达门禁沿用已有配置：≤0.20m、≤0.30rad，线速度<0.04m/s、角速度<0.06rad/s，TF/odom/laser新鲜度<0.5仿真秒，连续满足≥0.7秒。Nav2/DWB位置门限共同为0.12m，Nav2朝向门限0.18rad。另一个服务进程检查到达与资源持有权，明确返回started和succeeded，不按计划时刻自动成功。

逐段数据：[metrics.csv](/home/yhc/clinic_planning_ws/runs/three_verified/metrics.csv)；[实际轨迹与执行时间图](/home/yhc/clinic_planning_ws/runs/three_verified/three_trajectories.png)、[SVG](/home/yhc/clinic_planning_ws/runs/three_verified/three_trajectories.svg)；[实际查看的GUI截图](/home/yhc/clinic_planning_ws/verification/three_tb4_gui.png)。

## 共享点互斥：没有提前释放或无权服务

独立FIFO互斥器是本轮共同执行基础设施，不是MILP调度器。占用覆盖进入、服务和退出；仅在持有者新鲜定位确认离共享点≥1.2m后才接受释放。模拟服务工作进程还独立验证lease_id与机器人身份，并在服务中保持持有权要求。

| 持有者 | 实际授权区间/仿真秒 | 授权期间行为 |
|---|---|---|
| R1 | 39.60–89.60 | 进入、服务、返回、释放 |
| R2 | 89.60–150.42 | 等R1清场后进入、服务、返回 |
| R3 | 150.42–189.67 | 等R2清场后进入、服务、返回 |

三个机器人完成共享服务后，均主动尝试在仍位于共享点内释放，三次全部得到`release_denied/owner_not_confirmed_clear`，原lease保留。R2在R1持有期间另发送一次无持有权服务请求，得到`rejected/shared_lease_missing`，未出现started或succeeded。退出实际完成后才获得真正release确认。

独立评估从原始反馈和Gazebo实际位姿重建：三段lease不重叠、共享服务不重叠、占用者有持有权、位于中心0.6m内的采样占用数≤1。2025个进入该圆区的样本均符合要求；全程最小机器人中心采样距离2.028m。这里没有完整接触检测/连续碰撞证明，也没有一般共享通道预约模型。

## 启动调试、实测边界与保留失败

原始日志位于[verification](/home/yhc/clinic_planning_ws/verification)，没有删除失败或把未完成过程算成功：

- 初始三台同时调用标准create时，世界尚未准备完，出现生成请求超时；改为确认世界服务并使用一次有上限的EntityFactory请求，仍须以后续控制器/真值确认实体实际可用。
- 使用绝对robot_param_node时，当前插件又加上namespace，生成`/r3//r3/...`非法服务名；独立URDF改为相对节点名，官方模型文件未修改。
- 同进程并发加载diff-drive控制器时有class factory缺失异常；改为逐台生成和激活，不强行重装插件或替换模型。
- 一次GUI冷启动服务端在`getURDF()`等待参数future，线程栈已保存：[three_blocked_server_stack.txt](/home/yhc/clinic_planning_ws/verification/three_blocked_server_stack.txt)。该轮不能视为模型已就绪或正常导航。
- 最终组合采用顺序参数往返检查/生成/控制器激活，GUI延后至全部控制器active；独立进程使用已安装的CycloneDDS及本地配置。初始Cyclone配置分别暴露默认参与者容量不足、重复选择loopback的问题，已修正为容量128且不重复指定接口；保留对应失败日志。未做单因素对照，不能把全部成功归因于某一条中间调整。
- 测试脚本开发过程中有日志关键字重复、Node保留属性命名等错误，均未计为任务成功，失败目录保留。正式完整成功运行使用`three_verified`归档版本。

没有安装新依赖、没有改变全局RMW设置。最终ROS_DOMAIN_ID=75、ROS_LOCALHOST_ONLY=1、IGN_PARTITION=`clinic_three_tb4_yhc`；两入口脚本均局部设置RMW_IMPLEMENTATION及本工作区CYCLONEDDS_URI。原生Clinic的域73与用户shell默认值未改。

完整成功运行之后，为避免用户在结束后的私人点位置直接重复完整测试，新增初始位置检查；就绪门槛也统一了收到三条以上激光/里程计及TF边的要求。负向实测[three_reset_guard_verified](/home/yhc/clinic_planning_ws/runs/three_reset_guard_verified/result.json)按预期返回`initial_poses_not_reset_restart_experiment`、无导航派发；这不是另一轮失败任务实验。正式成功运行的源码快照早于这个额外前置检查，应按归档版本解释。

## 变更文件与尚未完成内容

独立工作区新增入口与工具：

- `run_clinic_three.sh`、`verify_clinic_three.sh`、`stop_clinic_three.sh`、`README_THREE_TB4.md`。
- `launch/clinic_l1_three_tb4.launch.py`、`worlds/clinic_l1_three.sdf`、`config/three_tb4/`。
- `prepare_three_tb4.py`、`spawn_tb4.py`、`bootstrap_three_tb4.py`、`start_three_gui.py`。
- `tb4_io.py`、`tb4_service_worker.py`、`shared_resource.py`、`verify_three_tb4.py`、`audit_three_tb4.py`、`stop_three.py`。
- 原始运行/源码快照、保护清单、资产审计、图表与本地DDS配置；早期仅激活控制器的尝试工具移入verification诊断目录，最终入口不再引用。

论文仓库只新增本结果报告、更新两处索引和既定接入方案的进展；旧规划、ROS、感知代码未改。旧单机README增加三机入口指引，不删除旧原型。

本轮证明三机执行基础与资源执行守卫可工作，没有接MILP、事件协议、跌倒、异构能力、能量或计划修复。固定FIFO与脚本任务顺序不代表协同分配算法创新。服务仍为有到达/持有权守卫的模拟操作；未证明真实核验/装卸、故障下活性、丢失lease恢复或一般多机无死锁。

## 复现及下一步命令

当前三机GUI仍运行、三机均返回私人服务点、共享资源为空闲。重跑完整验证需先复位：

```bash
cd /home/yhc/clinic_planning_ws
./stop_clinic_three.sh
./run_clinic_three.sh
```

另开终端：

```bash
cd /home/yhc/clinic_planning_ws
./verify_clinic_three.sh
# 使用刚打印的新目录
/usr/bin/python3 tools/audit_three_tb4.py runs/<新目录>
```

停止工具核对记录PID、创建时间、准确launch路径与partition后只终止该进程树；本次已用`--dry-run`核对当前launch及49个后代，不使用全局pkill。原生Clinic仍可用`/home/yhc/rmf_clinic_ws/run_clinic.sh demo`重新启动。

下一步才是将event-task/v1、能力/服务约束与独立MILP策略适配到这个共同执行后端；所有对照方法应共用本轮导航和互斥规则，不能把FIFO互斥器的作用算作规划算法收益。

参考：[TurtleBot4官方多机器人说明](https://turtlebot.github.io/turtlebot4-user-manual/tutorials/multiple_robots.html)、[Humble diff_drive_controller参数](https://control.ros.org/humble/doc/ros2_controllers/diff_drive_controller/doc/userdoc.html)。本轮以本机安装源码和实际接口为准，未使用Rolling特有接口。
