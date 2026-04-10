# Data Directory

本目录只保留可提交的小型文件和模板。

长期保留：
- [eval/](eval/)：标签模板、评估 CSV、网格搜索配置
- [streams/](streams/)：流地址模板
- `samples/.gitkeep`：示例目录占位

本地生成但默认不提交：
- `processed/`：处理后的 `.npz` 数据集
- `urfall/`：已下载的 UR Fall 原始视频与标签
- `Fall Detection Video Dataset/`：已下载并解压的 FallVision CSV / 视频
- `samples/*.mp4`：本地测试视频

如果要在新电脑上复现：
1. 先下载公开数据集
2. 再运行相应的数据构建脚本，例如 `build_pose_sequence_dataset.py` 或 `build_fallvision_sequence_dataset.py`
