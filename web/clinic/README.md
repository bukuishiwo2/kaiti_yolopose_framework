# Clinic 多机器人协同规划实验评审工作台

本地历史证据工作台，兼顾任务审查、语义事件展示、双／三画面对照和静态二维栅格实验。
实现位置在本研究仓库，默认只读访问 /home/yhc/clinic_planning_ws。
启动服务不会启动 ROS、Gazebo、MILP 或机器人控制器。

## 启动与打开

    cd /home/yhc/kaiti_yolopose_framework
    python3 scripts/serve_clinic_review.py --workspace /home/yhc/clinic_planning_ws --port 8765

打开 http://127.0.0.1:8765/ 。已有服务时直接刷新页面；不要为重启服务而使用广泛 kill 命令。
Ctrl-C 停止当前终端启动的服务。仅监听 127.0.0.1，不暴露远程控制接口。

Python 3 标准库即可运行服务；前端为原生 HTML / CSS / JavaScript，无 npm 安装或构建步骤。
浏览器自动检查脚本另需 Node.js 及 Google Chrome，这不是日常运行依赖。

## 七个页面

| 页面 | 主要用途 |
| --- | --- |
| 实验总览 | 保存的成功／失败结果、任务完成分母、任务结束与返场区分、不同时间口径、记录能力与关键时刻 |
| 空间与执行 | 原始参考占用地图、真实测量位置与轨迹、朝向、目标、资源与承诺线索、三机泳道、计划／实际条带 |
| 语义事件 | EventEpisode 生命周期、模型输出、空间注册、核验、显式 fall/no_fall 复核、应急服务与原始图片 |
| 任务与调度 | 逐任务阶段、筛选、长等待线索、到达误差、守卫曲线及评审笔记 |
| 规划与对比 | 求解阶段、真实计划版本、前缀与携货／监护投影、任务变化、影响传播边、独立多画面对照及离线实例 |
| 静态单机器人路径草稿 | 起终点、顺序访问点、临时障碍、四邻接 A*、撤销、草稿导入导出；仅作几何草稿，不属于论文的多机器人规划实验 |
| 证据与报告 | 后端分页日志、原始日志行、SHA256、成果边界、报告与实际运行手册，以及独立图表导出 |

顶部实验选择器和回放条为主时钟。地图、任务泳道、机器人状态、事件点击定位共用该时钟。默认选择器只展示后端人工审核的核心研究目录；打开“显示全部历史记录”后才显示工程探针、启动联调、资格检查和失败开发轮次。原始记录不删除，审计模式仍可查看原始 ID。
多策略对照有独立且明确标注的 aligned 时钟，每个画面同时显示本轮 episode 时间，避免混为同一轮数据。

## 推荐评审步骤

1. 选定历史实验，先看“实验总览”中的保存结果、记录能力及来源策略字段。
2. 失败实验顶部直接显示原始代码和中文说明。点击“失败定位”联动主时钟、目标地图和原始证据。
3. 在“空间与执行”拖动时间；点击任务条或任务目标检查对应任务及日志行。地图支持拖动、滚轮、跟踪与全屏。
4. 默认三机泳道可切换为逐任务模式；勾选“计划／实际对照”查看本时刻已提交计划，也可明确选定保存版本。
5. 在“语义事件”查看本轮真实闭环。普通常态运行显示无事件；负例保留 no_fall 关闭，不释放虚构应急任务。
6. 在“规划与对比”查看每个版本的释放、改派、顺序和时间变化；展开保存的规划输入投影查看承诺来源。
7. 在“证据与报告”检索日志，点击行读取未重写的原始文本，或导出带来源的独立图表。
8. 如需设计新几何条件，进入“二维栅格实验”操作独立草稿。

## 保存运行与时钟兼容性

默认读取：

- runs 下具有 result.json 和 trace.jsonl 的直接子目录。
- verification/visual_integration_2026-11-18_b1、visual_positive_2026-11-18_c1、visual_bed_2026-11-18_d1 中具有 summary.json 和 trace.jsonl 的直接子目录。
- 离线方法索引使用 verification/repair_methods_2026-11-18_e1/paired_02/rows.json，不将它们伪装为实体导航运行。

当前实际兼容性检查覆盖 110 份保存运行。具体数量可能随后续文件增加而变化，以刷新后的列表和收据为准。
缺失字段为 N/A；NaN / Infinity 经传输适配为 null，字段路径保存在 nonfinite_fields，原文件不改写。

时钟处理规则：

- 优先使用保存结果中的 epoch；trace.at 减去 epoch，任务和保存计划的回合相对时间保持原值。
- 结果缺少 epoch 时，只有至少三条非负 episode_time 记录给出一致偏移，才从 at − episode_time 提取偏移，并显示来源。
- 不一致或无法验证时标记 unverified；前置负时间记录保留。
- 事件的 _review_source_at、位姿 source_at 保留原绝对仿真时刻；_review_trace_line 指向原 trace 行。
- /api/raw 返回逐行原文，不重写其中时间戳。
- 模型 source_at、video_time、ROS stamp 和仿真 at 各自保留；不把源视频秒当仿真秒。
- 只有保存的明确源配对点展示为配对，不生成未验证的视频连续同步。

## 地图与状态的真实来源

- 底图读取 maps/clinic_l1.pgm 及 YAML 的 origin/resolution；这是工作区参考原图。每轮实验自己的地图配置身份在可比性凭据中单列。
- 服务点优先来自运行的 runtime_scenario.json 或冻结／哈希一致的 scenario；否则只提取任务记录中实际保存的 anchor 与 target。
- 不从当前未绑定的配置给旧实验补造房间用途或区域。
- 普通轨迹来自 pose_sample / measured_pose_sample；部分视觉日志只有守卫测量位置，明确标记为稀疏 guard_sample，不当作连续导航轨迹。
- 实际轨迹实线；未来路径只有存在保存折线坐标才画虚线。只有长度时显示 N/A，不能画目标之间的假路径。
- 超过两秒的测量间隔不连线，不插值；最后位置有数据年龄提示。
- 资源为最近显式 resource_feedback，不据任务重叠推断占用或冲突。
- 承诺来自保存前缀、motion_path_admitted/released、协议 token 与规划输入 active_commitments，不将“任务活动”自动当作完整承诺证明。
- 安全区域、语义房间多边形、首次完整验证解仿真时刻等缺失时明确显示 N/A。

## 任务阶段与缺陷口径

| 指标 | 计算 |
| --- | --- |
| 总时长 | end − begin |
| 导航／到达准备 | stable_at − begin |
| 到达后等待 | service_started − stable_at，可能包含计划等待和 ACK 等待 |
| 服务 | service_finished − service_started |
| 驶离／释放 | end − service_finished |
| 资源等待 | lease_granted_at − gate_arrival |
| 服务 ACK 等待 | service_started − start_requested |
| 到达误差 | arrival.position_error，单位 m |

缺少内部节点时不编造阶段；可用 begin/end 时显示整任务条，缺失区间不补零。
长等待、同 leg 额外导航尝试、准入拒绝是检查线索，不能单独作为失败根因。
entry / service / clear 不互算重试。status=5 且有姿态交接、到达守卫通过的导航不按失败统计。
明确失败终态保留原代码。守卫误差阈值只从本轮冻结／哈希绑定源码提取；没提取到就不画假阈值线。
hospital_normal_v5 可核对 0.7 秒稳定保持、12 秒窗口；具体位置／航向阈值若无本轮绑定来源仍为 N/A。

## 双／三画面同步对照

选择两或三份真实保存运行，点击“载入选择”。每幅画面使用各自的位姿、任务、计划和证据来源。

- 支持回合零点、已记录语义事件、已记录实体床扰动三种对齐基准。
- 选定基准在某轮缺失时统一播放为 BLOCKED；该轮仍可单独查看。
- 支持统一播放、暂停、重播、倍速、跳转及各画面独立播放／拖动。
- 比较地图身份、任务集合、机器人能力、扰动声明、配置凭据、权重与时钟。
- MATCH 只表示所列保存字段一致，不自动构成完整公平实验或统计显著性。
- unified_bed_local_r1 与 unified_bed_full_r1 的所列字段可匹配。
- 加入 bed_local_a13 后存在配置／地图凭据差异，三画面仍可独立看，但不能作同条件三策略定量排名。

36 构造实例／180 次调用支持规模、扰动机制与策略筛选；保留 FEASIBLE_BUDGET、UNKNOWN、INFEASIBLE、BLOCKED 等原始状态。
成功分母来自完整验证字段，worker 时间中位数与四分位数只统计成功者，并标注样本量，不生成显著性结论。

## 二维栅格实验

- 支持 0.25 / 0.50 / 1.00 m 单元；原图为 1200 × 1000、0.05 m/px，默认半米为 120 × 100 单元。
- 支持 0 / 0.20 / 0.30 m 膨胀；使用包围方形，偏保守，未知区域禁行。
- 点击设置起终点、临时障碍和顺序任务点；支持撤销及清空。
- “连通示例”只生成自由单元中的示例起终点，不代表真实初始位姿。
- A* 为四邻接单机器人静态几何规划。修改草稿后旧路径失效；无路时不产生执行轨迹。
- 导入核对 schema、原 PGM SHA256、尺寸、半径和单元范围。YAML 单独变更后应重建草稿。
- 草稿不会自动持久保存；刷新前手动导出。参数改变会清空草稿，请先导出。
- 不包含实时床、局部 costmap、交通预约、任务依赖、MILP 或 ROS 指令；未生成真实服务 ACK。

## 导出

“证据与报告”提供：

- 白底空间轨迹图 PNG / SVG。
- 泳道甘特图 SVG / PNG。
- 语义事件生命周期 SVG。
- 描述性策略指标 SVG。
- 任务变化 CSV、实验指标 CSV、任务度量 CSV、运行摘要 JSON。
- 中英文图表标题与说明选择；机器任务 ID、原始代码和原始证据内容保留原文。

图表附实验 ID、保存策略、时间单位、原始 trace SHA256 与 metadata。
同步视频导出为 NOT_RUN，未认证连续时间映射和实时编码可靠性。
不把图表中的设计草稿写入正式历史实验结果。

## 实现、缓存与接口

- scripts/serve_clinic_review.py：仅 HTTP 入口。
- src/kaiti_review/data.py：只读解析、时钟与来源适配、五轮 LRU 缓存、原日志字节偏移、事件分页、视觉摘要与离线索引。
- web/clinic/index.html、review.js、review.css：保留兼容与静态栅格功能。
- web/clinic/platform.js、platform.css：七页研究工作台、共享主时钟、泳道、语义链、独立同步回放和导出。

API 只允许固定注册运行、固定报告与注册的媒体资产，不接受任意文件路径。
/api/events 后端筛选分页，/api/raw 按字节偏移读取单行。
前端缓存四轮运行，后端缓存五轮并校验文件 stat 签名；原始地图只初始化一次。
轨迹按 128 样本缓存相机无关 Path2D，光标用时间索引定位，不逐帧扫描事件列表。
绘制性能处理不用于删改原始指标和原文访问。

## 验证与交付

当前研究目录由 [docs/clinic_research_catalog.json](../../docs/clinic_research_catalog.json) 登记，研究含义、节点与代价来源见 [研究实验与任务规划说明](../../docs/clinic_research_experiment_guide.md)。工作台默认显示5个核心运行和3个离线/能力研究卡片；其余运行仍保留在“显示全部历史记录”中。

手动执行浏览器回归（先启动服务）：

    node scripts/check_clinic_workbench.cjs --url http://127.0.0.1:8765/ --out /tmp/clinic_workbench_check_new

执行只读数据和解释适配回归：

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python3 -m pytest -q tests/test_clinic_review_data.py tests/test_clinic_review_explanations.py

上述测试不等于重新执行全部 ROS／Gazebo 实验或独立协议审计。原有完整根目录测试未以本轮结果冒充通过。


## 第二轮：规划可解释性（2026-11-24）

默认演示模式使用研究目录登记的中文名称；每个核心样本显示角色、场景、任务规划、事件/扰动插入时刻、研究内容和证据等级。右上角切换审计模式可查看原始ID。实验选择器支持中文/ID搜索、分类、保存状态、策略、研究内容、收藏、全部历史记录和工程探针筛选；原始目录和ID完全保留。分类元数据来自记录字段和人工研究目录，不按 C/r/W 字符串猜实验含义。显示编号使用类型前缀与稳定ID哈希，不能视为历史重复次数。

研究目录与任务规划的完整解释见 `docs/clinic_research_experiment_guide.md`，其要点也在选择器下方展开显示：任务由常态任务生成器或 event-task/v1 产生，节点来自场景注册服务点，旅行代价来自冻结 `travel_times` 矩阵，约束由依赖、能力、资源、监护和执行承诺共同形成。视频事件的 `video_source_registered` 区域不会伪装成 `sensor_estimated` 三维定位。

空间页增加五种轨迹模式（隐藏、当前任务、最近窗口、全部实际、选中机器人）、节点点击来源详情，以及节点登记/独立旅行时间矩阵。地图保持原坐标和比例。任务区域视口按实际位置和登记点计算，并在不裁切任务范围时移入原地图边界。地图和泳道采用可滚动布局，保证正文、机器人卡片与主表格可读，主要表格14px；不再为把所有内容塞进单屏而缩小文字。

任务页内置显式依赖DAG、持续监护守卫、资源需求表、逐版三机任务序列与语义字典。演示短名称中的“名义R1”表示任务通道，实际执行机器人单列。点击任务定位地图；计划版本间分别核对释放优化、实际改派、顺序变化、时间调整与保护承诺。

泳道支持实际、保存计划、叠加三种模式。填充区分阶段，描边区分机器人；粗框表示保存承诺保护，金色外晕表示释放优化，紫红描边表示实际改派。详细来源保留在任务悬停及证据抽屉。

语义页的事件规划使用 protocol/task ID 与提交记录关联。unified_bed_local_r1 的 E1 核验提交为187.65秒，不再使用不相关的0.56秒初始提交。人体空间结构资格、人体时效资格、机器人定位来源分别展示。

规划页增加六版演化和三次动态修复诊断：预算/原CBC终止原因、10/11释放范围、保护前缀、实际改派/顺序/时间调整、触发原因、请求/提交/派发及各自时间口径。首次完整验证解精确时刻未记录，种子准备耗时不替代该字段。

证据页可导出节点、任务字典、实验分类映射、路径接口审查与修复诊断JSON。摘要JSON包含 explanation 与原始来源。缺少未来路径、视频等显示独立“未记录 / N/A”，不写成算法失败。

本轮最初新增的只读验证：

```bash
cd /home/yhc/kaiti_yolopose_framework
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src python3 -m pytest -q tests/test_clinic_review_data.py tests/test_clinic_review_explanations.py
node scripts/check_clinic_workbench.cjs --out /tmp/clinic-regression-new
node scripts/check_clinic_explainability.cjs --out /tmp/clinic-explainability-new
PYTHONPATH=src python3 scripts/audit_clinic_workbench_explainability.py --out /tmp/clinic-registry-new
```

随后补入研究目录、普通用户实验说明及`video_source_registered`目标解释；研究目录计数、角色和任务插入说明见工作台页面与研究实验目录文档。工作台专项回归共15项，核心运行35页切换检查；这些只证明界面与保存证据可读，不是新机器人实验。研究结论和当前主线见[当前研究范围](../../docs/clinic_current_research_scope.md)。

## 应急插入与资源竞争

从首页进入四格对照，或访问 `/factorial.html`。页面自动列出实际工作区 `verification/factorial_*/viewer.json` 中已发布的批次。支持四格条件、快照、归属策略和评价线切换，显示常态延误、任务甘特图、地图目标点、Gazebo 服务记录与观测片段。新批次生成与发布见[实验说明](../../experiments/clinic_priority/README.md)。

## 在线协同配对与界面调整

「在线协同配对」作为原工作台的一项导航，读取 Gazebo 配对审计导出的 `viewer.json`。事件、计划和执行使用共同任务 ID，预测服务和实际服务可在同一甘特图切换。保留回合时钟、确认标记和 G1 预约区间，任务条可查看目标锚点和坐标。

同页的「路径查询拒绝后的重规划」读取最新的 `verification/feedback_repair_*/viewer.json`，可选择原路径拒绝快照，对比原候选、固定分工重算和允许改派重算的交付预测、巡检延误与任务次序。下方保留历史 Gazebo 证据。

「R3 进入 EPW2 的 Gazebo 资格对照」展示导航查询、跟踪结果、PW2 工位许可和实际轨迹。实体床闭环是独立历史回合，页面使用真实服务回执绘制甘特图。没有本地 Clinic 验证目录时，在线视图读取版本化的 `web/clinic/evidence/` 摘要。

「A 区空间站位验收」列出基线、备选点和负对照的实际 Nav2 查询，并展示代表点的跟踪、停稳、回执和实测轨迹。

「人体占用变化如何改变正式核验任务」展示三种人体位置对应的拒绝原因、待核验状态和 MILP 计划，以及备选点的 Nav2 实际请求与正式服务回执。

旧工作台主要用于单轮运行的空间轨迹、时钟回放和逐条日志审阅，`/factorial.html` 是后来新增的四格统计阅读页，两者入口和排版密度不同。进一步统一时可保留原导航与历史日志功能，在「规划与对比」中加入离线／在线计划／实际执行三级视图，共用任务命名、状态样式、颜色、时间轴和证据面板。科研读者可先读图和结论，再展开计算口径与原始证据。本轮将在线结果放回原导航，四格页保留原链接。
