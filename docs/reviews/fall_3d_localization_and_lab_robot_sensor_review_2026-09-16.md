# 跌倒人体三维落点与 Lab Robot 视觉传感器评审

日期：2026-09-16  
依据：

- [研究内容端到端全景说明](research_content_end_to_end_overview_2026-09-14.md)
- [Vision-Based Reactive Temporal Logic Motion Planning for Quadruped Robots in Unstructured Dynamic Environments](../../Vision-Based%20Reactive%20Temporal%20Logic%20Motion%20Planning%20for%20Quadruped%20Robots%20in%20Unstructured%20Dynamic%20Environments.pdf)
- `/home/yhc/智能机器人系统交付材料汇总/Lab Robot/模块化智能机器人教学平台实验指导书 V5.0.pdf`
- `/home/yhc/智能机器人系统交付材料汇总/Lab Robot/模块化智能机器人教学平台使用文档 V5.0.pdf`

## 1. 评审结论

### 1.1 当前是否已支持倒地人体各部位三维坐标

**不支持。** 当前仓库已经实现的是 RGB 图像上的人体框、COCO 17 点二维姿态、规则/LSTM/TCN
跌倒判断、原始时间戳贯通和部分事件稳定化。尚未实现以下在线链路：

```text
RGB关键点 + 对齐深度 + CameraInfo
  -> 每个关键点的相机坐标三维点
  -> source stamp时刻的TF
  -> map坐标三维点/地面投影
  -> 人体事件中心、人体占地区域和协方差
  -> SemanticEvent3D
```

代码证据如下：

- `src/yolopose/pipeline/runner.py` 的事件记录只输出人员数、跌倒状态、时序分数、质量摘要和
  source header；没有发布 17 点数组，更没有深度、内参或三维坐标字段。
- `ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py` 只订阅一个 RGB `Image`；没有订阅
  aligned depth、`CameraInfo`，也没有 `tf2` 查询。
- 仓库没有人体关键点反投影节点，也没有已经落地的 `SemanticEvent3D` 消息实现。
- 端到端总览已经将 Orbbec、D2C、深度窗口、反投影、TF 落点、协方差列为 S2/S3 未实施项。

因此，现阶段不能表述为“研究内容一已得到人体部位三维落点”。准确表述应为：

> 研究内容一已经得到人体二维姿态和跌倒视觉证据；研究内容二将利用 RGB-D、相机标定和
> TF，把这些二维视觉证据提升为带位置、不确定性和有效期的三维语义事件。

### 1.2 “各部位三维点”和“任务事件落点”必须分开

建议在实现与论文中区分三类空间结果：

1. **`BodyKeypoints3D`**：鼻、肩、肘、腕、髋、膝、踝等 17 个关节在相机或 `map` 坐标系
   中的三维位置，附带每点置信度、深度有效标记和协方差。用于可视化、姿态分析和消融。
2. **`HumanFootprint3D/2D`**：倒地人体在地面上的占地区域。可由有效关节点、人体框内点云、
   地面分割与凸包共同估计。它不是简单把每个关节的 z 坐标置零。
3. **`SemanticEvent3D`**：任务层消费的稳定事件锚点。建议用肩/髋的鲁棒深度聚合得到人体
   中心，以人体占地区域和协方差生成安全区、核验点与交付点。

多机器人规划层不应直接消费 17 个抖动关节点。其稳定接口应是 `SemanticEvent3D +
HumanFootprint + DynamicZone + service points`；17 点三维结果作为上游证据保留。

## 2. Lab Robot 视觉传感器核验

### 2.1 已确认的传感器

| 设备 | 资料证据 | 确认程度 | 对本研究的用途 |
|---|---|---|---|
| 奥比中光（Orbbec）Astra 系列 RGB-D 深度相机 | 指导书明确写“机器人本身提供的是奥比中光的深度相机”；使用 `56-orbbec-usb.rules` 和 `astra_camera`；多处运行 `astra.launch` | 厂商和系列已确认 | RGB、深度、CameraInfo、点云和三维反投影 |
| **很可能为 Orbbec Astra Pro** | 视觉例程明确运行 `roslaunch astra_camera astrapro.launch`；机器人照片中的横条外形也与 Astra 系列一致 | 高概率，但不能仅凭资料宣布精确 SKU 已确认 | 若为 Astra Pro，需要验证 UVC RGB 与深度流的时间同步和 D2C |
| KS1A552 全局快门 USB 单目相机 | 指导书 1.2.5 明确给出型号，最高分辨率 1280×720 | 型号已确认 | 单目图像、AR/机械臂视觉；单独使用时不能直接提供米制深度 |

资料还显示平台使用 ROS1 Melodic 风格的驱动与话题：

```text
/camera/rgb/image_raw
/camera/rgb/image_rect_color
/camera/depth/image_raw
/camera/rgb/camera_info
/camera/depth/camera_info
/camera/depth/points
```

这证明随车方案具备开展 RGB-D 反投影的硬件基础，但**不能只根据 `astrapro.launch` 文件名
最终锁定 SKU**。交付资料同时混用 `astra.launch` 与 `astrapro.launch`，而不同 Astra 型号、
批次及 UVC 模块可能使用不同 USB PID。最终确认必须读取实机设备信息和铭牌。

### 2.2 实机精确型号的冻结门禁

连接随车深度相机后，在机器人原生系统执行：

```bash
lsusb -nn | grep -Ei '2bc5|orbbec|astra'
v4l2-ctl --list-devices
roslaunch astra_camera astrapro.launch
rostopic list | grep -E '^/camera/(rgb|color|depth|ir|extrinsic)'
rostopic echo -n 1 /camera/rgb/camera_info
rostopic echo -n 1 /camera/depth/camera_info
```

如果已安装新版 Orbbec ROS 驱动，再补充：

```bash
rosservice call /camera/get_device_info "{}"
rosservice call /camera/get_camera_params "{}"
```

必须记录：

- 产品名、serial、USB VID:PID、固件和驱动版本；
- RGB/depth 分辨率、帧率、encoding、depth scale；
- RGB、depth、aligned depth 的实际 topic；
- RGB 与 depth 的 `header.stamp` 差；
- RGB/深度内参、深度到 RGB 外参和 `camera_link -> base_link` 外参；
- 最近/最远有效深度、倒地人体距离下的空洞率和强光干扰。

若 `astrapro.launch` 无法稳定同时输出 RGB 和 depth，不能用未对齐的深度像素直接查询 RGB
关键点；应先解决 D2C/注册，或改为显式使用深度到彩色外参进行投影匹配。

## 3. 三维反投影应如何开展

### 3.1 最小计算链

对 RGB 像素关键点 `(u, v)`，在已经对齐到 RGB 的深度图中取得鲁棒深度 `Z` 后，使用
`CameraInfo.K`：

```text
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
Z = depth(u, v) * depth_scale
```

这得到的是 RGB optical frame 中的点，随后必须在原图 `source stamp` 查询：

```text
T_map_camera(source_stamp)
  = T_map_base(source_stamp) * T_base_camera
p_map = T_map_camera * p_camera
```

不能使用推理完成时刻的最新 TF，否则机器人移动期间会造成系统性落点偏差。

### 3.2 推荐的鲁棒策略

- 为每个关键点使用 5×5 或随距离自适应的小窗口，不取单像素。
- 剔除零深度、超量程值、边界值和 MAD 异常值，保留有效样本数。
- 先实现总览中冻结的肩/髋 `[5, 6, 11, 12]` 事件锚点，再扩展全部 17 点。
- 为每个关节点发布 `valid/reason/confidence/covariance`，不能用 `(0,0,0)` 表示无效。
- 倒地人体安全区优先融合人体框内点云/分割轮廓与有效关节点，生成地面凸包；只有数据不足
  时才退化为中心点加保守半径。
- 深度或 TF 无效时保留 `EventEpisode`，发布 `pose_valid=false` 并触发 `reobserve`；禁止生成
  看似有效的零协方差任务目标。

### 3.3 建议的接口边界

```text
研究内容一
  PoseObservation2D
    stamp, camera_frame, track_id
    keypoints_2d[17], keypoint_confidence[17]
    bbox, fall_score, observation_quality

研究内容二
  BodyKeypoints3D
    event_id, track_id, frame_id=map
    points[17], covariance[17], valid_mask[17], reason[17]

  SemanticEvent3D
    event_id, semantic_state, pose_valid
    center_map, covariance, footprint, region_id
    perception_revision, valid_until, reason_code

  DynamicZone + verifier/courier service points + event task DAG

研究内容三
  TaskPlan / RepairStatus / ExecutionFeedback
```

这条边界保证将来替换姿态模型或 RGB-D 相机时，不需要修改多机器人 MILP、LocalRepair 或
LTL/任务执行逻辑。

## 4. 与 V-RTLMP 论文的关系

参考论文与本研究最一致的不是具体检测网络，而是跨层方法：

1. 使用视觉检测获得任务相关对象语义；
2. 由 RGB-D 内参、深度和 ROS TF 把二维检测投影到世界坐标；
3. 用点云聚类/模板拟合得到对象位置并持续更新先验知识；
4. 用时变标签函数把“对象语义”与“固定位置”解耦；
5. 视觉发现更近目标时采用 greedy 更新，目标不存在时用 gate 拒绝任务自动机错误迁移；
6. 环境变化时局部调整当前子任务路径，不必每次重建整个自动机。

本研究可在此基础上形成明确扩展：

| 论文 V-RTLMP | 本研究应采用/扩展的形式 |
|---|---|
| 单机器人、目标对象驱动 | 跌倒 `EventEpisode` 驱动双机器人角色任务 DAG |
| bbox 中心/框内点云定位对象 | 2D姿态 + aligned depth + 人体点云的鲁棒定位 |
| 时变标签更新地图知识 | 带 `revision/TTL/covariance` 的世界模型更新 |
| gate 验证当前子任务是否完成 | 事件确认门控、zone ACK、服务点有效和任务完成门控 |
| 当前子任务的反应式路径调整 | 影响传播后的 LocalRepair，失败回退 Full-Replan/HOLD_SAFE |
| 位置误差用 0.5 m 容差吸收 | 显式不确定性、动态安全半径和无效深度安全降级 |

因此，大论文内核可稳定表述为：

```text
视觉证据
  -> 稳定且可追踪的语义事件
  -> 带空间位置、不确定性和有效期的任务事实
  -> 多机器人任务分配与时序规划
  -> 世界变化驱动局部修复/全局重规划/安全停止
```

需要注意，参考论文的单点/框内点云定位和固定阈值容差不能直接替代本研究的事件稳定、位置
协方差、倒地人体安全区与多机器人一致性控制；这些正是本研究应形成的跨层贡献。

## 5. 实施顺序与验收指标

### S2：硬件与同步台架

1. 按实机 VID:PID/serial 冻结相机精确型号和驱动版本。
2. 证明 RGB、depth、CameraInfo、aligned depth 和 TF 可持续发布。
3. 静态画面采集不少于 300 帧，报告 RGB-depth 时间差、深度有效率与 D2C 像素误差。
4. 标定并记录 `base_link -> camera_link -> *_optical_frame`，禁止沿用总览中的
   `oakd_rgb_camera_optical_frame` 作为真实 Lab Robot 相机名。

### S3a：事件中心最小闭环

1. 先对肩/髋实现窗口深度、MAD、反投影、source-stamp TF 和协方差。
2. 输出 `SemanticEvent3D`，完成已知地面标记点的静态/运动定位测试。
3. 对比 zone centroid、2D ground projection、single-depth、robust RGB-D。

### S3b：全身三维与人体 footprint

1. 扩展 17 点三维输出和逐点有效性。
2. 融合人体框内点云/分割，生成倒地人体地面 footprint。
3. 对遮挡、远距离、深度空洞、反光/强光和运动模糊分层评估。

### 任务层验收

- 平面事件中心误差：median ≤ 0.25 m，p90 ≤ 0.50 m；
- region accuracy ≥ 95%；
- 无效 depth/TF 被发布为 `pose_valid=true` 的次数为 0；
- 所有有效事件保留原图 source stamp，TF 查询不使用推理完成时刻；
- confirmed 但 3D 无效时不派发 deliver；
- `DynamicZone` 当前 revision 未 ACK 时不派发导航任务。

## 6. 未解决风险

- 实机精确 SKU 尚未通过 VID:PID、serial 或铭牌冻结；“Astra Pro”目前是高概率结论。
- 交付材料是 ROS1 Melodic 体系，当前研究仓库是 ROS2；需要在原生 ROS2 驱动与
  ROS1-to-ROS2 bridge 之间做台架选择。
- Astra 系列的 RGB 与深度可能不是同一成像光路，必须验证 D2C 与同步，不能假定同像素对齐。
- 相机安装高度、俯角和机器人震动会显著影响倒地人体深度有效率及 TF 误差。
- 现有检测事件没有发布二维关键点数组；实现三维节点前需要先冻结 `PoseObservation2D`。
- 17 点全部三维化会增加无效点与抖动，不应阻塞肩/髋事件锚点的最小闭环。

## 7. 下一步命令

仓库侧先再次确认三维实现仍为空缺：

```bash
cd /home/yhc/kaiti_yolopose_framework
rg -n "CameraInfo|aligned_depth|BodyKeypoints3D|SemanticEvent3D|projectPixelTo3dRay" \
  src ros2_ws scripts
```

实机侧按 2.2 节执行型号与 topic 核验；采集结果应保存为 S2 台架证据，再开始写反投影节点。

