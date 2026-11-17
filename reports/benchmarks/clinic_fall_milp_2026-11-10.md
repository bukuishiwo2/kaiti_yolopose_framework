# Clinic L1：event-task/v1、独立MILP与三台TurtleBot4跌倒处置闭环

日期：2026-11-10。目标是在常态任务执行中注入跌倒脚本事件，验证协议生成核验、监护和取送任务，再由既有独立MILP分配/排程，交给三套Nav2实际运行，比较相同变化代价下的全量重规划、局部修复和结构保留。

本次新增全部实验代码在 `/home/yhc/clinic_planning_ws`，项目仅新增结果文档与索引。原生Clinic演示、原有三机常态入口及项目既有规划主链保留。不是DES伪装成导航结果；Gazebo物理、官方TurtleBot4 Lite/Create3轮式控制、AMCL、Nav2、到点稳定检查及独立服务ACK实际运行。

## 场景与事件链

地图/碰撞体直接复用既有Clinic L1，不重新建图。三个同型机器人启用部分重叠功能：r1支持核验/监护、搬运、巡检；r2支持核验/监护、搬运、检查；r3支持搬运、巡检、检查。这里的异构是功能配置，不是硬件异构实验。

初始计划：r1执行N0→N3→N5，r2执行N1→N4，r3执行N2。N0/N1/N2是基地常态服务，持续30/45/50秒；N3巡检、N4检查、N5共享补给分别最早45/130/160秒启动，具有截止期限。第8仿真秒三台均正在执行常态服务时，在(11.6,-28.0)注入事件E1。

1. 原版event-task/v1协议生成唯一核验任务E1:verify，第一次更新计划；活动常态任务不可中断。
2. 实际导航、稳定到达、started、核验服务succeeded后才将脚本核验结果fall反馈协议。
3. 协议生成E1:monitor、E1:pickup、E1:deliver，第二次更新计划。监护开始后才释放取物；取物成功才释放交付；取送同机器人，监护与取送不同机器人，监护必须覆盖取送全过程。
4. 所有任务执行结果来自独立ROS服务进程反馈；完成交付后结束监护，继续常态任务，最终三车返回基地。

事件每2秒同位置刷新，检验重复观测不重复创建任务；本轮只覆盖有效位置的确认跌倒闭环，遮挡/无效位置变化属于既有协议回放或后续物理实验。没有跌倒动画、实际感知输入和抓取模型；核验结论由脚本给出，监护验证驻留和状态健康，不证明视觉持续可见。事件点与服务点由脚本指定，尚未验证二者的视线或真实观察关系；本轮只验证服务点可导航到达，不能当作真实到场确认跌倒的感知证据。

## 三种策略与公平条件

| 策略 | 未来任务保留范围 | 不可行时处理 | 求解后端 |
|---|---|---|---|
| full_replan | 全部未来任务可重新分配/排序/定时 | 返回不可行/超时 | 同一单体MILP |
| local_repair | 影响闭包外分配、顺序、时间冻结 | 只有证明不可行后才全量回退 | 同一单体MILP |
| retained_milp | 闭包外分配/顺序保留，时间允许联动 | 按原开始时间逐项释放 | 同一单体MILP |

局部修复为现有独立验证器对项目dynamic_repair闭包规则的适配，本轮没有调用或改动生产主链。结构保留不是分解算法收益实验，三者都用同一MILP约束/目标；只改变保留范围。

变化权重共同为：owner=2、shift=0.25、adjacency=1；其他项travel=0.1、normal_delay=0.1、response=1、wait=0.01、energy=0.1、return=0.01。输入、能力、事件依赖、同取送者、异监护者、监护覆盖、资源互斥、期限、返航约束及完整校验共用。

`clinic_milp_backend.py`由既有`src/kaiti_task_sim/planner.py`生成副本，唯一算法函数变化是tau：从曼哈顿时间改为已有Clinic地图A*路径时间表。净空≥0.22m、八邻域不切角，时间ceil(长度/0.22+10秒)，同点0。差异及原文件哈希见[provenance](/home/yhc/clinic_planning_ws/config/fall/provenance.json)与[patch](/home/yhc/clinic_planning_ws/config/fall/backend_tau_only.patch)。没有把A*时间表当作实际导航完成反馈。

求解异步运行，仿真时间继续前进；空闲机器人共同留5秒提交裕量，正在运行的常态服务以不可变前缀进入源状态。提交时重新检查完整约束与时效，过期计划拒绝。只有两个支持的规划时点；中途携货、监护中断、途中状态的重规划本轮不支持。

公共执行条件：Nav2成功后仍需稳定≥0.7秒、位置≤0.20m、朝向≤0.30rad、低速度、TF/odom/scan新鲜，再由服务进程返回启动/完成。共享点FIFO租约覆盖接近至离开；非持有者使用相同Nav2 KeepoutFilter避开0.8m区域，所有策略配置相同。插件依据[Nav2官方Keepout说明](https://docs.nav2.org/rolling/tutorials/general_tutorials/navigation2_with_keepout_filter/navigation2_with_keepout_filter/)，实际配置采用本机Humble支持的参数。这是执行安全设施，不属于MILP策略贡献。

## 实际结果

**三轮正式物理执行均通过：每轮6项常态服务＋4项事件服务、13段Nav2导航，三车返航、共享资源释放。合计30项服务、39段导航，独立审计94,218项通过。**

表内执行时间均为事件剧本开始后的仿真秒；求解墙钟另列，不能混用。三种策略分别冷启动一轮，未将细小执行差异解释为优越性。

| 策略 | 常态未来任务改派数 | 三项常态开始时刻绝对偏移总和(s) | 交付完成(s) | 全部返航完成(s) | 两次在线规划端到端墙钟合计(s) | 独立检查 |
|---|---:|---:|---:|---:|---:|---:|
| 全量重规划 | 3 | 115.65 | 136.55 | 202.55 | 1.850 | 30,861通过 |
| 局部修复 | 3 | 115.59 | 136.53 | 202.11 | 2.033 | 30,931通过 |
| 结构保留 | 1 | 148.65 | 136.55 | 231.36 | 1.033 | 32,426通过 |

所有正式运行的命名空间审计通过；每轮4个协议任务ID各生成一次，反复观测保持身份。实际约束检查覆盖：常态活动前缀不改派/不中断、任务释放与截止时间、服务顺序、核验后生成响应、同一取送者/不同监护者、监护实际覆盖到交付结束、驻留与稳定到达、显式启动/完成ACK、租约与区域占用、最终返航。两次提交均通过共用完整MILP约束/目标校验和提交时效校验。

共享区采样最多1台车；租约有效期间非持有者进入0.6m区的采样数均0。最小采样中心距离依次为0.431m、0.608m、0.604m。这些是采样轨迹检查，不是连续时间无碰撞形式证明。94,218项主要是轨迹/位姿重复采样，不是94,218次独立场景。

实际前后分工如下（活动常态N0/N1/N2始终按原分配完成）：

| 时点/策略 | r1 | r2 | r3 |
|---|---|---|---|
| 原计划 | N0→N3→N5 | N1→N4 | N2 |
| 核验计划，三策略相同 | N0完成→核验→N3→N5 | N1完成→N4 | N2完成 |
| 核验后，全量/局部 | 持续监护 | 取物→交付→N5 | N3→N4 |
| 核验后，结构保留 | 持续监护→N5 | 取物→交付→N4 | N3 |

结构保留只释放N3的原分配，N4/N5仍由原机器人承担；局部修复在两个时点均因冻结时间不可行而回退全量。结构保留保持了更多任务所属结构，但让常态任务时间调整更大、最终返航更晚，不能笼统称为“减少全部计划扰动”。

### 相同现场快照的多轮交错求解

取正式全量执行的核验/处置两个完整快照，固定任务、机器人状态、参考计划和全部权重。每阶段每策略1次预热＋3次正式，三轮顺序循环轮换，共18次正式＋6次预热，全部OPTIMAL并通过完整独立校验，同组最优值重复一致。最终正式计时在三轮物理执行结束、本实验Gazebo/ROS进程全部退出后的相同后台条件下进行；此处仅测完整策略求解，不包含ROS执行负载或子进程启动。此前在运动期间和收尾阶段的预检查计时保留但不用于此表。

| 阶段 | 策略 | 同范围目标J | 正式墙钟中位数(s) | 最小–最大(s) | 回退/扩展 |
|---|---|---:|---:|---:|---|
| 核验 | 全量重规划 | 33.8955 | 0.0968 | 0.0959–0.1152 | 无 |
| 核验 | 局部修复 | 33.8955 | 0.1182 | 0.1178–0.1192 | 全量回退 |
| 核验 | 结构保留 | 33.8955 | 0.0247 | 0.0247–0.0250 | 无 |
| 处置 | 全量重规划 | 256.0025 | 0.6668 | 0.6629–0.6834 | 无 |
| 处置 | 局部修复 | 256.0025 | 0.7086 | 0.7078–0.7165 | 全量回退 |
| 处置 | 结构保留 | 264.1025 | 0.1253 | 0.1245–0.1261 | 释放1项 |

这里J采用相同目标函数，但结构保留增加保留约束，最优性只对其最终范围成立。处置时J=264.1025高于全量256.0025，差8.1；这与“少改派但效率成本更高”的执行结果一致。较短求解时间来自缩小可调整范围，本轮没有分解后端，不能归因于分解加速。样本规模和重复次数不足以给出统计显著性或普遍加速结论。

原始汇总：[比较JSON](/home/yhc/clinic_planning_ws/runs/fall_comparison_summary/comparison.json)、[实际指标CSV](/home/yhc/clinic_planning_ws/runs/fall_comparison_summary/comparison.csv)、[逐任务前后计划CSV](/home/yhc/clinic_planning_ws/runs/fall_comparison_summary/before_after_plans.csv)、[同快照计时CSV](/home/yhc/clinic_planning_ws/runs/fall_snapshot_benchmark_final_idle/timing.csv)。

三轮完整结果：[全量](/home/yhc/clinic_planning_ws/runs/fall_full_verified/result.json)、[局部](/home/yhc/clinic_planning_ws/runs/fall_local_verified/result.json)、[结构保留](/home/yhc/clinic_planning_ws/runs/fall_retained_verified/result.json)。各目录均有independent_audit.json及before_after.png/svg。

![结构保留：真实轨迹、原计划、更新计划和实际服务](/home/yhc/clinic_planning_ws/runs/fall_retained_verified/before_after.png)

保护核对：[105个保护文件全部未变](/home/yhc/clinic_planning_ws/verification/fall_protected_after.json)；[后端AST校验：除tau外一致](/home/yhc/clinic_planning_ws/verification/fall_backend_ast_audit.json)；[三机六套costmap实际启用同一禁入机制](/home/yhc/clinic_planning_ws/verification/fall_keepout_runtime_parameters.json)。三轮初始计划字节一致、8个核心执行/求解文件、协议及场景/三机Nav2配置的源哈希一致，见比较JSON。


## 调试中发现且保留的失败

- `runs/fall_pilot_full`：接近取物点时过早释放租约，独立服务进程以shared_lease_missing拒绝启动。修正为关联服务实际完成且驶离1.6m后才释放，没有绕过拒绝检查。
- `runs/fall_full`：十项任务完成，但独立物理审计发现81.34–82.43秒有55个采样中另一车途经共享区，占用数为2。该轮不算通过。增加所有策略共同的动态禁入掩膜与租约前清场检查后冷启动重跑，不调整该点位置或放宽占用门槛。

保留失败日志和原始结果，不能仅以主程序passed判定闭环有效；应以独立审计为准。

## 结论边界与后续

本轮可验证：任务集合动态出现时，协议、协同分配排程与实际导航/任务反馈能够形成闭环；策略在相同变化代价下有不同的保留/释放行为。并不证明提出了新的规划理论、结构保留普遍最优或优于最新方法。相同快照的受限最优值不能与全量最优值混为一谈。

每种策略只有一个物理场景的一次正式运行；采样检查数量不是独立实验数。后续应先增加多种触发时间/位置、任务负载和固定种子重复，报告响应/扰动/失败与端到端求解分布；再加入导航迟到/失败导致的重复修复。跨机器人通道预约、移动障碍/人员、真实电量、充电、监护/携货中断均未在本轮验证。当前耗电率统一0，电量约束接口保留但不起作用。

## 文件与复现

独立入口与完整说明：[README_FALL_MILP.md](/home/yhc/clinic_planning_ws/README_FALL_MILP.md)。核心文件：

- `run_clinic_fall.sh`、`stop_clinic_fall.sh`、`launch/clinic_l1_fall.launch.py`：独立域76/分区、三机场景；原生入口不变。
- `tools/prepare_fall.py`、`fall_model.py`、`clinic_milp_backend.py`、`clinic_plan_check.py`、`fall_solver_worker.py`：协议编译、地图时间及共用求解校验。
- `tools/run_fall_episode.py`、`fall_service_worker.py`：事件、两阶段计划、Nav2与真实服务反馈。
- `tools/fall_resource.py`、`fall_keepout.py`、`config/fall/r{1,2,3}_nav2.yaml`：三策略公共共享区执行守卫。
- `tools/audit_fall_episode.py`、`benchmark_fall_snapshots.py`：独立原始轨迹审计、相同快照循环交错计时。
- 每个run保留完整输入、模型/日志、结果、源代码哈希、提交校验、协议迁移、真值轨迹、CSV与前后计划图。

下一步复现命令（两个终端，新的输出目录）：

```bash
cd /home/yhc/clinic_planning_ws
./run_clinic_fall.sh --headless
# 第二个终端
./run_fall_episode.sh --policy retained_milp --out runs/my_retained_case
/usr/bin/python3 tools/audit_fall_episode.py runs/my_retained_case
# 下次实验前冷启动
./stop_clinic_fall.sh
```

收尾核对：[实验分区无残留进程](/home/yhc/clinic_planning_ws/verification/fall_shutdown_audit.json)。最终计时环境也记录于该文件。
