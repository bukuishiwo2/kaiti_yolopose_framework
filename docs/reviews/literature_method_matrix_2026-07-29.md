# 公共空间动态语义多机器人：逐篇文献方法矩阵

日期：2026-07-29

用途：将对话总结中列出的 15 篇文献落实为“研究对象—方法—实验—可借鉴点—不应照搬点”的可审查矩阵。

## 1. 使用原则

本矩阵不以“引用数量”替代方法选择。每篇文献只承担一种明确作用：

- **直接方法依据**：与当前任务分配、动态修复或语义不确定性高度对应；
- **系统结构借鉴**：借鉴分层和接口，不移植整套系统；
- **场景/基线依据**：证明问题合理或说明已有方法边界；
- **远期方向**：与毕业设计主线相关，但当前投入产出比不足。

## 2. 方法矩阵

| # | 文献与对象 | 核心方法 | 实验/验证对象 | 可借鉴到本项目 | 不应直接照搬 | 定位 |
|---:|---|---|---|---|---|---|
| 1 | [Multi-robot Mission Planning in Dynamic Semantic Environments](https://arxiv.org/abs/2209.06323) | 面向具有不确定位置的移动语义目标，以协同 LTL 任务为规范，在运动、规范状态和未来目标配置的联合空间采样，并用感知反馈在线修正路径 | 动态语义目标下的多机器人任务与运动规划 | “语义状态不确定—反馈更新—计划修订”的闭环论证 | 当前项目目标是跌倒事件响应，不需要复刻联合采样规划器 | 直接方法依据 |
| 2 | [Heterogeneous Multi-robot Task Allocation for Long-Endurance Missions in Dynamic Scenarios](https://arxiv.org/abs/2411.02062) | 异构机器人、充电、任务拆分/接力与联盟约束；精确 MILP 与启发式方法；执行架构在意外事件下修复或重算 | 长时多机器人任务规划 | 异构能力、能量、充电、执行期修复的强参考；支持保留现有 MILP 主线 | 接力、联盟和任务碎片化会显著扩大模型，不进入 MVP | 直接方法依据 |
| 3 | [Perception-Based Temporal Logic Planning in Uncertain Semantic Maps](https://arxiv.org/abs/2012.10490) | 在已知几何、但地标位置/类别不确定的语义地图中，对概率谓词定义 co-safe LTL，并边规划边更新地图 | 不确定语义地图上的机器人规划 | 将置信度、观测质量和位置协方差显式放入事件语义；LTLf 作为可检查规范 | 当前 LTLf 只做验证，不应据此声称已实现概率语义规划 | 直接方法依据 |
| 4 | [Reactive Semantic Planning in Unexplored Semantic Environments Using Deep Perceptual Feedback](https://arxiv.org/abs/2002.12349) | 目标检测、语义 SLAM、拓扑语义和逻辑/几何反应式规划联合；利用人体网格运动/手势反馈 | 轮式与足式机器人实验 | 感知变化应改变任务行为，而非只更新可视化 | 不新增一套反应式控制器，也不把“未探索环境”设为 MVP | 系统结构借鉴 |
| 5 | [3D Dynamic Scene Graphs: Actionable Spatial Perception with Places, Objects, and Humans](https://arxiv.org/abs/2002.06289) | 分层表示物体、墙、房间、人和机器人及其关系，保留可行动拓扑 | 视觉惯性输入下的动态 3D 场景图系统 | 借鉴“度量层—区域层—实体层—动态人/事件层”的数据结构 | 完整 SPIN/DSG 构建远超当前必需范围 | 系统结构借鉴 |
| 6 | [Optimal Task and Motion Planning and Execution for Human-Robot Multi-Agent Systems in Dynamic Environments](https://arxiv.org/abs/2303.14874) | 将任务/动作时间线规划与在线几何运动规划解耦，分别处理持续时间、协同关系和环境变化 | 制造场景机械臂/人协作 | 明确 MILP 管任务与资源，Nav2 管几何执行，LocalRepair 只修改受影响部分 | 不把机械臂动作协同模型原样移植到移动机器人 | 系统结构借鉴 |
| 7 | [Co-NavGPT: Multi-Robot Cooperative Visual Semantic Navigation using Large Language Models](https://arxiv.org/abs/2310.07937) | 融合多机器人子地图，使用视觉语言模型进行全局前沿分配和协同探索 | HM3D 与真实四足机器人探索 | 可作为“语义探索型多机器人”对照，帮助突出本项目是事件响应而非开放探索 | 不引入 VLM；它不是跌倒时序识别或约束 MRTA 的必要组件 | 场景对照 |
| 8 | [Hydra-Multi: Collaborative Online Construction of 3D Scene Graphs with Multi-Robot Teams](https://arxiv.org/abs/2304.13487) | 中心化融合多机器人度量语义地图、相对变换和回环，在线构建联合 3D 场景图 | 异构多机器人协同建图 | 借鉴共享图层和跨机器人实体合并概念 | 不集成整套 Hydra-Multi；当前主线是已知医院地图上的事件响应 | 远期方向 |
| 9 | [Khronos: A Unified Approach for Spatio-Temporal Metric-Semantic SLAM in Dynamic Environments](https://arxiv.org/abs/2402.13817) | 快速活动时间窗处理短期动态，较慢的长期因子图处理历史一致性 | 仿真与真实异构双机器人 | 借鉴动态实体 TTL、短期活动层和长期静态层分离 | 不实现完整时空 SLAM；只实现事件/人员动态层 | 远期方向 |
| 10 | [Collaborative Fall Detection and Response Using Wi-Fi Sensing and Mobile Companion Robot](https://arxiv.org/abs/2407.12537) | NLOS Wi-Fi CSI 跌倒检测与单个陪护机器人响应结合 | 跌倒检测和移动响应原型 | 证明“检测后让机器人响应”是成立的应用链条 | 单机器人、简单响应链不能覆盖本项目的并发任务和资源冲突贡献 | 场景/基线依据 |
| 11 | [New Eldercare Robot with Path-Planning and Fall-Detection Capabilities](https://www.mdpi.com/2076-3417/14/6/2374) | 2D LiDAR/IMU/相机，Hector SLAM、RRT*、YOLOv7，组合跌倒检测与移动响应 | 约 1 万张图像及机器人系统实验 | 作为集成型跌倒响应 baseline，说明动态障碍和距离是系统难点 | 其数据划分、指标和场景与本项目不同，不能只比较单一准确率 | 场景/基线依据 |
| 12 | [Dynamic Multi-Robot Task Allocation under Uncertainty and Temporal Constraints](https://iliad.stanford.edu/pdfs/publications/choudhury2022dynamic.pdf) | SCoBA 双层结构：单智能体 DP 策略树加冲突协调，处理在线到达、时间窗和完成不确定性 | 传送带机械臂与无人机场景仿真 | P2 可把任务持续时间/成功率不确定性纳入动态分配 | MVP 不需要策略树和随机任务完成模型 | 直接方法依据/P2 |
| 13 | [Self-Reactive Planning of Multi-Robots with Dynamic Task Assignments](https://sensorweb.engr.uga.edu/wp-content/uploads/2020/12/yang2019self.pdf) | 基于行为树组织感知、通信、规划、协商、一致和执行，联合任务选择、队伍形成与路径 | 最多 20 个机器人、无障碍仿真 | 可借鉴任务优先级、执行反馈和机器人自治循环的表述 | 缺少复杂几何和真实验证，不适合作为当前导航实现模板 | 系统/基线依据 |
| 14 | [HOV-SG: Hierarchical Open-Vocabulary 3D Scene Graphs for Language-Grounded Robot Navigation](https://arxiv.org/abs/2403.17846) | 构建楼层—房间—物体的开放词汇分层 3D 图，用于跨楼层语言导航 | 大型室内场景导航 | 借鉴区域层级和紧凑图表达 | 不做开放词汇、多楼层或语言导航 | 远期方向 |
| 15 | [Vision-Based Uncertainty-Aware Motion Planning Based on Probabilistic Semantic Segmentation](https://arxiv.org/abs/2209.06936) | 用深度集成估计概率语义分割不确定性，再进行情景规划和速度调度 | 不确定感知下的运动规划 | 借鉴置信度校准、可靠性图和不确定性敏感评估 | 不引入深度集成与情景运动规划；当前先校准已有感知输出 | 方法借鉴/P2 |

## 3. 第一优先级文献的可操作方法提取

二次评审指出，15 篇总表仍偏摘要级。这里不为没有进入实现的远期论文抄录大量公式，
而是对会直接影响 P0/P1 变量、约束和实验的 6 篇文献进一步展开。

| 文献 | 问题对象/关键状态 | 算法链 | 原文验证重点 | 本项目落地变量或实验 | 复现边界 |
|---|---|---|---|---|---|
| #1 动态语义环境多机器人任务规划 | 机器人状态、时序逻辑任务、位置不确定且会移动的语义目标 | 在运动/规范/未来语义配置的联合空间搜索；根据新感知在线更新路径 | 动态语义目标下的任务满足与在线修订 | `SemanticEvent3D` 的状态、位置分布和 revision 必须改变服务点/路径/计划，而不是只改 RViz | 不复现其采样规划器；用现有 Episode + MILP + LocalRepair 实现相同反馈原则 |
| #2 异构长时 MRTA | 机器人能力、电量/充电、任务分段/接力、联盟和执行期事件 | 精确 MILP 与启发式求解；执行中根据异常 repair 或 recompute | 小规模精确解比较、启发式扩展性、在线修复 | 保留能力、能量、资源和 CBC；比较 LocalRepair/Full-Replan、修改任务数和回退率 | P0 不引入任务接力或机器人联盟 |
| #3 不确定语义地图时序逻辑规划 | 已知几何、地标类别/位置概率、perception-based atomic predicates、co-safe LTL | 采样生成满足概率语义谓词的控制策略，并随语义地图更新 | 不确定语义下的任务满足和在线适应 | 事件表示增加 `p, Σ, region probability`；位置质量不足生成 `reobserve`；LTLf 只验证轨迹 | 不声称实现概率 LTL 规划或其最优采样算法 |
| #6 动态任务—运动规划 | 符号任务、可实现该任务的几何动作、持续时间和协同关系 | 上层 timeline-based task planning；下层 online motion planning；执行反馈闭环 | 人—机械臂协同制造的执行时间与动态适应 | MILP 只负责任务/资源/期限；Nav2 负责几何运动；Nav2 持续异常才升级为语义边变化 | 不复制制造动作模型；只借鉴层间责任边界 |
| #12 不确定与时间约束动态 MRTA | 在线任务、时间窗、任务完成不确定性和机器人冲突 | SCoBA：单机器人 DP 策略树 + 多机器人冲突协调 | 传送带机械臂与无人机场景中的在线任务表现 | P2 才加入任务持续时间/成功率不确定性；P0 只做确定时长和预注册 deadline 敏感性 | 不把策略树或随机完成模型放入 MVP |
| #15 视觉不确定性感知与运动 | 概率语义分割占用、模型校准和跟踪误差 | 深度集成 + 大规模增强得到概率占用；情景路径规划；速度调度 | 与现有方法比较并用人手障碍做实验 | 借鉴协方差校准和不确定性膨胀：`r_safe = r0 + r_robot + k√λmax(Σ_xy)` | 不引入分割集成、情景运动规划或其速度控制器 |

由这 6 篇文献实际导出的 P0 方法不是“拼接更多模块”，而是：

1. 将视觉证据压缩为带状态、位置协方差、TTL 和版本号的事件；
2. 由事件生成具有持续留场语义的任务 DAG；
3. 由位置不确定性生成导航级硬安全区和边界外角色服务点；
4. 把 Nav2 的持续异常提升为世界版本变化；
5. 只对受影响任务做修复，并量化相对 Full-Replan 的计划扰动。

## 4. 逐层对应关系

| 项目层 | 主要文献依据 | 本项目应采用的最小形式 |
|---|---|---|
| 事件语义与不确定性 | #1、#3、#4、#15 | 四态稳定机 + Episode + 置信度/观测质量/位置协方差 |
| 轻量世界模型 | #5、#8、#9、#14 | 2D 地图 + 事件局部 3D + 人工区域图 + 带 TTL 的动态层 |
| 任务与运动解耦 | #6 | MILP 负责任务/资源/期限，Nav2 负责路径与避障 |
| 多机器人任务分配 | #2、#12、#13 | 异构能力、能量、区域资源、在线任务到达与局部修复 |
| 场景合理性与 baseline | #10、#11 | 与单机器人检测—响应链比较，多出并发、持续监护和资源冲突 |

## 5. 对技术路线的直接结论

1. **保留 LSTM + Episode + MILP + LocalRepair 主线。** 文献支持动态语义反馈和执行期修订，但没有证据要求更换为 VLM 或完整 DSG。
2. **将 LTLf 降到“形式化监测/验证”的准确定位。** 若后续没有 DFA 驱动的任务合成，就不使用“LTLf 规划器”表述。
3. **采用轻量四层模型，不集成 Hydra/Khronos/HOV-SG。** 它们适合作为结构来源和远期工作，而非毕业设计依赖。
4. **多机器人贡献必须来自预先定义的任务并发。** R1 确认后持续留场直到 R2 完成交付；期限在实验前固定并做敏感性分析，不能根据结果反向收紧。
5. **感知对比应控制范围与公平性。** P0 的 Rule、LSTM、TCN 共享 54 维序列；Tiny Transformer 为 P1；ST-GCN 使用骨架图输入，应单独说明输入和参数量。

## 6. 官方实现兼容性补充

- [OrbbecSDK ROS2 官方仓库](https://github.com/orbbec/OrbbecSDK_ROS2)当前列出
  ROS2 Humble 与 Gemini 336L 支持；项目环境尚未安装 `orbbec_camera`，因此支持性仍需
  本机台架验证。
- [RTAB-Map ROS 官方仓库](https://github.com/introlab/rtabmap_ros)提供 Humble、
  RGB-D、3D LiDAR、TurtleBot4 与 Nav2 示例，说明其具备定位/建图能力；本项目路线仍将
  已知图 + AMCL 作为 P0，把 RTAB-Map 放在 P1 展示/辅助建图。
- [RTAB-Map 参数定义](https://github.com/introlab/rtabmap/blob/master/corelib/include/rtabmap/core/Parameters.h)
  表明 3D 栅格/OctoMap 与二维投影是可配置能力；是否启用必须由实验目的决定，不能仅凭
  “RTAB-Map”名称推断已经具备 3D 语义图。
- [Hydra 官方仓库](https://github.com/MIT-SPARK/Hydra)当前主分支说明主要测试环境为
  Ubuntu 24.04 / ROS2 Jazzy，且定位为研究代码。当前项目是 ROS2 Humble，因此完整
  Hydra 集成同时存在版本、构建和研究范围风险。

## 7. 文献矩阵的维护要求

后续写论文相关工作时，每一条“借鉴”都必须对应到实际代码变量、约束或实验指标。
仅在讨论部分出现、没有进入系统设计的文献，应标为背景或未来工作，不应包装为已实现
方法。对未计划复现的论文，不为了“显得深入”搬运其完整公式；对直接方法依据，则在
研究计划 v3 中继续补充变量定义、伪代码、参数表和与本项目实验的一一对应关系。
