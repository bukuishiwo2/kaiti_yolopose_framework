# Clinic基础设施复用与实验入口收敛

日期：2026-11-17。目标：先查上游再收敛非研究基础设施，把基础错误拦在正式研究任务之前。范围为独立Clinic工作区；不改原规划主链、感知算法、MILP模型/权重，不删除原生演示或旧结果。

## 实际完成

| 项目 | 收敛结果 |
|---|---|
| 执行入口与环境 | `clinic_experiment.sh`＋一份environment.sh；7个旧执行shell成为兼容别名 |
| 参数与场景 | 场景JSON统一供生成器和launch读取；一份Nav2模板按namespace/初始位姿展开；3机展开字典与旧验收参数一致 |
| 小车生成与控制 | 改用安装的`ros_gz_sim create`与官方controller spawner，不再在当前路径使用自写EntityFactory生成器；仍用官方TB4 URDF/控制器 |
| 执行实现 | 旧3层补丁实现平铺为一个Bot/Episode；旧Python入口只导出同一对象，无类替换补丁链 |
| 探针 | 4套循环合并到一个参数化Probe/执行循环；quick/corridor/sensor/source/clearance分别声明用途 |
| 预检 | 77项静态检查；真实消息、TF、QoS、生命周期、动作/服务与参数消费链72项检查；配置发布周期决定costmap新鲜度限制 |
| 正式实验门禁 | 完整run须有当前执行核心/配置对应的通过短测；静态到派发验证源码哈希，在线凭证检查域/partition/有效期 |
| 清理 | 按PID、创建时间、运行名/partition/进程组身份清理，包含启动中断孤儿；不按进程名全局kill |
| 审计/动画 | 显式函数接口，停止运行时字符串修改/exec脚本；新输出目录不覆盖原数据；历史审计读取冻结副本 |
| 低噪声反馈 | 终端报错摘要；原始状态和异常记录落文件。未启动新的完整MILP批次 |

这些是工程复用与可靠性改进，不作为研究创新点。

## 上游查阅与采用边界

1. [Nav2 Humble bringup](https://raw.githubusercontent.com/ros-navigation/navigation2/humble/nav2_bringup/launch/bringup_launch.py)：继续Include上游launch，复用namespace、ReplaceString与RewrittenYaml。
2. [Nav2 Humble默认恢复树](https://raw.githubusercontent.com/ros-navigation/navigation2/humble/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml)：上游已提供清图、旋转、等待等行为。当前仍调用这些原生服务器；该树还会周期性重规划，整段替换会影响当前批准路径/共享资源准入，因此未在没有等价性证据时强行更换。
3. [ros_gz_sim Humble create](https://raw.githubusercontent.com/gazebosim/ros_gz/humble/ros_gz_sim/src/create.cpp)：当前使用其文件/世界/名称/位姿参数生成机器人，编排层只处理就绪和激活顺序。
4. [TB4仿真](https://turtlebot.github.io/turtlebot4-user-manual/software/turtlebot4_simulator.html)、[多机命名空间](https://turtlebot.github.io/turtlebot4-user-manual/tutorials/multiple_robots.html)：继续复用模型与namespace隔离。
5. [Open-RMF Clinic Humble](https://raw.githubusercontent.com/open-rmf/rmf_demos/humble/README.md)：继续使用完整Clinic资产与地图，保持比例，未升级或替换原生演示。

本机Nav2 1.1.20、ros_gz_sim/bridge 0.244.26、TB4 description 1.0.5、controller_manager 2.54.3；完整deb版本与实际安装文件SHA见`/home/yhc/clinic_planning_ws/verification/runtime_convergence_2026-11-17/upstream_inventory.json`。没有仅据rolling/Jazzy文档假定Humble接口相同。

其他检查：感知已有Ultralytics/PyTorch复用，MILP使用既有PuLP/CBC，绘图继续使用Matplotlib/FFmpeg；本轮没有另造这些基础实现，也没有改动感知代码。`tb4_io`只保留frame/速度话题与状态接口适配。事件/承诺/MILP属于研究接口；FIFO和keepout仍是有限场景执行保护，不作为新交通规划算法。未把RMF任务调度与研究MILP同时接为任务所有者。

## 实测与回归

- `clinic_experiment.sh check`：77项静态检查通过。
- 当前回归17项通过：参数等价、错误scan拒绝、无Gazebo节点构造/本机QoS接口、失败前不启动世界、缺失/过期来源凭证、清理归属、停止运行名核对、121帧真实局部图回放、原研究方法/阶段逻辑AST一致、兼容模块同一对象、旧记录审计复核、禁止运行时exec/compile。
- `runtime_smoke_v7`约75.01墙钟秒：三机72项在线检查、静止R2的实体床短脉冲及两层图变化/恢复通过；真实调用标准双清图后重新观测；R1一项Nav2移动、稳定到达和服务反馈通过。仍为原0.20m/0.30rad/0.7s/0.5s到达条件。
- 新显式审计器对原始A13两轮分别复核549/557项通过；未改原始result/trace/NPZ或已有审计文件。动画重生成于新目录，1800×800、90.3秒，抽帧人工核查通过。

新预检不是一次全部写对：v1为ROS节点保留属性冲突；v2由域占用检查阻止启动（首轮启动中断遗留已按身份清理）；v3为Humble QoS返回值接口差异；v4为costmap 1 Hz发布与过严新鲜度判据不匹配，另修退出时进程环境读取竞争；v5真实床链已检测到占用，但移除后原生图残留需标准清图；v6脉冲恢复通过，但预检自身频繁图查询积压TF回调；v7增加检查节流后全部短链路通过。前六轮均未派发研究任务，原状态保留。这些说明迁移检查仍发现了缺陷，不是“以后不可能有基础错误”的保证；本次没有用40分钟完整闭环反复调试。

动画迁移也发现本机Matplotlib接口版本差异，已使用兼容布局API，没有为此升级依赖。源码迁移的中间审计/渲染失败输出保留于该工程验证目录，不混入论文对照。

## 历史保护、文件与使用

65份原验收源码/文档快照在`verification/runtime_convergence_2026-11-17/historical_accepted_sources/`；A13每轮`source/`及结果目录原样保留。当前兼容脚本改变后，不应要求工作区仍等于旧版本哈希；应核对对应冻结副本。原生/主链752文件另行核对，结果见最终工程验收JSON。

主要新增：`support/clinic_runtime/`、统一profile/Nav2模板、统一launch/CLI、回归测试、[当前手册](/home/yhc/clinic_planning_ws/README_CLINIC_RUNTIME.md)。原入口、探针和报告脚本收敛为兼容层。精确新增/变更文件及哈希见`/home/yhc/clinic_planning_ws/verification/runtime_convergence_2026-11-17/change_manifest.json`。

本轮没有对新版本重跑完整22项MILP闭环，不能将旧版本1352.39/1329.18秒用作新版本性能。静态自由像素/点距也不替代所有点位Nav2可达性与多机驻留验证；改变几何后要重新鉴定。当前短测证据用于配置/执行核心资格，CLI管理与报告模块变更由回归检查；不声称完成所有版本的长期稳定性验证。默认BT替代、RMF交通层整合仍须保持单一任务/资源所有权。

下一步只查看与离线检查：

```bash
cd /home/yhc/clinic_planning_ws
./clinic_experiment.sh --help
./clinic_experiment.sh test
```

正式研究实验前使用手册中的新运行名，先check/smoke再run；当前门禁会拒绝没有匹配短测的完整运行。原生Clinic仍通过其原入口启动，不需要经过本独立研究运行器。
