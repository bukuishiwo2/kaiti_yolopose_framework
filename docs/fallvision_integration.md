# FallVision Integration

> 说明：当前新增数据集资源接入已统一收口到 [external_dataset_workflow.md](external_dataset_workflow.md)，`FallVision` 的 canonical grouped view 为 `data/external/fallvision/`。本文件继续保留 `FallVision` 的方法和训练背景说明；若只做资源接入、解压整理、manifest 与 sample report，请优先使用新的外部数据集工作流。

本说明记录如何将 `FallVision` 数据集接入当前项目。

## 1. 当前建议的接入方式

FallVision 最适合当前项目的方式不是重新跑 `YOLOPose`，而是直接使用其自带的关键点 CSV。

原因：
- CSV 已包含每帧 17 个关键点的 `X / Y / Confidence`
- 与当前时序模型输入高度匹配
- 可避免重复做 pose 推理

## 2. 当前支持的数据格式

当前导入脚本支持的 CSV 列：
- `Frame`
- `Keypoint`
- `X`
- `Y`
- `Confidence`

每帧通常按 17 行关键点组织，关键点名如：
- `Nose`
- `Left Eye`
- `Right Eye`
- ...
- `Right Ankle`

## 3. 接入前提

当前仓库可以通过新脚本直接从官方 Harvard Dataverse 下载 `FallVision` 资源：
- DOI: `10.7910/DVN/75QPKK`
- 官方数据页：`https://doi.org/10.7910/DVN/75QPKK`

如果你当前只需要关键点 CSV，而不需要视频文件，推荐优先下载 `keypoints_csv.rar`，不要先拉全量视频。

下载脚本：
- `scripts/download_fallvision_assets.py`

默认行为：
- 只下载关键点压缩包
- 默认下载 `Mask Video` 这一支
- 不下载体积巨大的视频 `.rar`

推荐命令：

只下载关键点压缩包，不下视频：

```bash
python scripts/download_fallvision_assets.py
```

只下载 `No Fall` 关键点，适合先做 hard negative：

```bash
python scripts/download_fallvision_assets.py \
  --label no_fall \
  --asset-type keypoints
```

按 `(label, scene)` 每组先下 2 个文件做 smoke test：

```bash
python scripts/download_fallvision_assets.py \
  --asset-type keypoints \
  --max-files-per-group 2
```

如果后续确实需要视频，再显式切到视频资产：

```bash
python scripts/download_fallvision_assets.py \
  --asset-type videos \
  --variant raw
```

新工作流默认把 `FallVision` 资源放到：
- `data/external/fallvision_fall_keypoints/`
- `data/external/fallvision_fall_videos_debug/`

随后建议通过：
- `scripts/organize_fallvision_layout.py`

把旧 `No Fall` 目录和新的 `Fall` 补充目录统一整理到：
- `data/external/fallvision/`

旧脚本直连模式仍可使用；若直接运行旧脚本，其默认清单位置仍为：
- `data/Fall Detection Video Dataset/_download_manifest.json`

在运行导入脚本前，你需要先把这些 `*_keypoints_csv.rar` 解压出来，确保目录里真正存在 `.csv` 文件。

例如：
- `data/Fall Detection Video Dataset/Fall/Bed/Mask Video/.../*.csv`
- `data/Fall Detection Video Dataset/No Fall/Chair/Mask Video/.../*.csv`

如果你希望下载后自动解压，可使用：

```bash
python scripts/download_fallvision_assets.py --extract
```

说明：
- 自动解压依赖本机安装 `unrar`、`7z` 或 `unar`
- 如果机器上没有这些工具，脚本会提示并退出

## 4. 导入脚本

已新增：
- `scripts/build_fallvision_sequence_dataset.py`

该脚本会：
1. 递归读取 FallVision 的关键点 CSV
2. 将每帧 17 个关键点转成当前项目使用的 54 维特征
3. 在视频级别做训练/验证划分
4. 输出与当前训练脚本兼容的 `npz`

## 5. 标签策略说明

当前 FallVision 接入采用的是“弱监督视频级标签”策略：
- 路径中包含 `No Fall` 的视频 -> 标签 `0`
- 路径中包含 `Fall` 的视频 -> 标签 `1`

因为当前目录结构里还没有显式的段级跌倒起止时间，所以：
- `No Fall` 视频所有窗口都标 `0`
- `Fall` 视频默认用 `tail` 模式做近似标注

`tail` 模式含义：
- 不是整段都标正样本
- 而是仅将视频后半段附近的窗口视为更可能包含跌倒

这比“整段 fall 视频全部标正”更稳一些，但仍然属于弱监督近似。

## 6. 推荐命令

先做一个小规模 smoke test：

```bash
python scripts/build_fallvision_sequence_dataset.py \
  --root "data/external/fallvision/extracted" \
  --glob "**/*.csv" \
  --max-files-per-scene-label 5 \
  --seq-len 32 \
  --stride 4 \
  --positive-mode tail \
  --fall-positive-start-ratio 0.4 \
  --output data/processed/fallvision_smoke.npz
```

全量构建：

```bash
python scripts/build_fallvision_sequence_dataset.py \
  --root "data/external/fallvision/extracted" \
  --glob "**/*.csv" \
  --seq-len 32 \
  --stride 4 \
  --positive-mode tail \
  --fall-positive-start-ratio 0.4 \
  --output data/processed/fallvision_pose_sequences.npz
```

说明：
- `--max-files 20` 只会截取排序后的前 20 个文件，容易偏向某一类
- 更推荐用 `--max-files-per-label` 做平衡抽样 smoke test
- 如果你希望 `Bed / Chair / Stand` 都被覆盖，更推荐用 `--max-files-per-scene-label`

## 7. 当前最合理的用途

现阶段建议把 FallVision 用作：
- `no-fall / hard negative` 辅助数据源
- 与 `UR Fall` 的混合训练增强集
- 之后回到 `UR Fall` 的 fine-tune 前置训练源

而段级评估仍建议继续使用：
- `UR Fall`

原因：
- 你当前 `eval_fall_batch.py` 主要依赖显式的跌倒时间段标注
- FallVision 当前接入方式更偏向训练增强，而不是直接替代 UR Fall 的段级 benchmark

## 8. 当前实验结论

FallVision 的关键点 CSV 已成功接入项目，并能生成与当前时序训练脚本兼容的 `.npz` 数据集。

但基于 `FallVision-only` 训练得到的 `models/fall_sequence_lstm_fallvision.pt` 在 `UR Fall` 上的同口径回测结果明显退化：

- Precision: `0.3329`
- Recall: `0.7238`
- F1: `0.4561`

相较当前主学习型模型 `models/fall_sequence_lstm.pt` 的 `F1=0.7883`，该结果不可接受。

因此当前判断为：
- FallVision 不适合作为单独训练集直接替换默认模型
- 更适合作为补充训练源或 hard negative 数据来源
- 后续建议研究“UR Fall + FallVision no-fall / hard negative”混合方案

## 9. 新增结论：No-Fall Two-Stage 路线可行

在 `2026-04-13` 新增的实验中，已验证以下三种 `FallVision no-fall` 用法：

1. 全量直接并入训练
2. 视频级 `5%` 抽样后并入训练
3. `5%` 抽样并入训练后，再回到 `UR Fall` 单独 fine-tune

结果表明：

- 全量直接并入不可取  
  `stable F1 = 0.5706`
- `5%` 抽样后明显恢复  
  `stable F1 = 0.7485`
- 两阶段方案优于当前 `UR Fall` 基线  
  `stable F1 = 0.7979`

相较当前 `UR Fall` 基线：
- Precision: `0.8059 -> 0.8657`
- Recall: `0.7557 -> 0.7401`
- F1: `0.7800 -> 0.7979`
- ADL stable FP frames: `273 -> 162`

因此，当前最合理的 FallVision 接入方式已经明确为：

1. 只使用 `No Fall` 关键点 CSV
2. 做视频级受控抽样，避免数据分布淹没 `UR Fall`
3. 先做混合训练
4. 最后回到 `UR Fall` 做 fine-tune 收口

不建议的方式仍然包括：
- `FallVision-only`
- `FallVision no-fall` 全量直接并入
- 用 `FallVision` 替代 `UR Fall` 做主 benchmark

## 10. 后续可继续做的优化

如果后续拿到更明确的 FallVision 段级时间标注，可继续扩展：
- 生成 `video_labels_fallvision.csv`
- 接到现有 `eval_fall_batch.py`

如果后续你想让 FallVision 更贴近当前主线，也可以：
- 用其 no-fall 子集重点补 hard negative
- 和 UR Fall 合并训练

## 11. 当前阶段新增：受控补强候选集准备

截至 `2026-04-15`，当前阶段已经从“视频调试验证”推进到“受控补强候选集准备”，但仍然不进入训练。

当前建议流程：

1. 先用 `fallvision_fall_videos_debug` 选代表视频
2. 先做粗粒度段级标注
3. 再决定是否构造更合理的正样本窗口

当前第一批文件：

- 粗标模板：
  - `data/eval/fallvision_segment_annotation_template_2026-04-15.csv`
- 候选集：
  - `data/eval/fallvision_first_batch_segment_candidates_2026-04-15.csv`
- 阶段摘要：
  - `reports/benchmarks/fallvision_controlled_boost_prep_2026-04-15.md`

当前粗标建议字段：

- `video_path`
- `scene`
- `fall_style`
- `fall_start_frame`
- `fall_end_frame`
- `post_fall_start_frame`
- `notes`

这一步的目标是：

- 为 `Bed / Chair / Stand` 的 slow fall / slide / roll 准备更可靠的候选窗口
- 先做样本筛选与粗标，不直接进入训练

## 12. 当前阶段新增：训练前窗口构造可用性验证

截至 `2026-04-15`，在第一批 `15` 个视频完成粗粒度段级标注之后，已经新增一条训练前 smoke test 路线：

- `scripts/build_fallvision_labeled_window_dataset.py`

它的定位不是训练，而是：

1. 读取已标注的视频级粗标 CSV
2. 自动映射到 canonical `FallVision` keypoint CSV
3. 生成与当前 `LSTM` 主线兼容的 `32 x 54` 窗口特征
4. 输出窗口级 `csv + npz + markdown report`

当前默认输出：

- `data/eval/fallvision_labeled_window_smoke_2026-04-15.csv`
- `data/eval/fallvision_labeled_window_smoke_2026-04-15.npz`
- `reports/benchmarks/fallvision_labeled_window_smoke_2026-04-15.md`

当前窗口标签规则采用四类：

- `negative`
- `positive`
- `post_fall_stable`
- `transition_ignore`

其中：

- `negative=0`
- `positive/post_fall_stable=1`
- `transition_ignore` 不直接进入 train-ready `npz`

这一步的作用是：

- 验证粗标是否足以稳定生成正负窗口
- 检查哪些视频在当前 `seq_len=32` 下仍然存在边界问题
- 为后续是否进入受控补强训练提供依据
