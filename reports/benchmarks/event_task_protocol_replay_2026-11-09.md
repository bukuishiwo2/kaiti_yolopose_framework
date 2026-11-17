# 统一事件到任务协议：独立回放实测

日期：2026-11-09。目标：完成研究范围计划M1中的确认跌倒、短遮挡、重复观测、位置无效四类轨迹，统一核验、持续监护和取送的生命周期规则。

## 实际结果

**4类轨迹、37个步骤、1268项手写预期与独立不变量检查全部通过。**新增协议测试21项，连同既有独立DES/计时消融测试18项，共`39 passed in 4.94s`。

| 回放 | 步数 | 检查数 | 实际验证行为 |
|---|---:|---:|---|
| confirmed_fall | 10 | 416 | 先核验，成立后生成M/P/D；未开始目标更新保留ID；监护开始后取物；同机交付；交付完成后监护才结束 |
| short_occlusion | 9 | 358 | 短遮挡保留事件/任务；恢复不重复生成；显式解除后运行监护请求取消，ACK前执行承诺仍在 |
| duplicate_observation | 8 | 233 | 相同消息重发、新消息同语义、重复开始/完成反馈均幂等，不重复生成或推进任务 |
| invalid_position | 10 | 261 | 无位置不生成假导航目标；运行核验失去位置后请求取消；恢复仍等待ACK；同ID新attempt重试；响应任务位置失效后保持但阻止启动，恢复后更新 |

83个保护文件哈希前后不变：78个既有规划/ROS/相关配置/旧等价性脚本，加5个已有独立DES模块。没有修改生产主链或既有DES工厂/求解器，没有安装依赖、接ROS、启动Gazebo/实车。

原始结果：[2026-11-09_173132_925127](../../outputs/event_task_protocol/2026-11-09_173132_925127/)、[summary.json](../../outputs/event_task_protocol/2026-11-09_173132_925127/summary.json)、[逐任务时间线CSV](../../outputs/event_task_protocol/2026-11-09_173132_925127/task_timeline.csv)。每轨迹JSON保留每步原始输入、手写预期、完整快照、生成/保持/更新操作、规划视图和校验结果；source副本与哈希用于复核。输出使用新时间戳目录，不覆盖旧结果。此前开发试跑保留为历史，不替代本次最终结果。

## 明确的语义决定

- `confirmed`是上游证据，尚不等于机器人核验完成；位置/服务点有效时生成verify。`verify.succeeded(result=fall)`之后才创建持续监护、取物和交付任务。
- 未来任务可提前进入规划，但取物实际开始必须等待监护RUNNING；交付还要等待取物实际成功，并绑定物资持有者。不能同一机器人一边持续监护一边取送。
- 持续监护的终点由交付完成和监护完成ACK共同约束；verify固定动作完成不能代替持续监护。
- 同一事件/角色任务ID不变，目标修改增加revision，取消确认后的重试增加attempt。旧执行反馈不能完成新尝试。
- 短遮挡不关闭事件；位置TTL过期或明确无效会阻止启动/请求停止，不能无限续用陈旧坐标。显式解除取消未开始任务，运行任务等待取消ACK，不能提前释放执行承诺。
- 物资已取到但事件解除时标记需要后续处理，不谎报交付成功。

详细字段、状态表、版本语义与适配边界见[协议](../../docs/event_task_protocol.md)。

## 额外回归与错误注入

新增测试覆盖四轨迹逐步预期与确定性、核验no_fall、不允许提前取物/交付、不允许交付前结束监护、监护/取送角色冲突、错误物资owner、旧revision/attempt、短遮挡不无谓触发规划、长时间位置过期、监护和正在取物同时请求取消、迟到成功拒绝、显式解除后的物资处置标记、陈旧观测、消息ID冲突、非有限/错误坐标系、缺失服务点不编造目标，以及独立检查发现过早释放承诺/虚假监护完成。

坏输入被原子拒绝，不允许部分更新事件后再报错。协议不自动执行导航、停止或抓取；回放中的started/succeeded/cancelled是明确的执行桩输入，不能解释成真实机器人已实现对应动作。

## 证据与限制

“统一”是共同参考协议和独立实现，不是已将旧WorldState和旧DES全部迁移。旧WorldState中observe/verify/pickup/deliver与新协议的持续monitor衔接已明确；具体规划/执行适配器尚未接上。

本轮没有证明新事件推断方法优于成熟方法。事件ID、确认状态、空间坐标和服务点为输入；没有做图像跌倒识别、空间安全/可达性、真实监护可见性、通道预约或真实物资操作。每实例单活动事件；monitor执行端健康/失败、任务超时、人员引导和安全交接后续仍需扩展。四轨迹是手写行为验证，不是37个独立环境或1268次成功任务。

下一步适合在独立入口把规划视图接到共同MILP/执行桩，编译完整依赖、监护与取送关系，并加入实际行驶/启动延误。脚本事件与实车识别的验证分工及医院场景调研见[实验设计评审](../../docs/reviews/simulation_real_robot_validation_and_hospital_worlds_2026-11-09.md)。

## 文件与复现

- 新增`src/kaiti_task_sim/event_protocol.py`、`event_replay_cases.py`、`event_replay_validation.py`。
- 新增[scripts/replay_event_task_protocol.py](../../scripts/replay_event_task_protocol.py)、[tests/test_event_task_protocol.py](../../tests/test_event_task_protocol.py)。
- 新增协议、本文、仿真/实车与医院场景评审；更新文档索引与研究范围计划的M1状态。原主链及模型配置未改。

```bash
.venv/bin/python scripts/replay_event_task_protocol.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_event_task_protocol.py tests/test_task_level_simulation.py tests/test_task_repair_ablation.py
```
