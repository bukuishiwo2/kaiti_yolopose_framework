# Hard Negative Plan

本文件用于定义下一阶段的数据补强方案：针对学习型时序模型最容易误报的动作，系统补充 hard negative 视频。

## 1. 为什么现在要做 hard negative

当前 `LSTM` 主线已经完成两轮调参，综合主配置为：
- `score_threshold = 0.6`
- `min_true_frames = 3`
- `min_false_frames = 5`

但误报仍集中在以下动作：
- 躺下
- 坐下
- 弯腰
- 地面动作

这说明当前问题的核心已经不只是阈值，而是模型对“跌倒”和“非跌倒但姿态相似动作”的区分能力不足。

## 2. 目标

本轮 hard negative 数据补强的目标不是增加一般负样本数量，而是增加“最容易被判成跌倒”的负样本密度。

优先目标：
1. 降低 ADL 误报段数
2. 降低 `stable_false_alarm_per_min`
3. 尽量保持当前跌倒召回不明显下降

## 3. 优先收集的动作类别

建议至少覆盖以下 6 类：

1. `lie_down`
- 主动躺下
- 从坐姿转为卧姿
- 床边/地面躺下

2. `sit_down`
- 正常坐下
- 快速坐下
- 从站姿直接落到椅子/沙发

3. `bend_over`
- 弯腰捡东西
- 系鞋带
- 低位取物

4. `kneel_or_crouch`
- 下蹲
- 单膝跪地
- 长时间低位停留

5. `floor_activity`
- 在地上活动
- 俯卧/侧卧翻身
- 地面清洁、整理物品

6. `transition_motion`
- 坐下后再躺下
- 弯腰后再蹲下
- 先跪地再起身

## 4. 采集原则

每个动作类别建议覆盖：
- 多个拍摄角度
- 不同人物体型
- 不同速度
- 不同背景
- 不同服装
- 有无遮挡两种情况

最低建议：
- 每类先收集 `10~20` 段短视频
- 每段 `5~20` 秒
- 以单人为主，后续再补多人场景

## 5. 标注原则

对于 hard negative 视频：
- `fall_segments` 留空
- 因为这些视频在任务定义中属于“无跌倒”

为了后续分析误报来源，建议额外记录：
- `category`
- `priority`
- `notes`

本项目当前训练和评估脚本只要求以下字段必有：
- `video_id`
- `video_path`
- `fall_segments`
- `notes`

因此可以安全增加额外列，而不会破坏现有脚本。

## 6. 仓库内的模板文件

已提供：
- `data/eval/video_labels_hard_negative_template.csv`
- `data/eval/video_labels_hard_negative_seed.csv`

用途：
- `template`：空白模板，用于后续持续补充
- `seed`：建议优先覆盖的 hard negative 类型示例

## 7. 推荐工作流

### 7.1 收集视频

把本地 hard negative 视频放在任意你方便管理的位置。

不建议直接提交到 Git 仓库。

### 7.2 标注到 CSV

复制模板：

```bash
cp data/eval/video_labels_hard_negative_template.csv data/eval/video_labels_hard_negative.csv
```

然后填写：
- `video_id`
- `video_path`
- `fall_segments` 留空
- `category`
- `priority`
- `notes`

### 7.3 与现有标签合并

本项目已提供合并脚本：

```bash
python scripts/merge_label_csvs.py \
  --inputs data/eval/video_labels_urfall_cam0.csv data/eval/video_labels_hard_negative.csv \
  --output data/eval/video_labels_urfall_plus_hn.csv
```

### 7.4 重新构建序列数据集

```bash
python scripts/build_pose_sequence_dataset.py \
  --labels data/eval/video_labels_urfall_plus_hn.csv \
  --device 0 \
  --output data/processed/urfall_plus_hn_pose_sequences.npz
```

### 7.5 训练并复评

训练：

```bash
python scripts/run_fall_sequence_train.py --config configs/train_fall_sequence.yaml
```

复评：

```bash
python scripts/eval_fall_batch.py \
  --labels data/eval/video_labels_urfall_plus_hn.csv \
  --config configs/infer_pose_stream.yaml \
  --mode predict \
  --device 0 \
  --raw-key seq_raw_fall_detected \
  --stable-key seq_stable_fall_detected \
  --out-dir outputs/eval_urfall_plus_hn_sequence
```

## 8. 成功标准

做完 hard negative 补强后，重点看：
- `adl_fp_segments` 是否下降
- `stable_false_alarm_per_min` 是否下降
- `all_f1` 是否保持或提升
- 跌倒召回是否没有明显恶化

## 9. 当前建议

如果只能先做一件事，优先补：
- `lie_down`
- `sit_down`
- `bend_over`

因为从当前误报模式看，这三类最可能直接带来收益。
