# DUCT 独立研究串流与三维显示

最后实机验证：2026-10-19。小车 Wi-Fi `192.168.31.191`，电脑 `192.168.31.221`；遥控器所在图传网段为 `192.168.144.0/24`。本次恢复详情见 [10 月 19 日日志](worklogs/worklog_2026-10-19.md)。

## 数据链路

小车相机的带时间戳 JPEG 通过 TCP 发到电脑，电脑运行 YOLOPose/LSTM，将二维关键点事件和调试 JPEG 发回小车。小车本机读取原始对齐深度和 TF，生成三维关节、事件、地图 Marker 与标注视频。RGB 原始 `sec/nanosec/frame_id` 全程保留。

电脑研究节点使用 ROS domain **18**，DDS 只绑定 `lo`；小车原系统及本机感知处理使用 domain **8**。跨机器研究数据由有界 TCP 最新帧交换承载，避免持续传输深度图。地图点云在小车本机 RViz 中显示，通过 NoMachine 查看。

| 地址 / 接口 | 用途 |
| --- | --- |
| `192.168.144.30:8888` | 原机器人控制连接 |
| `rtsp://192.168.144.30:8554/stream` | 原主摄像头画面 |
| `rtsp://192.168.144.30:8554/stream2` | 原第二路摄像头；当前硬件采集超时 |
| `192.168.31.191:8560` | 新增、带源时间戳的 RGB/事件/调试帧交换 |
| `rtsp://192.168.144.30:8555/pose3d` | 遥控器 VLC 的独立三维标注流 |
| `rtsp://192.168.31.191:8555/pose3d` | 电脑 Wi-Fi VLC 的同一标注流 |
| `/perception/pose_observation_3d` | 三维关节、base/odom/map 坐标、变换来源和同步差 |
| `/perception/human_approach_preview` | 小车地图中的候选接近点 Marker |
| `/perception/human_approach_candidate_status` | 候选点、数据年龄及未通过导航验证的状态 |

## 启动和查看

2026-10-19 原图传和研究节点已恢复运行，不要重复启动。下次恢复时，在仓库根目录执行：

```bash
bash scripts/run_duct_research_stream.sh
```

小车用户服务为 `pose3d-tcp`、`pose3d-fusion`、`pose3d-visualization`、`pose3d-goal-preview`、`pose3d-rtsp`、`pose3d-cloud-display`。它们已启用；2026-10-19 设置 `Linger=yes`，避免 SSH 退出后研究服务被用户管理器停止。新配置无人登录整车冷启动尚未验收；需要回退时可执行 `sudo loginctl disable-linger duct`，但研究服务可能再次依赖登录会话。

小车 SSH 中复查：

```bash
systemctl --user is-active pose3d-tcp pose3d-fusion pose3d-visualization pose3d-goal-preview pose3d-rtsp
```

小车 NoMachine 桌面运行：

```bash
bash /home/duct/start_pose3d_rviz_on_duct.sh
```

RViz 通过 `pose3d-rviz` 用户临时服务启动，需先登录 NoMachine 桌面。其固定坐标系为 `map`，视点跟随 `base_link`，显示环境点云、人体骨架和橙色候选目标。2026-10-19 已部署 5 FPS 和最多 80000 点的 `/perception/cloud_map_display`，输入/输出保留最新地图，以支持静止时晚加入的窗口；当前样本 49640 点，未触发抽稀。原 `/cloud_map` 不改动。二维栅格图默认关闭，避免本机已有的 GLSL sampler 链接错误。

电脑只读采样：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=18 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/yhc/kaiti_yolopose_framework/configs/cyclonedds_pose3d_local.xml
python3 scripts/check_duct_pose_3d.py --seconds 20
```

遥控器 VLC 可直接打开表中的 8555 URL。已安装的 VLC 可从 ADB 启动：

遥控器 VLC「设置 → 高级 → 网络缓存值」已设置并读回确认为 **200 ms**。该设置只作用于 VLC，不改变原控制应用；实际显示延迟仍需动作对照测试。用户已确认 NoMachine 中的人体骨架和橙色候选目标可见。

```bash
adb -s 192.168.144.20:5555 shell am start -a android.intent.action.VIEW \
  -d rtsp://192.168.144.30:8555/pose3d -t video/mp4 \
  -n org.videolan.vlc/.StartActivity
```

## 延迟与显示

RGB 交换最多 5 FPS，推理实测约 4 FPS；各 TCP 消息类型只缓存最新一条。三维融合使用本机原始深度，TF 查询不阻塞回调。RTSP 显示为 5 FPS，队列为一帧，播放时间戳使用实时播放时钟；超过一秒无新标注时显示 stale 提示。

2026-10-12 短测 34 条三维结果均有人、map 有效；通常 16–17 个有效关节，观测年龄约 0.35–0.55 秒，RGB-D 时间差约 0.13–0.16 ms。两机 NTP 已恢复，仍存在约 0.1 秒相对时钟偏差；观测年龄不等同完整玻璃到玻璃延迟。VLC 的网络缓存还会增加显示延迟，应独立测试。

研究数据双向传输约 12 Mbps，低于此前跨机深度订阅约 120 Mbps；此数不包含 NoMachine 等其他流量。环境点云留在小车本机，避免跨网发送大点云。右侧列表显示各关节距离，减少远处人体上的文字重叠。

2026-10-19 恢复后短测：三维坐标中位年龄 502 ms、Marker 506 ms、标注 521 ms；稳定复采 21/21 条有人且 map 有效，约 13–15 个有效关节。该指标仍不包含最终播放器/远程桌面延迟。

用户随后确认实际视频延迟约 1 秒，满足当前调试需求，保持当前参数。骨架与箭头是同时显示的不同显示项，不是切换视频源：人体使用 `MarkerArray`、`Topic=/perception/pose_3d_markers`；箭头使用 `Marker`、`Topic=/perception/human_approach_preview`。两份 RViz 配置已修正曾误用的 `Marker Topic` 属性名，避免默默订阅默认话题而不显示人体。

点云显示使用 **Reliable / Transient Local**，以接收静止时保留的地图。曾出现晚加入窗口没有显示地图；调整配置并重开后，用户已确认点云和骨架同时可见。对照探针两种可靠性均收到地图，尚不能把故障唯一归因于 Best Effort。

同日后续发现显示节点积压：标注年龄中位 2.905 秒、Marker 2.695 秒。最新消息 QoS、过期拒绝、字节数组和绘制优化后，标注中位 0.499 秒、Marker 0.481 秒（35 条短测）。用户观看仍反馈 2–3 秒，故不能宣称玻璃到玻璃延迟已经解决。视频中的 `source` 为源时间，`age` 为绘制时源年龄，`RTSP` 为发送时钟；不要把其中年龄当作播放器当前显示年龄。

遥控器 VLC 最后切换为软件解码（设置 → 硬件加速 → 禁用，原为自动），保留网络缓存 200 ms。一次带发送时钟截图估计源到显示约 1.04–1.96 秒，尚未完成实际动作和长时间验证。若软件解码性能不佳，可将该选项恢复自动；不涉及原控制应用。

小车 SSH 中只读复查（先加载本机 ROS 与 domain8 配置）：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=8 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///data/ductcleanrob/scripts/cyclonedds.xml
python3 /home/duct/check_duct_research_latency.py --seconds 10
python3 /home/duct/check_duct_navigation_preflight.py --seconds 5
```

电脑可用独立播放器对照显示缓存，不替换原控制应用：

```bash
ffplay -rtsp_transport udp -fflags nobuffer -flags low_delay -framedrop \
  -an -probesize 32768 -analyzeduration 0 rtsp://192.168.31.191:8555/pose3d
```

## 候选目标与规划接口

目标根据有效脚踝的 map 坐标计算：沿人体到机器人方向保持默认 1 m 间距，并朝向人体。候选数据超过 1.5 秒、地图变换无效或脚踝缺失时清除；机器人已经在间距范围内时不生成向后移动目标。

当前只发布 Marker 和状态，`navigation_ready=false`、`collision_checked=false`。尚未检查代价地图、机器人外形碰撞和可行路径，也没有发布 Nav2 action、导航目标或 `cmd_vel`。后续需先做路径预览，再接入有新鲜度和失联停止约束的执行流程。

2026-10-12 运动前置审计：本机没有 Nav2 action/代价地图；`map→odom` 和 `odom→base_footprint` 存在静态/动态重复发布，移动定位必须先收敛唯一 TF 发布者；原驾驶节点发布 `/cmd_vel`，不得另起速度发布者争抢控制。用户确认有人急停与空旷通道，但上述软件门控仍未满足，实车接近未执行。

2026-10-19 补充：本次未再采到 map/odom 链静态零位姿重复边，但尚未完成移动定位验收。读取 M0601C 底盘源码发现定时重发保存的轮速、未见命令超时归零；原遥控器现场有人看守不能替代单一控制出口和本机 watchdog。接入研究自主速度前，须隔离设计并验证原遥控器优先接管、故障自动停止和限速限距，不能直接追加 `/cmd_vel` 发布者。

## 原图传修复与回退

原控制应用配置已恢复到修改前的备份，研究画面通过独立 VLC 查看。原第二路 USB 摄像头在直接 V4L2 采集、设备复位后仍超时，需进一步检查摄像头/内部连接。原服务对缺帧通道的 RTSP 准备等待会阻塞原应用打开主画面。

修复版本编译在 `/home/duct/rtsp_repair_ws`，原 `/data/ductcleanrob` 源码和安装保持原样。补丁见 `deployment/duct/rtsp-startup-preroll.patch`；启用后用明确标注的等待画面完成初始准备，随后保留原地址、分辨率、码率、通道控制和录像逻辑。主画面已在原应用中截图验证，第二路仍没有真实图像。

2026-10-19 补充开机恢复：Cyclone 绑定的 Wi-Fi 网卡未就绪会令全部 RTSP 子节点退出，而 launch 仍返回 0；单靠 `Restart=on-failure` 无法自恢复。wrapper 现在先运行 `/home/duct/wait_duct_research_network.sh` 等待该接口 IPv4，systemd 覆盖设置 `Restart=always`。用户已确认在线重启后原画面恢复，尚未整车冷启动复验。等待脚本和 wrapper 是配套部署文件，回退时应保持一致。

回退修复版本时，只需在小车上将该覆盖文件改名并重启图传服务：

```bash
sudo mv /etc/systemd/system/robot-rtsp.service.d/rtsp-startup-repair.conf \
  /etc/systemd/system/robot-rtsp.service.d/rtsp-startup-repair.conf.disabled
sudo systemctl daemon-reload
sudo systemctl restart robot-rtsp
```

原第二路采集故障并不会随软件回退消失。原控制的运动功能本次没有通过实际运动验收。
