# Clinic当前独立实验入口

> 新增独立实验配置：见[Fast/Standard/Benchmark手册](README_CLINIC_MODES.md)与[本轮实测](/home/yhc/kaiti_yolopose_framework/reports/benchmarks/clinic_sparse_repair_and_modes_2026-11-17.md)。默认Benchmark原条件保持。Fast/Standard功能通过但时间目标未达，不与旧Benchmark作同口径算法排名。

2026-11-17工程收敛。当前只维护`clinic_experiment.sh`。原生Clinic、旧算例与A13结果保留。统一入口已完成两组新的完整22项服务闭环，局部/热启动全量独立审计554/551项通过。实测与边界见[完整复验报告](/home/yhc/kaiti_yolopose_framework/reports/benchmarks/clinic_unified_full_loop_recheck_2026-11-17.md)；旧结果与新结果分开记录。

## 复用与职责

- Clinic地图/碰撞体、官方TurtleBot4模型、ros2_control控制器保持复用，不重建医院或小车。
- 机器人生成改用安装的`ros_gz_sim create`，控制器激活用官方`controller_manager spawner`，初始位姿只读`config/hospital_bed/scenario.json`。
- Nav2使用上游Humble `bringup_launch.py`与其`<robot_namespace>`/RewrittenYaml机制。三机从`config/clinic_runtime/nav2.template.yaml`生成参数，展开后与原验收三份参数字典相同。
- FollowPath、Spin、ClearEntireCostmap等继续由Nav2服务器实现；任务层只保留路径准入、稳定到达、服务ACK和等待升级等适配。默认上游BT会周期性重规划并有后退等恢复，直接替换会绕过当前批准路径/共享资源准入，因此本轮不整段切换BT。
- 研究逻辑保留：event-task、MILP/变化代价、承诺投影、失效检测与修复范围。MILP后端未重写、未调权重。
- `tb4_io.py`继续承担消息frame/速度话题与状态接口适配，不是新控制器。FIFO/keepout是当前有限场景的执行保护，不是通用交通算法贡献；本轮不再叠加RMF任务调度器形成双重所有者。
- 审计和Matplotlib/FFmpeg回放改为显式函数，不在运行时字符串替换/exec旧脚本。旧记录复核读冻结源码副本，不要求当前工作文件永远不变。

官方依据与本机版本见`verification/runtime_convergence_2026-11-17/upstream_inventory.json`。Humble源码：[Nav2启动](https://raw.githubusercontent.com/ros-navigation/navigation2/humble/nav2_bringup/launch/bringup_launch.py)、[默认恢复树](https://raw.githubusercontent.com/ros-navigation/navigation2/humble/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml)、[ros_gz_sim生成工具](https://raw.githubusercontent.com/gazebosim/ros_gz/humble/ros_gz_sim/src/create.cpp)、[TurtleBot4仿真](https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html)、[多机器人](https://turtlebot.github.io/turtlebot4-user-manual/tutorials/multiple_robots.html)、[Clinic Humble](https://raw.githubusercontent.com/open-rmf/rmf_demos/humble/README.md)。使用本机已安装组件，没有升级系统或重新下载世界。

## 命令顺序

```bash
cd /home/yhc/clinic_planning_ws
# 无Gazebo：配置、上游依赖、命名空间、点位等77项检查。使用新目录。
./clinic_experiment.sh check --out verification/clinic_runtime/check_repeat_01
# 无Gazebo：实际模块、参数等价、121帧回放、失败门禁、进程归属与旧记录审计回归。
./clinic_experiment.sh test
# 一个短世界：三机真实接口 + 实体床短脉冲/清图恢复 + R1一项到达/服务。
./clinic_experiment.sh smoke --name smoke_repeat_01 --domain 79
```

最后一次短验收为`runtime_smoke_v7`：72项在线检查、实体床真实激光/两层costmap变化与恢复、R1原到达守卫均通过，总墙钟约75秒。状态、预检、清理和smoke审计在`verification/clinic_runtime/runtime_smoke_v7/`，任务记录在`runs/runtime_smoke_v7/`。

仅在确需新研究实验时再运行（本次已使用新名称unified_bed_local_r1/full_r1顺序完成两组，下例仍须使用未存在名称）：

```bash
./clinic_experiment.sh run --name bed_local_new_01 --domain 79 --policy local_impact
./clinic_experiment.sh run --name bed_full_new_01 --domain 80 --policy full_warm
```

完整run在启动Gazebo之前要求存在**当前执行核心/配置**对应的通过短测记录。源码/配置不匹配、静态检查失败、在线消息/TF/QoS/生命周期不通过，均不得派发研究任务。静态预检到任务派发还检查全部源码哈希，在线凭证校验domain/partition及30秒有效期。短测复用签名排除CLI管理和报告渲染模块，这些由离线回归核查；不宣称每次文档/报告变动都重新验证了物理系统。

运行前检查域未被其他实验占用。当前入口采用0–101的保守域范围，默认79；原始高域号历史记录保留。所有输出使用新名称，禁止覆盖旧运行。Ctrl-C会结束本轮自己的执行器和Gazebo进程组；也可在另一终端：

```bash
./clinic_experiment.sh stop --name bed_local_new_01
```

只向PID、创建时间及运行名匹配的监督进程发送SIGINT，再由它清理自有进程。`stop_clinic_bed.sh --name ...`为别名；无参数/`--dry-run`保留历史手动启动器的原身份核查停止行为。原生Clinic演示不在清理范围。

## 专项探针与报告

同一个执行器支持`run --probe quick|corridor|sensor|source|clearance`。`sensor`探针明确预设携货，不是完整事件/MILP验证；`clearance`验证共享点服务—驶离—依赖反馈。探针不因注册为模式而算验证通过，按需要选取，不能每次修改都重跑全部。

对完整闭环输出复核并生成动画（新目录，不改原数据）：

```bash
./clinic_experiment.sh report runs/bed_local_a13 --out verification/clinic_runtime/a13_review_new
# 只审计，跳过动画：加 --no-render
```

77项静态检查不等于所有服务点可达/驻留安全证明；本轮布局和三机参数保持既有已验证几何。未来改变地图/点位，仍需复用已有Nav2路径/清空位探针重新鉴定，不能仅凭自由像素通过就直接做论文对照。

## 历史兼容与范围

7个`run_bed*.sh`变为兼容薄壳，共用环境；3个`run_bed_episode*.py`只导出同一实现，4个旧探针脚本转发到同一参数化运行器；旧审计/渲染转为显式函数别名。旧`run_bed_acceptance.py`仅解析原参数并转发，保留旧postprocess所需状态目录/EXECUTED标志；新工作直接使用本页入口。

`run_clinic_bed.sh`及旧launch保留给历史手动流程；当前完整run使用新的统一launch和官方生成工具。不要混合不同入口的源文件/配置来统计。原有65份源码/文档完整快照：`verification/runtime_convergence_2026-11-17/historical_accepted_sources/`；每轮A13原有`runs/*/source`、原数据及原结果不变。

此前工程收敛阶段只完成短集成；随后本次两组完整闭环验收通过。仍未证明多轮稳定性、默认BT替代可行或算法优势。前6次迁移预检中的API、退出清理、发布周期、清图/回调排空问题均有原始记录，均未派发研究任务；没有把它们删去或计入算法对照。
