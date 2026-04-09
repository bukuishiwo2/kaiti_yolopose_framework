# Project Conventions

## 1. Scope

本仓库是长期维护的研究型工程项目，不是单次实验目录。

仓库应长期保留：
- 源代码
- 配置文件
- 说明文档
- 标签模板
- benchmark 摘要
- 小型目录占位文件

仓库默认不提交：
- 本地虚拟环境
- 下载的视频数据
- 模型权重
- 自动生成的中间缓存
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

命名约定：
- 推理配置：`infer_*.yaml`
- 训练配置：`train_*.yaml`
- 导出配置：`export_*.yaml`
- 网格搜索配置：`*_grid*.yaml` 或 `fall_grid_*.yaml`

### 2.3 文档文件

- 工作记录：`worklog_YYYY-MM-DD.md`
- benchmark 摘要：`topic_YYYY-MM-DD.md`
- 目录说明：使用 `README.md`

### 2.4 目录命名

统一使用小写目录名；必要时使用下划线，不使用空格。

## 3. Directory Rules

### 3.1 `src/`

只放可复用源码。

当前模块划分：
- `src/yolopose/core/`：配置解析与通用工具
- `src/yolopose/pipeline/`：姿态推理与规则法跌倒检测
- `src/yolopose/temporal/`：学习型时序模型与在线检测器

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
- 公开数据集转换后的轻量 CSV
- 流地址模板
- 目录说明文件

本地保留但不提交：
- 原始视频
- 已下载数据集
- 处理后的大型 `npz`

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

## 4. Git Tracking Rules

`.gitignore` 应覆盖：
- `.venv/`
- `.idea/` 和 `.vscode/`
- `__pycache__/`
- `data/processed/`
- `data/urfall/`
- `data/samples/*.mp4`
- `models/*.pt`
- `models/*.json`
- `outputs/*`
- 根目录自动下载的 `*.pt`
- 各类日志文件

提交前建议执行：

```bash
bash scripts/clean_local_artifacts.sh
```

## 5. Documentation Rules

### 5.1 `README.md`

根 README 只保留这些内容：
- 项目定位
- 当前状态与关键结论
- 仓库结构
- 安装方法
- 快速开始
- 两条算法路线说明
- 数据准备、训练与评估流程
- GitHub 提交策略
- 常用维护命令

### 5.2 `docs/`

详细说明放入 `docs/`：
- `architecture.md`
- `project_conventions.md`
- `inference_resources.md`
- `references.md`
- `worklog_*.md`

### 5.3 `reports/`

关键实验结论不应只保留在 `csv/json` 中。

应整理为 Markdown 摘要，长期提交到：
- `reports/benchmarks/`

## 6. Recommended Workflow

1. 创建虚拟环境并安装依赖
2. 执行 `pip install -e . --no-deps`
3. 使用 `scripts/` 中的入口完成训练、推理和评估
4. 将关键结论整理到 `reports/benchmarks/`
5. 提交代码、配置、文档和摘要，不提交本地产物

## 7. Publishing Checklist

准备上传 GitHub 前，检查：

1. `README.md` 是否反映当前主线和最新结果
2. `reports/benchmarks/` 是否已有关键结果摘要
3. 本地数据、权重、输出目录是否已被忽略或清理
4. `configs/` 是否保留当前可复现实验配置
5. `docs/worklog_*.md` 是否记录最近阶段工作
