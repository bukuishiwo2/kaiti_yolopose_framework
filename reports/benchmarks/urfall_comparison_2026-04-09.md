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

## 6. Next Step

1. 继续调 `sequence_fall_detector.score_threshold`
2. 调整 `min_true_frames / min_false_frames`
3. 重新评估 ADL 误报
4. 如有必要，再扩展到 `TCN` 或 `ST-GCN`
