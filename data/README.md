# Data Directory

本目录只保留可提交的小型文件：
- `eval/`：标签模板、评估 CSV、网格搜索配置
- `streams/`：流地址模板
- `samples/.gitkeep`：示例目录占位

本目录不建议提交：
- `processed/`：处理后的 `npz` 数据集
- `urfall/`：已下载的 UR Fall 原始视频与标签
- `samples/*.mp4`：本地测试视频

如果你要在新电脑上复现：
1. 先下载公开数据集
2. 再运行 `build_pose_sequence_dataset.py` 构建处理后数据
