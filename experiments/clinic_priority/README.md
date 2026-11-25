# Clinic 优先级配对实验

本实验对应当前论文主线的三个优先问题。

1. 常态任务执行中插入一个应急事件。
2. 固定地图位置和机器人状态，只改变事件语义状态。
3. 在真实 YOLO Pose + LSTM 日志上回放短时缺失、持续低质量和恢复观测。

入口脚本为 `run.py`。它只读取已保存的 Clinic 工作区快照和真实模型因果日志，不启动 ROS/Gazebo，不派发任务，不修改原始运行证据。

```bash
.venv/bin/python experiments/clinic_priority/run.py \
  --out /home/yhc/clinic_planning_ws/verification/priority_NEW
```

输出目录必须不存在。正式结果保存在 Clinic 实际工作区，因为其中包含求解器日志、问题快照和哈希协议。脚本输出 `protocol.json`、`planning.csv`、`quality.json`、`semantic/` 和每个方法的独立求解证据。

方法含义：

- `B1`：最早可服务插入，保持常态任务原有归属和顺序。
- `retime`：固定应急角色和常态归属，保留常态任务相对顺序，允许选择插入位置和时间。
- `fixed_owner`：固定应急角色和常态归属，允许后缀重排与调时。
- `local_owner`：开放应急角色和原归属失效任务的合法归属。其余常态任务保持原归属，后缀仍可调整时间与顺序。
- `impact_closure`：按依赖、机器人序列和资源传播释放完整影响闭包。
- `full`：开放全部合法后缀归属和时间。

`local_owner` 与 `impact_closure` 分开报告。不能把完整影响闭包称为最小局部修复。

所有结果均为离线模型或协议回放证据。`execution_authorized=false`，不能直接作为新的实体派发计划。
