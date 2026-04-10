# Data Directory

本目录只保留可提交的小型文件、标签模板和说明文件，不作为原始数据仓库。

## 1. 目录职责

- `eval/`：标签模板、轻量评估 CSV、网格搜索配置
- `streams/`：流地址模板
- `samples/`：目录占位，不长期存放视频

## 2. 本地生成但默认不提交

- `processed/`：处理后的 `.npz` 数据集
- `urfall/`：已下载的 UR Fall 原始视频与标签
- `Fall Detection Video Dataset/`：FallVision 原始 CSV / 视频
- `samples/*.mp4`：本地测试视频

## 3. 放置规则

应提交：

- 标签模板
- 轻量 CSV
- 配置模板
- 必要说明文件

不应提交：

- 原始视频
- 大体积 `.npz`
- 临时样本视频
- 临时脚本输出

## 4. 新机器复现

1. 先下载公开数据集
2. 再运行相应的数据构建脚本
3. 最后把关键实验结论整理到 `reports/benchmarks/`

相关脚本通常位于：

- `scripts/build_*.py`
