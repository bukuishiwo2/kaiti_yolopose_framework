# Perception Audit 2026-04-10

## 任务目标

检查本仓库感知链路是否与当前项目默认主线一致，重点核对：
- 数据构建、训练、推理、评估、稳定化是否已形成代码结构闭环
- 默认主模型是否仍然是 `LSTM`，`TCN` 是否仅作为低误报候选
- 规则法 baseline、学习型时序模型、语义事件稳定化三者边界是否清楚
- 是否存在会影响后续系统接入的结构性风险或接口缺口

## 检查范围

- `src/yolopose/pipeline/`
- `src/yolopose/temporal/`
- `scripts/`
- `configs/`
- `reports/benchmarks/`
- 参考：
  - `README.md`
  - `docs/kaiti_alignment.md`
  - `docs/worklogs/worklog_2026-04-10.md`

## Changed Files

本次仅写入 1 个文件：
- `docs/reviews/perception_audit_2026-04-10.md`

## 关键发现

### 1. 感知主链路在代码结构上基本闭环，但默认入口已失配

从结构上看，当前感知链路已经具备完整环节：

| 环节 | 代码入口 | 审计判断 |
|---|---|---|
| 数据标注构建 | `scripts/build_urfall_labels.py` | 已覆盖 `UR Fall` 标签 CSV 生成 |
| 序列数据构建 | `scripts/build_pose_sequence_dataset.py`、`scripts/build_fallvision_sequence_dataset.py` | 已覆盖 `UR Fall` 与 `FallVision` 两类来源 |
| 时序训练 | `scripts/run_fall_sequence_train.py` + `configs/train_fall_sequence*.yaml` | 已支持 `LSTM` / `TCN` 统一训练 |
| 在线推理 | `scripts/run_pose_infer.py` + `src/yolopose/pipeline/runner.py` | 已统一接入姿态、规则法、时序法 |
| 批量评估 | `scripts/eval_fall_batch.py` | 已支持按 JSONL 字段评估规则法或时序法 |
| 调参与结果归档 | `scripts/tune_fall_grid.py` + `reports/benchmarks/*.md` | 已形成调参和 benchmark 归档链路 |
| 稳定化 | `src/yolopose/pipeline/stabilizer.py` | 规则法与时序法都在复用同一稳定器 |

结论：
- 主链路不是“缺模块”，而是“已有闭环，但默认配置和默认入口没有收敛到当前主线”
- 当前最大问题不在模块缺失，而在主线定义和实际默认运行入口不一致

### 2. 文档口径仍然是 “LSTM 为默认主模型”，但默认推理配置已偏离

文档和记录的主线判断是一致的：
- `README.md` 明确写明 `LSTM` 是综合主模型，`TCN` 是低误报候选
- `docs/kaiti_alignment.md` 明确要求保留 `LSTM` 为感知主线
- `docs/worklogs/worklog_2026-04-10.md` 明确写了“默认推理模型切回 `models/fall_sequence_lstm.pt`”
- `reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md` 也明确将 `LSTM` 定位为 default main model

但代码默认入口不是这个口径：
- `configs/infer_pose_stream.yaml` 当前实际加载的是 `models/fall_sequence_tcn.pt`
- 同一个配置里却保留了 `score_threshold=0.6 / min_true_frames=3 / min_false_frames=5`，这套参数来自 `LSTM` 主线调参结论，不是 `TCN` 的当前推荐配置
- `Makefile` 中 `infer`、`eval-seq`、`tune-seq` 都直接使用 `configs/infer_pose_stream.yaml`
- `README.md` 中“LSTM 评估”和“学习型主线调参”的命令也都引用 `configs/infer_pose_stream.yaml`

结构性判断：
- 当前仓库的“默认学习型入口”已经不是纯 `LSTM` 主线，而是一个“文档宣称为 LSTM、配置实际加载 TCN、阈值又沿用 LSTM”的混合状态
- 这会直接破坏 benchmark 复现性，也会误导后续 `ros2_ws` 或任务层接入时选择错误模型

### 3. 规则法 baseline、学习型模型、稳定化模块在代码边界上是清楚的

边界划分总体清楚：
- 规则法 baseline 在 `src/yolopose/pipeline/fall_detector.py`
- 学习型时序模型在 `src/yolopose/temporal/model.py`
- 在线时序检测在 `src/yolopose/temporal/sequence_fall_detector.py`
- 稳定化统一复用 `src/yolopose/pipeline/stabilizer.py`
- 统一运行入口在 `src/yolopose/pipeline/runner.py`

因此，模块职责上已经不是“混写在一起”的状态。

但运行接口层还有一个未收敛问题：
- 默认推理配置同时开启 `fall_detector` 与 `sequence_fall_detector`
- JSONL 同时输出 `stable_fall_detected` 和 `seq_stable_fall_detected`
- 当前仓库没有一个明确的“最终任务级语义输出字段”，例如单一的 `task_fall_state`

这意味着：
- 从研究角度，当前设计利于对照实验
- 从系统接入角度，当前接口仍然暴露的是“实验态双输出”，不是“系统态单语义输出”

### 4. 训练分布与在线部署分布之间存在潜在错位

当前 `UR Fall` 训练数据构建脚本 `scripts/build_pose_sequence_dataset.py` 使用的是 `extract_primary_person_feature()`，即默认只取单帧最大人体目标构造序列。

但在线时序检测 `src/yolopose/temporal/sequence_fall_detector.py` 已支持：
- 全局单人缓冲
- 基于 tracker 的逐 track 序列缓冲

这带来两个问题：
- 训练主数据仍然是单人、主目标、弱多目标假设
- 在线部署接口已经朝“多目标 + track 级状态”扩展

在当前 `UR Fall` 单人数据集上这不是立即故障，但对后续动态家居场景系统接入是潜在风险：
- 多人场景下，训练分布和推理分布不完全一致
- 后续若任务层需要“按 person / track 消费语义状态”，当前训练链路没有显式围绕该接口组织数据

### 5. benchmark 和工作记录已经给出明确阶段性结论

可提炼的最重要结构性结论如下：

1. `LSTM` 仍然是当前综合最优主模型。
   - `reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md` 给出的同口径结果中，`LSTM` 的综合 F1 最好，且 fall recall 最强。

2. `TCN` 的定位应保持为低误报候选，而不是默认主模型。
   - `TCN` 在 ADL 误报抑制上更强，但明显牺牲 recall。

3. 当前 `LSTM` 阈值微调收益已接近饱和。
   - `docs/worklogs/worklog_2026-04-10.md` 已明确这一轮优化不应继续停留在细粒度阈值搜索。

4. 下一阶段重点应转向 hard negative 和补充训练，而不是直接更换更复杂模型。
   - 当前最缺的是负样本区分能力，不是更复杂 backbone。

5. `FallVision-only` 结果不能替换当前主模型。
   - 当前更适合作为 hard negative 或补充训练源，而不是直接替换 `UR Fall` 主模型。

## 结构性结论

### 对问题 1 的回答

感知主链路在“模块存在性”和“代码组织”上已经基本闭环，数据构建、训练、推理、评估、稳定化都能一一对应。

但闭环状态不是完全稳固的，原因有两点：
- 默认推理配置与当前主模型定位不一致
- 缺少一个明确绑定“checkpoint + infer config + benchmark 结论”的主线配置约定

因此，本次审计结论不是“主链路未闭环”，而是：

`主链路已基本闭环，但主线默认入口失配，当前属于可运行、可评估、但不够可复现的状态。`

### 对问题 2 的回答

当前仓库的文档、benchmark、工作记录都坚持：
- 默认主模型是 `LSTM`
- `TCN` 是低误报候选，不是默认主模型

但实际默认推理配置不是这样。

审计结论：
- `LSTM` 仍是项目声明上的默认主模型
- 但仓库当前默认运行入口已经偏离这个声明
- 代码 / 配置 / 文档目前存在实质性不一致，且不一致发生在默认入口而不是边缘文件

### 对问题 3 的回答

三者边界总体清楚，但系统消费边界还不够清楚：
- 规则法 baseline：职责清楚
- 学习型时序模型：职责清楚
- 稳定化：作为共享后处理，职责也清楚

真正不清楚的是：
- 后续系统到底消费哪个最终语义状态
- 是规则法、学习型、还是二者并存对照

当前接口更像“研究用多路输出”，不是“系统用单路主输出”。

### 对问题 4 的回答

当前最值得优先处理的结构性风险有 4 个：

1. 默认主模型配置失配。
   - 这是最高优先级问题，会直接污染评估复现和系统接入。

2. 缺少单一 canonical perception output。
   - 对后续 ROS2 / 任务层接入不友好。

3. 训练单人主目标假设，与未来多目标 track 级在线接入存在分布错位。
   - 当前不会立刻报错，但会在系统阶段放大。

4. benchmark 结论主要靠文档和命名约定维持，没有在配置层形成强绑定。
   - 容易再次出现“文档是 LSTM、默认配置却不是 LSTM”的漂移。

### 对问题 5 的回答

当前最重要的结构性结论是：

`感知主线已经不是缺算法，而是缺“主线收口”。`

更具体地说：
- `LSTM` 主线已经给出阶段性可用结果
- `TCN` 的研究定位也已明确
- 当前真正阻碍后续系统接入的，不是模型数量不够，而是默认配置、默认输出语义、以及 benchmark 复现入口还没有完全统一

## 未解决风险

- `configs/infer_pose_stream.yaml` 当前与项目主线口径不一致，若不修复，后续所有默认命令都可能继续输出与文档声明不符的结果。
- `Makefile` 与 `README.md` 依赖该默认配置，意味着错误会被持续放大，而不是停留在单文件。
- `SequenceFallDetector` 在模型文件缺失时不会 fail fast，只会返回 `model_loaded=false` 的静默降级输出；对系统联调阶段不够强约束。
- 当前仍缺少“面向任务层的最终单一语义字段”定义，不利于 `ros2_ws` 后续桥接。
- 多人/多 track 真实场景下，训练链路与在线链路的接口假设仍未完全对齐。

## 下一步命令

建议按以下顺序推进：

```bash
git diff -- docs/reviews/perception_audit_2026-04-10.md
rg -n "model_path: models/fall_sequence_tcn.pt|infer_pose_stream.yaml" README.md Makefile configs docs
python scripts/run_fall_sequence_train.py --config configs/train_fall_sequence.yaml
python scripts/eval_fall_batch.py --labels data/eval/video_labels_urfall_cam0.csv --config configs/infer_pose_stream.yaml --mode predict --device 0 --raw-key seq_raw_fall_detected --stable-key seq_stable_fall_detected --out-dir outputs/eval_urfall_sequence
```

其中更关键的工程动作不是立刻重训，而是：
- 先把 `infer_pose_stream.yaml` 收回到真正的 `LSTM` 主线
- 再把 `README.md` / `Makefile` / benchmark 入口统一到同一份 canonical config
- 最后再定义面向系统层的单一 perception output
