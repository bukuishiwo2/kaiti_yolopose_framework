# FallVision Video Debug Contrast 2026-04-14

## 1. 目标

在不改变当前 `UR Fall + LSTM` 默认主线、不进入训练、不调整阈值的前提下，对 `FallVision` 视频调试集做最小离线 debug 对照验证。

本次目标不是得出新的正式 benchmark，而是回答三个工程问题：

1. `fallvision_fall_videos_debug` 是否已可用于最小离线视频调试
2. 默认 pipeline 在 `Bed / Chair / Stand` 三类 home-style fall 上的 `rule / seq` 表现差异是什么
3. 当前 `LSTM` 的类别能力边界更像落在哪一侧

## 2. 资源接入状态

配置：

- `configs/external_datasets/fallvision_fall_videos_debug.yaml`

本次最小资源接入结果：

- matched archives：`3`
- scenes：`Bed / Chair / Stand`
- manifest entry count：`716`

说明：

- 当前最小视频调试集已经可自动下载、解压并生成 manifest / stats / sample report
- 本次只使用 `Fall` 视频，不引入 `No Fall`

## 3. 使用的视频样本

本次每类只选 1 个代表视频，优先使用 `resized.mp4` 以降低离线调试成本。

### Bed

- `data/external/fallvision_fall_videos_debug/extracted/Fall/Bed/Raw Video/f_raw_b_1/f_raw_b_1/B_D_0006_resized.mp4`

关键帧观察：

- 初始已接近床上躺姿
- 后续更像从床边缓慢滚落 / 滑落

类别判断：

- 更像 `滑落 / 慢性失稳`

### Chair

- `data/external/fallvision_fall_videos_debug/extracted/Fall/Chair/Raw Video/f_raw_c_1/f_raw_c_1/C_M_01_resized.mp4`

关键帧观察：

- 初始为坐姿
- 后续沿椅侧向地面滑落

类别判断：

- 更像 `慢跌倒 / 侧向滑落`

### Stand

- `data/external/fallvision_fall_videos_debug/extracted/Fall/Stand/Raw Video/f_raw_s_1/f_raw_s_1/S_D_0002_resized.mp4`

关键帧观察：

- 初始为站立
- 中段快速倒地，后段卧地

类别判断：

- 更像 `快跌倒`

## 4. 调试命令

本次按默认 pipeline 分别运行：

```bash
python scripts/run_pose_infer.py \
  --config /tmp/infer_pose_stream_bed.yaml \
  --source "data/external/fallvision_fall_videos_debug/extracted/Fall/Bed/Raw Video/f_raw_b_1/f_raw_b_1/B_D_0006_resized.mp4" \
  --device 0 \
  --save-debug-video \
  --debug-output /tmp/fallvision_bed_debug.mp4
```

```bash
python scripts/run_pose_infer.py \
  --config /tmp/infer_pose_stream_chair.yaml \
  --source "data/external/fallvision_fall_videos_debug/extracted/Fall/Chair/Raw Video/f_raw_c_1/f_raw_c_1/C_M_01_resized.mp4" \
  --device 0 \
  --save-debug-video \
  --debug-output /tmp/fallvision_chair_debug.mp4
```

```bash
python scripts/run_pose_infer.py \
  --config /tmp/infer_pose_stream_stand.yaml \
  --source "data/external/fallvision_fall_videos_debug/extracted/Fall/Stand/Raw Video/f_raw_s_1/f_raw_s_1/S_D_0002_resized.mp4" \
  --device 0 \
  --save-debug-video \
  --debug-output /tmp/fallvision_stand_debug.mp4
```

本次将 `save_jsonl` 临时改写到 `/tmp/`，避免覆盖仓库默认：

- `/tmp/fallvision_bed_pose_events.jsonl`
- `/tmp/fallvision_chair_pose_events.jsonl`
- `/tmp/fallvision_stand_pose_events.jsonl`

## 5. 每类结果摘要

### 5.1 Bed: `B_D_0006_resized.mp4`

- frames：`90`
- rule raw true frames：`71`
- rule stable true frames：`77`
- rule stable segments：`(6, 82)`
- max rule score：`1.0`
- seq raw true frames：`0`
- seq stable true frames：`0`
- max seq score：`0.00385`
- seq window ready frames：`59`
- seq visible keypoint max：`17`

观察：

- 规则法几乎从开头不久就进入持续稳定触发
- `seq` 分支模型已加载、窗口已形成、关键点可见性正常，但全程不触发
- `seq` 最高分只有 `0.00385`，离默认阈值 `0.6` 非常远

判断：

- 对这类 `床边滚落 / 滑落` 风格，当前 `LSTM` 几乎视为强负样本

### 5.2 Chair: `C_M_01_resized.mp4`

- frames：`60`
- rule raw true frames：`10`
- rule stable true frames：`6`
- rule stable segments：`(55, 60)`
- max rule score：`1.0`
- seq raw true frames：`0`
- seq stable true frames：`0`
- max seq score：`0.0000076`
- seq window ready frames：`29`
- seq visible keypoint max：`17`

观察：

- 规则法只在后段倒地姿态较明确时才触发
- `seq` 分支得分几乎为零，明显低于 `Bed` 和 `Stand`
- 这更像椅侧缓慢滑落，不像剧烈跌倒

判断：

- 对这类 `chair slow fall / side slide`，当前 `LSTM` 响应最弱

### 5.3 Stand: `S_D_0002_resized.mp4`

- frames：`96`
- rule raw true frames：`18`
- rule stable true frames：`18`
- rule stable segments：`(55, 63)`、`(88, 96)`
- max rule score：`1.0`
- seq raw true frames：`0`
- seq stable true frames：`0`
- max seq score：`0.03776`
- seq window ready frames：`65`
- seq visible keypoint max：`17`

观察：

- 规则法能在倒地附近两次形成稳定段
- `seq` 虽然仍不触发，但相对分数明显高于 `Bed` 和 `Chair`
- `seq` 最高分约 `0.0378`，仍远低于 `0.6`

判断：

- 当前 `LSTM` 对 `快跌倒` 的相对响应高于 `Bed / Chair`，但绝对置信度仍太低，无法触发

## 6. 结构性结论

### 6.1 当前 `LSTM` 并不是“链路没工作”

三类样本中：

- `seq_model_loaded=true`
- `seq_window_ready` 均已形成
- `seq_visible_keypoint_count` 最高均达到 `17`

因此当前问题不是：

- 模型没加载
- 时序窗口没形成
- 输入关键点无效

### 6.2 当前主问题是“home-style 视频域下分数整体过低”

相对响应顺序大致为：

- `Stand` > `Bed` >> `Chair`

但三类样本都没有达到 `seq_raw_fall_detected=true`。

这说明当前默认 `LSTM`：

- 对 `快跌倒` 有一定相对敏感性
- 对 `床边滚落 / 椅侧滑落 / 慢跌倒` 响应明显不足
- 在 `FallVision` 视频域下整体呈现“严重保守”

### 6.3 规则法更像“姿态末态检测”，时序法更像“过程型匹配”

本次三类样本都能看到：

- 规则法会在倒地或明显侧卧姿态形成后触发
- `seq` 分支则更依赖与训练分布相似的时序过程

因此，当前 `LSTM` 的边界更接近：

- 对 `UR Fall` 风格有效
- 对家居风格 `Bed / Chair / Stand` 视频尤其是慢跌倒和滑落泛化不足

## 7. 对后续补强方向的含义

这轮结果支持当前数据策略判断：

1. 不需要推翻 `UR Fall` 主 benchmark
2. 后续应优先补：
   - `FallVision fall`
   - 特别是 `bed / chair / standing slow fall`
3. 当前更需要的是：
   - 补正样本分布
   - 做受控补强
   - 保持默认模型主线不变，先验证再决定是否训练

## 8. 未解决风险

1. 本次每类只跑了 1 个样本，不代表整个 `FallVision` 视频域的完整结论。
2. 规则法在 `Bed` 样本上触发很早，说明它对“已处于近躺姿 + 多人干扰”的场景可能偏激进。
3. 当前 `Chair` 样本的 `seq` 得分极低，后续如果继续验证，应优先扩展更多椅侧滑落视频，而不是立即调阈值。
