# Clinic 评审工作台第二轮：规划可解释性

日期：2026-11-24。目标：在保留七页工作台与原功能的基础上，使研究人员可以区分任务语义、实际执行、计划约束、修复范围与证据缺口。

## 修改范围

实现位于 `/home/yhc/kaiti_yolopose_framework`，只读数据位于 `/home/yhc/clinic_planning_ws`。本轮未启动 ROS/Gazebo、未派发任务、未求解新的研究实例；未修改原始实验目录、ID、地图、结果、日志、规划/修复算法或执行接口。原工作区其他未提交改动保留。

|文件|变更|
|---|---|
|src/kaiti_review/explanations.py|新增结构字段驱动的任务字典、节点登记、事件关联、实验元数据、路径来源与修复诊断|
|src/kaiti_review/data.py|只读聚合 explanation，补充事件输入与任务约束比较凭据|
|scripts/serve_clinic_review.py|目录API暴露元数据，显式注册新增静态文件|
|web/clinic/index.html|接入解释层脚本和样式|
|web/clinic/platform.js|修正事件规划关联、轨迹模式、防碰撞标签、节点命中、友好名称、泳道及状态维度|
|web/clinic/review.js|任务名称及中文检索，保留原有任务度量|
|web/clinic/explain.js、explain.css|新增选择器、演示/审计模式、关系视图、来源与诊断、可读布局和导出|
|scripts/check_clinic_workbench.cjs|保留原功能回归；布局断言改为可读地图及滚动泳道|
|scripts/check_clinic_explainability.cjs|本轮13组浏览器专项验证及截图|
|scripts/audit_clinic_workbench_explainability.py|全部历史运行只读兼容审计、登记导出、保护哈希复核|
|tests/test_clinic_review_explanations.py|语义来源、归属反例、节点、事件关联和修复诊断回归|
|web/clinic/README.md|补充用户操作、来源边界和验证命令|
|docs/reviews/clinic_node_path_sources_2026-11-24.md|节点、代价、执行接口与资格来源审查|
|docs/reviews/clinic_three_repairs_diagnosis_2026-11-24.md|三次修复诊断与独立算法改进实验清单|
|docs/worklogs/worklog_2026-11-24.md|开发与验证记录|

原有 platform.css 没有覆盖重写；新增 explain.css 在末尾改进字号、地图大小与响应布局。主表14px，地图/泳道可滚动，优先可读性。

## 结构性结论

- C/r/W 的含义由冻结任务构造代码和结构字段支持。`C0_r3_W2` 名义R3而实际R1执行；固定清空节点 CPW2C 随任务通道，不随实际机器人名改变。
- 重点样本22个节点有独立登记；W不是地图节点，CTL未登记，不做别名扩展。坐标为场景登记，坐标最初采集方式和RMF拓扑属性未获充分证明。
- 空间视图不伪造连通边。已保存旅行矩阵与实际采样轨迹分离；浏览器A*为独立草稿，没有连接MILP/Nav2。
- E1核验提交187.65，排除0.56初始常态提交。注册空间有效、人体位置时效与机器人定位是独立字段。
- 三次修复每次释放10/11后缀任务，实际改派0；有原CBC时间上限停止证据。详细变化、触发与保护任务见诊断报告。
- 结果保存、任务完成、求解状态、硬约束审计与记录完整性独立展示。缺少未来路径等不标作算法FAIL。
- 双/三画面保留独立数据源和同步回放。新增约束检查发现重点局部/全量样本事件任务释放时间不同，因此不标为直接同输入定量比较；配置背景相近不消除实际输入差异。

## 验证与实际证据

第一轮完整网页改版的原始回归收据、截图、历史运行登记和保护哈希保存在本机`reports/demos/2026-11-24_clinic_explainability_vs7bui2_/`，未作为逐运行派生输出上传。后续目录迭代重新运行21项相关Python测试和15项工作台专项检查，并对5个核心运行执行35次页面切换检查。证据收据位置为`reports/demos/2026-11-24_clinic_loading_recheck/`中的 README、manifest、浏览器检查、逐页状态与研究目录审计。

这些只证明只读解析、目录分类、页面可解释性和已有证据查看，不是新ROS/Gazebo实验、算法对照或独立约束审计。110份历史运行可读，5个核心运行默认展示，3个离线/能力实验显示为研究卡片，其他历史数据保持原位。

## 输出登记与证据边界

节点、任务、实验分类、路径、事件规划与修复诊断JSON均由当前代码针对所选运行重新生成；GitHub保留实现和稳定说明，不提交逐运行派生输出、历史源快照或大批浏览器图片。完整边界见节点路径来源与三次滚动修复审查。

未来完整路径几何、精确首次验证时间、连续视频同步、未保存房间多边形、通用安全/可达证明仍缺失；不能由浏览器补造。现有单轮相关修复不支持局部算法普遍优越或创新成立。

## 使用命令

```bash
cd /home/yhc/kaiti_yolopose_framework
python3 scripts/serve_clinic_review.py --workspace /home/yhc/clinic_planning_ws --port 8765
```

浏览器打开 http://127.0.0.1:8765/ 。已有本轮服务时直接刷新。
