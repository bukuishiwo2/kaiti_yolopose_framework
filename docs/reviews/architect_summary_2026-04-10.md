# Architect Summary 2026-04-10

## 1. 任务目标

基于以下已完成输入，做一次项目级统一收口：

- `docs/reviews/perception_audit_2026-04-10.md`
- `docs/reviews/system_audit_2026-04-10.md`
- `README.md`
- `docs/kaiti_alignment.md`
- `docs/system_architecture.md`
- `docs/system_bringup_skeleton.md`

本报告的目标不是重复两份审计细节，而是回答 4 个项目级问题：

1. 当前感知主线和系统骨架分别到了哪一步
2. 哪些问题属于“主线收口问题”，哪些属于“系统闭环问题”
3. 哪些问题优先级最高，会直接影响后续联调与阶段结论可信度
4. 还差哪一步，项目才能算“感知主线收住、系统骨架立住”

## 2. Changed Files

本次仅写入 1 个文件：

- `docs/reviews/architect_summary_2026-04-10.md`

## 3. 项目级判断

### 3.1 当前总体阶段

当前仓库已经不是“只有跌倒检测代码的实验仓库”，也还不是“感知到任务层已打通的机器人系统原型”。

更准确的阶段判断是：

`感知主线已基本形成可训练、可推理、可评估的研究闭环；ROS2 系统骨架已完成节点边界、topic 命名和启动入口的第一轮搭建；但默认主线尚未完全收口，运行时闭环尚未真正打通。`

因此，项目当前最合适的阶段标签应是：

`感知子系统已成型，系统骨架处于 v0，占位接口已立、运行闭环未完成。`

### 3.2 感知侧结论

感知链路的核心结论不是“缺模块”，而是“缺主线收口”。

已成立的部分：

- 数据构建、训练、推理、评估、稳定化链路已经形成代码闭环
- `LSTM` / `TCN` / 规则法三条研究分支边界清楚
- benchmark 与工作记录已经给出阶段性结论：`LSTM` 是当前综合主模型，`TCN` 是低误报候选

未收住的部分：

- 默认推理入口仍指向 `TCN`，与文档、benchmark、工作记录中的 `LSTM` 主线结论不一致
- 运行接口仍暴露双路实验输出，没有单一任务级最终语义输出

项目级判断：

`感知主线在研究结构上已经闭环，但在默认配置、默认输出语义、默认运行入口上还没有收成单一 canonical 主线。`

### 3.3 系统侧结论

系统骨架的核心结论不是“方向错了”，而是“边界已立、运行未闭环”。

已成立的部分：

- `pose_stream_node`、`system_supervisor_node`、系统级 launch、YAML 配置和文档边界已经搭起来
- `/kaiti/perception/events`、`/kaiti/system/supervisor/status`、`/kaiti/task_planner/request` 这组接口命名方向是清楚的
- `RTAB-Map / Nav2 / PlanSys2 / LTL` 的系统扩展位置已在文档层预留

未闭环的部分：

- 感知桥接当前不是在线持续发布语义事件，而是推理结束后才发一次结束消息
- 监督节点没有真正向 planner request topic 发布任务请求
- 参数 YAML 与节点名不匹配，配置实际是否注入节点不可靠

项目级判断：

`ros2_ws` 当前更适合定义为系统骨架 v0，而不是可联调的感知到任务层桥接实现。`

## 4. 优先级归类

### 4.1 主线收口问题

这类问题会直接影响“当前默认主线到底是什么”以及 benchmark、README、系统接入是否指向同一套结论。

#### P0

1. 默认学习型入口未收口到 `LSTM`
   - 文档、benchmark、工作记录都认定 `LSTM` 是主模型
   - 默认推理配置却仍指向 `models/fall_sequence_tcn.pt`
   - 这是当前项目最核心的主线漂移问题

2. 缺少单一 canonical perception output
   - 当前同时暴露 `stable_fall_detected` 和 `seq_stable_fall_detected`
   - 这适合研究对照，不适合作为系统默认主输出

#### P1

1. benchmark 结论没有在配置层形成强绑定
   - 当前主线更多靠文档和命名维持
   - 容易再次出现“文档说 A，默认入口跑 B”

2. 训练分布与未来系统消费接口存在错位
   - 当前训练仍偏单人主目标
   - 在线接口已朝多目标、track 级状态扩展

### 4.2 系统闭环问题

这类问题会直接影响“系统骨架能否作为下一阶段联调基座”。

#### P0

1. 感知桥接不是在线事件源
   - 运行期没有持续语义事件流
   - 监督层和后续规划层无法基于实时消息工作

2. 参数配置注入路径不自洽
   - YAML 顶层键与实际节点名不一致
   - topic、infer config、planner mode 等参数可能未按文档预期生效

3. planner request 只有命名，没有真实发布链路
   - 当前 `/kaiti/task_planner/request` 仍是文档接口，不是运行时接口

#### P1

1. 事件 schema 尚未冻结
   - 字段名在文档、runner、supervisor 之间仍有漂移
   - 继续扩展时会持续增加兼容逻辑

2. `RTAB-Map / Nav2 / PlanSys2 / LTL` 仍主要停留在架构占位
   - 方向正确
   - 但尚未形成可验证的订阅、发布、action 或消息边界

## 5. 结构性结论

### 5.1 当前已经收住的部分

可以认为已经基本收住的，是“研究型感知子系统框架”这一层：

- 感知代码结构闭环已经成立
- benchmark 已能支持主模型判断
- ROS2 节点边界和系统命名方向已经立住
- 项目定位已经从单模型实验扩展到“感知子系统 + 系统骨架”

### 5.2 当前还没有收住的部分

当前还不能说“感知主线和系统骨架都已收住”，原因有两个：

1. 感知主线还没有在默认入口层完成统一
   - 当前主线结论和默认运行配置不一致
   - 因而仍是“可运行、可研究、但默认口径不够稳定”的状态

2. 系统骨架还没有形成真实运行时闭环
   - 当前缺在线事件流
   - 缺 planner request 真发布
   - 缺可靠参数注入

### 5.3 项目现在到底到了哪一步

项目现在到了这样一个节点：

`感知研究主线已经具备阶段性可交付结果，系统骨架已经具备架构落点，但两者之间还没有通过稳定默认配置和实时消息闭环真正合并成同一条系统主线。`

这意味着当前阶段已经可以支撑：

- 感知 benchmark 持续推进
- ROS2 拓扑与接口命名继续收敛
- 后续系统节点分工不再从零设计

但还不能支撑：

- 用默认入口直接代表当前项目主线
- 把现有 `ros2_ws` 视为已经打通的感知到任务层桥接
- 基于现状直接开展规划层联调并输出可信系统结论

### 5.4 还差哪一步才算“感知主线和系统骨架都收住”

至少还差以下 3 个收口动作：

1. 把默认学习型入口、默认 checkpoint、README 命令、benchmark 口径统一到 `LSTM` 主线
2. 把感知输出收敛成单一任务级语义事件，并通过 ROS2 持续流式发布
3. 让 `system_supervisor_node` 真实承担“感知到任务层 handoff”职责，至少完成稳定的 planner request 输出

只有这 3 步完成后，才能说：

`感知主线已收口，系统骨架已从文档占位升级为可联调骨架。`

## 6. 指标或结构性结论

本次收口不新增实验指标，项目级有效结论以结构性判断为主：

1. 感知主链路已具备完整研究闭环，但默认主线入口仍失配。
2. 当前默认主模型的项目结论仍应保持为 `LSTM`，`TCN` 仍应定位为低误报候选，不应成为默认系统入口。
3. `ros2_ws` 已完成骨架 v0 搭建，但还未形成真实的感知事件流和任务请求流闭环。
4. 当前项目的首要任务不是继续扩展新模块，而是先完成“主线统一”和“运行时闭环”两类收口。
5. 在这两类收口完成前，仓库最准确的阶段描述是“感知子系统已成型，系统级联调尚未完成”。

## 7. 未解决风险

- 若默认入口继续漂移，后续 benchmark、README 命令、ROS2 默认接入将长期指向不同主线，项目结论可信度会继续下降。
- 若感知输出继续维持研究态双输出而不收敛为单一系统输出，任务层接口会反复返工。
- 若 ROS2 侧参数注入问题不先修正，后续 topic 重映射、多实例、部署迁移都会不稳定。
- 若系统层继续只补文档占位、不补在线事件链路和 planner request 链路，`RTAB-Map / Nav2 / PlanSys2` 接入将缺少稳定 handoff 点。
- 若多人场景与 track 级接口成为下一阶段重点，当前训练分布与运行分布的错位会被放大。

## 8. 下一步命令

建议下一轮按“先收主线，再补闭环”的顺序推进：

```bash
git diff -- docs/reviews/perception_audit_2026-04-10.md docs/reviews/system_audit_2026-04-10.md docs/reviews/architect_summary_2026-04-10.md
rg -n "fall_sequence_tcn.pt|fall_sequence_lstm.pt|infer_pose_stream.yaml|task_planner/request|person_state" README.md docs configs ros2_ws src
python3 -m compileall ros2_ws/src/yolopose_ros
ros2 launch yolopose_ros system_stack.launch.py
```

下一轮工程动作建议按这个顺序执行：

1. 先统一 `infer_pose_stream.yaml`、README、benchmark 与默认主模型口径
2. 再让 `pose_stream_node` 发布逐帧稳定语义事件
3. 最后让 `system_supervisor_node` 真正输出 `/kaiti/task_planner/request`

