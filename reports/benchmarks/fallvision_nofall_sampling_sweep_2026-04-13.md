# FallVision No-Fall Sampling Sweep (2026-04-13)

## Scope

本摘要记录 `FallVision no-fall` 作为 hard negative 来源时，不同视频级抽样比例对当前学习型跌倒检测主线的影响。

统一实验流程：
1. 从 `FallVision no-fall` 做视频级抽样
2. 与 `UR Fall` 混合训练
3. 回到 `UR Fall` 单独 fine-tune
4. 使用 `UR Fall` 做正式同口径评估

对比对象包括：
- `UR Fall` baseline LSTM
- `3% / 5% / 10% / 15%` 抽样比例

## 1. Same-Metric Comparison

按 `eval_fall_batch.py` 的稳定逐帧指标对比：

| Variant | Precision | Recall | F1 |
|---|---:|---:|---:|
| Baseline (`UR Fall -> LSTM`) | 0.8059 | 0.7557 | 0.7800 |
| `3%` sampled + fine-tune | 0.7979 | 0.7630 | 0.7801 |
| `5%` sampled + fine-tune | 0.8657 | 0.7401 | 0.7979 |
| `10%` sampled + fine-tune | 0.8536 | 0.7417 | 0.7938 |
| `15%` sampled + fine-tune | 0.8428 | 0.7479 | 0.7925 |

结论：
- `5%` 是当前 sweep 中的最佳比例
- `10% / 15%` 也优于 baseline，但略低于 `5%`
- `3%` 基本只与 baseline 持平，没有形成明确增益

## 2. ADL False Positive Comparison

按 `metrics_per_video.csv` 汇总的 ADL 稳定误报：

| Variant | ADL FP Frames | ADL FP Segments |
|---|---:|---:|
| Baseline (`UR Fall -> LSTM`) | 273 | 11 |
| `3%` sampled + fine-tune | 285 | 13 |
| `5%` sampled + fine-tune | 162 | 9 |
| `10%` sampled + fine-tune | 189 | 15 |
| `15%` sampled + fine-tune | 195 | 14 |

结论：
- `5%` 不仅综合 `F1` 最优，误报控制也最好
- `3%` 过于保守，未能有效改善最难 ADL
- `10% / 15%` 仍有提升，但已经开始重新引入更多 ADL 误报段

## 3. Worst ADL Videos

当前所有比例中，最顽固的误报热点仍集中在：
- `adl-37`
- `adl-13`
- `adl-14`

不同采样比例下，这几个视频仍反复出现在前列，说明当前感知层剩余优化空间主要不在“再换模型族”，而在：
- 更定向的 hard negative
- 更贴近这些 ADL 的辅助样本筛选
- 针对这些动作过渡过程的时序区分能力

## 4. Current Usability

截至 `2026-04-13`，当前最佳默认主线：
- `FallVision no-fall sampled 5%`
- `-> mixed train`
- `-> UR Fall fine-tune`

对应模型：
- `models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`

该模型的正式结果为：
- Precision: `0.8657`
- Recall: `0.7401`
- F1: `0.7979`
- ADL FP Frames: `162`
- ADL FP Segments: `9`

判断：
- 当前结果已经可以作为后续系统工作使用
- 感知层不再是“卡住整个项目推进”的主要瓶颈
- 后续应将其视为可工作的正式主线，而不是继续停留在方法探索阶段

## 5. Remaining Optimization Space

感知层仍然存在优化空间，但优先级应下降，且优化方向应收窄为：

1. 围绕 `adl-37 / adl-13 / adl-14` 做更定向的 hard negative
2. 比较少量额外采样策略，而不是继续扩大比例
3. 固定随机种子，提高实验复现性
4. 仅在现有框架内做小幅结构或训练策略优化

不建议当前优先做的事：
- 再次切换到完全不同的方法族
- 全量并入更多 `FallVision no-fall`
- 把大量时间继续投入无边界的感知微调

## 6. Recommendation

当前建议分两条线推进：

1. 感知主线冻结在当前 `5%` two-stage 结果上，作为正式默认主线继续使用。
2. 项目主精力转向系统主线，将该感知结果接入 `ROS2 / supervisor / planner_request` 后续工作。
