# FallVision Labeled Window Smoke 2026-04-15

## 1. 目标

基于已完成的粗粒度段级标注，验证这批 `FallVision` 视频是否已经足以支撑训练前的窗口构造与可用性检查。

本次不进入训练，只做：

1. 兼容当前 `LSTM` 主线输入格式的窗口构造
2. 窗口级标签规则验证
3. 每视频 / 每场景的窗口统计

## 2. 窗口构造规则

- `seq_len=32`, `stride=4`，沿视频滑窗构造窗口。
- 每个窗口先通过 `video_path -> *_keypoints.csv` 自动映射到 canonical FallVision keypoint CSV。
- 若窗口结束帧仍早于 `fall_start_frame`，标为 `negative`。
- 若窗口中心帧落在 `[fall_start_frame, fall_end_frame]` 且与 fall 段的重叠比例 `>= 0.50`，标为 `positive`。
- 若窗口中心帧晚于 `fall_end_frame` 且与 `[post_fall_start_frame, video_end]` 的重叠比例 `>= 0.50`，标为 `post_fall_stable`。
- 其余跨边界混合窗口标为 `transition_ignore`，不直接进入 train-ready NPZ。
- `y_binary` 中：`negative=0`，`positive/post_fall_stable=1`，`transition_ignore=-1`。

## 3. Smoke Test 输出

- window csv: `data/eval/fallvision_labeled_window_smoke_2026-04-15.csv`
- train-ready npz: `data/eval/fallvision_labeled_window_smoke_2026-04-15.npz`

## 4. 每视频窗口统计

| Video | Scene | Style | Total Windows | Positive | Transition Ignore | Post-Fall Stable | Negative |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `B_D_0006_resized.mp4` | `bed` | `bed_roll_slide` | 15 | 7 | 4 | 3 | 1 |
| `B_D_0007_resized.mp4` | `bed` | `bed_side_slide` | 15 | 7 | 4 | 0 | 4 |
| `B_D_0008_resized.mp4` | `bed` | `bed_slide_short` | 15 | 3 | 0 | 12 | 0 |
| `B_D_0009_resized.mp4` | `bed` | `bed_side_roll` | 23 | 5 | 0 | 18 | 0 |
| `B_D_0010_resized.mp4` | `bed` | `bed_slow_roll` | 15 | 7 | 2 | 6 | 0 |
| `C_M_01_resized.mp4` | `chair` | `chair_side_slide` | 8 | 3 | 4 | 0 | 1 |
| `C_M_04_resized.mp4` | `chair` | `chair_forward_slide` | 21 | 7 | 4 | 9 | 1 |
| `C_M_05_resized.mp4` | `chair` | `chair_forward_slide` | 11 | 5 | 3 | 0 | 3 |
| `C_M_06_resized.mp4` | `chair` | `chair_forward_slide` | 14 | 7 | 4 | 1 | 2 |
| `C_M_07_resized.mp4` | `chair` | `chair_forward_slide` | 14 | 6 | 4 | 1 | 3 |
| `S_D_0002_resized.mp4` | `stand` | `stand_fast_fall` | 17 | 5 | 3 | 6 | 3 |
| `S_D_0004_resized.mp4` | `stand` | `stand_fast_fall` | 23 | 5 | 4 | 9 | 5 |
| `S_D_0005_resized.mp4` | `stand` | `stand_fast_fall` | 23 | 6 | 3 | 11 | 3 |
| `S_D_0016_resized.mp4` | `stand` | `stand_fast_fall` | 10 | 0 | 7 | 3 | 0 |
| `S_D_0028_resized.mp4` | `stand` | `stand_slow_collapse` | 5 | 0 | 1 | 4 | 0 |

## 5. 每场景汇总

| Scene | Total Windows | Positive | Transition Ignore | Post-Fall Stable | Negative |
| --- | ---: | ---: | ---: | ---: | ---: |
| `bed` | 83 | 29 | 10 | 39 | 5 |
| `chair` | 68 | 28 | 19 | 11 | 10 |
| `stand` | 78 | 16 | 18 | 33 | 11 |

## 6.1 需要单独关注的视频

- B_D_0007_resized.mp4: post_fall_stable=0
- B_D_0008_resized.mp4: negative=0
- B_D_0009_resized.mp4: negative=0
- B_D_0010_resized.mp4: negative=0
- C_M_01_resized.mp4: post_fall_stable=0
- C_M_05_resized.mp4: post_fall_stable=0
- S_D_0016_resized.mp4: positive=0, negative=0
- S_D_0028_resized.mp4: positive=0, negative=0

## 7. 当前判断

- 若一个视频能稳定生成 `positive + post_fall_stable + negative` 三类窗口，则其粗标已具备最小训练前可用性。
- `transition_ignore` 的存在是正常的，它用于避免把粗标边界附近的混合窗口直接塞进正负样本。
- 当前 15 个视频若都能稳定生成窗口，则足以支持后续受控补强训练的 pilot，但仍不足以直接替代主 benchmark 训练分布。
