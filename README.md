# kaiti-yolopose-framework

基于 `YOLOPose` 的人体姿态识别与跌倒检测研究型工程仓库。

当前仓库已经具备两条完整技术路线：
- 规则法基线：基于关键点几何关系进行单帧判断，再做时序稳定
- 学习型主线：基于关键点序列训练 `LSTM` 时序分类器，再做事件稳定输出

当前推荐主线：**学习型时序模型**。规则法保留为 baseline 和对照组。

## 1. 项目目标

本项目面向“视频流场景下的跌倒检测”任务，当前重点不是重训练人体姿态模型，而是：
1. 使用预训练 `YOLOPose` 稳定提取人体关键点
2. 在关键点基础上完成跌倒检测模块实现
3. 建立统一的训练、推理、评估、调参和结果归档流程
4. 将仓库整理成可长期维护、可上传 GitHub、可跨电脑复现的工程结构

当前项目定位应表述为：

`基于预训练人体姿态估计模型的跌倒检测研究框架`

## 2. 当前状态

### 2.1 已完成

- 姿态推理主链路
- GPU 推理验证
- 视频 / 摄像头 / 流输入支持
- 规则法跌倒检测与稳定器
- 姿态序列数据集构建脚本
- `LSTM` 时序跌倒分类器训练脚本
- 统一批量评估脚本
- 规则法与学习型模型对照评估
- 网格搜索调参脚本
- 工作记录、benchmark 摘要与仓库规范文档

### 2.2 当前未完成

- 自定义 pose 模型微调
- 多数据集系统性 benchmark
- 学习型模型误报压制优化
- 更强时序模型（如 `TCN` / `ST-GCN`）
- 面向部署的完整服务化、报警接口和前端展示

## 3. 当前结论

### 3.1 UR Fall 基准结果

规则法基线（`outputs/eval_urfall/`）：
- Precision: `0.7558`
- Recall: `0.4196`
- F1: `0.5396`

学习型时序模型（`outputs/eval_urfall_sequence/`）：
- Precision: `0.7769`
- Recall: `0.8000`
- F1: `0.7883`

同口径结论：
- 学习型模型相对规则法显著提升了召回率和 F1
- 规则法仍有参考价值，但不再是后续优化主线
- 学习型模型当前主要问题是 ADL 场景误报偏多
- 第一轮学习型调参后，当前默认候选配置已更新为 `score_threshold=0.6`、`min_true_frames=3`、`min_false_frames=5`

更详细的结果摘要见：
- [UR Fall 对比摘要](reports/benchmarks/urfall_comparison_2026-04-09.md)

## 4. 仓库结构

```text
kaiti_yolopose_framework/
├── configs/                    # 手工维护的推理/训练配置
├── data/                       # 可提交的小型模板、标签与说明
│   ├── eval/
│   ├── streams/
│   └── README.md
├── datasets/                   # 数据集 yaml 模板
├── docs/                       # 设计说明、约定、工作记录
├── models/                     # 本地模型目录（默认不提交权重）
├── outputs/                    # 本地运行产物目录（默认不提交）
├── reports/                    # 长期保留的 benchmark 摘要
├── ros2_ws/                    # 后续 ROS2 对接骨架
├── scripts/                    # 统一入口脚本
├── src/yolopose/               # 可复用源码
│   ├── core/
│   ├── pipeline/
│   └── temporal/
├── .editorconfig
├── .gitattributes
├── .gitignore
├── Makefile
├── pyproject.toml
├── requirements.txt
├── requirements-cu118.txt
└── requirements-cu121.txt
```

目录职责约定：
- `src/` 只放可复用源码
- `scripts/` 只放入口脚本
- `configs/` 只放手工维护配置
- `outputs/` 只放本地运行结果
- `reports/` 只放适合长期提交的结果摘要

详细命名与目录规则见：
- [项目约定](docs/project_conventions.md)
- [文档索引](docs/README.md)

## 5. 环境安装

```bash
cd /path/to/kaiti_yolopose_framework
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e . --no-deps
```

说明：
- `requirements.txt` 当前默认安装 `cu121` 组合
- 若你的环境更适合 `cu118`，可改用 `requirements-cu118.txt`
- `pip install -e . --no-deps` 用于让 `src/` 包以可编辑模式被 Python 发现

## 6. 快速开始

### 6.1 运行姿态推理

```bash
python scripts/run_pose_infer.py \
  --config configs/infer_pose_stream.yaml \
  --source /path/to/video.mp4 \
  --device 0
```

常见 `device` 写法：
- `--device 0`
- `--device cuda:0`
- `--device cpu`

### 6.2 摄像头推理

```bash
python scripts/run_pose_infer.py --source 0 --device 0
```

若报 `/dev/video0` 不存在，请先检查：

```bash
ls /dev/video*
```

### 6.3 多路流推理

先编辑：
- [example.streams](data/streams/example.streams)

每行写一个 RTSP 地址，然后运行：

```bash
python scripts/run_pose_infer.py --mode track --device 0
```

## 7. 两条算法路线

### 7.1 规则法基线

核心文件：
- [fall_detector.py](src/yolopose/pipeline/fall_detector.py)
- [runner.py](src/yolopose/pipeline/runner.py)
- [infer_pose_stream.yaml](configs/infer_pose_stream.yaml)

方法：
1. `YOLOPose` 输出人体框和 17 个关键点
2. 根据人体框宽高比、躯干垂直比例、下肢垂直比例做单帧判断
3. 用稳定器输出 `raw_fall_detected` 和 `stable_fall_detected`

该路线优点：
- 实现简单
- 解释性强
- 可作为 baseline

该路线缺点：
- 对复杂动作和边界动作不够鲁棒
- 召回率有限

### 7.2 学习型时序主线

核心文件：
- [features.py](src/yolopose/temporal/features.py)
- [model.py](src/yolopose/temporal/model.py)
- [sequence_fall_detector.py](src/yolopose/temporal/sequence_fall_detector.py)
- [run_fall_sequence_train.py](scripts/run_fall_sequence_train.py)
- [build_pose_sequence_dataset.py](scripts/build_pose_sequence_dataset.py)

方法：
1. `YOLOPose` 提取关键点
2. 将连续若干帧编码为姿态序列
3. 使用 `LSTM` 做跌倒 / 非跌倒二分类
4. 用稳定器输出 `seq_raw_fall_detected` 和 `seq_stable_fall_detected`

该路线优点：
- 已在 `UR Fall` 上显著优于规则法
- 更符合跌倒是“动作过程”而非“单帧姿态”的任务本质

当前短板：
- ADL 场景误报偏多
- 仍需要阈值和稳定参数进一步调优

## 8. 数据准备

### 8.1 下载 UR Fall

```bash
bash scripts/download_urfall_cam0.sh --mode all
```

### 8.2 构建 UR Fall 标签 CSV

```bash
python scripts/build_urfall_labels.py \
  --falls-csv data/urfall/labels_raw/urfall-cam0-falls.csv \
  --video-dir data/urfall/cam0_mp4 \
  --out data/eval/video_labels_urfall_cam0.csv \
  --include-adl
```

### 8.3 构建姿态序列数据集

```bash
python scripts/build_pose_sequence_dataset.py \
  --labels data/eval/video_labels_urfall_cam0.csv \
  --device 0 \
  --seq-len 32 \
  --stride 4 \
  --output data/processed/urfall_pose_sequences.npz
```

### 8.4 补 hard negative 数据

如果当前误报主要来自躺下、坐下、弯腰、地面动作，建议补 hard negative 数据而不是继续细调当前 LSTM 阈值。

说明文档：
- [hard_negative_plan.md](docs/hard_negative_plan.md)

模板文件：
- [video_labels_hard_negative_template.csv](data/eval/video_labels_hard_negative_template.csv)
- [video_labels_hard_negative_seed.csv](data/eval/video_labels_hard_negative_seed.csv)

合并脚本：
- [merge_label_csvs.py](scripts/merge_label_csvs.py)

合并示例：

```bash
python scripts/merge_label_csvs.py \
  --inputs data/eval/video_labels_urfall_cam0.csv data/eval/video_labels_hard_negative.csv \
  --output data/eval/video_labels_urfall_plus_hn.csv
```

### 8.5 接入 FallVision

如果你已经下载了 FallVision 的 `keypoints_csv.rar`，当前推荐做法是：
- 先解压得到实际 `.csv`
- 然后直接用 CSV 构建时序训练集

说明文档：
- [fallvision_integration.md](docs/fallvision_integration.md)

导入脚本：
- [build_fallvision_sequence_dataset.py](scripts/build_fallvision_sequence_dataset.py)

小规模验证：

```bash
python scripts/build_fallvision_sequence_dataset.py \
  --root "data/Fall Detection Video Dataset" \
  --glob "**/*.csv" \
  --max-files-per-scene-label 5 \
  --output data/processed/fallvision_smoke.npz
```

## 9. 训练与评估

### 9.1 训练学习型时序模型

```bash
python scripts/run_fall_sequence_train.py \
  --config configs/train_fall_sequence.yaml
```

默认输出：
- [fall_sequence_lstm.pt](models/fall_sequence_lstm.pt)
- [fall_sequence_lstm.history.json](models/fall_sequence_lstm.history.json)

### 9.2 评估规则法

```bash
python scripts/eval_fall_batch.py \
  --labels data/eval/video_labels_urfall_cam0.csv \
  --config configs/infer_pose_stream.yaml \
  --mode predict \
  --device 0 \
  --out-dir outputs/eval_urfall
```

### 9.3 评估学习型模型

```bash
python scripts/eval_fall_batch.py \
  --labels data/eval/video_labels_urfall_cam0.csv \
  --config configs/infer_pose_stream.yaml \
  --mode predict \
  --device 0 \
  --raw-key seq_raw_fall_detected \
  --stable-key seq_stable_fall_detected \
  --out-dir outputs/eval_urfall_sequence
```

### 9.4 调学习型阈值与稳定参数

推荐先调这 3 个参数：
- `sequence_fall_detector.score_threshold`
- `sequence_fall_detector.min_true_frames`
- `sequence_fall_detector.min_false_frames`

已提供序列模型专用网格：
- [fall_grid_sequence.yaml](data/eval/fall_grid_sequence.yaml)
- [fall_grid_sequence_refine.yaml](data/eval/fall_grid_sequence_refine.yaml)

直接运行：

```bash
python scripts/tune_fall_grid.py \
  --labels data/eval/video_labels_urfall_cam0.csv \
  --base-config configs/infer_pose_stream.yaml \
  --grid data/eval/fall_grid_sequence.yaml \
  --target-detector sequence_fall_detector \
  --mode predict \
  --device 0 \
  --raw-key seq_raw_fall_detected \
  --stable-key seq_stable_fall_detected \
  --out-dir outputs/tune_fall_grid_sequence
```

或使用：

```bash
make tune-seq
```

第一轮结果表明最有效参数是 `score_threshold`。当前推荐主配置是：
- `score_threshold=0.6`
- `min_true_frames=3`
- `min_false_frames=5`

如果继续做第二轮小范围精调，建议运行：

```bash
python scripts/tune_fall_grid.py \
  --labels data/eval/video_labels_urfall_cam0.csv \
  --base-config configs/infer_pose_stream.yaml \
  --grid data/eval/fall_grid_sequence_refine.yaml \
  --target-detector sequence_fall_detector \
  --mode predict \
  --device 0 \
  --raw-key seq_raw_fall_detected \
  --stable-key seq_stable_fall_detected \
  --out-dir outputs/tune_fall_grid_sequence_refine
```

### 9.5 结果文件说明

批量评估输出目录通常包含：
- `summary.json`：总体汇总指标
- `metrics_per_video.csv`：逐视频指标
- `metrics_compare.csv`：`raw` 与 `stable` 对比
- `segments_per_video.csv`：真实跌倒段与检测段

如果你要看“检测到的跌倒时间段”，优先查看：
- `segments_per_video.csv`

如果你要看逐帧状态，查看：
- `jsonl/*.jsonl`
- 或单次推理输出 `outputs/pose_events.jsonl`

## 10. 当前配置入口

主推理配置：
- [infer_pose_stream.yaml](configs/infer_pose_stream.yaml)

当前关键配置块：
- `stabilizer`：人体存在稳定器
- `fall_detector`：规则法跌倒检测参数
- `sequence_fall_detector`：学习型时序检测参数

时序模型训练配置：
- [train_fall_sequence.yaml](configs/train_fall_sequence.yaml)

## 11. 结果归档与 Git 提交策略

本仓库提交到 GitHub 时，建议只提交：
- 源码
- 配置文件
- 说明文档
- 小型标签模板
- benchmark 摘要

不要提交：
- 虚拟环境
- 下载的视频数据
- 训练权重
- 自动下载的 `YOLO` 权重
- `outputs/` 下的运行产物
- 大型 `npz` 数据集
- IDE 私有目录

当前这些策略已经体现在：
- [`.gitignore`](.gitignore)
- [项目约定](docs/project_conventions.md)

## 12. 常用维护命令

### 12.1 清理运行结果

```bash
bash scripts/clean_outputs.sh
```

### 12.2 清理本地大体积产物

```bash
bash scripts/clean_local_artifacts.sh
```

### 12.3 Makefile 入口

```bash
make help
make setup
make build-seq
make train-seq
make eval-rule
make eval-seq
```

## 13. GitHub 上传建议流程

如果你准备把当前目录作为正式仓库上传：

```bash
cd /path/to/kaiti_yolopose_framework
git init -b main
git add .
git commit -m "Init fall detection research framework"
```

然后在 GitHub 创建空仓库后执行：

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

建议上传前先执行：

```bash
bash scripts/clean_local_artifacts.sh
```

这样可以避免把本地数据、权重和中间产物一并推上去。

## 14. 推荐阅读顺序

1. [README.md](README.md)
2. [project_conventions.md](docs/project_conventions.md)
3. [architecture.md](docs/architecture.md)
4. [UR Fall benchmark 摘要](reports/benchmarks/urfall_comparison_2026-04-09.md)
5. [worklog_2026-04-08.md](docs/worklog_2026-04-08.md)
6. [worklog_2026-04-09.md](docs/worklog_2026-04-09.md)

## 15. 下一步建议

1. 以学习型时序模型为主线，优先压低 ADL 误报。
2. 继续调 `sequence_fall_detector.score_threshold` 与稳定参数。
3. 增加更多无跌倒复杂动作视频做泛化验证。
4. 需要更强性能时，再尝试 `TCN` 或 `ST-GCN`。
