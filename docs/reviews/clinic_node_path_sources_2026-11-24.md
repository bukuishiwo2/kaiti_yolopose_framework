# Clinic 节点、旅行代价与执行路径来源审查

日期：2026-11-24。范围：只读历史证据及工作台适配层；未启动 ROS / Gazebo、未执行新规划、未修改研究算法。

## 已有能力与本轮证据缺口

第一轮已提供七页工作台、三机泳道、地图回放、双/三画面同步、静态二维栅格草稿和图表导出。本轮补充结构化名称、节点来源、显式关系、事件到计划关联和修复诊断。运行可读不等于原实验成功；PASS/FAIL 始终保留原字段。

未来完整 Nav2 几何路径、首次完整验证解精确时间、连续视频同步以及语义房间多边形没有充分记录。相应字段保持未记录 / NOT_RUN，不能以派发目标、模型估计或人工注入结果替代。

## 审查来源与优先级

1. 每轮 `runtime_scenario.json`、`result.json`、`trace.jsonl`、各阶段 `problem.json` 和原始 CBC 日志。
2. 每轮 `source/tools/dense_tasks.py`、`aligned_contract.py`、`bed_contract.py`、`bed_solver.py`、`tb4_io.py` 等冻结源码。
3. 当前工作区手册 `/home/yhc/clinic_planning_ws/README_CLINIC_RUNTIME.md`、`README_CLINIC_ACTIVE_BED.md` 及其引用的验收报告提供工程背景，不能自动替代每轮冻结事实。
4. 原有 `docs/reviews/clinic_research_workbench_upgrade_2026-11-23.md`、`clinic_temporal_logic_adoption_2026-11-23.md` 和最新相关实验报告用于界定已完成能力与科研结论边界。

逐字段来源、代码 SHA256 和矩阵由脚本输出到独立审查目录中的 `unified_bed_local_r1-path_report.json`；节点登记 JSON/CSV 包含精确坐标、用途、任务关联、能力、静态/候选属性、来源字段及有限到达证据。该派生输出留在本机审查目录，不提交原始运行快照或大日志。

## 命名与真实节点

`dense_tasks.py::cycle_tasks` 明确构造 `C{cycle}_{rid}_W{k+1}`，同时写入 `cycle_id`、`nominal_owner`、`waypoint`。

- C0/C1 是原始周期索引 0/1，友好显示为第1/2周期。
- W1/W2/W3 是名义任务序列站次，不是导航节点。
- 名称中的 r1/r2/r3 对应名义任务通道，不决定实际机器人；实际执行读取 `records[].robot`，各版归属读取 `plan.owners`。
- 反例：`C0_r3_W2` 名义 R3，实际 R1 执行；其固定清空节点仍为 CPW2C。这不是“R3 专用机器人点”。
- PW1、PW2 等名称不根据缩写扩展成臆测房间用途。

`unified_bed_local_r1` 的独立场景登记了22个坐标锚点，框架为 map。静态注册表能证明坐标被配置，不能单独证明坐标最初如何测量、任意场景可达或属于 RMF 拓扑图。

|标识|已验证用途|
|---|---|
|DL、G1、PW1、PW2、TL|常态任务保存定义引用的服务位置；DL/G1/PW1 也用作记录中的起点|
|ADL、AG1、EPW1、EPW2、ETL|对应资源阶段的入口；分别关联 DL/G1/PW1/PW2/TL|
|CDL、CG1、CPW1、CPW2、V3|对应资源的默认清空/释放停靠点；V3 对应 TL|
|BDL|DL 的名义 R1 通道清空覆盖位置|
|CPW2B、CPW2C|PW2 的名义 R2/R3 通道清空覆盖位置|
|CTLR3|TL 的名义 R3 通道清空覆盖位置|
|V1、M1、H1|本轮场景登记的事件核验、监护、交接服务候选位置|
|CTL|本轮未登记；不得自动改写为 CTLR3|
|W1/W2/W3|任务站次，不在本轮锚点注册表中|

坐标示例：EPW2=(18.8,-11.2,π)，ETL=(12.7,-15.7,π/2)，BDL=(20.35,-21,π/2)，CPW2C=(24,-11.8,π)。完整数值以 JSON 中原始浮点记录为准。其他实验使用各自来源，不把当前 `/config/services.yaml` 的 S1/S2/S3 合并进旧运行。

## MILP 与 Nav2 的接口关系

```text
保存场景节点 + 任务阶段/能力/资源
   ├─ 保存 travel_times（模型秒）→ MILP 归属、顺序、时刻
   └─ 保存任务目标/阶段节点 → Nav2 ComputePathToPose
                                  → 已批准 FollowPath → 必要 Spin/稳定到达
实际 pose_sample / guard_sample → 只读轨迹、阶段、原始证据
独立浏览器静态栅格 A*          → 草稿实验（没有 MILP/Nav2/ROS 控制连接）
```

本轮场景的 `travel_prior` 声明为语义配置空间格点路径除以0.22，加每段12秒姿态/ACK先验；并声明不保证物理耗时上界。冻结 `aligned_contract.py` 使用：

`tau = previous.egress + travel_times[previous.clear_anchor][next.entry_anchor] + next.approach`

因此旅行矩阵不是浏览器直线距离、不是已保存未来折线，也不是同场景历史执行耗时表。格点先验具有静态障碍背景；不能称为动态障碍预测。机器人能力是独立的归属资格约束；资源占用、清空与缓冲是独立调度/执行约束，不能声称矩阵本身已经编码全部动态约束。

冻结 `bed_contract.project` 另用欧氏剩余距离/0.22+12构造活动承诺释放预测。这是投影估计，不是上述完整旅行矩阵，也不是实际完成反馈或保证上界。

本轮记录 `nav_kind = Nav2 ComputePathToPose + FollowPath`，并保存获准路径长度等证据。只有保存未来折线坐标时才可绘制未来路径；本样本没有完整未来路径折线。任务序列用有序任务按钮表示，不能把节点连线伪装成导航路径。地图底图为工作区原始 PGM/YAML，具体运行的地图身份单独通过来源哈希核对。

## 动态事件与候选点资格

本场景 E1 中心 (15.4,-10.8)，V1=(14.5,-13.7)、M1=(18.3,-12)、H1=(19,-12.4) 是预登记位置，不是从当帧人体几何在线采样生成的位置。注入事件不能证明真实人体检测/定位效果。

`space.valid` 是保存空间注册结构的资格；`position_valid` 还涉及时间有效性与来源政策；`result.localization=gazebo_reference_pose` 描述机器人定位来源。这三者不应合并。源策略中无效/关闭的 sensor_estimated 与合法的已登记视频位置不是同一个资格字段。

实际稳定到达、原始导航查询、资格审查记录各证明有限测试条件；注册点在图中、或者像素可通行，不等于全局可达、安全多边形及服务资格全部通过。没有记录独立障碍/安全区域审计时明确未知。

## 关系边与证据边界

- 严格前置边只读取保存任务 `dependencies` 或协议 `completion_dependencies`。
- 核验→监护/取货，取货→交付；跨周期末站→次周期首站，均以实际字段为准。
- `monitor_active` 是持续监护守卫，与任务完成前置不同。
- 资源需求单列，不根据任务时间重叠推导资源先后关系。
- 同机器人取送、监护到交付接管等义务不因画图而自动改写为严格 DAG 边。
- 当前适配层未建立经过验证的导航拓扑连通边集，空间节点不自动全连接。

## 复核命令

```bash
cd /home/yhc/kaiti_yolopose_framework
PYTHONPATH=src python3 scripts/audit_clinic_workbench_explainability.py \
  --out /tmp/clinic-workbench-explainability-new
```

该命令只读取已保存实验并生成新的登记/审计输出；不会执行机器人实验。
