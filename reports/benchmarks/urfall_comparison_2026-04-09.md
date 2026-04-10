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

## 8. Next Step

1. 保留当前 LSTM 主配置作为正式 baseline
2. 收集或构造更多 hard negative（躺下、坐下、弯腰、地面动作）
3. 在现有关键点序列框架上继续研究更合适的时序模型
4. 优先考虑 `TCN`，再考虑更复杂的 `Transformer` 或 `ST-GCN`
