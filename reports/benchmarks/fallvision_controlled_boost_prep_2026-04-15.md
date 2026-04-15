# FallVision Controlled Boost Preparation 2026-04-15

## 1. 目标

当前阶段目标不是训练，而是为后续 `FallVision` 受控补强准备一批可人工粗标的 home-style fall 视频。

本次只做三件事：

1. 在 `fallvision_fall_videos_debug` 中补齐每类 `Bed / Chair / Stand` 的代表视频
2. 形成第一批人工粗标候选集
3. 给出粗粒度段级标注模板和标注方法

## 2. 选样原则

本次继续遵守当前项目定位：

- `UR Fall` 继续作为主 benchmark / 主训练收口集
- 默认 `LSTM` 主线不变
- 不进入训练，不做微调，不改阈值，不改模型

因此，本次候选集筛选原则是：

1. 优先保留 home-style fall
2. 优先覆盖上轮已暴露短板的动作类型
3. 每类先做粗粒度段级标注准备，不急着全量扩展

## 3. 第一批人工粗标候选集

清单路径：

- `data/eval/fallvision_first_batch_segment_candidates_2026-04-15.csv`

粗标模板路径：

- `data/eval/fallvision_segment_annotation_template_2026-04-15.csv`

当前第一批候选共 `15` 个视频：

- `Bed`：`5`
- `Chair`：`5`
- `Stand`：`5`

### 3.1 Bed 候选

目标：

- 补 `slow fall / roll / slide`

候选：

1. `B_D_0006_resized.mp4`：`bed_roll_slide`
2. `B_D_0007_resized.mp4`：`bed_side_slide`
3. `B_D_0008_resized.mp4`：`bed_slide_short`
4. `B_D_0009_resized.mp4`：`bed_side_roll`
5. `B_D_0010_resized.mp4`：`bed_slow_roll`

### 3.2 Chair 候选

目标：

- 补 `chair side slide / slow fall`

候选：

1. `C_M_01_resized.mp4`：`chair_side_slide`
2. `C_M_04_resized.mp4`：`chair_forward_slide`
3. `C_M_05_resized.mp4`：`chair_forward_slide`
4. `C_M_06_resized.mp4`：`chair_forward_slide`
5. `C_M_07_resized.mp4`：`chair_forward_slide`

### 3.3 Stand 候选

目标：

- 同时保留 `fast fall` 与 `slow collapse`

候选：

1. `S_D_0002_resized.mp4`：`stand_fast_fall`
2. `S_D_0004_resized.mp4`：`stand_fast_fall`
3. `S_D_0005_resized.mp4`：`stand_fast_fall`
4. `S_D_0016_resized.mp4`：`stand_fast_fall`
5. `S_D_0028_resized.mp4`：`stand_slow_collapse`

## 4. 为什么这样选

与 `2026-04-14` 的视频调试对照结论保持一致：

- 当前默认 `LSTM` 在 `Stand > Bed >> Chair`
- `Chair` 对应的 `side slide / slow fall` 是当前最弱项
- `Bed` 的 `roll / slide` 也是明显低响应区域
- `Stand` 相对响应最高，但仍远低于触发阈值

所以这批候选集的价值不是“再证明一次快跌倒能被规则法抓住”，而是：

- 为 `bed / chair / standing slow fall` 提供后续受控补强样本池
- 为是否进入后续受控训练提供更清晰的段级候选

## 5. 粗粒度标注建议

推荐只做粗粒度三段：

1. `fall_start_frame`
   - 明显开始失稳、滑落、翻滚或快速下坠的起点
2. `fall_end_frame`
   - 跌倒主过程结束，身体已经完成落地或姿态稳定
3. `post_fall_start_frame`
   - 倒地后稳定持续阶段的起点

不要求精确到单帧真值，只要求：

- 粗粒度可重复
- 后续可用于构造更合理的 `tail` / `post-fall` 候选窗口

## 6. 人工标注操作建议

如果你自己来标，建议按下面流程：

1. 先打开 `data/eval/fallvision_first_batch_segment_candidates_2026-04-15.csv`
2. 复制成你自己的工作副本
3. 逐个视频查看并填写：
   - `fall_start_frame`
   - `fall_end_frame`
   - `post_fall_start_frame`
   - `notes`
4. `notes` 里建议补：
   - 是否多人干扰
   - 是否有遮挡
   - 是否存在长时间预躺姿
   - 是否更像 `slide / roll / slow collapse / fast fall`

建议标注标准：

- 若人已经一开始接近躺姿，不要把视频开头直接记为 `fall_start_frame`
- `fall_start_frame` 应尽量对齐“明显开始失稳/移动”的帧
- `fall_end_frame` 应对齐“主要跌倒动作结束”的帧
- `post_fall_start_frame` 应对齐“倒地后姿态基本稳定”的帧

## 7. 对系统层的含义

这轮工作不改 `ROS2` 主闭环，但对系统层有一个清晰启发：

- 对遮挡、低可见度、慢滑落这类样本，后续系统更适合保留 `need_reobserve` 占位语义，而不是要求当前单次观察直接做强判定

本轮只做文档级占位，不接真实 `Nav2`

## 8. 当前结论

1. `FallVision` 视频调试集已经足够支撑第一批人工粗标候选集准备。
2. 当前最合理的下一步不是训练，而是先把 `15` 个候选视频做粗粒度段级标注。
3. 这批标注将直接决定后续是否值得做：
   - 更合理的 `tail` 窗口构造
   - `Bed / Chair / Stand` 的受控补强候选集
