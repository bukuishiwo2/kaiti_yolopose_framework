# Clinic独立多事件能力入口

本目录扩展问题表达能力，不比较B3优越性，不接实车或自动启动Gazebo，不替换正式Clinic执行器。分支为本轮读取到的既有分支，用户未提交改动均保留。正式运行入口仍是原来的单事件Clinic链；这里的registry、编译器、MILP和监测器是独立离线能力入口。

本轮权威证据根：
`/home/yhc/clinic_planning_ws/verification/multievent_2026-11-23_k1`。
结果说明见本目录`report_2026-11-23.md`。

## 文件职责

| 文件 | 职责 |
|---|---|
| event_registry.py | 一个全局事件registry，按event_id复用原单事件状态转移；实际快照导入、全局机器人占用/携货保护、显式复核和交接门禁 |
| event_model.py | 事件索引化MILP、活动监护剩余区间、issued owner/goal、完整资源区间及独立验证 |
| prepare_active.py | 编译已冻结的真实E1活动快照；可单独插入仅核验的E2候选 |
| capability_cases.py | 预设7类能力输入，保留可行、不可行和不支持边界 |
| solve_model.py | 原CBC求解、独立审计、待执行单事件的新旧模型对照 |
| audit_capability.py | 读取冻结源码/输入，重验完整方案与身份/资源负例 |
| diagnose_cargo.py | S4只读ACK/actual/proxy来源诊断，绝不修改正式恢复后端 |
| ltlf_specifications.json | 8条独立事件级有限轨迹规则及事实语义 |
| generate_tables.py | 复用原Spot生成器，隔离处理有限自动机缺失转移并验证语言保持 |
| ltlf_transition_tables.json | Spot 2.15.1生成的运行时表；普通ROS/Python无需导入Spot |
| trace_monitor.py | 流式读取真实反馈，绑定worker ACK；事件隔离、计划版本继承和checkpoint |
| test_registry.py / test_multievent_model.py / test_trace_monitor.py | 状态、模型、篡改与有限轨迹负例；不是新视觉或三机执行证据 |

## 约束和表达边界

每个event_id拥有独立生命周期、任务映射、candidate/confirmed时钟、位置来源和关闭义务。新事件不会覆盖旧事件。候选仅生成verify；阳性分支必须有本事件明确来源的复核条件。两个事件不得共用完成事实或交接凭据。

活动monitor以`monitor_continuation`表示剩余占用：其区间起点为当前快照时刻，原actual_started_at、owner、record task ID、attempt、execution_revision和目标仍逐字段保留，不重新启动服务。残余最小服务时长为`max(0, 原minimum-(now-actual_start))`；原start deadline检查实际开始时刻，不把它改成新的响应窗口。

原backend的异常检查保留。原来被移出后缀的活动monitor现在有明确的剩余区间，monitor/pickup/deliver仍需完整存在。未来动作仍用原route、能力、依赖、能量和cargo模型；新层补充事件级响应、交接4秒、完整entry/service/clear互斥和持续监护资源。原清场任务、同监护机器人直接清场、courier常态任务等待清场的约束也保留。

目标沿用11月18日独立分配契约及原权重：4×各事件阶段响应之和 + .1×剩余完工 + .1×常态等待 + 2×accepted改派 + .05×accepted绝对时移 + .1×旅行。活动监护的响应为已发生的常数；不重复收费或重置。这里不是对原部署目标做改写，也不改变360秒开始时限、1800秒事件结束期限。旧部署原权重保存在输入中供辨别，未修改原配置。

所有计划输出均禁止dispatch，不生成实际关闭记录。future availability是可撤回预测，不是完成ACK。暂不支持活动非监护服务恢复、活动监护交接、实物携货交接、非零活动前缀电池账本、未知持续阻挡下的保证恢复。遇到这些状态输出BLOCKED，不删义务或改owner。

## 能力验收

正式仅采用`capability_formal_03`及`capability_audit_02`。共7个模型输入：5 PASS、1 INFEASIBLE、1 BLOCKED；44项冻结/结果审计和934项完整返回方案检查通过。INFEASIBLE是预设单相机覆盖两个正重叠监护区间的边界；并发重叠是结构测试，不是新设响应阈值。

E2正例是明确标记的离线语义分支，不是新模型视频结果或实际ACK。顺序事件采用另一条真实已完成E1日志的最终空闲状态，不把两个不同历史episode拼成同一执行轨迹。

待执行单事件对照使用`single_pending_smoke_02`：新旧模型都证明最优，目标相等，方案通过双方检查。活动监护做了残余区间代数一致性与原历史身份检查；旧模型本不支持活动事件，所以不声称取得其通用形式化等价证明。

B0/B1/B2/B3尚未全部适配相同多事件语义，正式多事件算法对照仍为BLOCKED。不要把本轮可行性结果写成某个策略性能更好。

## LTLf和S4证据

真实历史`positive_02`、成功床扰动`bed_before_pickup_04`和误报关闭`visual_false_alarm_a2`通过本轮时序范围检查。失败/未完成的`bed_before_pickup_01`保留INCONCLUSIVE_PREFIX。原式样未触发的规则单列coverage，不以真空满足证明行为已验证。新双事件方案只有优化预测，未计作LTLf实际执行通过。

真实receiver日志是受控场景交接，按本事件已存在的delivery ACK绑定；原日志没有独立receiver执行token，这一细粒度身份范围没有被补造。计划版本直接读取actual日志，缺失版本的commit仅标为缺失，不自行编号冒充真实版本。

S4结论为合法不同表示：actual_snapshot和commitment持有E1，取货worker/protocol ACK相符；snapshot_states是已清cargo的后缀代理。配送记录缺少的token字段仍为空，不能据此声称完整配送token审计通过。未知解阻仍BLOCKED。

## 运行命令

新输出目录必须不存在，不覆盖本轮正式目录。现有真实输入及源日志是复现依赖，不是新的可独立部署包。

```bash
cd /home/yhc/kaiti_yolopose_framework
E=/home/yhc/clinic_planning_ws/verification/multievent_2026-11-23_k1
N=/home/yhc/clinic_planning_ws/verification/multievent_REPRO_NEW
.venv/bin/python experiments/clinic_multievent/capability_cases.py generate --seed "$E/active_monitor_fixture_seed_01.json" --output "$N/formal"
.venv/bin/python experiments/clinic_multievent/capability_cases.py run --output "$N/formal"
.venv/bin/python experiments/clinic_multievent/audit_capability.py "$N/formal" --output "$N/audit"
.venv/bin/python experiments/clinic_multievent/trace_monitor.py /home/yhc/clinic_planning_ws/verification/visual_positive_2026-11-18_c1/positive_02/trace.jsonl --output "$N/ltlf_positive"
.venv/bin/python experiments/clinic_multievent/diagnose_cargo.py --output "$N/cargo_diagnosis.json"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q experiments/clinic_multievent/test_registry.py experiments/clinic_multievent/test_multievent_model.py experiments/clinic_multievent/test_trace_monitor.py tests/test_ltlf_monitor.py
```

普通回放只加载现有表。若以后改公式，必须在原独立Spot环境重新生成到新文件，先审查并保留旧表，不在ROS环境装Spot：

```bash
/home/yhc/anaconda3/envs/kaiti-ltlf-spot/bin/python experiments/clinic_multievent/generate_tables.py --source experiments/clinic_multievent/ltlf_specifications.json --output /home/yhc/kaiti_yolopose_framework/experiments/clinic_multievent/ltlf_tables_NEW.json --audit-output /home/yhc/clinic_planning_ws/verification/finite_completion_NEW.json
```

本轮最终相关回归70项通过，非全仓测试声明。旧公共空间S1不运行、不修改；原Benchmark/Fast/Standard、Nav2、worker和求解器均保持本轮写入边界之外。全体原文件保护结果以新证据根`protection_check.json`为准。
