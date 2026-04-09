# New Machine Setup

本说明回答一个具体问题：换一台电脑后，`git clone` 本仓库还需要做什么，才能继续调试。

## 1. `git clone` 能恢复什么

可以恢复：
- 源码
- 配置文件
- 文档
- 标签模板
- benchmark 摘要
- 运行脚本

不能恢复：
- 本地虚拟环境
- 原始数据集视频
- 处理后的 `npz`
- 训练权重
- 运行输出
- 自动下载的模型权重

原因不是仓库不完整，而是这些内容被刻意排除在 Git 之外。

## 2. 新电脑上的最小步骤

```bash
git clone <your-repo-url>
cd kaiti_yolopose_framework
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e . --no-deps
```

## 3. 按用途恢复资源

### 3.1 只做推理调试

准备一个本地视频，然后运行：

```bash
python scripts/run_pose_infer.py --source /path/to/video.mp4 --device 0
```

首次运行会自动下载 `yolo11n-pose.pt`。

### 3.2 做规则法评估

```bash
bash scripts/download_urfall_cam0.sh --mode all
python scripts/build_urfall_labels.py   --falls-csv data/urfall/labels_raw/urfall-cam0-falls.csv   --video-dir data/urfall/cam0_mp4   --out data/eval/video_labels_urfall_cam0.csv   --include-adl
python scripts/eval_fall_batch.py   --labels data/eval/video_labels_urfall_cam0.csv   --config configs/infer_pose_stream.yaml   --mode predict   --device 0   --out-dir outputs/eval_urfall
```

### 3.3 做学习型时序模型调试

```bash
python scripts/build_pose_sequence_dataset.py   --labels data/eval/video_labels_urfall_cam0.csv   --device 0   --output data/processed/urfall_pose_sequences.npz
python scripts/run_fall_sequence_train.py --config configs/train_fall_sequence.yaml
```

如果你不想重新训练：
- 直接把旧电脑的 `models/fall_sequence_lstm.pt` 复制到新电脑 `models/` 下即可。

## 4. Codex 是否能“还原完整项目”

可以还原的是：
- 仓库里已经提交的源码、配置和文档结构
- 基于这些文件继续修改和扩展项目

不能自动还原的是：
- 没有被提交到 Git 的数据集、视频、权重和本地产物

因此，新的 Codex 能读懂并继续维护这个仓库，但不能凭空恢复被 `.gitignore` 排除的本地文件。

如果要提高跨电脑还原能力，推荐后续补一项：
- 把必要权重放到 GitHub Release 或网盘
- 或用 `Git LFS` 管理少量关键模型文件
