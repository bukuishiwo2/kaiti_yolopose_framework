# Clinic语义到规划离线反事实检查（2026-11-18）

## 任务与结论

核对研究内容一、二、三能否在现有Clinic内连通，并先验证语义差异是否能够改变任务与规划。三项研究内容不变；实际工作区为`/home/yhc/clinic_planning_ws`，`experiments/clinic`不是运行位置。

**本轮诊断通过，但图像到仿真执行整链尚未通过。**运行了9类人工编写的协议输入用例和3次不同完整输入的小型MILP，21项诊断断言通过。现有事件有效性确实能够改变任务集合和求解输出；空间位置变化仍被当前编译器固定锚点覆盖。没有启动ROS/Gazebo、没有运行本轮图像推理、没有生成真实服务ACK，也没有验证仿真人体的LSTM识别率。

`audit_passed=true`仅表示诊断断言符合实际；`integration_ready=false`和`observed_end_to_end_semantic_simulation=false`才是本轮整链状态。不能把21项诊断通过写成21项整系统验收通过。

## 方法与输入

入口：[audit_clinic_semantic_readiness.py](../../scripts/audit_clinic_semantic_readiness.py)。只读实际工作区，直接导入既有`EventTaskProtocol`、`dense_tasks`、`bed_contract.config`、`dense_solver`和`dense_validate`。没有改写研究MILP、权重或执行主链；为复现部署配置，对`dt.config`的绑定仅存在于本轮独立Python进程。

协议用例人工提供确认/遮挡、空间输入和核验反馈；**这些不是YOLO/LSTM推理结果，空间输入也没有经过本轮Nav2可达性校验。**其用途是定位跨层信息是否能传下去，不能冒充第一项的识别或第二项的空间验证结果。

求解对照统一使用仿真时间12秒的同一合成物理快照：三机均空闲于既有起点，各保留一项首周期根任务，共3项常态任务。机器人能力、路程表、服务/资源相位、规划权重均取实际配置。该快照由配置构建，不是从某次物理执行分叉得到。所有任务释放/状态一致，仅改变输入协议所得的事件任务。

采用原编译器与原Dense MILP、全自由小问题求解和原独立验证器。每次求解给5秒截止参数，3次均返回`OPTIMAL`并通过验证；这只是离线功能检查，不是严格墙钟预算、性能排名、修复策略比较或具有统计意义的优化实验。完全相同完整输入以哈希复用，不重复求解。

## 结果

| 用例 | 协议/任务结果 | 求解情况 |
| --- | --- | --- |
| 无检测 | 不创建事件任务 | 基线3项常态任务，OPTIMAL，独立校验通过 |
| 已确认但位置无效 | 可存在OPEN事件；不释放事件移动任务 | 与基线完整规划输入相同 |
| 已确认且位置有效 | 核验READY；尚未核验时不生成监护/取送 | 4项任务，OPTIMAL，独立校验通过 |
| 同逻辑观测重复 | 不改变planning view、不重复生成 | 与有效确认的完整输入相同 |
| 短遮挡 | 位置TTL内保持原任务 | 与有效确认的完整输入相同 |
| 位置过期 | 停止向规划视图提供未执行的事件任务 | 与基线完整输入相同 |
| 事件及服务点x坐标移动1米 | 协议目标更新，但编译目标仍为V1 | 第3次不同完整输入求解；OPTIMAL；排程与移动前完全相同 |
| 核验判定no_fall | 不生成监护/取送，事件关闭 | 与基线当前规划输入相同 |
| 核验判定fall | 生成monitor/pickup/deliver及监护覆盖、同车取送/监护分离关系 | 检查任务图；没有为此用例求解或执行完整响应 |

最直观的规划输出差异：

| 项目 | 无事件 | 有效确认事件 |
| --- | --- | --- |
| `E1_verify` | 无 | R1执行，预测122秒开始 |
| `C0_r3_W1` | R1执行，预测206秒开始 | R3执行，预测175秒开始 |
| R1预测路线 | `C0_r1_W1 → C0_r3_W1` | `E1_verify → C0_r1_W1` |

这证明**给定手工语义事实时，现有协议—编译—MILP已能改变常态分工和时序**。不能把不同任务集合下的目标值直接比较成算法收益；也不能把这个空闲初态例子当作活动承诺修复。

位置变化用例的完整请求SHA不同，原因是`protocol_revision`从1变2。移除这一项版本元数据后，其余整个请求相同：任务坐标、锚点、旅行时间等均未变化，求解计划也相同。脚本同时保留完整输入SHA和明确剔除`protocol_revision`的投影SHA，不把它们混为一个口径。

另测：活动monitor在空间证据过期后变为`CANCEL_REQUESTED`，仍保留在活动承诺中等待取消ACK，并未自动释放资源。这与Clinic硬承诺之间的在线取消/安全恢复策略尚未集成，不能直接把位置丢失解释为允许中断监护或换车交付。

## 原始证据、回归与失败

原始输出留在实际工作区：

```text
verification/semantic_readiness_2026-11-18_a1/  # 首轮诊断及3次求解，保留
verification/semantic_readiness_2026-11-18_a2/  # 正式修正后的诊断及3次求解
```

正式统计仅取a2的`summary.json`、`protocol_cases.json`、`inventory.json`、`*_problem.json`、`*_solver.json`和`source_hashes.json`。a1不并入统计。CBC/MPS/解文件仅留本机新目录，不导入仓库。相同输入复用情况逐项记录在summary。

a1的2项诊断断言失败：初版诊断错误地预期位置变化前后整个请求相同，忽略了版本元数据变化。读取差异后仅修正诊断口径，未更改生产编译器/求解器，也未通过删除版本来修改实际送入求解器的请求；a2重新检查并保存完整证据。

专项回归：`tests/test_event_task_protocol.py` **21 passed**。首次普通pytest调用因自动加载ROS `launch_testing`插件、虚拟环境缺少`lark`而在收集前退出；未安装或改动依赖。随后仅对这个纯Python协议测试禁用第三方插件自动加载后通过。没有运行根目录完整测试，也没有修复或绕报旧S1的两项已知失败。

## 复现命令

仅离线，输出必须为不存在的新目录：

```bash
cd /home/yhc/kaiti_yolopose_framework
.venv/bin/python scripts/audit_clinic_semantic_readiness.py --solve \
  --out /home/yhc/clinic_planning_ws/verification/semantic_readiness_repro_new01
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_event_task_protocol.py
```

该脚本是本阶段断点的可复现诊断，刻意检查固定锚点丢位置等当前行为；不是未来部署的生产准入工具。以后修复断点时，需相应更新诊断预期，不得保留“必须丢位置”的断言作为正常验收。

完整接入路线、人物/相机资产及学术结论边界见[三项研究串联可行性评审](../../docs/reviews/clinic_semantic_end_to_end_readiness_2026-11-18.md)。
