# Project Conventions

## 1. Scope

本仓库是长期维护的研究型工程项目，不是一次性实验目录。

仓库长期保留：

- 可复用源码
- 手工维护配置
- 说明文档
- 标签模板
- benchmark 摘要
- 必要的目录占位文件

仓库默认不提交：

- 本地虚拟环境
- 下载的视频数据
- 训练权重
- 自动生成的缓存
- 运行产物
- IDE 私有配置

## 2. Naming Rules

### 2.1 Python 文件

统一使用 `snake_case.py`。

示例：

- `run_pose_infer.py`
- `build_pose_sequence_dataset.py`
- `sequence_fall_detector.py`

### 2.2 配置文件

统一使用 `snake_case.yaml`。

推荐前缀：

- 推理配置：`infer_*.yaml`
- 训练配置：`train_*.yaml`
- 导出配置：`export_*.yaml`
- 网格搜索配置：`fall_grid_*.yaml` 或 `*_grid*.yaml`

### 2.3 ROS2 文件

- launch 文件：`snake_case.launch.py`
- 节点文件：`snake_case_node.py`
- ROS2 topic：`/kaiti/<layer>/<name>`

### 2.4 文档文件

统一规则：

- 根目录或稳定说明文档：优先无日期
- 工作日志：`docs/worklogs/worklog_YYYY-MM-DD.md`
- 阶段审计：`docs/reviews/<topic>_audit_YYYY-MM-DD.md`
- 阶段汇总：`docs/reviews/<topic>_summary_YYYY-MM-DD.md`
- benchmark 摘要：`reports/benchmarks/<topic>_YYYY-MM-DD.md`
- 历史归档：`docs/archive/<topic>_stageN.md` 或 `docs/archive/<topic>_YYYY-MM-DD.md`

当前像 `system_interface_contract_2026-04-10.md` 这类文件，属于“冻结草案快照”。后续如果契约稳定，应升格为无日期的稳定文件名。

### 2.5 目录命名

统一使用小写目录名；必要时使用下划线，不使用空格。

## 3. Directory Rules

### 3.1 `src/`

只放可复用源码。

当前模块划分：

- `src/yolopose/core/`：配置解析与通用工具
- `src/yolopose/pipeline/`：姿态推理与规则法跌倒检测
- `src/yolopose/temporal/`：学习型时序模型与在线检测

### 3.2 `scripts/`

只放入口脚本。

推荐命名：

- `run_*.py`：运行、训练、导出
- `build_*.py`：构建标签或数据集
- `download_*.sh`：下载公开资源
- `clean_*.sh`：清理本地产物

### 3.3 `configs/`

只放手工维护配置，不放运行时自动生成配置。

### 3.4 `data/`

仓库中只保留：

- 标签模板
- 轻量 CSV
- 流地址模板
- 目录说明文件

本地保留但默认不提交：

- 原始视频
- 已下载数据集
- 处理后的大型 `npz`
- 临时样例视频

### 3.5 `models/`

本目录用于本地模型管理。

仓库中只保留：

- `README.md`
- `.gitkeep`

不提交：

- 训练权重 `.pt`
- 历史指标 `.json`
- 自动下载的预训练权重

### 3.6 `outputs/`

本目录是运行目录，不作为正式版本内容。

长期需要保留的结果，应整理为 Markdown 摘要并放入：

- `reports/benchmarks/`

### 3.7 `reports/`

只保留适合长期提交的结果归档：

- benchmark 摘要
- 阶段结论
- 对比分析说明

### 3.8 `docs/`

`docs/` 必须分层使用：

- `docs/` 根目录：长期稳定说明文档
- `docs/reviews/`：阶段审计、接口评审、架构汇总
- `docs/worklogs/`：按日期记录的开发过程
- `docs/archive/`：被替代但仍需保留的历史文档

根目录 `docs/` 不再接受：

- `worklog_*.md`
- `*_audit_*.md`
- `*_summary_*.md`
- 已过时的旧架构稿

## 4. Git Tracking Rules

`.gitignore` 应覆盖：

- `.venv/`
- `.idea/` 和 `.vscode/`
- `__pycache__/`
- `data/processed/`
- `data/urfall/`
- `data/Fall Detection Video Dataset/`
- `data/samples/*.mp4`
- `models/*.pt`
- `models/*.json`
- `outputs/*`
- `ros2_ws/build/`
- `ros2_ws/install/`
- `ros2_ws/log/`
- 根目录和 `ros2_ws/` 下自动下载的 `*.pt`
- 各类日志文件

提交前建议执行：

```bash
bash scripts/clean_local_artifacts.sh
```

## 5. Documentation Rules

### 5.1 根 README

根 README 应只保留：

- 项目定位
- 当前状态与关键结论
- 仓库结构
- 文档导航
- 安装方法
- 快速开始
- 感知与系统主线概览
- 训练、评估与维护入口
- 提交与清理规则

### 5.2 `docs/`

详细说明统一放入 `docs/` 子树。

当前稳定核心文档包括：

- `docs/project_conventions.md`
- `docs/agents.md`
- `docs/kaiti_alignment.md`
- `docs/system_architecture.md`
- `docs/system_bringup_skeleton.md`

### 5.3 `reports/`

关键实验结论不应只保留在 `csv/json` 中。

应整理为 Markdown 摘要，长期提交到：

- `reports/benchmarks/`

### 5.4 Markdown Links

仓库内文档必须优先使用相对路径链接，例如：

- `docs/project_conventions.md`
- `../README.md`
- `../reports/benchmarks/urfall_comparison_2026-04-09.md`

不要在仓库文档中使用宿主机绝对路径，例如：

- `/home/yhc/...`
- `C:\\Users\\...`

## 6. Collaboration Rules

项目级多代理规则以仓库根目录的 [AGENTS.md](../AGENTS.md) 为准。

长期角色：

- `architect`
- `perception`
- `system_planner`

执行原则：

1. 先定义写入范围，再开子代理
2. 不同代理默认不要并行修改同一文件
3. 任何实验结论必须落到 `reports/benchmarks/` 或 `docs/worklogs/`
4. 默认配置切换由 `architect` 收口
5. 接口设计和 ROS2 文档由 `system_planner` 收口

## 7. Recommended Workflow

1. 创建虚拟环境并安装依赖
2. 执行 `pip install -e . --no-deps`
3. 使用 `scripts/` 中的入口完成训练、推理和评估
4. 将关键结论整理到 `reports/benchmarks/`
5. 将过程记录整理到 `docs/worklogs/`
6. 提交代码、配置、文档和摘要，不提交本地产物

## 8. Publishing Checklist

准备上传前，检查：

1. `README.md` 是否反映当前主线和最新状态
2. `docs/README.md` 是否仍能正确导航
3. `reports/benchmarks/` 是否已有关键结果摘要
4. `docs/reviews/` 中是否有阶段审计或接口汇总
5. 本地数据、权重、输出目录是否已被忽略或清理
6. `configs/` 是否保留当前可复现实验配置
7. `docs/worklogs/` 是否记录最近阶段工作
