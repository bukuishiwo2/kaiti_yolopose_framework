# Models Directory

本目录用于存放本地模型文件，但默认不提交训练产物。

推荐约定：
- 预训练权重：本地自动下载或手动放入，不提交
- 训练产物：如 `fall_sequence_lstm.pt`、`fall_sequence_lstm_fallvision.pt`，本地保留，不提交
- 历史指标：如 `*.history.json`，本地保留，不提交
- 仓库中只保留说明文件或 `.gitkeep`

当前默认推理模型由 [configs/infer_pose_stream.yaml](../configs/infer_pose_stream.yaml) 指定。
