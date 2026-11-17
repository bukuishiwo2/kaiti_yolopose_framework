# Clinic demo图形启动等待诊断与修复

日期：2026-11-09。目标：定位`./run_clinic.sh demo`长时间无响应、`world`可启动的差异，修复独立环境入口，保持论文规划主链不变。

## 现场与结论

原demo于18:28启动，约十分钟后仍无Gazebo世界服务或ROS仿真时钟。RViz与RMF节点已运行。Gazebo GUI、服务端进程均存在，但Ogre日志仍停留在前一次18:27的world运行。内存可用约22GiB；NVIDIA RTX3060 Laptop驱动可提供OpenGL4.6，显存占用约717MiB/6GiB。

GDB只读附加后自动分离，未修改ptrace或驱动设置：服务端主线程在`runServer()`条件变量等待；GUI主线程在`createGui()`内部请求`Empty→StringMsg_V`世界列表。其余线程以Ignition发现、消息接收等等待为主，未见模型解析或OpenGL驱动加载栈。可定位为**组合启动中的服务端/GUI启动等待**，但没有证明消息丢失、特定竞态或某个驱动缺陷是底层原因。

因此本次现场不支持“模型缺失导致持续下载”“显存耗尽”或“OpenGL版本不足”。不能从OpenGL版本合格推断所有渲染路径都绝无问题；本次修复后的真实画面才提供了对应运行证据。[Fortress官方排障](https://gazebosim.org/docs/fortress/troubleshooting/)说明了OpenGL要求与渲染诊断方法。上游[RMF issue #378](https://github.com/open-rmf/rmf/issues/378)也报告过类似等待世界列表的现象，但该issue没有确认根因，不能据此认定相同缺陷。

## 独立入口修复

原入口使用单个`ign gazebo -r ... clinic.world`，由CLI组合启动server和GUI。现在改为：

1. 始终直接运行`ign gazebo -s -r ... clinic.world`，不依赖GUI启动服务端。
2. GUI模式通过独立工具轮询`/gazebo/worlds`，确认响应包含`sim_world`后执行`ign gazebo -g`；单次请求1秒，子进程3秒保护，总等待90秒，超时明确报错。
3. headless模式不启动GUI等待工具。world/demo仍复用同一入口，原RMF调度、机器人和RViz参数保留。

未修改上游rmf_demos、`/opt/ros`、显卡驱动、模型素材或论文规划/感知源码。没有清理Fuel缓存。原卡住实例停止后还有一个server孤儿，已确认PID与原现场对应后定点终止，没有批量终止其他Gazebo任务。

## 实测证据

全部原始记录：[诊断目录](/home/yhc/rmf_clinic_ws/verification/gui_startup_diagnosis)。原始挂起线程栈：[server](/home/yhc/rmf_clinic_ws/verification/demo_hang_server_stack.txt)、[GUI](/home/yhc/rmf_clinic_ws/verification/demo_hang_gui_stack.txt)。

- 第一次分离启动：世界服务成功响应；启动期15.014墙钟秒内收到1149个clock样本，推进5.74仿真秒，4台机器人fleet状态与楼层有效。
- 真实GUI已查看：Clinic家具、贴图、实体树和仿真控制栏可见，[画面记录](/home/yhc/rmf_clinic_ws/verification/gui_startup_diagnosis/split_gazebo.png)。GUI初次有一段SDF解析/释放的CPU繁忙期；18:38:43启动到18:39:46新Ogre日志约63秒。这段时间与原先长期互等不同，世界仿真已在推进。
- 渲染完成后稳态：10.014墙钟秒推进8.95仿真秒，1680个clock样本，4台机器人状态有效。这里clock样本数不等于唯一仿真时刻数量，推进量按首尾时间差计算。

- 第二次demo复启：13.19秒收到世界列表；25.022墙钟秒采样推进15.88仿真秒，3177个clock样本、4台机器人状态有效。18:42:33启动到18:43:37新Ogre日志约64秒，[再次查看的真实画面](/home/yhc/rmf_clinic_ws/verification/gui_startup_diagnosis/repeat_gazebo.png)包含医院整体布局，GUI已留给用户继续操作。
- world无界面回归：15.009墙钟秒采样推进14.05仿真秒，2811个clock样本、4台robot_state均有合法楼层。
- 既有78个规划/ROS/配置及验证文件哈希再次核对，无变化；上游已跟踪源码diff为空。

汇总结果：[result.json](/home/yhc/rmf_clinic_ws/verification/gui_startup_diagnosis/result.json)。它们用于检查启动修复，不是论文算法性能实验。就绪服务约13秒响应和完整GUI约一分钟加载是两个不同阶段；90秒上限只限制前者。

## 边界与变更清单

完整demo退出时部分子进程仍可能不及时结束，ROS launch会升级终止信号；第一次分离测试额外清理了两个本次clock bridge相关进程。GUI中仍有上游`qfloors`初始化警告，未阻止本次画面加载；未完整测试所有GUI插件。没有开展长期稳定性或不同驱动组合的统计测试，不能将两次启动成功称为彻底证明底层竞态消失。

修改独立工作区：`launch/clinic.launch.py`、`README_CLINIC.md`；新增`tools/start_clinic_gui.py`及本次verification证据。论文仓库新增本诊断文档，更新安装记录与两处文档索引。

下一步使用原命令；同一partition先停止旧实例，勿并行启动world与demo：

```bash
cd /home/yhc/rmf_clinic_ws
./run_clinic.sh demo
```

本轮修复用于环境可运行性；没有接入论文MILP、Nav2或实车。
