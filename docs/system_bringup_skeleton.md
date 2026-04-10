# ROS2 Skeleton

本文件说明 `ros2_ws/` 里当前已经准备好的系统级骨架，以及下一步如何往 `RTAB-Map`、`Nav2`、`PlanSys2` 对接。

## 1. 目录结构

```text
ros2_ws/
├── README.md
└── src/
    └── yolopose_ros/
        ├── config/
        │   ├── perception_bridge.yaml
        │   └── system_stack.yaml
        ├── launch/
        │   ├── perception_bridge.launch.py
        │   ├── pose_stream.launch.py
        │   └── system_stack.launch.py
        ├── resource/
        ├── yolopose_ros/
        │   ├── pose_stream_node.py
        │   └── system_supervisor_node.py
        ├── package.xml
        ├── setup.py
        └── setup.cfg
```

## 2. 文件职责

### 2.1 `launch/pose_stream.launch.py`

作用：
- 只启动感知桥接节点
- 适合本地调试视频 / RTSP / 摄像头输入

### 2.2 `launch/perception_bridge.launch.py`

作用：
- 和 `pose_stream.launch.py` 对应，但参数来源更适合 ROS2 工作区安装后的调用
- 便于后续被更大的系统级 launch 引入

### 2.3 `launch/system_stack.launch.py`

作用：
- 当前系统级入口
- 同时拉起感知桥接节点和系统监督节点
- 用日志说明 `RTAB-Map`、`Nav2`、`PlanSys2` 的未来挂载点

### 2.4 `config/perception_bridge.yaml`

作用：
- 给感知桥接节点提供参数默认值
- 包含项目根目录、推理配置路径、事件话题

### 2.5 `config/system_stack.yaml`

作用：
- 给系统监督节点提供参数默认值
- 定义感知输入、监督输出、规划请求的 topic 约定

### 2.6 `yolopose_ros/system_supervisor_node.py`

作用：
- 订阅感知事件
- 将事件标准化
- 预留触发规划层的接口

当前它不负责真正规划，只负责把系统边界先打通。

## 3. 当前可执行方式

### 3.1 构建

```bash
cd /home/yhc/kaiti_yolopose_framework/ros2_ws
colcon build --symlink-install --packages-select yolopose_ros
source install/setup.bash
```

### 3.2 只启动感知桥接

```bash
ros2 launch yolopose_ros pose_stream.launch.py
```

### 3.3 启动系统级骨架

```bash
ros2 launch yolopose_ros system_stack.launch.py
```

## 4. 当前消息流

当前系统骨架中，消息流建议按如下方式理解：

```text
camera / video / rtsp
        ↓
pose_stream_node
        ↓  /kaiti/perception/events
system_supervisor_node
        ↓  /kaiti/task_planner/request
planner layer (future)
        ↓
nav2 / rtabmap / task execution
```

## 5. 命名规则

建议统一使用以下规则：

- ROS2 包名：`snake_case`
- launch 文件：`snake_case.launch.py`
- config 文件：`snake_case.yaml`
- 节点名：`snake_case`
- topic：`/kaiti/<layer>/<name>`

推荐命名示例：
- `pose_stream_node`
- `system_supervisor_node`
- `/kaiti/perception/events`
- `/kaiti/system/supervisor/status`
- `/kaiti/task_planner/request`

## 6. 当前已实现与下一阶段

### 6.1 当前已实现

- 感知桥接包 `yolopose_ros`
- 只启动感知的本地 launch
- 系统级 skeleton launch
- 系统监督占位节点
- 参数化 YAML 配置

### 6.2 下一阶段

- 把感知事件从 `std_msgs/String` 逐步升级成结构化消息
- 引入 `RTAB-Map`
- 引入 `Nav2`
- 引入 `PlanSys2` 或同类规划层
- 用真实任务流替代当前日志占位

## 7. 说明

这个骨架的目标不是一次性把所有模块都接完，而是先把工程边界和启动入口固定下来，避免后续把感知、建图、规划混成一个难以维护的文件堆。
