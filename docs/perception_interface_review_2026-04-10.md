# Perception Interface Review (2026-04-10)

## 任务目标

对照当前 ROS2 topic 的临时 `std_msgs/String + JSON` 接口，审查感知侧逐帧输出字段的稳定性，回答以下问题：

1. 当前 perception 侧实际输出了哪些字段，哪些稳定，哪些仍是临时占位或研究态字段。
2. 如果 system_planner 收敛成正式 schema，当前哪些字段已经够用，哪些字段名称或语义需要调整。
3. 当前跌倒检测模块是否可用，可用到什么程度。
4. 若目标是逐步达到 `/home/yhc/kaiti.docx` 所描述的项目使用要求，感知模块下一阶段最该如何发展。

本次只做审查与接口建议，不改模型逻辑。

## 变更文件列表

- `docs/perception_interface_review_2026-04-10.md`

## 1. 当前 perception 侧实际输出字段

当前逐帧事件载体由 `PoseRunner.run()` 直接拼接生成，基础字段定义在 [src/yolopose/pipeline/runner.py](/home/yhc/kaiti_yolopose_framework/src/yolopose/pipeline/runner.py#L120)，规则跌倒字段来自 [src/yolopose/pipeline/fall_detector.py](/home/yhc/kaiti_yolopose_framework/src/yolopose/pipeline/fall_detector.py#L74) 与 [src/yolopose/pipeline/fall_detector.py](/home/yhc/kaiti_yolopose_framework/src/yolopose/pipeline/fall_detector.py#L129)，时序跌倒字段来自 [src/yolopose/temporal/sequence_fall_detector.py](/home/yhc/kaiti_yolopose_framework/src/yolopose/temporal/sequence_fall_detector.py#L101)。

### 1.1 基础感知字段

当前每帧固定输出：

| 字段 | 当前含义 | 稳定性判断 |
|---|---|---|
| `ts` | UTC 时间戳字符串 | 稳定，建议后续正式化为 `header.stamp` 或 `stamp` |
| `frame_id` | 感知内部帧序号，从 1 递增 | 稳定，建议更名为 `frame_seq` 或进入标准 `Header` 语义 |
| `source` | 输入源标识，来自结果路径或配置源 | 半稳定，当前混合了文件路径、整数摄像头索引等多种语义 |
| `person_count` | 当前帧人数 | 稳定，可直接用于正式 schema |
| `raw_person_present` | 是否达到最小人数阈值 | 半稳定，属于中间判定值 |
| `stable_person_present` | 经过迟滞稳定化后的人存在状态 | 稳定，适合作为任务层可消费字段 |
| `state_changed` | `stable_person_present` 是否本帧切换 | 半稳定，更像传输优化或调试信号 |

### 1.2 规则跌倒字段

当前规则法输出：

| 字段 | 当前含义 | 稳定性判断 |
|---|---|---|
| `fall_detector_enabled` | 规则法是否启用 | 调试/健康态字段，不应直接作为任务语义 |
| `fall_track_mode_used` | 是否使用 track 级稳定化 | 内部实现细节，研究态 |
| `raw_fall_detected` | 单帧或当前候选层面的跌倒判定 | 研究态，噪声较大 |
| `stable_fall_detected` | 迟滞稳定后的规则跌倒状态 | 稳定，可作为候选正式字段 |
| `fall_state_changed` | `stable_fall_detected` 是否切换 | 半稳定，适合作为边沿提示，不适合做唯一主语义 |
| `fall_person_candidates` | 当前帧跌倒候选人数 | 稳定，可作为观测统计 |
| `fall_max_score` | 当前规则法最高分 | 半稳定，分值语义依赖当前规则定义 |
| `fall_top_candidate` | 最高分候选的明细字典 | 研究态，嵌套结构尚未冻结 |
| `fall_active_track_ids` | 当前稳定为跌倒的 track id 列表 | 研究态，接口层不宜直接冻结 |
| `fall_active_track_count` | 当前稳定为跌倒的 track 数量 | 半稳定，可保留为统计字段 |

其中 `fall_top_candidate` 当前内部还带有 `track_id`、`score`、几何特征或几何派生值，语义随实现分支变化，不适合在这一阶段冻结成任务层契约。

### 1.3 时序跌倒字段

当前时序模型输出：

| 字段 | 当前含义 | 稳定性判断 |
|---|---|---|
| `seq_fall_detector_enabled` | 时序分支是否启用 | 调试/健康态字段 |
| `seq_fall_model_loaded` | 模型是否成功加载 | 健康态字段，适合作为诊断，不适合作为任务主语义 |
| `seq_fall_track_mode_used` | 是否采用 track 级序列缓存 | 内部实现细节，研究态 |
| `seq_raw_fall_detected` | 分数过阈的原始时序跌倒状态 | 研究态，噪声高于稳定态 |
| `seq_stable_fall_detected` | 稳定化后的时序跌倒状态 | 稳定，当前最接近正式主输出 |
| `seq_fall_state_changed` | `seq_stable_fall_detected` 是否切换 | 半稳定 |
| `seq_fall_score` | 当前时序分数 | 半稳定，保留为诊断/置信信息可以接受 |
| `seq_fall_threshold` | 当前阈值 | 配置回显，诊断字段 |
| `seq_fall_person_candidates` | 可用于时序判定的人候选数量 | 半稳定 |
| `seq_fall_top_candidate` | 当前最高分候选字典 | 研究态，嵌套结构未冻结 |
| `seq_active_track_ids` | 当前稳定为跌倒的 track 列表 | 研究态 |
| `seq_active_track_count` | 当前稳定为跌倒的 track 数量 | 半稳定 |

## 2. 对正式 schema 的适配判断

`system_planner` 如果要收敛成正式 perception event schema，当前 perception 侧已经有一批字段足够支撑“最小可消费语义源”，但不能把整个 `record` 原样冻结。

### 2.1 当前已经够用的字段

以下字段已经足够作为正式 schema 的第一版候选：

- `ts`
- `frame_id`
- `person_count`
- `stable_person_present`
- `stable_fall_detected` 或 `seq_stable_fall_detected`
- `fall_person_candidates` 或 `seq_fall_person_candidates`
- `fall_active_track_count` 或 `seq_active_track_count`

但这里不能继续并行暴露两套“最终跌倒结论”。如果进入正式 schema，感知层必须收敛成单一任务级输出，例如：

- `human_presence_state`
- `fall_state`
- `fall_confidence`
- `subject_count`
- `detector_backend`

其中 `fall_state` 应只保留一套最终语义，不再让任务层同时理解 `stable_fall_detected` 和 `seq_stable_fall_detected`。

### 2.2 需要后续调整名称或语义的字段

以下字段当前不适合直接原名冻结：

- `ts`
  - 应迁移到 ROS2 统一时间戳字段，如 `header.stamp`。
- `source`
  - 当前混合“文件路径 / 摄像头索引 / 结果路径”语义，建议拆成 `input_mode` 和 `source_id`。
- `state_changed`
  - 当前只表示 `stable_person_present` 的边沿，不够直观，建议改为 `presence_state_changed`。
- `raw_*`
  - 这些字段是内部候选态，不建议直接暴露给规划层。
- `fall_top_candidate`、`seq_fall_top_candidate`
  - 结构未冻结，不适合先进入正式接口。
- `*_track_mode_used`
  - 实现细节，不是任务语义。
- `*_enabled`、`seq_fall_model_loaded`
  - 应归入 health/diagnostic 语义，不应混入单帧任务事件主体。

### 2.3 建议的最小正式 perception schema 视角

从 perception 侧看，最小正式 schema 可以先收成下面这组语义，而无需立刻大改模型：

| 建议字段 | 来源 | 说明 |
|---|---|---|
| `stamp` | `ts` | 统一时间戳 |
| `frame_seq` | `frame_id` | 统一帧序号 |
| `input_mode` | ROS2 节点侧补充 | `mock / video_file / camera` |
| `source_id` | `source` 规整后 | 视频名、设备名、流 id |
| `person_count` | 现有字段 | 当前人数 |
| `human_presence_state` | `stable_person_present` | 任务层可消费的人存在状态 |
| `fall_state` | 从单一最终分支映射 | 当前最关键正式任务语义 |
| `fall_confidence` | `seq_fall_score` 或 `fall_max_score` | 先定义成可选诊断值 |
| `event_transition` | `state_changed / fall_state_changed / seq_fall_state_changed` 规整后 | 边沿信息，供上层去重 |
| `backend` | 节点侧或配置侧补充 | `rule / lstm / tcn / fused` |
| `health_state` | `*_enabled / model_loaded` 规整后 | `ok / degraded / unavailable` |

其中最关键的是：`fall_state` 必须尽快成为单一正式字段。

## 3. 当前跌倒检测模块是否可用

结论：可用，但目前仍是“研究原型可用”，还不是“任务层长期稳定语义源可用”。

### 3.1 可用到什么程度

结合 [reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md](/home/yhc/kaiti_yolopose_framework/reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md#L27)：

- 规则法基线稳定帧级 `F1=0.5396`，只能算基线参考。
- 时序 `LSTM` 稳定帧级 `F1=0.7883`，三者中综合最好，且跌倒段漏检为 `0`。
- 时序 `TCN` 稳定帧级 `F1=0.7111`，误报更低，但召回下降明显。

这说明当前跌倒检测模块已经具备以下能力：

- 能在离线评测上稳定区分“规则法 / 学习法 / 候选保守分支”。
- 能输出连续帧稳定化后的跌倒状态，而不是只有单帧检测框。
- 能作为当前 ROS2 最小闭环中的事件源，支撑 `perception -> supervisor -> planner_request` 占位链路。

但它目前只能算：

- 适合研究验证与系统原型联调。
- 适合做 mock、视频回放和接口收敛。
- 还不适合直接当作最终任务层唯一可信事件源。

### 3.2 目前为什么还不能算“正式可用”

主要问题有四个：

1. 默认主线不一致。benchmark 结论明确 `LSTM` 是当前主模型，但默认推理配置 [configs/infer_pose_stream.yaml](/home/yhc/kaiti_yolopose_framework/configs/infer_pose_stream.yaml#L35) 仍指向 `TCN`。
2. 当前对任务层暴露了两套最终跌倒语义：`stable_fall_detected` 和 `seq_stable_fall_detected`，没有收成一个正式结论。
3. `seq_fall_score`、`fall_max_score`、`top_candidate` 这些值更多还是研究调参与诊断字段，尚未形成长期可解释、可对比的接口语义。
4. 现有 benchmark 主要建立在 `UR Fall` 上，距离 `/home/yhc/kaiti.docx` 所要求的动态家居、遮挡、持续运行、可供任务层消费的稳定语义源，还有明显场景差距。

## 4. 面向 `kaiti.docx` 的下一阶段发展建议

`/home/yhc/kaiti.docx` 对感知层的核心要求不是“再多一个检测分支”，而是“把检测结果转成可被任务层稳定消费的语义状态量”，并且要在遮挡、短时不可观测、动态环境下尽量减少抖动。

因此，下一阶段感知模块最该做的不是系统大扩张，而是把当前研究原型收成稳定语义源。

### 4.1 第一优先级：冻结单一任务级跌倒语义

先完成下面这件事，而不是继续叠更多模型：

- 选定单一主输出分支，当前应优先以 `LSTM` 稳定态作为默认主线。
- 对外只给一个正式 `fall_state`。
- 规则法与 `TCN` 保留为诊断/对照分支，不直接暴露给任务层做主决策。

这一步完成后，perception 才从“研究输出”变成“可消费接口”。

### 4.2 第二优先级：把布尔量发展成事件生命周期语义

对于任务层，单纯的 `True/False` 仍然偏弱。下一步建议在不大改模型的前提下，把当前稳定化布尔量升级成有限状态机式语义，例如：

- `no_person`
- `person_present`
- `fall_suspected`
- `fall_confirmed`
- `fall_cleared`
- `degraded`

这些状态都可以基于当前已有稳定器和时序分数演进出来，不需要先换模型。这样做更符合 `kaiti.docx` 中“语义状态量支撑任务更新与异常触发”的要求。

### 4.3 第三优先级：做目标场景上的负样本加固

当前最现实的感知提升方向不是先追求更复杂模型，而是补“家居 ADL 场景”：

- 坐卧、弯腰、拾物、倚靠、遮挡恢复、多人交错。
- 视频回放中的长时停留、慢速坐下、半遮挡躺卧。

原因很明确：

- benchmark 已表明 `LSTM` 的主要问题不是漏检，而是 ADL 误报偏多。
- `kaiti.docx` 真正需要的是“可供任务层长期消费的稳定语义”，误报比单次检测精度更致命。

所以应优先做：

- 负样本补充。
- hard negative 挖掘。
- 家居场景验证集。
- 误报模式分型与阈值/稳定帧再标定。

### 4.4 第四优先级：为任务层补齐最小可解释性

任务层不需要看到完整研究细节，但需要知道“为什么这次触发可信”。因此建议后续最小补充：

- `backend`
- `fall_confidence`
- `health_state`
- `transition_reason`

这些字段足以支撑 supervisor 做降级处理、去重和恢复，不需要先开放 `top_candidate` 这种不稳定嵌套结构。

## 5. 最小改造建议

在不大改模型逻辑的前提下，感知侧最小改造建议如下：

1. 统一正式主输出，冻结一个 `fall_state`，默认从 `LSTM` 稳定态映射。
2. 保留规则法和 `TCN`，但降为诊断/比较字段，不再让上层直接依赖。
3. 把 `source` 拆成 `input_mode + source_id`，避免路径、索引、设备名混用。
4. 把 `state_changed / fall_state_changed / seq_fall_state_changed` 统一成明确的 transition 语义。
5. 把 `*_enabled` 和 `model_loaded` 收进 health/diagnostic 字段，不再混在任务事件主体里。
6. 先冻结扁平字段，暂不冻结 `top_candidate`、`track_ids` 这类研究态嵌套结构。

## 结构性结论

- 当前 perception 逐帧输出已经足够支撑“最小正式 schema”的第一版，但不能把整份 JSON 原样升级为长期契约。
- `stable_person_present` 和单一稳定跌倒态是最适合冻结的正式任务语义；`raw_*`、`*_track_mode_used`、`top_candidate`、`track_ids` 仍应视为研究态或诊断态。
- 当前跌倒检测模块可用，但层级是“研究原型可用、系统联调可用”，还不是“正式任务语义源可用”。
- 若要满足 `/home/yhc/kaiti.docx` 的使用要求，感知下一阶段重点应放在“单一正式语义输出、事件生命周期、家居负样本加固、最小可解释性”四件事上，而不是继续扩模型种类。
- 当前主线仍应是 `LSTM`，默认配置未收口到这条主线，属于感知接口冻结前必须先修正的问题。

## 未解决风险

- 本次审查时 [docs/system_interface_contract_2026-04-10.md](/home/yhc/kaiti_yolopose_framework/docs/system_interface_contract_2026-04-10.md) 尚不存在，因此判断主要基于当前 perception 真实输出字段，而不是基于已冻结的跨模块合同。
- 我没有在本次子任务里直接读取 ROS2 节点封装层字段映射，结论聚焦于感知原始事件载体，而非 topic 打包细节。
- benchmark 主要来自 `UR Fall`，还不能直接代表最终家居动态场景表现。
- `top_candidate` 等嵌套字段的内部内容随实现分支变化，后续若 system_planner 想保留目标级信息，需要另行设计正式子结构。

## 下一步命令

```bash
cd /home/yhc/kaiti_yolopose_framework
git diff -- docs/perception_interface_review_2026-04-10.md
```

```bash
cd /home/yhc/kaiti_yolopose_framework
rg -n "stable_fall_detected|seq_stable_fall_detected|fall_state_changed|seq_fall_state_changed|source:" src configs ros2_ws docs
```

```bash
cd /home/yhc/kaiti_yolopose_framework
sed -n '1,260p' docs/perception_interface_review_2026-04-10.md
```
