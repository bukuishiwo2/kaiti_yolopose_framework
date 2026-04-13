# UR Fall Benchmark Summary (2026-04-09)

## Scope

本摘要记录当前项目两条主线在 `UR Fall` 数据集上的结果：
- 规则法基线
- 学习型时序模型（LSTM）

详细运行产物在本地 `outputs/`，但 Git 仓库中长期保留本摘要作为结果归档。

## 1. Rule-Based Baseline

评估目录：
- `outputs/eval_urfall/`

稳定结果：
- Precision: `0.7558`
- Recall: `0.4196`
- F1: `0.5396`

特点：
- 误报控制较好
- 漏检较多
- 平均检测延迟较高

## 2. Sequence LSTM

评估目录：
- `outputs/eval_urfall_sequence/`

稳定结果：
- Precision: `0.7769`
- Recall: `0.8000`
- F1: `0.7883`

训练阶段最佳验证窗口结果：
- Precision: `0.6222`
- Recall: `0.9333`
- F1: `0.7467`

对应模型：
- `models/fall_sequence_lstm.pt`

## 3. Same-Metric Comparison

按 `eval_fall_batch.py` 的稳定逐帧指标对比：

| Method | Precision | Recall | F1 |
|---|---:|---:|---:|
| Rule baseline | 0.7558 | 0.4196 | 0.5396 |
| Sequence LSTM | 0.7769 | 0.8000 | 0.7883 |

增量：
- Precision: `+0.0211`
- Recall: `+0.3804`
- F1: `+0.2487`

## 4. Segment-Level Observation

规则法：
- `fall_fn_segments = 4`
- `adl_fp_segments = 10`
- 平均检测延迟约 `1.019s`

学习型时序模型：
- `fall_fn_segments = 0`
- `adl_fp_segments = 21`
- 平均检测延迟约 `0.377s`

解读：
- 学习型模型显著减少了漏检
- 检测触发更早
- 代价是 ADL 误报段增加

## 5. Current Conclusion

当前阶段结论：
- 学习型时序模型已经明显优于规则法基线
- 后续主线应切换到“学习型模型降误报优化”
- 规则法保留为 baseline / 对照组

## 6. LSTM Tuning Result

在 `outputs/tune_fall_grid_sequence/` 与 `outputs/tune_fall_grid_sequence_refine/` 上，已完成两轮基于阈值和稳定参数的调参。

### 6.1 当前综合主配置

当前推荐的学习型默认配置为：
- `score_threshold = 0.6`
- `min_true_frames = 3`
- `min_false_frames = 5`

该配置对应第一轮调参中的 `c019`，也是第二轮精调后仍然保留下来的综合最优点。

相对学习型原始基线（`0.5 / 3 / 5`）：
- `stable F1: 0.7883 -> 0.7970`
- `adl_fp_segments: 21 -> 14`
- `stable_false_alarm_per_min: 4.675 -> 3.109`

### 6.2 低误报备选配置

若当前阶段更重视误报控制，可使用备选：
- `score_threshold = 0.62`
- `min_true_frames = 3`
- `min_false_frames = 5`

特点：
- `adl_fp_segments: 14 -> 12`
- 综合 F1 仅小幅低于当前主配置

### 6.3 调参结论

两轮调参已经说明：
- `score_threshold` 是最关键的参数
- `min_true_frames = 3` 在当前数据上优于 `4/5`
- `min_false_frames` 影响较小
- 小范围继续微调的收益已经明显下降

因此，当前 LSTM 主线已接近“参数调优上限”，后续若要继续提升，重点不应再放在阈值微调，而应转向：
- 更强的负样本
- 更好的时序模型
- 更针对性的动作区分设计

## 7. FallVision-Only LSTM Result

评估目录：
- `outputs/eval_urfall_sequence_fallvision/`

对应模型：
- `models/fall_sequence_lstm_fallvision.pt`

稳定结果：
- Precision: `0.3329`
- Recall: `0.7238`
- F1: `0.4561`

与当前主学习型模型（`models/fall_sequence_lstm.pt`）相比：
- Precision: `0.7769 -> 0.3329`
- Recall: `0.8000 -> 0.7238`
- F1: `0.7883 -> 0.4561`

观察：
- `stable_fp_frames` 从 `410` 激增到 `2589`
- 主要退化来自 ADL 误报爆炸，而不是召回提升
- 因此，FallVision 目前不适合直接作为单独训练集替换当前主模型

结论：
- FallVision 更适合作为补充训练源或 hard negative 来源
- 不应采用“FallVision-only 训练后直接替换默认推理模型”的方案

## 8. FallVision No-Fall Two-Stage Result (2026-04-13)

为验证 `FallVision` 是否能作为 hard negative 来源，新增了三组同口径实验：

1. `FallVision no-fall` 全量直接并入训练
2. `FallVision no-fall` 视频级 `5%` 抽样并入训练
3. `5%` 抽样并入训练后，再回到 `UR Fall` 单独 fine-tune

### 8.1 Full Merge Result

评估目录：
- `outputs/eval_urfall_sequence_fallvision_nofall/`

稳定结果：
- Precision: `0.4385`
- Recall: `0.8168`
- F1: `0.5706`

观察：
- `stable_fp_frames` 从基线的 `325` 激增到 `1867`
- `adl_fp_segments` 明显爆炸

结论：
- `FallVision no-fall` 不能全量直接拼接到当前训练集

### 8.2 Sampled 5% Result

评估目录：
- `outputs/eval_urfall_sequence_fallvision_nofall_sampled/`

稳定结果：
- Precision: `0.7829`
- Recall: `0.7171`
- F1: `0.7485`

观察：
- 相比全量并入，误报已明显回落
- 但仍未超过当前 `UR Fall` 基线

结论：
- `FallVision` 可以作为辅助数据，但必须做受控抽样

### 8.3 Two-Stage Fine-Tune Result

评估目录：
- `outputs/eval_urfall_sequence_fallvision_nofall_sampled_finetuned/`

对应模型：
- `models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`

训练流程：
1. 使用 `UR Fall + FallVision no-fall sampled 5%` 训练
2. 使用该 checkpoint 回到 `UR Fall` 单独 fine-tune

稳定结果：
- Precision: `0.8657`
- Recall: `0.7401`
- F1: `0.7979`

与当前 `UR Fall` 主线基线（`outputs/eval_urfall_sequence/`）相比：
- Precision: `0.8059 -> 0.8657`
- Recall: `0.7557 -> 0.7401`
- F1: `0.7800 -> 0.7979`

段级与误报观察：
- `adl_fp_frames: 273 -> 162`
- `adl_fp_segments: 11 -> 9`
- `fall_fn_segments` 仍保持为 `0`

结论：
- `FallVision` 路线是可行的
- 关键不是“是否使用 FallVision”，而是“如何使用”
- 当前最优方案不是 `FallVision-only` 或全量直接并入，而是：
  - `FallVision no-fall` 受控抽样
  - 与 `UR Fall` 混合训练
  - 最后回到 `UR Fall` 做收口 fine-tune

### 8.4 Updated Default

截至 `2026-04-13`，默认学习型主线更新为：
- `models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`
- `score_threshold = 0.6`
- `min_true_frames = 3`
- `min_false_frames = 5`

## 9. Next Step

1. 保留当前 LSTM 主配置作为正式 baseline
2. 围绕 `FallVision no-fall` 继续做更细的抽样比例比较（如 `3% / 10% / 15%`）
3. 优先针对 `adl-37 / adl-13 / adl-14` 做更定向的 hard negative 设计
4. 在默认学习型主线冻结后，把更多精力转向系统主线接入
