# ROS2 Workspace

这个目录是系统层骨架，当前只包含 `yolopose_ros` 一个最小包。

## 1. 结构

```text
ros2_ws/
└── src/yolopose_ros/
    ├── launch/
    ├── config/
    ├── resource/
    └── yolopose_ros/
```

## 2. 当前职责

当前这个 workspace 只做两件事：

1. 把当前感知管线封装成 ROS2 节点入口
2. 为后续的 `RTAB-Map`、`Nav2`、`PlanSys2` 提供系统级骨架

## 3. 启动顺序

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
ros2 launch yolopose_ros pose_stream.launch.py
```

系统级骨架入口：

```bash
ros2 launch yolopose_ros system_stack.launch.py
```

## 4. 环境变量

建议设置：

```bash
export KAITI_PROJECT_ROOT=/home/yhc/kaiti_yolopose_framework
```

这样 launch 文件和节点脚本都可以从环境变量读取项目根目录，而不是把绝对路径写死在配置里。

## 5. 命名规则

- launch 文件统一使用 `snake_case.launch.py`
- YAML 配置统一使用 `snake_case.yaml`
- 节点统一使用 `snake_case_node.py`
- topic 建议统一以 `/kaiti/` 作为前缀

## 6. 下一阶段

后续这里会继续扩展：
- 传感器/建图节点
- 导航节点
- 任务规划节点
- 监督与恢复节点
