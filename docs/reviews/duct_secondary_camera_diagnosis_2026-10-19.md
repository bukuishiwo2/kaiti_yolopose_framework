# DUCT 第二路相机无帧复查（2026-10-19）

## 目标和结论

用户反馈改动前第二视角正常，要求定位/修复且保留原功能。本次在线复查未恢复真实第二路图像。证据定位到 USB/UVC 采集层之前或其中，不是单纯 ROS 话题、RTSP 地址、VLC 或遥控器显示层问题；**不据此断言摄像头物理断线或损坏**。

## 实测证据

- SSH：192.168.31.191；设备 `YLX-4K-S858`，USB VID:PID `1bcf:28c4`，独立路径 `1-3`，480 Mbps。
- `/dev/ylx_cam` 初始正确指向 `/dev/video8`；另一 video 节点是 metadata，不是第二个可采集视角。无人占用视频节点。
- 原服务日志第二路 `topic_frames=0`；原 usb_cam 启动后 `Select timeout`、exit -6。没有持续工作的第二路采集进程。
- 隔离修复工作区与 OEM 安装目录的 `image2rtsp.launch.py` 使用 cmp 比较一致；仍是 `/dev/ylx_cam`、1280×720、30 FPS、mjpeg2rgb，重映射到 `/camera/rgb/image_raw`。未发现此前 RTSP preroll 补丁修改了该启动配置；不能由此证明所有历史外部环境从未变化。
- 绕过 ROS/RTSP，v4l2-ctl 的 mmap 队列及 STREAMON 均成功，但 1280×720 MJPEG / 30 FPS、640×480 MJPEG / 5 FPS、640×480 YUYV / 5 FPS 均零帧超时（timeout exit 124）。低带宽模式也失败，不支持“只是高分辨率带宽不足”的单因素解释。
- 仅对 VID/PID/product 验证通过的 YLX 设备做取消授权/重新授权，系统重新枚举为 `/dev/video0`，udev 别名正确跟随；仍然无帧。未卸载整个 uvcvideo 模块，未重置共享 USB 总线。
- 对同一设备执行 USBDEVFS_RESET 成功，低带宽 mmap 采集仍零帧。随后独立运行系统原 usb_cam 驱动，再次约 5 秒后 Select timeout，未恢复话题。
- usb_cam 报旧控件名 `exposure_auto` / `focus_auto` 等不支持；但直接 V4L2 完全绕过此节点仍无帧，不能将这些告警当作唯一根因。

## 结束状态和原功能

未改 OEM 启动文件、RTSP 参数、原应用或底盘服务；测试结束恢复 1280×720 MJPEG / 30 FPS。亮度、对比度、曝光、自动对焦等读回与初始一致；USB power/control 恢复 auto，authorized=1。研究及原主图传没有为复查停止。

robot-start、robot-rtsp 均 active。原 `8554/stream` 实际解码 10 帧成功（退出 0），有非单调 DTS 告警，不能说媒体时间轴完全无异常。第二路仍无真实画面，未用主路复制或占位画面冒充恢复。

## 文件与验证

新增 `scripts/reprobe_duct_secondary_camera.py`：仅允许特定 YLX 身份/路径、检查相机无人占用，再执行限定设备重枚举；finally 恢复授权及电源管理。此脚本是诊断工具，**不是已成功的修复方案**，也不保证真实切断 USB 供电。已上传小车并执行，返回设备重新枚举成功，但后续真实帧测试失败。新增本审计及当日日志。

## 待完成条件

### 用户照片与首次改动前版本追溯（追加）

用户提供车尾照片：黄色长条下方可见单个圆形窗口，外观符合镜头窗口，长条疑似补光组件；照片不能读取型号，不能仅凭外观证明其对应 USB YLX。未见足以确认的物理隐私开关。普通镜头遮挡通常仍能输出黑暗图像，不能直接解释当前完全无帧；不建议拆卸黄色部件或撬开面板。

追溯小车自带 `/data/ductcleanrob` Git，而不再仅比较当前两份安装文件：

- 历史提交 `e69cc9ce9f2318c3991ca895b8c83085da03c954`（2026-06-02）。
- 历史第二路 launch、当前源码、OEM 安装版、隔离修复安装版的 Git blob 均为 `3aff155d2d5062904211117c52a0e92a53824ed0`。
- 历史 parameters.yaml、当前源码、OEM 安装版 blob 均为 `abe3b4287bfedb1743dcecdce92042f7ad4df6c9`。
- 上述配置未发现相对六月版本的内容变化。这比文件修改时间更可靠，但仍不涵盖内核、固件和全部外部环境历史，不能排除所有软件原因。
- 持久 journal 最早保留到 2026-09-28 上午，该时段已出现第二路 `topic_frames=0`。当日下午 15:28:25 原 robot-rtsp.sh 启动的 usb_cam 明确出现 Select timeout，随后 exit -6；10 月 7 日和 9 日原服务同样报错。这证明现象早于 10 月 12 日隔离 RTSP preroll 修复，**不证明一定早于用户所说的首次调试**，因为首次干预准确时间仍未建立。

本轮追加仅查询历史、比较内容及检查服务，无新相机参数或设备复位操作；robot-start、robot-rtsp 仍 active。仍未恢复第二路。

需要用户补充最后正常时刻/对应改动，以及相机本体可见指示灯、开关/遮盖状态。下一步可做特定相机的真实断电复位和独立主机交叉验证，以区分相机内部固件/传感器状态、供电/数据链路与主机驱动问题。仅软件 USB reset 不等于真正断电；已有整车重启记录也不能证明该 USB 电源已完全放电。未经确认不拆车，不切断共享总线或修改内核/全局驱动参数。

只读复查命令（小车）：

```bash
ls -l /dev/ylx_cam
v4l2-ctl -d /dev/ylx_cam --get-fmt-video --get-parm
systemctl is-active robot-start robot-rtsp
```
