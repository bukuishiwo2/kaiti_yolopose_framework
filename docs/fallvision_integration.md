# FallVision Integration

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

当前仓库里的 `data/Fall Detection Video Dataset/` 下还只是下载好的 `.rar` 文件。

在运行导入脚本前，你需要先把这些 `*_keypoints_csv.rar` 解压出来，确保目录里真正存在 `.csv` 文件。

例如：
- `data/Fall Detection Video Dataset/Fall/Bed/Mask Video/.../*.csv`
- `data/Fall Detection Video Dataset/No Fall/Chair/Mask Video/.../*.csv`

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
  --root "data/Fall Detection Video Dataset" \
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
  --root "data/Fall Detection Video Dataset" \
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
- 学习型时序模型训练增强集
- 补充 `fall / no-fall` 视频级数据

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

## 9. 后续可继续做的优化

如果后续拿到更明确的 FallVision 段级时间标注，可继续扩展：
- 生成 `video_labels_fallvision.csv`
- 接到现有 `eval_fall_batch.py`

如果后续你想让 FallVision 更贴近当前主线，也可以：
- 用其 no-fall 子集重点补 hard negative
- 和 UR Fall 合并训练
