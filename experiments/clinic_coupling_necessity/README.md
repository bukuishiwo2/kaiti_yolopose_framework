# 联合分配必要性：五类耦合情景

研究内容三仍为语义事件驱动的动态协同分配与排程。本轮固定现有B0/B1/B2/B3和共同目标，先找出哪些耦合需要联合协调，哪些用简单可服务时间或固定分工重排即可。没有新分配算法、求解器或权重。

## 预先固定的场景与假设

编号S1至S5仅属于本独立实验，与仓库旧公共空间S1无关。所有新输出禁止实体派发。

| 编号 | 医院任务解释 | 冻结控制变量与简单条件 | 本轮边界 |
|---|---|---|---|
| S1 | 最近的核验机器人有不可中断工作，较远机器人较早可服务 | 以保存投影source的旅行时间定义最近者；其ready额外延长0/60/180秒；源位置和已接受计划不变。0为简单对照 | 离线投影占用假设，不把投影source说成当前真实人体或机器人位置 |
| S2 | E1监护未结束时E2跌倒，新核验、监护和配送与原义务竞争 | 第二事件偏移0/60/180秒；保留两个事件ID和独立时间/确认/ACK；禁止释放原监护 | 当前活跃监护条件缺少可验证的多事件插入契约，先保存阻断规格与实际模型探测，不伪造性能数据 |
| S3 | 普通物资配送和应急取货共用G1 | 新增普通G1→DL取送对，服务8/6秒，首名义owner=r2，不冒充accepted；额外G1预约0/120/300秒。0为无额外预约对照，原取送竞争仍存在 | 复用原锚点、entry/clear旅行表、完整资源占用和两组同车相邻约束；不声称实现狭窄通道几何冲突规划 |
| S4 | r2已携E1物资，持续阻挡期间不得换携货owner，合法常态后缀可调整 | 阻挡预计60/180秒与结束未知分开；监护随真实交付和交接才释放 | 原快照含投影携货承诺，但normalized cargo与其不一致；未知阻挡不能用固定ready证明恢复，保存证据缺口，不把后缀可行当全链恢复 |
| S5 | 应急插入挤压未来常态任务的服务期限 | 每项常态的假设due=历史accepted finish+0/90/240秒；分别做评价型due和硬deadline；逐一配对无新应急的固定归属背景 | SLA是假设，非医院实测。评价型只测迟到不改原J；硬截止不放松，迟到方案不接受；背景本已不可行时不归因于插入 |

两份固定来源为`dense_loop_a13`、`unified_bed_local_r1`。已接受常态plan来自原trace的plan_committed；源历史事件为旧脚本，当前任务束是已验证视觉角色模板的离线拼接。没有新视频/感知或Nav2实测。不同level是同源相关条件，不是独立随机试验，不按算法结果挑样本。

## 方法和公平性

- B0：全部owner固定，MILP仍优化顺序和资源时间，是强重新排程基线。
- B1：保留accepted常态owner/顺序，枚举合法应急任务束和插入位置，最早服务选择。S3唯一接口扩展是对新普通取送对枚举合法owner和相邻插入槽，不将新任务伪造成accepted；无MILP回退。
- B2：原受限域；除原necessary_normal外固定常态owner，新普通取送用名义归属。
- B3：合法未派发后缀联合分配与排程。

四法均保留现有第三角色业务硬约束、能力域、原不可撤销prefix、原资源、监护覆盖及4秒交接、取送同车相邻、release与硬deadline。剔除唯一被比较的owner锁行后，四法的目标和共同数学约束签名必须相同。

J沿用原定义：4×阶段响应 + .1×剩余预测完工 + .1×常态释放等待 + 2×accepted换机 + .05×accepted绝对时移 + .1×旅行。普通等待不冒充迟到，新增普通订单无accepted变更费。每法5秒算法墙钟、CBC seed17/单线程/同CPU，次序轮转；首次可行包含原构造初解，并非CBC内部首次发现。

正式包含24个事件条件×4法=96次调用，另12个S5无新应急背景×B0=12次。S2/S4不进入性能分母，保存结构性探测和阻断理由。

## 判别规则

先看完整约束及服务可行性，再分别看应急响应、交付、常态迟到、改派与计算时间，最后解释共同J。J更低本身不等于联合优化必要或更符合服务要求。

S1检验B1核验是否达到min(ready+travel)下界。S3比较B0与B1以区分资源排序价值和换机价值，再比较B2/B3。S5先看固定归属背景可行性，再看应急插入后的硬期限保持及评价型迟到；背景B0失败不等于联合背景也已证无解，不得把硬不可行记成零迟到成功。

预算内只有B3找到解不等于其他策略已证无解；若B0可行且质量相当，保留“简单重新排程足够”。如果联合法的J改进伴随更晚交付，作为明确权衡报告，不称全面改善。所有数量都是离线条件计数，不作实体成功率或创新性证明。

## 文件和命令

- `coupling_adapter.py`：原四策略薄适配、新普通订单接入及独立due指标。
- `run.py`：冻结实例生成、S2/S4能力门禁、复用原worker。
- `audit.py`：原完整约束、独立J与迟到重算、共同模型/来源检查、逐例与背景归因。
- `test_scenarios.py`：新身份、accepted范围、硬承诺、due和模型公平性专项测试。

本轮实际证据根：`/home/yhc/clinic_planning_ws/verification/coupling_necessity_2026-11-23_j1`。完整实测与判断见本目录`report_2026-11-23.md`。

从项目根目录运行，NEW目录必须不存在：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q experiments/clinic_coupling_necessity/test_scenarios.py
.venv/bin/python experiments/clinic_coupling_necessity/run.py generate --output /home/yhc/clinic_planning_ws/verification/coupling_NEW/formal
.venv/bin/python experiments/clinic_coupling_necessity/run.py run --output /home/yhc/clinic_planning_ws/verification/coupling_NEW/formal
.venv/bin/python experiments/clinic_coupling_necessity/audit.py /home/yhc/clinic_planning_ws/verification/coupling_NEW/formal --output /home/yhc/clinic_planning_ws/verification/coupling_NEW/audit
```

本轮不启动Gazebo，不改部署MILP/Nav2/服务worker/旧S1/历史结果，不自动提交推送。新时序、并发和普通运输角色均缺实体资格，结果只用于判别下一步研究是否必要。

本轮已完成36输入108调用、1783项审计、45项相关回归。98次返回完整合法方案；8次事件条件调用和2次背景调用在最严格硬期限处失败，全部保留。S1贪心6/6达到核验时间下界；S3没有独占可行性收益；S5存在减少常态迟到/提前监护但延后交付的取舍。评价型S5的6个阈值条件只有2个不同优化模型，不能当作6个独立决策证据。S2/S4仍为明确BLOCKED，不计入性能分母。
