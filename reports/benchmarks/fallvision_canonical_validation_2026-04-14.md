# FallVision Canonical Validation 2026-04-14

## 1. 目标

在不改变当前 `UR Fall + LSTM` 默认主线的前提下，验证 `data/external/fallvision/` 这个 canonical root 是否已经具备最小可用性：

1. 能否稳定提供统一的 `Fall / No Fall` 读取入口
2. 能否支持 manifest 统计与 sample report
3. 能否直接驱动 `build_fallvision_sequence_dataset.py` 做 smoke test
4. 能否为后续慢跌倒与家居场景离线调试准备一个小规模 curated pool

## 2. Canonical Root 状态

- canonical root：`data/external/fallvision/`
- manifest entry count：`5864`
- 当前 manifest 全部来自 `extracted/`
- 当前资源类型以 keypoint CSV 为主，不包含视频文件

## 3. 统计结果

按 `manifest.csv` 中 `is_csv=true` 的记录统计：

| Label | Scene | Count |
| --- | --- | ---: |
| Fall | Bed | 987 |
| Fall | Chair | 992 |
| Fall | Stand | 1021 |
| No Fall | Bed | 896 |
| No Fall | Chair | 959 |
| No Fall | Stand | 1009 |

汇总：

- `Fall`：`3000`
- `No Fall`：`2864`
- `Bed`：`1883`
- `Chair`：`1951`
- `Stand`：`2030`

## 4. Sample Report 覆盖性检查

当前 `data/external/fallvision/reports/sample_report.md` 存在，但默认抽样不覆盖全部主要类别。

本次检查结果：

- sample report 当前展示 `8` 条样本
- 这 `8` 条全部来自 `Fall / Bed`
- `Fall / Chair`、`Fall / Stand` 与 `No Fall` 当前没有出现在默认 sample report 中

因此，当前 sample report 可以证明 canonical root 已可读，但不能单独当作“类别覆盖已验证”的证据。

## 5. Sequence Dataset Smoke Test

执行命令：

```bash
python scripts/build_fallvision_sequence_dataset.py \
  --root data/external/fallvision/extracted \
  --max-files-per-scene-label 1 \
  --seq-len 32 \
  --stride 8 \
  --output /tmp/fallvision_sequence_smoke.npz
```

结果：

- 输出文件：`/tmp/fallvision_sequence_smoke.npz`
- dataset samples：`73`
- train：`61`
- val：`12`
- positive：`13`
- negative：`60`

关键张量形状：

- `x`: `(73, 32, 54)`
- `y`: `(73,)`
- `scene`: `(73,)`
- `video_id`: `(73,)`

结论：

- canonical root 已可直接驱动 `build_fallvision_sequence_dataset.py`
- 当前 `FallVision` keypoint 资源已具备最小 sequence dataset 构建可用性

## 6. Curated Pool 建议

当前阶段的 curated pool 目标不是直接训练，而是优先准备：

- 慢跌倒 / 家居跌倒候选池
- 离线结构化检查入口
- 后续视频版调试与外部验证的对照清单

本次按每个 `Fall` 场景下的 `csv` 数量近似筛选“更长片段优先”的候选：

| Scene | Candidate Clip | CSV Count | 用途判断 |
| --- | --- | ---: | --- |
| Bed | `Fall/Bed/Mask Video/f_mask_b_2_keypoints_csv/f_mask_b_2_keypoints_csv` | 355 | 优先保留 |
| Bed | `Fall/Bed/Mask Video/f_mask_b_1_keypoints_csv/f_mask_b_1_keypoints_csv` | 243 | 优先保留 |
| Chair | `Fall/Chair/Mask Video/f_mask_c_2_keypoints_csv/f_mask_c_2_keypoints_csv` | 514 | 优先保留 |
| Chair | `Fall/Chair/Mask Video/f_mask_c_3_keypoints_csv/f_mask_c_3_keypoints_csv` | 252 | 优先保留 |
| Stand | `Fall/Stand/Mask Video/f_mask_s_3_keypoints_csv/f_mask_s_3_keypoints_csv` | 535 | 优先保留 |
| Stand | `Fall/Stand/Mask Video/f_mask_s_1_keypoints_csv/f_mask_s_1_keypoints_csv` | 243 | 优先保留 |

备用候选：

- `Fall/Stand/Mask Video/f_mask_s_2_keypoints_csv/f_mask_s_2_keypoints_csv`：`243`
- `Fall/Bed/Mask Video/f_mask_b_4_keypoints_csv/f_mask_b_4_keypoints_csv`：`215`
- `Fall/Chair/Mask Video/f_mask_c_1_keypoints_csv/f_mask_c_1_keypoints_csv`：`226`

对应的结构化清单已写入：

- `data/eval/fallvision_curated_pool_2026-04-14.csv`

## 7. 当前结论

1. `data/external/fallvision/` 已经不是“只做目录占位”，而是具备实际可用性的 canonical root。
2. `Fall / No Fall / Bed / Chair / Stand` 六个主要分区都已经进入统一入口。
3. 当前 sample report 只能证明“资源可读”，不能证明“类别覆盖已检查完全”。
4. 当前 `FallVision` unified root 已可作为后续：
   - 数据筛选入口
   - sequence dataset 构建入口
   - curated pool 准备入口

## 8. 未解决风险

1. 当前 unified root 只有 keypoint CSV，没有视频文件；因此这轮 curated pool 更适合做数据层筛选，不适合直接跑 `run_pose_infer.py`。
2. `sample_report.md` 当前是默认抽样，不是类别均衡抽样；如果后续要当正式审计材料，建议额外生成按 `label/scene` 分层的 sample report。
3. 本轮 smoke test 只是工程可用性验证，不代表正式训练划分或正式指标。
