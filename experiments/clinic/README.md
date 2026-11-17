# Clinic独立实验源码快照

这是2026-11-17从独立工作区整理的源码及必要导航配置，不是完整运行目录，也不是新规划主链。

- 当前入口：[clinic_experiment.sh](clinic_experiment.sh)。三模式说明见[README_CLINIC_MODES.md](README_CLINIC_MODES.md)。
- 包含统一执行器、独立MILP适配、离线验证工具、必要地图/碰撞栅格、官方TB4展开配置与实验测试；具体来源、大小和SHA256见[source_inventory.json](source_inventory.json)。
- 未包含`runs/`、原始`verification/`、视频、NPZ、CBC日志、缓存、第三方Python依赖或Gazebo模型资产。`verification/hospital_semantics/`仅保留启动必需的地图配置及栅格，作为实验输入，不是审计输出归档。
- 地图、模型与Nav2依赖沿用Open-RMF Clinic Humble、TurtleBot4、ROS2 Humble/Nav2及ros_gz；第三方资产和依赖应通过各自上游获取并遵守原许可。该快照不改变其许可归属。

## 路径与复现边界

为保持与已验收源一致，导出文件没有重写原绝对路径。已验收的工作区是`/home/yhc/clinic_planning_ws`，项目依赖位于`/home/yhc/kaiti_yolopose_framework`；仅克隆仓库不能自动满足ROS、地图资产、环境和历史数据依赖。其他机器部署前须人工核对路径和上游依赖，随后执行静态检查、短集成和离线门禁，不能跳过安全校验。

`source_inventory.json`是导出清单，不应直接代替原运行的source_manifest。原始实验证据仍保存在本机原目录，历史审计/部分回归及模式离线门禁需要这些数据。`benchmark_sparse_repair.py`可通过`--source`显式指定实际修复快照；仓库没有伪造或打包原始运行记录。

Benchmark保持冻结条件。Fast/Standard均完成闭环，但分别901.92/1243.46仿真秒，未达到300～500/600～850目标。不能将不同模式与旧Benchmark直接作为同口径算法性能比较。

实验结论见[近期完整报告](../../reports/benchmarks/clinic_sparse_repair_and_modes_2026-11-17.md)。报告内本机绝对路径指向未上传的原始证据，GitHub无法在线打开，这些链接不代表缺失的源码依赖。

## 上游

- [Open-RMF rmf_demos / Humble Clinic](https://github.com/open-rmf/rmf_demos/tree/humble)
- [TurtleBot4 Simulator](https://github.com/turtlebot/turtlebot4_simulator)
- [Nav2 Humble](https://github.com/ros-navigation/navigation2/tree/humble)
- [ros_gz Humble](https://github.com/gazebosim/ros_gz/tree/humble)

仓库默认pytest只发现根`tests/`；归档中的Clinic验收需显式指定文件，避免在缺少ROS/历史记录的环境自动运行。轻量模式测试可执行：`.venv/bin/python -m pytest -q experiments/clinic/tests/test_experiment_modes.py`。
