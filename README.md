# kaiti-yolopose-framework

面向动态家居场景移动机器人任务系统的研究型工程仓库。当前已经形成两条稳定主线：

- 感知主线：基于人体关键点的跌倒检测、时序模型、语义事件稳定化
- 系统主线：ROS2 骨架、感知到任务层桥接、后续 `RTAB-Map / Nav2 / PlanSys2 / LTL` 接口预留

当前仓库的准确定位是：

`面向动态家居场景移动机器人任务系统的感知子系统与系统层骨架研究框架`

## 1. 当前默认与阶段结论

当前推荐默认：

- 主学习模型：`LSTM`
- 默认学习型模型：`models/fall_sequence_lstm_urfall_finetune_from_fallvision_sampled.pt`
- 默认学习型推理参数：`score_threshold=0.6`、`min_true_frames=3`、`min_false_frames=5`
- `TCN`：低误报候选，不是默认主模型
- 规则法：baseline 和对照组
- supervisor 默认消费 `seq_stable_fall_detected`，规则法仅保留为 debug/baseline，并只在时序分支显式失效时回退
- ROS2 输入模式：`mock` 默认可跑，`video_file / camera` 可选
- ROS2 在线图像模式：`ros_image`，可接 `/camera/image_raw`
- ROS2 调试可视化：可选发布 `/perception/debug_image`

当前结论：

- `YOLOPose + 时序模型` 已经形成可训练、可推理、可评估、可调参的完整闭环
- `ROS2` 已经打通最小闭环：`/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status`
- topic 仍使用 `std_msgs/msg/String + JSON`，但接口语义已经收敛为稳定 schema v1
- 当前默认学习型正式结果：`Precision=0.8657`、`Recall=0.7401`、`F1=0.7979`
- 当前重点是冻结感知默认主线，并继续收口系统正式接口与外部验证策略

关键 benchmark 摘要：

- 规则法 baseline：`Precision=0.7558`，`Recall=0.4196`，`F1=0.5396`
- 默认 `LSTM` 时序模型：`Precision=0.8657`，`Recall=0.7401`，`F1=0.7979`
- `TCN` 时序模型：`Precision=0.8990`，`Recall=0.5882`，`F1=0.7111`

详见：

- [UR Fall Benchmark 摘要](reports/benchmarks/urfall_comparison_2026-04-09.md)
- [UR Fall Rule / LSTM / TCN 对比摘要](reports/benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md)

## 2. 仓库结构

```text
kaiti_yolopose_framework/
├── configs/                    # 手工维护的训练 / 推理配置
├── data/                       # 可提交的小型模板、标签与说明
├── datasets/                   # 数据集 yaml 模板
├── docs/                       # 长期维护文档
│   ├── archive/                # 归档的历史文档
│   ├── reviews/                # 阶段审计、接口评审、汇总结论
│   └── worklogs/               # 按日期记录的开发日志
├── models/                     # 本地模型目录，仓库内只保留说明文件
├── outputs/                    # 本地运行产物目录，仓库内只保留说明文件
├── reports/                    # 长期保留的 benchmark 摘要与阶段结论
├── ros2_ws/                    # ROS2 工作区与系统骨架
├── scripts/                    # 入口脚本
├── src/yolopose/               # 可复用源码
└── AGENTS.md                   # 项目级协作边界
```

目录职责规则：

- `src/` 只放可复用源码
- `scripts/` 只放入口
- `configs/` 只放手工维护配置
- `reports/` 只放长期保留的结果摘要
- `docs/reviews/` 只放阶段性审计和汇总结论
- `docs/worklogs/` 只放按日期命名的开发记录
- `docs/archive/` 只放被替代但仍需保留的历史文档

详细规范见：

- [项目约定](docs/project_conventions.md)
- [文档索引](docs/README.md)
- [文档信息架构](docs/documentation_information_architecture.md)
- [多代理协作说明](docs/agents.md)
- [项目级角色边界](AGENTS.md)

## 3. 文档导航

建议阅读顺序：

1. [项目约定](docs/project_conventions.md)
2. [开题目标对齐](docs/kaiti_alignment.md)
3. [系统架构说明](docs/system_architecture.md)
4. [ROS2 最小骨架说明](docs/system_bringup_skeleton.md)
5. [系统接口契约](docs/system_interface_contract.md)
6. [数据集定位与外部验证策略](docs/dataset_positioning.md)
7. [ROS2 工作区说明](ros2_ws/README.md)
8. [阶段审计与汇总](docs/reviews/README.md)
9. [开发工作日志](docs/worklogs/README.md)

文档信息架构说明见：

- [文档信息架构](docs/documentation_information_architecture.md)

## 4. 环境安装

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

## 5. 快速开始

### 5.1 运行姿态推理

```bash
python scripts/run_pose_infer.py \
  --config configs/infer_pose_stream.yaml \
  --source /path/to/video.mp4 \
  --device 0
```

如需输出与 ROS2 调试图像风格接近的离线 OSD 可视化视频：

```bash
python scripts/run_pose_infer.py \
  --config configs/infer_pose_stream.yaml \
  --source /path/to/video.mp4 \
  --device 0 \
  --save-debug-video
```

常见 `device` 写法：

- `--device 0`
- `--device cuda:0`
- `--device cpu`

### 5.2 ROS2 最小闭环

```bash
cd ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py input_mode:=mock
```

另开终端观察四条 topic：

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /perception/events
ros2 topic echo /system/supervisor/status
ros2 topic echo /task_planner/request
ros2 topic echo /task_planner/status
```

### 5.3 视频文件模式

```bash
source ros2_ws/install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=video_file \
  video_file_path:=/absolute/path/to/demo.mp4
```

### 5.4 电脑摄像头 + ROS2 图像流在线模式

```bash
source ros2_ws/install/setup.bash
ros2 launch yolopose_ros system_stack.launch.py \
  input_mode:=ros_image \
  camera_stream_enabled:=true \
  camera_index:=0 \
  visualization_enabled:=true
```

另开终端观察：

```bash
source ros2_ws/install/setup.bash
ros2 topic echo /camera/image_raw
```

```bash
source ros2_ws/install/setup.bash
rqt_image_view /perception/debug_image
```

## 6. 感知主线

### 6.1 规则法 baseline

核心文件：

- [src/yolopose/pipeline/fall_detector.py](src/yolopose/pipeline/fall_detector.py)
- [src/yolopose/pipeline/runner.py](src/yolopose/pipeline/runner.py)
- [configs/infer_pose_stream.yaml](configs/infer_pose_stream.yaml)

方法：

1. `YOLOPose` 输出人体框和关键点
2. 根据框比例与关键点几何关系做单帧判断
3. 用稳定器输出 `raw_fall_detected / stable_fall_detected`

### 6.2 学习型时序主线

核心文件：

- [src/yolopose/temporal/features.py](src/yolopose/temporal/features.py)
- [src/yolopose/temporal/model.py](src/yolopose/temporal/model.py)
- [src/yolopose/temporal/sequence_fall_detector.py](src/yolopose/temporal/sequence_fall_detector.py)
- [scripts/run_fall_sequence_train.py](scripts/run_fall_sequence_train.py)
- [scripts/build_pose_sequence_dataset.py](scripts/build_pose_sequence_dataset.py)

方法：

1. 提取关键点序列
2. 构建固定长度时序窗口
3. 使用 `LSTM` 或 `TCN` 做跌倒二分类
4. 输出 `seq_raw_fall_detected / seq_stable_fall_detected`

当前建议：

- 默认先以 `LSTM` 作为正式主线
- `TCN` 继续作为低误报对照分支
- 优先补 hard negative 和家居 ADL 误报治理，而不是盲目扩模型族

## 7. 数据、训练与评估

### 7.1 构建 UR Fall 标签

```bash
python scripts/build_urfall_labels.py \
  --falls-csv data/urfall/labels_raw/urfall-cam0-falls.csv \
  --video-dir data/urfall/cam0_mp4 \
  --out data/eval/video_labels_urfall_cam0.csv \
  --include-adl
```

### 7.2 构建姿态序列数据集

```bash
python scripts/build_pose_sequence_dataset.py \
  --labels data/eval/video_labels_urfall_cam0.csv \
  --device 0 \
  --seq-len 32 \
  --stride 4 \
  --output data/processed/urfall_pose_sequences.npz
```

### 7.3 训练时序模型

```bash
python scripts/run_fall_sequence_train.py \
  --config configs/train_fall_sequence.yaml
```

```bash
python scripts/run_fall_sequence_train.py \
  --config configs/train_fall_sequence_tcn.yaml
```

### 7.4 评估模型

规则法：

```bash
python scripts/eval_fall_batch.py \
  --labels data/eval/video_labels_urfall_cam0.csv \
  --config configs/infer_pose_stream.yaml \
  --mode predict \
  --device 0 \
  --out-dir outputs/eval_urfall
```

学习型：

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

更多数据、训练、网格搜索和 hard negative 说明见：

- [data/README.md](data/README.md)
- [docs/fallvision_integration.md](docs/fallvision_integration.md)
- [docs/hard_negative_plan.md](docs/hard_negative_plan.md)

## 8. ROS2 系统主线

`ros2_ws/` 当前只做三件事：

1. 将感知链路封装为 ROS2 节点入口
2. 输出稳定的系统桥接 topic
3. 为后续 `RTAB-Map / Nav2 / PlanSys2 / Gazebo` 预留稳定边界

当前最小消息边界：

- `/perception/events`
- `/system/supervisor/status`
- `/task_planner/request`

当前相关文档：

- [系统架构说明](docs/system_architecture.md)
- [ROS2 骨架说明](docs/system_bringup_skeleton.md)
- [系统接口契约](docs/system_interface_contract.md)
- [ROS2 工作区 README](ros2_ws/README.md)

## 9. 命名与分层规则

统一约定：

- Python 文件：`snake_case.py`
- 配置文件：`snake_case.yaml`
- launch 文件：`snake_case.launch.py`
- ROS2 节点：`snake_case_node.py`
- 工作日志：`docs/worklogs/worklog_YYYY-MM-DD.md`
- 阶段审计：`docs/reviews/<topic>_YYYY-MM-DD.md`
- benchmark 摘要：`reports/benchmarks/<topic>_YYYY-MM-DD.md`
- 历史归档：`docs/archive/<topic>_stageN.md` 或 `docs/archive/<topic>_YYYY-MM-DD.md`

禁止继续把临时审计、工作日志、历史方案平铺在 `docs/` 根目录。

## 10. 提交与清理规则

仓库默认应提交：

- 源码
- 配置文件
- 长期维护文档
- benchmark 摘要
- 小型模板和标签

仓库默认不提交：

- 训练权重
- 自动下载的检测权重
- 本地运行产物
- 大型数据集
- 中间缓存
- IDE 私有目录

维护前建议阅读：

- [项目约定](docs/project_conventions.md)
- [模型目录说明](models/README.md)
- [运行产物目录说明](outputs/README.md)

## 11. 常用维护命令

```bash
bash scripts/clean_outputs.sh
bash scripts/clean_local_artifacts.sh
make help
```

## 12. 下一步重点

当前最应该推进的是三类收口：

1. 保持默认 `LSTM` 主线不变，并将规则法稳定定位为 baseline/debug
2. 在当前 schema v1 基础上继续冻结系统层正式接口，再平滑迁移到 `kaiti_msgs`
3. 用补充数据和 external validation 补齐慢跌倒、家居场景与遮挡场景盲区
