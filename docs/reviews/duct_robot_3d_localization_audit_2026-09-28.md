# DUCT 小车倒地人体三维定位实机审计

日期：2026-09-28  
目标主机：`duct@192.168.1.121`  
审计边界：只读 SSH 检查、订阅现有 ROS2 数据并执行临时反投影程序；未修改小车配置，未启动或停止小车原有服务，未发送运动指令。

## 1. 任务目标

验证该小车能否把人体二维姿态关键点与深度图结合，生成相机坐标系三维点，并进一步转换为多机器人任务分配与规划可使用的 `map` 坐标。

## 2. 验收结论

**结论：能够开展该功能，而且当前传感器与 ROS2 链路已经具备可运行的三维反投影和地图坐标转换能力。**

本轮完成了真实深度像素的端到端验证：从深度图取像素窗口，使用 `CameraInfo` 反投影到 `camera_color_optical_frame`，再查询该图像时间戳的 TF 转换到 `map`，成功得到地图三维坐标。

当前状态不是“论文精度已经验收”。相机内参来自设备/驱动，外参来自 URDF，尚未用控制点独立测量误差；本次场景也没有倒地人体。因此判断分为：

| 能力 | 状态 | 证据 |
|---|---|---|
| RGB-D 数据流 | PASS | 1280×720 RGB、深度及点云持续输出 |
| RGB/深度同步 | PASS | 最近时间戳差中位数 0.147 ms |
| 深度对齐到彩色坐标 | PASS（运行状态） | 深度图和 CameraInfo 均使用 `camera_color_optical_frame`，内参一致 |
| 相机系三维反投影 | PASS | 实际像素已成功反投影 |
| `base/odom/map` TF 转换 | PASS | 三条变换均可在运行时查询 |
| RTAB-Map 在线建图/定位链路 | PASS（当前为建图模式） | 地图、视觉里程计和 `map -> odom` 正常输出 |
| 倒地人体 17 点三维定位 | READY TO IMPLEMENT | 尚缺 YOLO Pose 关键点到深度/TF 的业务节点 |
| 论文级定位精度 | NOT VALIDATED | 缺控制点、人体目标和重复性实验 |

## 3. 平台与传感器

- 主机：GMKtec NucBox K6；
- CPU：AMD Ryzen 7 7840HS，8 核 16 线程，Radeon 780M 集显；
- 内存：12 GiB；本次约 5.9 GiB 可用；
- NVIDIA GPU：无；
- 系统：Ubuntu 22.04.5，ROS2 Humble；
- 主工作空间：`/data/ductcleanrob`；
- RGB-D：**Orbbec Gemini 336**，USB VID:PID `2bc5:0803`，序列号 `CP9E853000E1`；
- 另有 4K UVC 相机 `YLX-4K-S858`；
- 2D 激光雷达：`sllidar_ros2`，`/scan` 约 10.02 Hz；
- IMU：`/imu/data` 与 `/imu/data_transformed`；
- 底盘与轮状态、两路 CAN、串口控制器均已枚举。

当前已安装 Orbbec ROS2、RTAB-Map、Nav2、robot_localization、OpenVINS/MSCKF、点云与深度处理包，比旧的 Astra Pro/ROS1 平台更容易直接接入本研究仓库的 ROS2 系统主线。

## 4. RGB-D 与同步实测

现有系统通过以下命令常驻启动相机：

```text
ros2 launch orbbec_camera gemini_330_series.launch.py enable_point_cloud:=true
```

实测话题：

- `/camera/color/image_raw`：1280×720，`rgb8`，约 29.35 Hz；
- `/camera/color/camera_info`：持续发布；
- `/camera/depth/image_raw`：1280×720，`16UC1`；
- `/camera/depth/camera_info`：持续发布；
- `/camera/depth/points`：约 27.15 Hz；
- `/rgbd_image`：RTAB-Map 同步后的 RGB-D 数据。

短时采样结果：

| 指标 | 数值 |
|---|---:|
| 深度帧采样数 | 90 |
| 深度有效像素均值 | 89.840% |
| 深度有效像素最小值 | 89.445% |
| 场景帧中值深度 | 688 mm |
| RGB/深度时间戳采样 | 各 120 帧 |
| 最近时间戳差中位数 | 0.147 ms |
| 最近时间戳差 p95 | 0.158 ms |
| 最近时间戳差最大值 | 33.521 ms（单个边界配对样本） |

Gemini 启动文件默认启用 `enable_frame_sync=true`、`align_mode=SW`、主机时间同步与 1280×720@30 Hz。深度消息的 frame 为 `camera_color_optical_frame`；彩色与深度 CameraInfo 使用相同的投影矩阵，符合“深度已对齐到彩色图”的运行配置。

彩色相机当前内参为：

```text
fx = 692.3676147461
fy = 692.2613525391
cx = 642.3387451172
cy = 362.8396606445
model = rational_polynomial
```

畸变参数不是全零，说明驱动在发布设备标定数据；但仍需实验性精度验证，不能只凭消息存在就宣称论文级标定通过。

## 5. TF 与地图定位

URDF 中的安装关系为：

```text
base_link -> camera_link
translation = [0.1914724718, -0.0000687462, 0.0955] m
rotation = identity
```

光学坐标轴转换存在且符合 ROS optical frame 形式。运行时已验证：

- `base_footprint -> camera_color_optical_frame`；
- `odom -> camera_color_optical_frame`；
- `map -> camera_color_optical_frame`；
- `map -> base_footprint`。

RTAB-Map 当前配置：

- `frame_id=base_footprint`；
- `odom_frame_id=odom`；
- 视觉 RGB-D 里程计，`Reg/Force3DoF=true`；
- 激光松耦合生成二维占据栅格；
- 当前 `localization=false`，即在线建图模式，而非在冻结地图上的纯定位模式；
- `/rtabmap/odom` 约 16.1 Hz，诊断为 `Tracking`，未丢失；
- 当前诊断样本：833 个特征、554 个匹配、433 个内点；
- `/grid_prob_map` 分辨率 0.01 m，尺寸 415×387，frame 为 `map`。

需要注意：机器人状态被约束为平面 3DoF 定位，但深度人体点仍可保留地图坐标中的 `z`。任务规划通常消费地面投影 `(x,y)`、人体 footprint 和安全服务点，而不是直接导航到人体三维中心。

## 6. 端到端真实落点试验

在 1280×720 深度图中心 `(u=640,v=360)` 取 21×21 窗口，441 个样本均有效，中值深度为 0.924 m。使用该帧的 CameraInfo 反投影，并使用**相同图像时间戳**查询 `map <- camera_color_optical_frame`：

```text
图像时间戳：1790565968.427951104
相机坐标点：[-0.0031, -0.0038, 0.9240] m
地图坐标点：[ 1.1155,  0.0031, 0.1393] m
```

这证明当前链路可以执行：

```text
RGB 像素 + 对齐深度 + CameraInfo
  -> camera_color_optical_frame 三维点
  -> TF(t_image)
  -> map 三维点
```

该点是普通场景中心点，不是人体关键点，也不是精度标定结果。

## 7. 对研究内容的落地建议

下一实现节点应订阅：

```text
/camera/color/image_raw
/camera/depth/image_raw
/camera/color/camera_info
/tf
/tf_static
二维 PoseObservation（17 点、置信度、track_id、原图时间戳）
```

处理规则：

1. 对每个关键点在对齐深度图取局部窗口中值，而非单像素；
2. 输出 17 点的 `valid/reason/depth_samples/covariance`；
3. 必须查询原图时间戳的 `map <- optical_frame`，禁止使用“当前最新 TF”替代；
4. 用肩、髋 `[5,6,11,12]` 稳健聚合倒地事件中心；
5. 用人体点云/关键点地面投影生成 footprint 和动态禁行区；
6. 深度或 TF 无效时仍可保留 `FALL_CONFIRMED`，但位置状态必须为 `UNLOCALIZED`，任务层先派发观察/验证，不直接导航。

推荐事件链：

```text
YOLO Pose / 时序跌倒确认
  -> PoseObservation3D
  -> SemanticEvent3D(position_map, covariance, footprint, revision)
  -> verifier/courier 安全服务点生成
  -> 多机器人任务分配
  -> Nav2 / LTL 规划与事件修订触发重规划
```

## 8. 尚缺条件与风险

### P0：功能实现

- 实现 ROS2 `PoseObservation2D + depth + CameraInfo + TF -> PoseObservation3D` 节点；
- 将当前研究仓库消息接口与小车话题、QoS、frame 名统一；
- 将规划输入由单点扩展为带协方差、footprint、时间和 revision 的事件；
- 固化 RTAB-Map 的建图/定位模式切换，实验时使用明确的地图数据库；
- 加入 TF、深度有效率、视觉里程计 `lost` 状态的门控。

### P1：标定和论文验收

- 用标定板或已知三维控制点核验 Gemini 工厂内参和 D2C 对齐；
- 独立测量 `base_link -> camera_link` 六自由度外参，判断当前 URDF 的 CAD 数值是否等于实机安装；
- 报告相机系、底盘系、地图系误差的均值、RMSE、p95；
- 采集真实倒地人体的 17 点有效率、事件中心误差和端到端延迟；
- 覆盖遮挡、黑色衣物、近远距离、机器人运动和回环修正场景；
- 验证 RTAB-Map 回环造成 `map` 坐标修订时，事件 revision 与任务重规划是否正确触发。

### 运行风险

- 无 NVIDIA GPU；YOLO Pose + 时序模型的实际帧率需要单独基准测试，可评估 CPU、ROCm/ONNX Runtime 或外部工作站推理；
- RTAB-Map 当前是在线建图模式，回环会调整历史地图坐标，事件必须支持 revision；
- 本次只验证静态普通场景，没有验证真人跌倒；
- Orbbec 参数/设备信息 ROS2 服务可发现但本次用户态调用未返回，序列号改由 udev 实机属性确认；
- 当前系统负载约 4.94（16 线程主机），仍有余量，但相机、RTAB-Map、YOLO 同机运行需测端到端性能。

## 9. 电脑端推理接入复核

电脑与小车当前网络地址分别为 `192.168.1.131/24` 和 `192.168.1.121/24`。小车环境使用：

```text
ROS_DOMAIN_ID=8
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml
```

电脑默认 `ROS_DOMAIN_ID=0`，因此初始状态看不到小车话题。电脑设置 `ROS_DOMAIN_ID=8` 后，即使继续使用本机 Fast DDS，也已实测可以发现 Gemini 相机、深度、TF 和 RTAB-Map 话题。

电脑为 NVIDIA RTX 3060 Laptop GPU，现有模型文件和 CUDA PyTorch 可用。现已完成 DUCT 实机适配：

- `pose_stream_node` 可直接订阅 `CompressedImage`，输出17点 `(u,v,confidence)`、检测框和 ByteTrack ID；
- `pose_3d_fusion_node` 可直接解码 Gemini `compressedDepth`，完成局部窗口深度、反投影、`base_link/odom/map` 转换；
- `/perception/pose_observation_3d` 持续提供关节点、人体中心、有效性、距离与同步质量；
- `/perception/semantic_event_3d` 在跌倒 uncertain/confirmed 时按 V3 协议发布；
- DUCT 专用 launch、参数、Cyclone DDS 配置和启动脚本已经加入仓库。

实机人工注入17点观测已得到17/17有效三维点。真实人体联调得到 `track_id=1`、二维可见15点、15/17有效三维点，肩髋中心 `base_link=[4.2165,-0.4402,0.6223] m`、车体平面距离 `4.2394 m`，并通过 `/rtabmap/odom` 回退得到 `odom=[-0.9561,-4.2811,0.6623] m`。当前电脑使用 Fast DDS 时，普通图像消息可跨 RMW 互通，但小车 Cyclone DDS 的 transient-local `/tf_static` 不能在电脑端恢复，因而正式 `map` 输出仍需电脑安装并启用 `rmw_cyclonedds_cpp`。

跨 Wi-Fi 直接订阅 1280×720 未压缩 RGB 仅约 2.2 Hz，消息大小约 2.76 MB/帧。压缩 RGB 实测约 26.7 Hz、约 0.22 MB/帧。实现已改为节点内直接解码压缩 RGB 和压缩深度，不再依赖会在该 Humble 版本报错的 `compressedDepth -> raw` republish 插件。

## 10. 下一步命令

安装电脑端 Cyclone DDS 后直接启动，不需要修改小车现有导航配置：

```bash
sudo apt install ros-humble-rmw-cyclonedds-cpp
cd /home/yhc/kaiti_yolopose_framework
scripts/run_duct_pose_3d.sh
```

完成实现后应记录以下证据：

```bash
ros2 bag record \
  /camera/color/image_raw/compressed /camera/depth/image_raw/compressedDepth \
  /camera/color/camera_info /perception/events \
  /perception/pose_observation_3d /perception/semantic_event_3d \
  /rtabmap/odom /tf /tf_static
```

## 11. 2026-09-28 Cyclone 安装后复验结论

电脑端 `ros-humble-rmw-cyclonedds-cpp` 已正确安装，但使用与小车相同的 Cyclone 配置时只能发现本机端点；加入小车显式 peer 后仍未恢复发现。因此，当前 AP/Wi-Fi 路径下不能仅凭安装完成宣称 Cyclone 通信验收通过。

采用 Fast DDS 后，实测可接收压缩 RGB（约 30 Hz）、压缩深度（约 16 Hz）、动态 TF 和 `/rtabmap/odom`。融合节点对静态相机外参使用有来源标记的 URDF fallback，并将 RTAB-Map 最新 `map->odom` 校正与时间邻近 odom 组合。真人样本最终得到：

```text
base_transform_source: urdf_fallback
map_transform_source: map_odom_latest_plus_odom
valid_3d_keypoints: 11
center_base: [2.325, -0.154, 0.518] m
center_map:  [2.327, -0.153, 0.558] m
distance_3d_to_robot: 2.387 m
rgb_depth_delta: 0.143 ms
```

新增可视化输出：

- `/perception/pose_3d_debug_image`：逐关键点三维距离与人体中心坐标；
- `/perception/pose_3d_debug_image/compressed`：供无线网络和遥控端使用；
- `/perception/pose_3d_markers`：RViz 三维骨架、中心和测距线；
- `rviz/duct_pose_3d.rviz`：地图、点云、人体 Marker 和图像的预配置界面；
- `configs/duct_pose3d_rtsp.yaml`：独立 `8555/pose3d` 遥控验证流，不修改原始 `8554/stream`。小车端已收到 raw 叠加图并产生 `push_ok`，但 ffmpeg 仅完成 RTSP/H.264 会话协商、未解出帧；需用实际遥控器客户端继续验收。

这完成的是“可观察、可人工核验”的三维转换链路。精度结论仍必须等待中心线/已知控制点和相机到底盘外参标定实验。
