# External Dataset Workflow

本文件说明如何在不改变当前 `UR Fall + LSTM` 默认主线的前提下，新增外部数据集资源接入、解压整理、manifest 生成、最小统计与离线调试支持。

## 1. 目标

当前外部数据集接入只承担三类职责：

1. 为慢跌倒和家居场景提供补充样本池
2. 为外部泛化提供 external validation 资源
3. 为离线视频调试提供可复用输入

当前不做的事：

- 不替换 `UR Fall` 主 benchmark
- 不直接全量混入训练
- 不改变默认模型和权重

## 2. 新目录结构

新增资源统一放到：

- `data/external/`

每个数据集统一使用：

```text
data/external/<dataset_key>/
├── raw/
├── extracted/
├── manifests/
├── reports/
└── splits/
```

其中：

- `raw/`：原始下载包或用户手动放入的压缩包
- `extracted/`：解压结果
- `manifests/`：清单 JSON / CSV
- `reports/`：最小统计报告与 sample report
- `splits/`：候选 split 文件，不直接代表正式训练划分

## 2.1 FallVision 的 canonical 入口

当前 `FallVision` 已经存在两类本地来源：

- 旧目录：`data/Fall Detection Video Dataset/`，当前主要是 `No Fall`
- 新目录：`data/external/fallvision_fall_keypoints/`、`data/external/fallvision_fall_videos_debug/`

为避免同一数据集继续分散在两套目录里，统一使用：

- `data/external/fallvision/`

作为 canonical grouped view。

这个 canonical 目录默认通过 `scripts/organize_fallvision_layout.py` 生成安全 symlink 视图，不直接搬动或删除已有本地数据。

## 3. 当前支持的数据集配置

### 3.1 FallVision fall keypoints

配置：

- `configs/external_datasets/fallvision_fall_keypoints.yaml`

用途：

- 作为慢跌倒 / 家居 fall 补充样本池
- 主要面向后续数据筛选与候选训练集构建
- 整理完成后建议再同步到 `data/external/fallvision/`

### 3.2 FallVision fall videos debug

配置：

- `configs/external_datasets/fallvision_fall_videos_debug.yaml`

用途：

- 作为最小离线视频调试集
- 用于直接跑 `run_pose_infer.py` 和 OSD 可视化
- 整理完成后建议再同步到 `data/external/fallvision/`

### 3.3 Le2i external eval

配置：

- `configs/external_datasets/le2i_external_eval.yaml`

用途：

- 作为 external validation 资源池
- 当前先做资源接入与整理，不直接进入训练

## 4. 下载与放置方式

### 4.0 先同步 FallVision 统一视图

如果你本地已经同时存在旧 `No Fall` 目录和新的 `Fall` 补充目录，先执行：

```bash
python scripts/organize_fallvision_layout.py --apply
python scripts/prepare_external_dataset.py \
  --dataset-config configs/external_datasets/fallvision_unified.yaml \
  --generate-manifest --generate-split --generate-stats --generate-sample-report
```

这样后续统一从：

- `data/external/fallvision/extracted`

读取 `FallVision` 资源，而不是继续在旧目录和新目录之间手动切换。

### 4.1 FallVision

FallVision 可直接下载，不需要用户额外提供 URL。

下载来源：

- Harvard Dataverse DOI: `10.7910/DVN/75QPKK`

Fall keypoints 补充样本：

```bash
python scripts/prepare_external_dataset.py \
  --dataset-config configs/external_datasets/fallvision_fall_keypoints.yaml \
  --download --extract --generate-manifest --generate-split --generate-stats --generate-sample-report
```

最小离线视频调试集：

```bash
python scripts/prepare_external_dataset.py \
  --dataset-config configs/external_datasets/fallvision_fall_videos_debug.yaml \
  --download --extract --generate-manifest --generate-split --generate-stats --generate-sample-report
```

如果只想先做 smoke test，可额外加：

```bash
--max-files-per-group 1
```

### 4.2 Le2i

Le2i 当前不在脚本中硬编码下载地址。若你已经有可用下载链接或本地压缩包，可用两种方式：

方式 A：直接给 URL

```bash
python scripts/prepare_external_dataset.py \
  --dataset-config configs/external_datasets/le2i_external_eval.yaml \
  --source-url "<LE2I_ARCHIVE_URL>" \
  --download --extract --generate-manifest --generate-split --generate-stats --generate-sample-report
```

方式 B：手动下载后放到：

- `data/external/le2i_external_eval/raw/`

然后运行：

```bash
python scripts/prepare_external_dataset.py \
  --dataset-config configs/external_datasets/le2i_external_eval.yaml \
  --extract --generate-manifest --generate-split --generate-stats --generate-sample-report
```

## 5. 统一解压流程

当前统一支持：

- `.zip`
- `.tar`
- `.tar.gz`
- `.tar.bz2`
- `.tar.xz`
- `.tgz`
- `.rar`
- `.7z`

说明：

- `zip/tar` 优先使用 Python 内置解压
- `rar/7z` 需要系统存在 `7z`、`unrar` 或 `unar`

## 6. 生成结果

每个数据集都会在对应目录下生成：

- `manifests/manifest.json`
- `manifests/manifest.csv`
- `splits/default_split.csv`
- `reports/dataset_stats.json`
- `reports/dataset_stats.md`
- `reports/sample_report.md`

## 7. 最小离线调试

若 sample report 中存在视频样本，可直接运行：

```bash
cd /home/yhc/kaiti_yolopose_framework
source .venv/bin/activate
python scripts/run_pose_infer.py \
  --config configs/infer_pose_stream.yaml \
  --source "<sample_video_path>" \
  --device 0 \
  --save-debug-video
```

对于 `FallVision fall videos debug`，也可以直接从 `sample_report.md` 中复制第一条推荐命令。

补充说明：

- `fallvision_unified` 当前主要是 keypoint CSV grouped view，不包含视频文件
- 因此 `data/external/fallvision/reports/sample_report.md` 适合做资源可读性检查，不适合直接替代视频调试入口
- 若要做类别覆盖检查或后续慢跌倒候选筛选，应结合：
  - `data/external/fallvision/manifests/manifest.csv`
  - `data/eval/fallvision_curated_pool_2026-04-14.csv`
  - `reports/benchmarks/fallvision_canonical_validation_2026-04-14.md`

若要做最小视频调试对照验证，可参考：

- `reports/benchmarks/fallvision_video_debug_contrast_2026-04-14.md`

若已经完成 `FallVision` 视频的粗粒度段级标注，并想做训练前窗口构造 smoke test，可继续使用：

```bash
python scripts/build_fallvision_labeled_window_dataset.py \
  --labels-csv data/eval/fallvision_first_batch_segment_candidates_2026-04-15_labeled.csv
```

默认输出：

- `data/eval/fallvision_labeled_window_smoke_2026-04-15.csv`
- `data/eval/fallvision_labeled_window_smoke_2026-04-15.npz`
- `reports/benchmarks/fallvision_labeled_window_smoke_2026-04-15.md`

## 8. 当前工程判断

当前这套支持的目标是：

- 先把新增数据集资源接入、整理、可观察化
- 先形成 manifest / split / stats / sample report
- 再决定哪些资源适合进入训练，哪些只做 external validation

这与当前项目定位一致：

- `UR Fall` 继续是主 benchmark
- `LSTM` 继续是默认主线
- 外部数据先做补盲区和外部验证，不直接改主线
