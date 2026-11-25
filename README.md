# kaiti-yolopose-framework

本项目当前服务于硕士论文《动态环境下融合语义感知的多智能体协同规划研究》。研究主线固定为：

1. 动态环境下的语义事件感知；
2. 面向动态事件的机器人任务生成；
3. 动态任务环境下的多智能体协同规划。

论文核心是第三项。第一项提供可靠事件信息，第二项将事件转换为带空间目标和依赖的可执行任务。统一闭环为“动态事件感知 → 语义事件向可执行任务转换 → 多智能体协同规划 → 执行反馈与动态协调”。当前研究边界、实现对应关系、保留成果和后续验收以[研究范围收口与完成计划](docs/research_scope_and_completion_plan.md)为准。

当前优先配对实验见[Clinic优先级配对实验](reports/benchmarks/clinic_priority_paired_experiments_2026-11-25.md)。当前Clinic阶段成果和边界见[研究范围与实验目录](docs/clinic_current_research_scope.md)及[Clinic研究实验与任务规划说明](docs/clinic_research_experiment_guide.md)。实际 Clinic 工作区为 `/home/yhc/clinic_planning_ws`；仓库内 `experiments/clinic` 是上传用源码快照，不是实际运行工作区。

近期证据包括真实UR Fall视频经YOLO Pose/LSTM产生候选并进入A区三机核验/应急执行，以及独立离线的动态任务分配、多事件能力和局部修复分析。这些结果分别支持有限功能闭环或离线能力，不代表泛化性能、全面性能优势或三项研究全部完成。Fast/Standard功能验收通过，但时间目标未达；局部修复只有条件性证据。

此前的家居场景毕业方案和医院公共空间双机器人V3计划保留作历史版本，不是当前执行路线；不据其旧S0/S1状态推断当前Clinic进度。

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

- `YOLOPose + LSTM` 已形成可训练、可推理、可评估、可调参的感知闭环；该项模型指标来自相应原评估划分，不等于Clinic外部泛化
- `ROS2` 已经打通最小闭环：`/perception/events -> /system/supervisor/status -> /task_planner/request -> /task_planner/status`
- topic 仍使用 `std_msgs/msg/String + JSON`，但接口语义已经收敛为稳定 schema v1
- 已报告的 UR Fall 默认学习型模型结果：`Precision=0.8657`、`Recall=0.7401`、`F1=0.7979`（对应原评估划分，不代表Clinic独立外部测试）
- 当前三项研究内容、Clinic证据层级和执行边界以[当前研究范围](docs/clinic_current_research_scope.md)为准；历史公共空间V3与house方案不再作为当前路线

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
├── experiments/clinic_*/        # Clinic独立离线研究和证据适配入口
├── ros2_ws/                    # ROS2 工作区与系统骨架
├── scripts/                    # 入口脚本
├── src/yolopose/               # 人体姿态/时序感知源码
├── src/kaiti_task_sim/         # 事件协议、Clinic任务编译与分配模型
├── src/kaiti_review/           # 只读实验解释工作台适配器
├── web/clinic/                 # Clinic实验展示前端
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

1. [当前研究范围与证据边界](docs/clinic_current_research_scope.md)
2. [Clinic研究实验目录与任务规划说明](docs/clinic_research_experiment_guide.md)
3. [项目约定](docs/project_conventions.md)
4. [开题目标对齐](docs/kaiti_alignment.md)
5. [系统架构说明](docs/system_architecture.md)
6. [ROS2 最小骨架说明](docs/system_bringup_skeleton.md)
7. [系统接口契约](docs/system_interface_contract.md)
8. [数据集定位与外部验证策略](docs/dataset_positioning.md)
9. [ROS2 工作区说明](ros2_ws/README.md)
10. [阶段审计与汇总](docs/reviews/README.md)
11. [开发工作日志](docs/worklogs/README.md)

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

`ros2_ws/` 是通用感知/系统骨架，保留 mock、视频文件和ROS图像输入。它与 Clinic 三机 Nav2 执行不是同一个运行入口；Clinic真视频实验通过独立脚本回放并桥接到任务层。不要根据 skeleton topic 连通推断完整研究闭环。

通用骨架负责：

1. 将感知链路封装为 ROS2 节点入口
2. 输出稳定的系统桥接 topic
3. 维护可复用的感知消息与模块接口

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

## 12. 当前研究推进重点

优先完成 A 区角色和并发资格，验证动态事件插入后多机在异步反馈、任务依赖和资源竞争下的分工与执行。感知与任务生成同步补齐遮挡对照、空间目标、依赖释放和可达性检查。最小 RGB-D 代表位置在任务空间接口验收。参见[技术路线](docs/method_roadmap.md)与[后续实验](docs/research_scope_and_completion_plan.md#后续开发与验收)。
