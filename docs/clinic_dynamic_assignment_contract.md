# Clinic独立动态任务分配实验契约

冻结日期：2026-11-18。研究内容三以语义事件驱动的动态协同分配和排程为主体；执行承诺、版本与局部修复作为执行保障。本文对应独立离线适配器，不更改实际部署MILP或成功运行入口，也不声称提出新求解器。

## 1. 时间与接受计划

所有优化时刻均为Clinic时钟。UR Fall源视频时间、回放单调钟、ROS时间另有映射，不与该时钟相减。

- `candidate_at`：首次有效模型候选建立时间，本证据为43.87。
- `confirmed_at`：带事件ID与来源的显式fall核验结论被接受时间，本证据为172.26。verify服务成功不自动产生该结论。
- `task_planning_release`：该任务首次满足语义生成条件、允许参与排程的时间。verify为43.87，后续三角色为172.26。可先联合排程，不代表允许绕过依赖立即执行。
- `execution_ready`：运行时依赖、位置、资源及服务守卫均满足后的派发条件；本轮不派发，不能从预测start推定其已满足。
- `compile_frozen`逐任务用首次generated_at编译；重复规划的now只更新当前可执行下界，不移动release或start_deadline。首次360秒响应时窗属于当前既有任务语义；deadline仍使用保存模型的硬截止，不因等待自动延后。新任务修订不在本轮隐式重置时限。
- `nominal_owners`仅为首次名义分工。不是accepted plan，不收取owner/shift费用。
- `reference`只收录有来源的已接受软计划。本次verify/response源中的release=0回退reference被排除；`repair_00`真实接受后缀保留。不可撤销承诺另作硬约束，不用大罚项代替。

## 2. 数学定义

任务集合J、机器人R、事件任务依赖DAG、能力需求Kj、候选服务锚点、entry/service/clear占用与旅行表均由同一冻结输入给定。`x_rj`表示归属，`a_ruv`表示同一机器人任务顺序，`s_j/f_j`表示服务开始/完成。监护完成时间可延长，其他服务duration固定。

合法候选域为：

`D_j = capability_compatible(j) ∩ declared_spatial_domain(j) ∩ hard_owner(j)`。

策略约束只能进一步缩小域；如果与硬owner冲突则空域，不覆盖硬承诺。已下发/活动任务从优化后缀移除，原prefix、执行记录/token及状态原样保留，后缀首段从投影source_anchor和ready之后开始。反事实busy只延长ready，不能提早释放前缀。

共享物理约束复用原`aligned_solver.Model`与`aligned_contract.validate`：唯一归属、路线流/次序、能力、release与硬截止、历史/后缀依赖、phase-aware旅行、完整资源占用/互斥与阻塞、能量、取送同车且相邻、monitor与courier不同、监护先于pickup并覆盖deliver。本适配器明确保持deliver结束后4秒交接裕量。本场能耗率为0，不能据此宣称电量分配贡献。

资源占用为 `[s_j-approach_j, f_j+egress_j]`，不是仅服务duration。旅行用原entry/clear表并包含离开、接近时间，虚拟END保持原open-route含义；Cmax不是实际返航时间。

共享评价与MILP目标：

`J = 4 R_stage + 0.1 (Cmax-now) + 0.1 Σ_normal(s_j-release_j)`

`    + 2 Σ_accepted(owner_j≠old_owner_j) + 0.05 Σ_accepted |s_j-old_s_j| + 0.1 Σ_route τ_r(u,v)`。

- 核验阶段`R_stage=s_verify-candidate_at`。
- fall确认后的响应阶段`R_stage=s_monitor-confirmed_at`；同时报告monitor/deliver从candidate_at与confirmed_at起算的指标，不拼接有利起点。
- Cmax为所有后缀路线预测结束的最大值，另报告交付预测完成；全部不是实际Nav2完成时间。
- 普通任务项是释放后等待，不是逾期惩罚。没有实际due date就不制造软逾期项；保存的硬deadline仍严格检查。
- 只有accepted集合收取改派/时移，名义偏离单独作为指标，不混称已有承诺破坏。两项不再同时把初次release=0等待重复收费。
- 本轮固定权重，无新紧急度/公平负载项；工作量变化通过实际任务、依赖与ready影响分配，负载另作评价。

## 3. 四策略实现和比较范围

| 方法 | 决策规则 | 失败处理 |
|---|---|---|
| B0 | 所有名义角色/常态owner固定，MILP优化排序与时间/资源，是强于固定序列的重新排程基线 | 原样报告无解/预算内未知 |
| B1 | 常态owner不改；枚举能力/域合法的应急角色组合和插入槽，完整依赖、覆盖、资源传播与原验证；按最早应急开始、交付、J选择 | 确定性资源顺序造成的循环/不可行明确失败，无MILP/全量回退 |
| B2 | 保留当前受限插入的归属政策：除necessary_normal外常态owner固定；响应保留该常态由monitor/courier之外第三机执行的政策 | 不静默扩大自由域 |
| B3 | 所有合法未派发后缀联合owner/序列/时间优化；prefix和hard_owner仍不可撤销 | 预算内无新解可以保留自己已验证的构造初解，不借用B0/B2最终解 |

B1是较强的bundle最早服务插入，而非单任务最近距离贪心。固定资源顺序/常态owner是其明确局限。B2保留政策但换用本实验统一目标/时钟，不能称原部署可执行文件的原样性能；B2→B3既移除第三角色政策也开放常态域，不是单一自由域消融。

B0/B2/B3共用各自政策下的B1式构造作为MIPStart，先通过完整模型行、边界和独立计划约束再使用，包含在共同5秒墙钟预算。CBC单线程、固定随机种子17、绑定同一可用CPU，BLAS线程1；方法运行顺序按实例轮转。原构造解/模型构建/求解/验证均计时。预算指worker算法时间，Python导入与进程启动另报supervisor墙钟；最终计时写盘允许0.15秒收尾容差。

`first_feasible_seconds`为首个完整验证、可交付incumbent的可用时间（包括构造阶段）。CBC内部首整数解秒数另存，不能将该内部日志时间当作端到端首次可行。若只在CBC返回后能读取验证解，则first_feasible为保守上界，不伪造更早时间。没有可行解为空值，不算零秒成功。

## 4. 冻结生成规则与样本单位

正式`formal_01/protocol.json`在求解前冻结代码SHA、源problem SHA、全部任务输入SHA、两个种子113/229、每机制两level、共同预算和目标。开发seed7只用于排错，不与正式结果混算，未按性能修改权重或筛选样本。

| 机制 | level0 / level1；正常duration用同seed的0–3秒扰动 |
|---|---|
| busy | 真实verify前缀上r1 ready额外延长0/160秒；同时保留6项未来常态 |
| ready | response上r1延长160秒，r3延长0/230秒；保持实际能力重叠 |
| monitor_load | C0_r1_W3服务4/240秒，考察持续监护与常态竞争 |
| resource | G1从规划now起不可用80/300秒，服务资源与巡逻任务共同竞争 |
| load_count | 6/9项常态；新增3项LOAD在原合法锚点，依赖各自W3，服务30秒 |
| hard | 实际repair_00接受后缀，增加未来hard_owner(r3,W3)；level1移除r3的move，使硬承诺与能力不相容，所有策略应拒绝，不解锁 |
| region | A/B注册语义锚点及原phase/旅行/资源表随位置改变；G1仍为取货点 |

另保留2个原verify/response时钟、角色与常态域严格限制的保存输入control。总计30输入、120调用。hard的4输入属于执行保障/后缀反例，不能与新事件分配收益混为同一总体；两个control也不算新独立实体实验。正常duration扰动不是新观测。所有level、seed共享一个真实episode，不能称30个IID随机试验，也不能以滚动修复快照凑分配样本。未进行多事件实验。

## 5. 空间资格与后续实体门禁

本轮扩大的是显式反事实模型域，不是原Nav2执行资格。A只已有r1 verify/monitor、r2 pickup/deliver的完整角色证书；其他能力合法角色和常态跨机/新增顺序均标`MODEL_FEASIBLE_NOT_PHYSICALLY_QUALIFIED`。原角色组合也仅标`ROLE_ASSIGNMENT_QUALIFIED_EXECUTION_NOT_RUN`，新时序并发仍需检查，绝不自动dispatch。

B只有部分资格，已知特定占用下r2→G1无路径。本轮region B仅模型反事实；正式双区域实体分配对照BLOCKED，不将碰撞栅格点或MILP可行当资格。source保持`video_source_registered`，未宣称RGB-D三维定位或多机器人几何路径协同完成。

先从离线成对结果选择确实不同的分工；对新增r3监护、r3取送或常态跨机，分别验证原Nav2路径/到达/稳定/freshness、entry/clear、停靠、同伴keepout、资源ACK、并发及返回。不得为获得收益降低守卫；实体配对前先持证，原Benchmark/Fast/Standard保持不动（功能通过，时间目标未达）。

## 6. 复现

在项目根目录，使用已有`.venv`，不安装/升级部署库：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_clinic_assignment.py
.venv/bin/python scripts/benchmark_clinic_assignment.py generate --output /home/yhc/clinic_planning_ws/verification/assignment_NEW --seeds 113 229 --budget 5
.venv/bin/python scripts/benchmark_clinic_assignment.py run --output /home/yhc/clinic_planning_ws/verification/assignment_NEW
.venv/bin/python scripts/audit_clinic_assignment.py /home/yhc/clinic_planning_ws/verification/assignment_NEW --output /home/yhc/clinic_planning_ws/verification/assignment_audit_NEW
```

目录已存在会拒绝写入；失败目录保留诊断后换新目录。审计重新调用原完整约束检查，独立复算目标、政策锁、原prefix/source与接受计划，并输出逐例、配对及level敏感性CSV。它验证保存解，不会将优化器状态直接当成功，也不会用放松约束的解覆盖失败方法。
