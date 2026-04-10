# Models Directory

本目录用于本地模型管理，仓库中默认只保留说明文件和目录占位。

## 1. 应放在本地但不提交的内容

- 训练权重，如 `*.pt`
- 历史指标，如 `*.history.json`
- 自动下载的预训练检测权重

## 2. 仓库内长期保留的内容

- `README.md`
- `.gitkeep`

## 3. 使用约定

- 当前默认推理模型由 [configs/infer_pose_stream.yaml](../configs/infer_pose_stream.yaml) 指定
- 如果切换默认模型，应同步更新配置、README 和 benchmark 摘要
- 模型结论应写入 `reports/benchmarks/`，不要只留在权重文件名里
