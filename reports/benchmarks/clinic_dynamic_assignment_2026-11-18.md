# Clinic动态协同任务分配：四策略离线强基线实测

日期：2026-11-18。研究内容三保持**语义事件驱动、考虑执行承诺与任务依赖的动态多机器人任务分配与排程**；承诺、版本、局部修复作为执行保障。本轮实际新增算法适配器、实例生成器、四策略求解、独立复核与敏感性补充；不重复模型审查或无扰动视觉正例，不优化局部修复求解器，不启动Gazebo。

## 1. 已完成与主要判断

**阶段A/B/C最小可执行版本与离线强基线比较已完成。** 30个冻结输入×4策略＝120次正式调用，原完整phase-aware约束和新增契约独立审计3742项PASS。112份可行解全部通过；另8次为两个硬承诺—能力不相容实例下四策略拒绝，无解不是算法成功。额外4个能力可用性对照×4策略＝16次调用，263项复核PASS，单列不合并统计。10项专项测试PASS。

**动态角色选择有作用，但B3优势不成立。** 24个主体反事实输入中，B3相对B1为1胜23平0负，相对B2为1胜17平6负。固定分工B0也都可行，因此没有证明常态改派是可行性恢复所必需。少数方案改派名义后缀能改善J，不能据此宣称减少已接受任务的扰动、所有任务指标都改善或学术创新成立。

最终定向回归：本轮10项专项加原视觉接口12项，共22项PASS（`tests_final.txt`）。原S1测试未运行。PuLP仅产生既有API弃用警告，未升级依赖。

## 2. 输入、冻结与证据位置

证据根目录：`/home/yhc/clinic_planning_ws/verification/dynamic_assignment_2026-11-18_g1/`。

- `formal_01/protocol.json`：求解前冻结的目标、预算、策略、种子、源码SHA与全部输入SHA。
- `formal_01/cases/<case>/problem.json`：共同输入，含源路径/SHA、反事实参数、任务时钟、prefix与实际状态记录。
- `formal_01/cases/<case>/<B0..B3>/`：result、worker日志、CBC原始日志、MPS/solution/MIPStart；失败也保留。
- `audit_01/per_instance.csv`与JSON：逐输入/方法的响应、交付、Cmax、常态等待、真正accepted改派与时移、名义偏离、分工、路线、预算与资格。
- `audit_01/paired.csv`：同输入B3−B0/B1/B2，每项指标而非只平均J。
- `audit_01/sensitivity.csv`：同seed同策略的level1−level0；`native_constraint_audits.json`保留原验证器逐解检查。
- `analysis_01/summary.json`、`primary_timings.csv`、`primary_pairwise.csv`、`presolve.csv`：可复算的主体描述统计与预处理模型规模。
- `capability_01/`、`capability_audit_01/`：能力单因素补充，含两组重复基线及其相机能力撤销对照，不当4个新独立实体样本。
- `dev_01/`、`dev_02/`与`development_diagnostics.json`：开发/失败证据，均不混入正式统计。开发seed7的64次调用另有1975项审计PASS。

来源为已成功真实视频床扰动运行`visual_bed_2026-11-18_d1/bed_before_pickup_04`的verify、response及repair_00轻量problem、资格证书。没有导入47MB汇总或历史大轨迹；也没有重新推理或把这些反事实输入冒充新视觉观测。视频源仍为已声明的UR Fall历史训练/开发域，空间来源仍为video_source_registered；本轮不能增加感知泛化或三维定位证据。

## 3. 时间、代价和接受计划的实际改动

完整数学与时间定义见`docs/clinic_dynamic_assignment_contract.md`。

独立适配器以candidate=43.87、explicit confirmed=172.26与首次task_planning_release冻结任务时钟。重复规划用新的now不再平移release或首次start_deadline，专项测试以44与144两次编译验证输出相同。原部署compile_tasks未改，本轮修复仅适用于新适配器/实验输入。

统一J：`4×阶段响应 + .1×后缀Cmax跨度 + .1×常态释放等待 + 2×accepted换机数 + .05×accepted绝对时移 + .1×phase旅行`。verify响应从candidate起，monitor响应从confirmed起，另同时报告candidate起的端到端指标与交付完成。response实例的verify时间来自共享真实历史，明确标注shared_actual_history，不能当各方法新优化结果。

初次名义分工从accepted reference剥离，不对release=0回退参考重复收shift。普通任务没有新增软逾期项；等待不改名为延期，原硬deadline仍保留。只有repair_00后缀有真实已接受软计划，硬执行承诺另以prefix/owner约束保留。

预算5秒包含构造初解、模型构建、CBC及验证；所有方法单CPU、CBC单线程、随机种子17，方法顺序轮转。启动/导入的supervisor时间另存。CBC日志目标不含模型常数，不能直接拿日志raw objective与表中含常数J比较。

## 4. 四策略与公平性

- B0固定名义owner及原角色分工，仍优化顺序、时间和资源，是“固定归属重新排程”强基线。
- B1常态owner固定，对应急角色组合/插入槽做完整可行性检查的最早服务bundle贪心；确定性资源顺序，不用MILP或其他方法的解回退。
- B2复用当前受限归属政策、必要常态第三角色约束；在独立适配器中使用本次共享目标/时钟，**不是原部署可执行文件的原样性能**。
- B3联合优化合法未派发后缀的owner、序列和时间，prefix/硬owner不可释放。共用自己政策内验证后的构造初解，不从B0/B2最终解获益。

共同物理硬约束及任务输入相同，各策略有明确的不同策略约束；B2→B3同时改变第三角色政策和常态自由域，不能作为纯粹单因素消融。B1按预计最早应急服务选插入，不声称直接最小化共享J的全局最优。

## 5. 冻结实例与样本口径

七机制×两level×两seed(113/229)，另两control，共30输入：busy、ready、monitor_load、resource、load_count、hard、region。具体参数在契约与protocol；6/9项常态、G1不可用80/300秒、r1/r3 busy extension、A/B锚点变化均先固定再求解，不按结果筛选。

其中24例为主体分配模型反事实、4例为真实accepted后缀的承诺保障正/反例、2例为原保存输入限制资格域的control。共享一个真实episode，种子/level间有依赖，**不是30个IID实体试验**。没有把滚动修复快照混成新分配成功率。

## 6. 逐例结果与强基线结论

24个主体输入全部四方法均给出原约束可行解。B0/B2各24例证明其政策域内最优；B3均为预算内可行，没有最优证明。下表胜负仅按每例同目标J、容差.001描述：

| B3相对方法 | 胜 | 平 | 负 |
|---|---:|---:|---:|
| B0固定分工重新排程 | 5 | 15 | 4 |
| B1最早服务bundle贪心 | 1 | 23 | 0 |
| B2受限事件插入MILP | 1 | 17 | 6 |

B3相对B1相同较多，与其持有同一构造策略生成的初解有关，不是独立算法一致性的证明。B3数学可行域包含较小策略的解，也不保证5秒后找到更优incumbent。

### 6.1 busy：动态选核验者有效，简单贪心足以取得响应收益

r1前缀延长160秒后，B0核验响应285.13秒；B1/B2/B3改选r3，响应189.13秒，减少96秒。没有提早释放r1当前不可中断任务。两seed一致。

这证明预计可用时间和能力共同作用于角色选择，但不证明B3比贪心更好。r3核验未在原A证书资格内，不能直接派发。

### 6.2 ready：明确分工改变与普通任务调整的价值

`ready_l0_s113`，r1延后、r3可早用：

| 方法 | monitor/courier | monitor响应秒 | 交付从confirmed秒 | 后缀Cmax跨度秒 | 常态总等待秒 | 名义常态偏离 | J |
|---|---|---:|---:|---:|---:|---:|---:|
| B0 | r1/r2 | 228.03 | 364.03 | 672 | 3411.74 | 0 | 1413.294 |
| B1 | r3/r2 | 80.03 | 224.03 | 580 | 3189.74 | 0 | 785.794 |
| B2 | r3/r2 | 80.03 | 224.03 | 566 | 3098.74 | 1 | 772.394 |
| B3 | r3/r2 | 80.03 | 224.03 | 580 | 3189.74 | 0 | 785.794 |

B2把C0_r3_W2交给r1，进一步减少常态等待91秒、Cmax14秒；B3未在预算内找到该更优结构。该常态没有早先accepted计划，1项是名义偏离而非既有计划改派。r3监护和跨机常态均需补实体资格。

当r3也额外延长230秒（level1），各方法改回r1监护。B1/B3更早交付，但常态等待更大；B0/B2以交付晚123秒换取常态等待少326秒（seed113），按冻结J反而更低。**低J不等于每个应急完成指标都更好**。本轮目标的事件响应项是monitor开始，交付时刻另报；如果论文要直接最小化交付响应，必须另行预注册目标而非事后换口径。

### 6.3 共享G1：联合排程有取舍，不宜只汇报一个目标值

`resource_l1_s113`：B1/B3 monitor响应68.03、交付461.03、常态等待3400.74、J791.994；B2选择r3监护、释放一项名义常态给r1，monitor80.03、交付544.03、常态等待2759.74、J759.094。

B2低J同时付出monitor晚12秒、交付晚83秒，换来常态等待少641秒。该trade-off有清楚因果，不可只写“B2全面更优”。B3在长资源阻塞两seed均劣于B2，是本次六个B3劣例之一部分。

### 6.4 唯一B3优于贪心的实例及其局限

`busy_l0_s229`：B0/B1/B2 J835.331，B3 J805.331；核验响应仍125.13秒，Cmax跨度518.11→465.11，常态总等待2059→1943秒，但**五项名义常态换机**。这不是少改派示范，也不是accepted计划扰动减少；新分工未获实体资格。该case仅支持更大域可能降低共享代价，不能独立支持创新。

### 6.5 未发生分工收益的条件同样保留

monitor_load由4→240秒只拉长常态末端服务与Cmax，四方法仍同分工；load_count由6→9项增加等待和完成跨度，四方法仍同J。A→B改变monitor/交付锚点、phase、资源和旅行条件，使monitor响应68.03→121.03秒，但本组没有换机，四法相同。**不能把参数有影响写成一定产生归属变化**。

## 7. 计算代价与首次可行

24主体输入的单次描述中位数，秒，非重复计时置信区间：

| 方法 | 端到端算法 | CBC阶段 | 首个完整验证可用解 |
|---|---:|---:|---:|
| B0 | .484 | .187 | .232 |
| B1 | .241 | 0 | .241 |
| B2 | 1.055 | .740 | .242 |
| B3 | 4.454 | 4.178 | .243 |

B3通常很快有共同构造解，但大部分剩余预算未产生更好结果。这与“首次可行快”等于“优化更好/完成求解快”不同。

`ready_l0_s113`原始变量都为674；不能说B3原始变量数量更多。CBC预处理后B0为245行/101列/25整数，B2为544/172/57，B3为1554/487/209。更宽域保留更多有效组合，预处理与搜索明显更重。该例日志、所有实例的presolve.csv均保留，不做求解器种子优化。

## 8. 能力单因素补充与承诺反例

`capability_01`只在同一ready_l0输入撤去r3的camera，其他carry/move、位置、ready、任务负载、资源和权重不变。B1/B2/B3都从r3监护80.03秒变为r1监护228.03秒；交付224.03→364.03秒。B0本来固定r1，结果不变。证明任务需求—机器人能力域确实改变分配，而非只改变描述字段。

hard机制保留实际活动monitor/courier及普通任务的原prefix、来源、ready、执行记录与accepted后缀；新增future hard_owner到r3。能力正常两seed可行；撤去move后所有方法拒绝，不把任务交给其他机器、不伪造ACK、不释放承诺。这是离线拒绝非法后缀的证据，不能新增“在线活动服务取消恢复已验证”的结论。

能力补充是模型可用性反事实，不是机器人传感器真实失效实验。没有新增urgency、公平负载或复杂多事件机制。

## 9. 阶段验收、风险与下一步

| 项目 | 状态 | 验收范围 |
|---|---|---|
| A 时间/数学/accepted契约 | PASS | 新离线模式与冻结编译测试；原部署未改 |
| B 四策略实际实现 | PASS | 原MILP基础、无隐式策略回退 |
| C 冻结生成与可复现求解 | PASS | 30主输入、120调用；补充16调用独立列出 |
| D 配对、强基线与敏感性 | PASS | 全量逐例数据，不宣称方法优越 |
| 硬承诺/完整约束审计 | PASS | 主3742+补充263检查；可行解无违规 |
| B3稳定优于B1/B2 | FAIL | 1/24优于贪心、6/24劣于B2 |
| 新角色/常态跨机实体资格 | NOT_RUN | 未自动放行；需资格和新时序并发检查 |
| B区完整空间角色资格 | BLOCKED | 历史特定占用r2→G1失败未被本轮覆盖 |
| 实际Nav2方法配对 | NOT_RUN | 无新增Gazebo/实车，actual_nav2_completion为空 |
| 定量泛化/学术创新 | NOT_ESTABLISHED | 单episode派生、固定权重、无独立实体总体 |

实体资格筛查：112个主可行结果中79个仅原角色分工筛查通过但新时序未执行，33个标`MODEL_FEASIBLE_NOT_PHYSICALLY_QUALIFIED`；前者也不是新的执行证书。

建议代表候选：ready_l0_s113先补r3监护（同时r2取送）与r1执行C0_r3_W2的停靠、同伴keepout、entry/clear、Nav2稳定/新鲜度、资源ACK及并发；再比较B1/B2，因其真实存在不同owner且区别可解释。busy_l0_s229涉及5项常态换机，资格代价高，不优先实体化。region B在控制变量定位历史路径阻断根因前仍不进入正式A/B对照。

算法判断：当前证据足以支持继续研究**事件到达时，在执行前缀与DAG/资源条件下联合选择应急角色和少量普通后缀**这一问题；不足以支持立即宣称或包装新算法。B1已取得主要响应改善，B2在共同预算下很强。下一步先分离B2第三角色政策与普通任务开放范围两因素，补“新事件到来前已有接受软计划”的动态插入快照，再检验结构化联合插入是否填补明确缺口。保持本轮权重与失败数据，不以更换求解器/权重、扩大自由域或回到局部修复种子调优替代贡献论证。

## 10. 变更、保护与复现命令

新文件：

1. `src/kaiti_task_sim/clinic_assignment.py`：冻结编译、共享目标/域、原MILP扩展、可行bundle构造、完整热启动与指标。
2. `scripts/benchmark_clinic_assignment.py`：预注册生成、B0–B3 worker、共同预算、日志与顺序控制。
3. `scripts/audit_clinic_assignment.py`：原完整约束和目标/前缀/政策独立审计、逐例/配对/敏感性CSV。
4. `scripts/probe_clinic_assignment_capability.py`：单因素相机能力补充、实际求解及复核。
5. `scripts/summarize_clinic_assignment.py`：描述统计、成对胜负和CBC预处理规模。
6. `tests/test_clinic_assignment.py`：10项专项测试。
7. `docs/clinic_dynamic_assignment_contract.md`：长期数学与实验运行契约。
8. 本报告；另只追加docs索引/当日日志，保留此前文字。

254项原部署/模式/源码/历史证据保护哈希在写文档前全部一致；最终保护报告对工作日志只允许本轮尾部追加并复核旧字节前缀。未修改旧S1、未运行其已知失败测试，未提交推送。Fast/Standard仍为功能通过、时间目标未达。

在项目目录执行，所有NEW目录必须不存在：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_clinic_assignment.py
.venv/bin/python scripts/benchmark_clinic_assignment.py generate --output /home/yhc/clinic_planning_ws/verification/assignment_NEW --seeds 113 229 --budget 5
.venv/bin/python scripts/benchmark_clinic_assignment.py run --output /home/yhc/clinic_planning_ws/verification/assignment_NEW
.venv/bin/python scripts/audit_clinic_assignment.py /home/yhc/clinic_planning_ws/verification/assignment_NEW --output /home/yhc/clinic_planning_ws/verification/assignment_audit_NEW
.venv/bin/python scripts/probe_clinic_assignment_capability.py generate /home/yhc/clinic_planning_ws/verification/assignment_camera_NEW
.venv/bin/python scripts/probe_clinic_assignment_capability.py run /home/yhc/clinic_planning_ws/verification/assignment_camera_NEW
.venv/bin/python scripts/probe_clinic_assignment_capability.py audit /home/yhc/clinic_planning_ws/verification/assignment_camera_NEW --output /home/yhc/clinic_planning_ws/verification/assignment_camera_audit_NEW
```

已保存结果无需重跑求解，下一步可先换新目录只读复核：

```bash
.venv/bin/python scripts/audit_clinic_assignment.py /home/yhc/clinic_planning_ws/verification/dynamic_assignment_2026-11-18_g1/formal_01 --output /home/yhc/clinic_planning_ws/verification/assignment_review_NEW
```

CBC墙钟预算、主机负载及单次计时可能影响预算内incumbent；协议和原始输入可复现不等于每次必须得到相同incumbent。后续若需统计性能，应在独立场景/多次计时上重新预注册，不能将本次胜负扩展为总体显著性。
