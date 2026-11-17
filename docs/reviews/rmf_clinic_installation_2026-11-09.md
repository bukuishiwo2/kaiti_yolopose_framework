# Open-RMF Clinic humble：下载、构建与本机启动验收

日期：2026-11-09。目标：安装可用于后续算法仿真验证的Clinic场景，处理本机空间问题，保持当前论文规划主链与资产不变。

## 实际结果

**独立工作区已下载、构建并通过无界面运行检查。**

后续GUI问题与修复见[同日启动诊断](rmf_clinic_gui_startup_diagnosis_2026-11-09.md)：原组合启动出现服务端与GUI等待，已改为独立服务端加服务就绪后启动GUI，并查看到真实Clinic画面。下文“尚未GUI验收”描述的是初次安装验收时的边界。

- 工作区：`/home/yhc/rmf_clinic_ws`。
- 上游：[open-rmf/rmf_demos，humble分支](https://github.com/open-rmf/rmf_demos/tree/humble)，commit `d79ac6f03baeedbf8ee572347428b4a817098446`，演示包版本2.0.4。
- 采用官方推荐的“RMF核心二进制依赖＋演示源码构建”方式；本机Ubuntu22.04、ROS2 Humble、Ignition Gazebo Fortress6.18.0。没有切换ROS版本、替换现有工作区或修改shell启动文件。
- 9个非Classic演示包构建成功，实际构建19.4秒；排除`rmf_demos_gz_classic`。地图生成含各演示world/navgraph，但只补充Clinic需要的外部素材。
- Clinic34个外部模型全部可用，其中3个复用已有Fuel缓存；38种model URI均可解析，无缺失，world含712处include。生成模型、外部素材和两种机器人均由本机资源路径找到。
- ROS依赖检查为`All system dependencies have been satisfied`，Python运行依赖导入通过。
- 源码**已跟踪文件没有修改**；运行时在两个上游Python包生成未跟踪`__pycache__`，不把它误判为代码补丁。自定义入口/工具放在工作区源码目录之外。

完整机器可读结果：[installation_result.json](/home/yhc/rmf_clinic_ws/verification/installation_result.json)。上游commit、依赖版本、模型清单、构建与启动日志均保存在工作区。

## 磁盘处理与安装依赖

初始根分区可用约38GB，`/home`仅约4.6GB。先用pip缓存工具清理，旧pip未覆盖http-v2缓存，再用项目已有新版pip的`cache purge`清理**3360.5MB HTTP下载缓存**。没有更新项目虚拟环境包，也没有删除数据集、模型、旧outputs、Fuel模型、其他工作区或驱动。

结束时`/home`约7.7GB可用，根分区约38GB可用。独立工作区约76MB；模型由`clinic_models/`符号链接复用`~/.ignition/fuel`，不再完整复制素材。这个Fuel缓存现在包含安装所需资源，不能当作无用缓存随意清空。

安装了`ros-humble-rmf-dev`、`python3-vcstool`、`python3-colcon-mixin`及其依赖，并补充Flask/CORS/SocketIO、paho-mqtt、FastAPI、Uvicorn。确切版本见[installed_packages.tsv](/home/yhc/rmf_clinic_ws/verification/installed_packages.tsv)。没有执行apt autoremove或删除旧NVIDIA/系统包。授权凭据没有写入脚本或文档。

官方模型下载器在遍历Fuel全局索引时发生TLS连接中断；独立下载工具直接按34个模型URL下载，最多3次尝试、每次150秒上限，并复用现有缓存。未禁用TLS检查，未修改`/opt/ros`中的工具实现。

## 运行检查及其边界

所有运行使用独立本机`ROS_DOMAIN_ID=73`、`ROS_LOCALHOST_ONLY=1`、`IGN_PARTITION=rmf_clinic_yhc`，没有连接实车或接管实际机器人。

| 检查 | 实际结果 |
|---|---|
| Clinic无界面world加载 | PASS，服务`/world/sim_world/...`及场景描述可查询 |
| 仅场景入口 | PASS，含building_map_server与clock桥；4秒探针收到402个clock样本，推进4.01仿真秒，4台robot_state均有合法楼层 |
| 完整RMF演示入口 | PASS，deliveryRobot与tinyRobot两支车队共4台机器人注册并发布fleet状态 |
| 稳态探针 | 15.016墙钟秒内1396个clock样本，推进13.95仿真秒，4台机器人状态有效 |
| 原生巡逻运动探针 | 原生任务请求被接受；25.014墙钟秒采样中推进24.85仿真秒，2486个clock样本，deliveryRobot_1实际位移累计3.044m |
| 目标返回检查 | 最后采样deliveryRobot_1位于L1 `(8.0071,-31.7342)`，task_id为空、mode为idle，与回程目标一致 |
| 论文规划链保护 | 78个既有规划/ROS/相关配置及旧验证脚本哈希前后相同 |

两次原生巡逻请求分别去往/返回`L1_sub_waiting_area_1`与`L1_left_negative_air_pressure`。这是**RMF原生演示任务与运动的安装冒烟测试**，不将其称为本文规划算法性能或形式化全任务验收。

原始证据位于[verification目录](/home/yhc/rmf_clinic_ws/verification)：`runtime_probe.json`、`motion_probe.json`、`final_demo_probe.json`、`world_only_probe.json`、`patrol_request.log`、`patrol_return_request.log`、`clinic_scene.pbtxt`、`asset_uri_audit.json`和各启动日志。

观察到的问题已保留：

- 第一次仅world试启动未运行building_map_server，原生slotcar无法标定楼层。独立入口已补map server，并重新验证通过；没有改上游launch。
- 完整demo有一次tinyRobot位置查询瞬时失败，后续4机器人采样恢复正常；不声称已完成长时间稳定性验证。
- 完整demo退出时部分上游fleet adapter未在SIGINT/SIGTERM后及时退出，ROS launch最终对其升级SIGKILL。本次所有测试进程最终已停止；运行日志保留该行为，不能写成优雅退出全部通过。
- 尚未进行GUI画面的人工验收，本轮运行证据来自headless、ROS状态与Gazebo服务；不提供未经查看的“渲染正常”结论。

初次测试在论文仓库当前目录生成了一份RMF schedule运行文件，停止该次测试后移入工作区verification保存；入口已改为先切到独立工作区，后续运行数据不落在论文仓库根目录。

## 两个独立启动入口

日常查看/作为后续自有算法的场景基础：

```bash
cd /home/yhc/rmf_clinic_ws
./run_clinic.sh world
```

仅启动医院world、原生场景中的机器人、building map与clock桥，不启动RMF分配器/车队适配器。加`--headless`可无界面运行。

原生RMF完整演示（无legacy Web panel，GUI模式还会启动RViz）：

```bash
cd /home/yhc/rmf_clinic_ws
./run_clinic.sh demo
```

同一partition内先Ctrl-C结束一种模式，再启动另一种；完整demo退出可能需要等待launch终止其子进程。未设置开机自启或常驻服务，本轮结束时没有遗留本次场景进程。

原生巡逻命令、重构建与资源恢复步骤见[工作区README](/home/yhc/rmf_clinic_ws/README_CLINIC.md)。运行其他观察命令时需在对应终端设置相同ROS域。

## 与后续论文算法的关系

Clinic当前保留L1/L2两层和原生4台机器人，尚未裁剪成单层。原生机器人主要使用RMF slotcar运动插件，不等于已配置Nav2、激光/相机/TF闭环。仅场景入口只是避免原生调度器介入，没有自动换成论文的机器人模型。

下一步应在独立场景入口中选择L1实验区域，接入具备相应传感器/TF/Nav2的机器人与命名空间，将[event-task/v1](../event_task_protocol.md)脚本事件和论文MILP接入，保留同目标的全量/局部/保留策略对照。采用原生RMF调度或交通协调时须明确它负责什么，不能把它的收益算作论文方法。

本轮是环境准备与可运行性验证，不修改现有规划主链，不新增跌倒动画、算法对照或实车结果。

## 变更文件与结构性结论

独立工作区新增：`src/rmf_demos/`、`build/install/log/`、`clinic_models/`、`run_clinic.sh`、`launch/clinic.launch.py`、`tools/fetch_clinic_models.py`、`tools/observe_clinic.py`、`README_CLINIC.md`与`verification/`。

论文仓库只新增本安装评审并更新文档索引/研究计划的环境状态入口；没有修改模型、现有源码或规划参数。结论是Clinic基础环境可用于下一步独立算法接入；GUI、长期稳定性、真实Nav2避障与本文任务闭环仍需各自验证。
