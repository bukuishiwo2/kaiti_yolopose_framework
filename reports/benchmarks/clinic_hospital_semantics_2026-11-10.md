# Clinic L1医院语义点位、常态路线与事件服务位验收

日期：2026-11-10。目标：参考原Clinic护理站/候诊/诊疗区与带房间名底图，区分待命、充电、取货和交付，设计正常巡检/配送，核验事件—观察/监护/交付关系，展示标注地图。本轮不加行人，不改既有规划主链，保留原有验证算例。

## 实际结论与范围

**已完成独立hospital-semantics/v1方案：24个点、4条常态路线、3个分别测试的事件位置。68项Nav2路径正例全部通过，1个墙内目标被正确拒绝；6组观察关系、2592条视线/视场采样通过。**

这是静态几何与真实Nav2 ComputePathToPose动作查询，不是机器人已沿新路线运行。没有启动Gazebo、控制器或实车，没有验证充电/SOC、实际物资搬运或人体识别。原跌倒/MILP实测入口仍使用原算例，本轮没有静默替换其坐标。

![整层语义设施与常态参考路线](/home/yhc/clinic_planning_ws/verification/hospital_semantics/hospital_semantic_routes.png)

## 1. 依据与点位用途

核对原始`clinic.building.yaml`、米制nav_graphs/0.yaml、原始`clinic.png`和现有L1世界。用唯一命名锚点拟合像素→米制变换，配准一致；重复名称排除。代数拟合残差只说明同源坐标一致，不能当成真实医院定位精度。[配准记录](/home/yhc/clinic_planning_ws/verification/hospital_semantics/source_registration.json)

原RMF的nurse_center作为左右护理站的演示服务语义。原建筑底图相邻位置还标有ACGME/BOH等用途，不能据机器人路点名宣称其真实临床房间用途。新交接设施均标为研究接口，不宣称已有实体柜或医疗设施。

尤其核对了原图STORE的门名：**L1_cleaning_supplies**，原模型还放置清洁推车。因此保持清洁用品库原用途，不把它改称护理/应急物资库；此前STORE门外候选不采纳。G1改为左BOH ADMIN AREA工作人员柜台外侧的临时备货/取货交接位，由工作人员提供封装普通辅助物资。本研究不声称药房、无菌供应或自动临床处置能力。

| 类别/ID | 坐标(x,y)m | 用途与来源 |
|---|---|---|
| B1 | (12.700, -37.900) | 研究待命位，原演示充电区邻近墙边 |
| B2 | (12.700, -38.900) | 研究待命位，与B1/C1独立 |
| B3 | (12.700, -39.900) | 研究待命位，避开原固定家具 |
| C1 | (12.716, -36.900) | 充电预留位，参考原charger命名区后调整；不等同充电硬件 |
| CA | (13.650, -36.900) | C1进场/退出位置 |
| G1 | (22.700, -27.500) | BOH工作区外侧人工备货/交接，研究新增接口 |
| DL | (21.524, -19.626) | 原L1_left_nurse_center语义，交付/巡检共享容量1 |
| DR | (40.905, -20.215) | 原L1_right_nurse_center语义，交付/巡检共享容量1 |

三个待命位、充电和取货点分开管理。原demo的is_charger标志与名称不完全一致，不据此自动认定真充电设施。待命/充电预留带位于原演示充电区边缘，**不是原有专用设备房**。旁边局部保留1.2m通行带，并检查全部泊位有车时的进出；1.2m是本科研方案的局部验收假设，不代表医院主走廊或病床/轮椅通行规范。

HR、卫生间、清洁用品库、急救推车位和楼梯不改作机器人设施。交接位不能当作长期堆放/排队点；后续增加行人时，还要验收工作人员交接、门前活动和净通行空间。

![设施细节](/home/yhc/clinic_planning_ws/verification/hospital_semantics/hospital_facilities_detail.png)

[原始带房间名底图的标注版本](/home/yhc/clinic_planning_ws/verification/hospital_semantics/hospital_source_semantics.png)用于复核业务来源。

## 2. 常态路线

不再用基地定时服务冒充巡检，也不只把在物资点停留叫配送。两条巡检是闭合路线，包含往返路段，不声称覆盖最优或全部走廊只走一遍。名义r1西巡、r3东巡、r2交替配送，**不是硬编码能力限制**。

| 路线 | 访问顺序 | 几何参考长度(m) | 仅按0.22m/s估计行驶时间(s) |
|---|---|---:|---:|
| PATROL_WEST | DL → PW2 → TL → PW1 → DL | 75.52 | 343.3 |
| PATROL_EAST | DR → PW3 → PR → TR → PW7 → DR | 84.15 | 382.5 |
| DELIVERY_WEST | G1 → DL → G1 | 16.73 | 76.0 |
| DELIVERY_EAST | G1 → DR → G1 | 81.52 | 370.6 |

- 西巡：左护理站DL→候诊2观察位PW2→左诊疗入口外侧TL→候诊1观察位PW1→DL。
- 东巡：右护理站DR→候诊3观察位PW3→操作区入口PR→右诊疗入口TR→南侧候诊观察位PW7→DR。
- 左/右配送：G1人工取一个物资包→对应护理站交付→返回G1。两单交替，不假定同时携带两单；取送同车，交付需人员接收ACK，现阶段为模板。

巡检点停留5秒、名义周期600秒、最大重访间隔900秒；配送取货15秒/交付10秒，左右交替周期1200秒。它们是研究负载设定，不是医院实际工作量调查结果，也未通过整段导航测出任务耗时。表内长度为独立A*参考路径；Nav2输出可略有不同，保留在JSON中。

**诊室/隔离诊室、治疗与操作区内部、HR/WC、清洁库、楼梯和急救推车区设置语义禁穿区。** 门洞开放并不表示允许穿过诊室抄近路。禁穿区是在原图注册的保守包络，不修改原场景碰撞体或原地图；所有几何/路径查询使用同一政策。标注图灰蓝区域表示禁穿包络。

## 3. 跌倒事件、观察与交付关系

三个候选事件分别测试，不声称三起事件并发已验证。人体假设长1.6m、宽0.55m，安全余量0.35m；机器人半径0.20m与额外0.10m净空另外计算。人体本体不与原固定几何相交；机器人不导航到人体中心。

| 事件/功能区 | 事件中心 | 核验V | 监护M | 人员接收交付H |
|---|---|---|---|---|
| E1 候诊区2 | (15.40, -10.80) | V1 (14.50, -13.70) | M1 (18.30, -12.00) | H1 (19.00, -12.40) |
| E2 候诊区1出口侧 | (10.70, -31.70) | V2 (13.50, -32.40) | M2 (13.30, -31.30) | H2 (13.50, -33.90) |
| E3 左诊疗入口外侧公共区 | (13.20, -14.60) | V3 (13.30, -12.00) | M3 (13.00, -17.30) | H3 (13.70, -17.80) |

V/M朝向均对准事件。核验完成后可导航到独立M点；G1→H路线在人体安全区和M点监护车同时占位的情况下仍可达。现场交付给工作人员，不假定机器人直接接触患者；任务模板与医护响应不是一回事。

![事件与核验/监护/交付位置及视线](/home/yhc/clinic_planning_ws/verification/hospital_semantics/hospital_event_visibility.png)

视线验收使用原TB4 Lite URDF相机外参，camera frame相对base约(-0.0371,0,0.1859)m，原水平FOV为1.25rad（约71.6°），垂直FOV由320×240与水平FOV推导。对每个V/M位：

- 检查人体9个平面代表点×3个高度0.08/0.18/0.28m，共27个目标。
- 检查标称位姿及15组采样位姿：中心/四个轴向位置误差0.20m，分别配朝向误差-0.30/0/+0.30rad。
- 位姿采样还需保持几何/语义可行、处于人体安全区外；射线必须在相机视场内，且不被原场景可视表面遮挡。

**六组关系、2592条射线/视场样本全部通过。** 选点按现有执行器0.20m/0.30rad门槛设计，避免为了看见目标额外强求更精确到达。离散采样不构成整个连续误差范围的保证；射线不包含机器人自身遮挡、动态人员、光照/材质识别效果，不等同RGB画面或YOLO/LSTM验证。后续仍需实际RGB-D与稳定到达反馈。

负例：旧算例的V→事件射线穿墙、相机背向事件、墙内目标均被拒绝，证明没有简单地把“有一条导航路”当作“能观察到事件”。

## 4. 可复核的验证方法与结果

1. 从原L1世界405个include读取487个碰撞部件、284,983个三角面。家具碰撞体采用保守高度带投影，墙体按三角面；原地图未知区不可通行。独立派生审核图层，不进行SLAM重建，不覆盖原PGM/YAML。
2. 读取490个可视部件、747,604个三角面用于视线，避免只依据简化collision网格判断。COLLADA单位显式处理，Playground的inch按0.0254m换算；未跳过模型。材质/纹理读取警告不参与几何计算。
3. 栅格0.05m，机器人半径0.20m＋净空0.10m，图搜索不切角。构造基础、3个满位停车、3个人体安全区、3个人体+监护占位，共10类配置空间地图。
4. 在独立ROS域78启动安装的Humble Navfn/map_server，真实调用ComputePathToPose，use_start=true。物理安全半径已编码进配置空间，Nav2只做0.001m数值半径质点查询，不重复膨胀；再保守侵蚀一格用于插值余量。这不是实际机器人驱动配置。
5. 每次载图等待全局代价图与目标掩膜逐格一致再查询，避免旧地图假通过。对Nav2路径按1cm采样复核原配置空间，且独立复核不穿语义禁行区。

**68项正例全部成功：13个常态路线段、7个转场段、6个其他泊位占用时进/出库、42个事件相关查询。另1个墙内目标失败符合预期。** Nav2路径采样最小静态中心净空0.30m，终点最大偏差0.05m；24个标称点最小静态中心净空0.453m。均不是实车误差或实际执行里程。

独立产物审计998项通过，含重复路径/区域采样，不是998个独立医院场景。原场景、原配置/地图、原验证结果与规划源等337个保护文件哈希不变；原验证算例保留。

原始证据：

- [独立审计](/home/yhc/clinic_planning_ws/verification/hospital_semantics/independent_audit.json)、[几何验证](/home/yhc/clinic_planning_ws/verification/hospital_semantics/geometry_validation.json)
- [Nav2动作查询与完整路径](/home/yhc/clinic_planning_ws/verification/hospital_semantics/nav2_validation.json)、[全部参考路径](/home/yhc/clinic_planning_ws/verification/hospital_semantics/paths.json)
- [全部视线/FOV样本](/home/yhc/clinic_planning_ws/verification/hospital_semantics/visibility.json)、[点位CSV](/home/yhc/clinic_planning_ws/verification/hospital_semantics/point_table.csv)
- [碰撞源几何](/home/yhc/clinic_planning_ws/verification/hospital_semantics/geometry_manifest.json)、[可视源几何](/home/yhc/clinic_planning_ws/verification/hospital_semantics/visual_manifest.json)

保留的候选/失败：pilot_01中人体压墙和监护射线受遮挡；pilot_03中第三泊位虽有窄几何通路，但额外插值余量下Nav2无法驶出；之后调整停车布局，没有放宽安全门槛。pilot_05/06等记录逐步加入房间政策、核对清洁库业务来源和放宽到已有执行误差范围的设计过程。它们不是正式通过结果，也不是额外机器人实验。

## 5. 文件变更、限制与下一步

新增独立工作区文件：

- [design.yaml](/home/yhc/clinic_planning_ws/config/hospital_semantics/design.yaml)：语义点、事件、正常路线、资源/周期、业务来源、禁穿区。
- `tools/hospital_geometry.py`、`design_hospital_semantics.py`：只读源几何与设计/视线核验。
- `tools/export_hospital_planning_masks.py`、`query_hospital_nav2_paths.py`、`launch/hospital_path_audit.launch.py`、`config/hospital_semantics/path_audit.yaml`：独立Nav2路径查询。
- `tools/render_hospital_semantics.py`、`audit_hospital_semantics.py`：标注地图与独立审计。
- [verify_hospital_nav2_paths.sh](/home/yhc/clinic_planning_ws/verify_hospital_nav2_paths.sh)、[README_HOSPITAL_SEMANTICS.md](/home/yhc/clinic_planning_ws/README_HOSPITAL_SEMANTICS.md)：可复现入口与范围。
- `verification/hospital_semantics/`：4组PNG/SVG、路径、采样、原图配准、源哈希和日志；`support/semantic_geometry_deps/`：本地隔离几何依赖，未改系统或项目venv。

项目只新增本benchmark文档并更新索引、阶段进展和worklog。没有修改原事件协议、MILP/ROS规划主链、原native演示、旧launch/config/map或已有实测输出。

尚未解决：护理站是RMF演示业务语义，G1是研究新增人工交接接口；未证明真实医院设施配置合规。未运行新路线的控制器/实际导航，未验证动态避障、真实人员交接、充电、耗电、视觉识别与连续误差鲁棒性。当前L1沿用已有门洞开放假设，不代表门/电梯交互已验证。本轮不是规划创新或动态协同策略优劣实验。

下一阶段应先在新的独立入口实际执行这些正常路线和服务、采集RGB-D观察画面，再接脚本事件；不替换旧通过算例的证据。

复核命令（不启动Gazebo/实车）：

```bash
cd /home/yhc/clinic_planning_ws
./verify_hospital_nav2_paths.sh
/usr/bin/python3 tools/audit_hospital_semantics.py
```

完整重建命令、Python环境区别与结果目录见独立README。查询程序自行关闭域78的子进程。
