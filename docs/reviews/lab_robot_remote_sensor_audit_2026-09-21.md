# Lab Robot 远程传感器与三维定位条件审计

日期：2026-09-21  
目标：`kybot.local / 192.168.124.49`  
方式：SSH 实机枚举、ROS1 临时单组件/整机启动、数据流与 TF 检查。结束后已停止临时节点并退出 SSH，未修改小车配置。

## 1. 总结论

小车的 **Orbbec Astra Pro RGB-D 相机能够实时输出 RGB、毫米深度图和 XYZ/XYZRGB 点云，硬件上支持把人体二维关键点反投影到相机三维坐标系**，可作为“视觉语义 → 三维事件 → 任务分配与规划”的实验平台。

但当前还不能给出论文级可信的“倒地人体各部位在 `map` 坐标系中的三维落点”，主要阻断项为：

1. 当前相机序列号对应的 RGB/深度标定文件缺失，`CameraInfo` 无消息；
2. depth-to-color 外参为 `NaN`，运行 TF 却将二者设成单位变换，不能视为已完成 RGB-D 配准；
3. `base_link` 与 `camera_link` 是断开的 TF 树，历史安装外参还互相冲突；
4. 本次仅运行 `odom` 级 EKF，没有 `map_server + AMCL` 或 RTAB-Map，因而没有 `map -> odom`；
5. 仓库尚缺由二维人体关键点、深度和 TF 生成带有效性/协方差的 `PoseObservation3D` 节点；
6. 小车是 ROS1 Melodic，研究系统主线是 ROS2，需要桥接或分机部署方案。

| 能力 | 状态 | 说明 |
|---|---|---|
| RGB 与深度取流 | PASS | 均为 640×480，约 30 Hz |
| 相机系稠密点云 | PASS | XYZ 和 XYZRGB 点云可用 |
| 二维关键点反投影到相机系 | CONDITIONAL | 必须先恢复可信内参及 D2C 标定 |
| 人体各部位相对小车坐标 | FAIL | `base_link -> camera_link` 断链且外参冲突 |
| 人体各部位地图落点 | FAIL | 无完整 TF 链，无在线地图定位 |
| 已完成标定 | FAIL | 序列号标定文件缺失，外参返回 NaN |
| 可直接驱动多机器人规划 | FAIL | 缺三维事件接口、质量门控和 ROS1/ROS2 接口 |

## 2. 实机环境

- Ubuntu 18.04.6 LTS，x86_64，ROS Melodic；Catkin 工作空间 `/home/kybot/robot_ws`；
- 内存 7.7 GiB，本次可用约 6.1 GiB；无 NVIDIA GPU；
- `.bashrc` 设置 `ROS_MASTER_URI=http://localhost:11311`、`ROS_HOSTNAME=localhost`，外部主机不能按常规 ROS1 网络方式直接订阅；
- 未发现 ROS2 环境。

无独立 GPU 意味着轻量 YOLO Pose 仍需实测帧率。更稳妥的初期架构是小车负责传感器与导航，工作站负责人体姿态/时序推理，再回传语义事件。

## 3. 已确认传感器

| 设备 | 实机身份与运行验证 | 用途/状态 |
|---|---|---|
| RGB-D 相机 | Orbbec Astra Pro；深度 `2bc5:0403`、UVC RGB `2bc5:0501`；序列号 `17122222203`；固件 `RD108C-009`；RGB、depth、点云均成功 | 三维人体定位核心 |
| 2D 激光雷达 | `lslidar_x10_driver` 配置为 `N10`；USB `1a86:55d4`，`/dev/ls_lidar`；`/scan` 约 10 Hz、501 点、360° | 建图、定位、避障 |
| 底盘/编码器 | USB `1a86:7523`，`/dev/kybot`，230400 baud；`/raw_odom` 可用 | 里程计 |
| IMU | `/imu/onboard_imu` 约 100 Hz；Madgwick 输出 `/imu/data`；启动做 300 样本陀螺零偏校准 | EKF 姿态 |
| 四麦阵列 | SEEED ReSpeaker 4 Mic Array，`2886:0018` | 已枚举，非核心 |
| 超声波 | URDF 有 `sonar1/2/3` link | 未观察到 ROS topic |
| KS1A552 单目相机 | 交付资料提及 | 实机未枚举独立设备，当前未连接或未识别 |

相机服务返回名称 `Astra`、OpenNI `2.3.0 Build 85`、ROS SDK `1.1.4`。驱动位于 `/home/kybot/robot_ws/src/ros_astra_camera`。

## 4. RGB-D 实测

用匹配硬件的 `astra_pro.launch`（UVC PID `0x0501`）临时启动，确认：

- `/camera/color/image_raw`：640×480，`rgb8`；
- `/camera/depth/image_raw`：640×480，`16UC1`，毫米深度；
- `/camera/depth/points`：XYZ 点云；
- `/camera/depth_registered/points`：XYZRGB 点云。

静态场景短时采样：

| 指标 | 实测值 |
|---|---:|
| RGB/深度帧率 | 约 30 Hz |
| 深度采样帧 | 67 |
| 有效深度像素均值/最小值 | 56.349% / 55.672% |
| 帧中值深度 | 1381 mm |
| 场景深度 p10 / p90 | 496 / 5205 mm |
| RGB-depth 配对帧 | 60 |
| 时间戳差中位数 | 6.167 ms |
| 时间戳差 p95 / 最大值 | 15.216 / 18.340 ms |

这证明数据流可用，不证明倒地场景的遮挡、黑色衣物、近距盲区和关键点精度已合格。

## 5. 标定审计

驱动日志明确报告以下文件不存在：

```text
/home/kybot/.ros/camera_info/rgb_17122222203.yaml
/home/kybot/.ros/camera_info/depth_17122222203.yaml
```

同时发现：

- 彩色/深度 `camera_info` 有 publisher，但等待期间无消息；
- `/camera/get_camera_params` 全为 `NaN`；
- `/camera/extrinsic/depth_to_color` 的旋转和平移全为 `NaN`；
- `/camera/get_camera_info` 仅返回通用默认针孔参数（`fx=fy≈570.342`、零畸变），不能当作正式标定；
- 驱动又发布 depth 到 color 的单位 TF，与 `NaN` 外参矛盾。

`robot_vslam/config/astrapro/` 有 2023 年历史 YAML：RGB 约为 `fx=588.974, fy=588.740, cx=340.565, cy=276.947`，深度约为 `fx=582.795, fy=584.395, cx=326.416, cy=249.989`。这些文件无设备序列号、标定板、重投影误差等溯源，且未被当前驱动加载，只能作为待核验候选。

相机安装外参也存在至少 `0,0,0.05 m`、`0.21,0,0.20 m`、`0,0,0.53 m`、`0.115,0,0.25 m` 等互相冲突的历史值。整机启动实测 `odom -> base_footprint -> base_link -> laser/imu` 连通，但 Astra `camera_link` 是独立树，`tf_echo base_link camera_link` 失败。

结论：**当前实机没有完成可复现、可追溯的 RGB-D 与安装外参标定。**

## 6. 启动配置问题

- 实际 RGB PID 为 `0x0501`，`astra_pro.launch` 与其匹配；
- `bringup_2d/3d/4m.launch` 引用 `astra_pro_plus.launch`，配置为 `0x050f`；
- 旧 `robot_vslam/launch/camera/astrapro.launch` 硬编码 `0x0502`；
- `bringup_3d` URDF 有 `usb_camera` link，但没有把 Astra 驱动的 `camera_link` 接入底盘树；
- `/camera/camera/set_camera_info` 出现重复服务警告。

整机启动时相机仍有数据，但配置不一致会造成重启、换机或 USB 枚举变化后的不确定性，应统一并加入启动回归测试。

## 7. 导航与全局坐标

实机已有 AMCL、Cartographer、GMapping、move_base、RTAB-Map RGB-D/激光融合 launch，以及多份二维地图。EKF 以 2D 模式融合轮速与 IMU，发布 `odom -> base_footprint`，`base_link -> laser` 可用。

本次只有 `/ekf_localization`，没有 `map_server`、AMCL、SLAM 或 RTAB-Map，故没有 `map` frame。历史地图数量多，但未归档对应场地和有效期。

应分两阶段验证：先输出 `camera_color_optical_frame` 下 17 个三维关键点与鲁棒人体中心；再接通并验证 `map -> odom -> base_link -> camera_link -> camera_color_optical_frame`，转换为规划事件坐标。

## 8. 三维反投影与事件接口建议

对 RGB 像素关键点 `(u,v)`，使用对齐深度 `Z` 和 RGB 内参：

```text
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
P_map = T_map_base(t_image) * T_base_camera * P_camera
```

不应只读单像素：在关键点附近取窗口，剔除 0、越界和离群值后取中位数；记录 `valid`、失败原因、样本数和协方差。倒地事件中心可优先由双肩、双髋 `[5,6,11,12]` 的有效三维点稳健聚合，人体 footprint 由框内点云或关节点地面投影形成。

```text
PoseObservation3D:
  stamp, source_frame, target_frame, track_id
  joints[17]: {name, x, y, z, score_2d, valid, reason, covariance}
  robust_center, footprint, depth_valid_ratio, tf_valid

SemanticEvent3D:
  event_id, event_type=FALL_CONFIRMED, person_track_id
  position_map, covariance, footprint, confidence
  first_seen, confirmed_at, expires_at, revision
```

CameraInfo、D2C、深度或图像时刻 TF 无效时，事件层可以保留“已确认跌倒”，规划层只能触发 `reobserve/verify`，不能直接导航到未经验证的坐标。

## 9. 仍缺条件（按优先级）

### P0：功能闭环必须完成

1. 对序列号 `17122222203` 重新标定并安装 RGB/深度内参；
2. 获取或实测 depth-to-color 外参，以彩色/深度边缘重合验证 D2C；
3. 实测 `base_link -> camera_link` 六自由度外参，只保留一份权威配置；
4. 修复并自动检查完整 TF 树，统一 Astra Pro PID/launch；
5. 实现二维关键点 + aligned depth + CameraInfo + TF 的三维节点和质量门控；
6. 选择实验地图并启动 AMCL 或 RTAB-Map，验证 `map` 定位；
7. 打通 ROS1 小车与 ROS2 研究系统，或统一运行环境。

### P1：论文实验必须量化

- 用已知三维/地面控制点报告相机系、底盘系、地图系误差均值、RMSE 和 p95；
- 覆盖站立、蹲下、倒地、远近距、遮挡、不同衣物与照明；
- 测量关键点有效率、事件中心误差、端到端延迟和事件稳定性；
- 对比静止/运动底盘，验证同步及 `TF(t_image)`；
- 导航到人体周边安全服务点，不能把人体中心直接作为目标点。

## 10. 未解决风险

- 本次无人体目标，深度有效率不能外推为人体关键点成功率；
- 超声波接线/topic 未确认，独立 KS1A552 未发现；
- IMU 启动零偏校准与 `imu_calib.yaml` 的使用关系尚未追踪；
- 历史地图未建立场地、日期和有效状态索引；
- 无 GPU，小车端端到端推理帧率待测；
- ROS1 网络、ROS1/ROS2 桥接尚未验证；
- Astra Pro 与 OpenNI/ROS1 驱动较旧，需冻结软件环境并考虑备件。

## 11. 下一步命令

完成 P0 标定与独立实验 launch 后执行验收：

```bash
roslaunch kybot_bringup bringup_3d_calibrated.launch
rostopic echo -n 1 /camera/color/camera_info
rostopic echo -n 1 /camera/depth/camera_info
rostopic hz /camera/color/image_raw /camera/depth/image_raw
rosrun tf tf_echo base_link camera_color_optical_frame
rosrun tf tf_echo map camera_color_optical_frame

# 研究工作站
ros2 launch yolopose_ros pose_3d_event.launch.py
ros2 bag record /pose_observation_3d /semantic_event_3d /tf /tf_static
```

本仓库只读复查脚本：

```bash
ssh kybot@192.168.124.49 'bash -s' < scripts/audit_lab_robot_sensors.sh \
  | tee reports/lab_robot_sensor_audit_2026-09-21.txt
```
