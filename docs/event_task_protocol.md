# 独立事件到任务协议 event-task/v1

本协议统一目标语义及独立参考回放，供后续感知/事件、任务规划、执行适配共同遵守。实现位于`src/kaiti_task_sim/event_protocol.py`，不导入ROS或生产规划器。

**当前没有替换旧WorldState或旧DES的TaskFactory，没有接入求解器/导航。**“统一”指核验、持续监护和取送采用下述同一参考语义；已有两条链的迁移/适配是后续工作，不宣称全仓库已经使用同一实现。

## 1. 本版范围与前提

- 每条回放一个上游已给定身份的跌倒事件，不做图像识别、多人关联或事件ID推断。
- 输入`confirmed`为上游确认的事件证据，不等于现场核验已经完成；必须收到核验任务的`fall`完成反馈后才释放响应任务。
- `space`由上游提供地图事件位置与各角色服务点。本模块检查坐标/时间/版本有效性，不生成安全区域，不证明服务点的碰撞安全或路径可达。
- 任务反馈是独立执行桩的确认，不是ROS action结果、真实摄像头持续可见性或真实取放证明。`started`代表执行端已检查其到达/就绪条件；本版不实现这些底层检查。
- 时间统一为同一回放时钟的秒。实际接入时必须转换到一致时域；没有将墙钟与ROS时钟混用的隐式约定。
- 固定位置有效期TTL=10秒、物资点(6,4)仅为回放配置，不是实测最优或真实机器人安全参数。生产适配应显式配置/标定。

## 2. 输入消息

共同字段：`schema="event-task/v1"`，非空`message_id`，`kind`，非递减接收时刻`at`；除tick外均需`event_id`。

| kind | 额外字段 | 含义 |
|---|---|---|
| observation | `source_at`、`status=confirmed/occluded`；confirmed需`space` | 上游语义观测，source_at不可在未来；陈旧观测不能覆盖新目标 |
| feedback | `task_id`、`phase=started/succeeded/cancelled`、`robot_id`、正整数`task_revision/attempt`；verify成功需`result=fall/no_fall` | 实际开始/完成或取消确认；没有反馈不自动完成 |
| resolution | `result=no_fall/resolved` | 显式否定/解除事件；不使用短时遮挡当解除 |
| tick | 无 | 推进回放时钟，检查位置过期；无新观测时也需调用 |

确认事件示例：

```json
{
  "schema": "event-task/v1",
  "message_id": "obs-001",
  "kind": "observation",
  "event_id": "E1",
  "at": 0,
  "source_at": 0,
  "status": "confirmed",
  "space": {
    "valid": true,
    "frame": "map",
    "event_xy": [2, 1],
    "service_points": {
      "verify": [2, 0],
      "monitor": [2, 0],
      "deliver": [3, 1]
    }
  }
}
```

位置无效用`space={"valid":false}`，不填假坐标；缺少某角色服务点时该任务保持PENDING，没有可派发目标。不能用事件区域中心替代缺失的安全服务点而不说明假设。

重复message_id、相同逻辑内容为幂等；接收时刻可改变。相同ID不同内容拒绝。新ID但同一语义观测不重复建任务；同一次反馈换ID重发也幂等。更晚源时间的相同位置可刷新有效期，不因此改任务ID或目标revision。同源时刻冲突内容拒绝。所有拒绝均为原子操作，不留下半个更新。

时间推进可使位置过期，即使到达的是重复消息也不能无限续用旧位置；这是时效变化，不是重复消息导致任务重新创建。

## 3. 事件、任务身份与版本

事件生命周期`OPEN → COMPLETED`或`OPEN → CLOSED`，终态的相同事件ID不会被普通观测复活。短遮挡只是`perception=occluded`，不改变事件身份；新一轮独立事件需上游分配新ID，本版每实例只接受一个ID。

任务ID固定为`<event_id>:verify/monitor/pickup/deliver`。位置更新、暂停、取消后重试不换ID；目标/空间版本或取送owner条件改变时增加任务`revision`，取消确认后重试增加`attempt`。已成功或已取消的终态记录不可改写。

`execution_revision/execution_target`保存实际已启动的那一版承诺。目标更新时不能把机器人正在执行的目标静默改成新点。取消确认须匹配这版实际执行，而非新目标revision；旧尝试迟到的成功不能完成新尝试。

`world_revision`只在业务状态改变时增加。输出另给`planning_changed`：仅上游短遮挡状态改变但任务输入不变时，它为false，不应仅凭收到消息就触发规划。重复消息/反馈不会增加业务revision；真实的时间过期或目标变化除外。

## 4. 任务何时生成、保持、更新和取消

| 条件/反馈 | verify | monitor | pickup | deliver |
|---|---|---|---|---|
| 确认跌倒，位置有效 | 首次生成；有服务点则READY | 不生成 | 不生成 | 不生成 |
| 确认跌倒，位置无效 | 保留事件，暂不生成导航任务 | 不生成 | 不生成 | 不生成 |
| verify开始 | RUNNING | 不生成 | 不生成 | 不生成 |
| verify完成且fall | SUCCEEDED | 首次生成，目标有效则READY | 首次生成PENDING，等待monitor实际开始 | 首次生成PENDING，等待pickup完成与monitor有效 |
| monitor开始 | 保留成功事实 | RUNNING | 满足条件后READY | 仍等待pickup完成 |
| pickup完成 | 保留 | 持续RUNNING | SUCCEEDED，记录物资owner | READY，强制同一物资owner交付 |
| deliver完成 | 保留 | 允许结束，仍需自身完成反馈 | 保留 | SUCCEEDED |
| monitor完成反馈 | 保留 | 只有deliver已完成才接受SUCCEEDED | 保留 | 保留；四任务成功后事件COMPLETED |
| 短遮挡且位置未过期 | 保留 | 保留 | 保留 | 保留 |
| 未开始任务的有效目标更新 | 同ID更新目标revision | 同左 | 必要时同步空间版本 | 同左 |
| 位置无效/过期或运行目标改变 | 未开始者PENDING；运行者请求取消 | 同左 | 监护不再有效时阻止启动/请求取消 | 同左 |
| 位置恢复 | 同ID重新就绪；若取消待确认仍等待ACK | 同左 | 仍须monitor启动 | 仍须pickup成功/monitor有效 |
| 明确no_fall/resolved | 未开始者取消；运行者CANCEL_REQUESTED | 同左 | 同左 | 同左 |

“生成”和“允许启动”不同：核验成立后可把完整响应任务图交给规划器，提前安排未来取送；但执行不能将PENDING当READY。持续监护不是固定时长verify的别名：必须覆盖取物开始到交付完成，并由独立开始/完成反馈约束。

事件源短遮挡与监护执行端失效不是同一信号。本版短遮挡测试仅验证事件与任务保持，假定监护执行桩仍在服务；没有验证人体始终可见。监护自身失效/观测健康、失败重试、任务超时策略还需后续执行契约扩展，不能用本轮结果声称物理持续监护已通过。

## 5. 状态与执行承诺

任务状态：`PENDING`、`READY`、`RUNNING`、`CANCEL_REQUESTED`、`SUCCEEDED`、`CANCELLED`。

- READY才接受started；取送需monitor当前RUNNING且目标有效；deliver还需pickup实际成功。
- 实际取物与交付机器人相同，且与监护者不同；同一机器人不能同时有两个RUNNING或取消待确认的承诺。本版只声明任务能力需求，机器人能力匹配/任务选择属于后续规划器，不在这里求解。
- CANCEL_REQUESTED仍占用该机器人执行承诺，位置恢复也不能自动撤销取消。收到匹配cancelled后才释放；若事件仍OPEN，同ID、attempt+1等待再执行；若事件CLOSED则终态CANCELLED。
- 位置失效不直接关闭事件，不把正在运行的服务静默记为停止。实际停止由执行端负责并反馈，本模块不发送停车命令。
- 取物后事件解除时，`cargo_disposition=REQUIRES_FOLLOWUP`，不伪造已交付；真实退货/安全交接不在本版范围内。

## 6. 规划输出与后续适配

`planning_view()`输出：

1. `tasks`：目标有效的PENDING/READY未来任务，包含能力、完成依赖、运行守卫、目标、owner限制及revision。
2. `active_commitments`：RUNNING/CANCEL_REQUESTED的实际执行，包括旧execution_target；尚未确认释放。
3. `completed_facts`：真实成功反馈对应的历史事实，供依赖核对；其旧目标不是新导航目标。
4. `relations`：监护覆盖取送、同机取送/异机监护；`world_revision`用于版本追踪。

此输出不是旧MILP输入的直接替代。适配器必须编译所有依赖与关系，例如`s_monitor<=s_pickup`、`f_monitor>=f_deliver`及取送owner绑定，并保留当前事实与执行承诺；不能只拿任务坐标而丢掉守卫。当前没有生成通道预约、完成物资处理、计算机器人运动或连接旧求解器。

旧WorldState含uncertain→observe的策略，本版从confirmed开始，不删除旧功能，也未实现observe迁移。脚本注入区域事件可用相同输入协议，后续真实感知也需转成此协议，而不是分别写两套任务语义。

## 7. 回放与验证

```bash
.venv/bin/python scripts/replay_event_task_protocol.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_event_task_protocol.py tests/test_task_level_simulation.py tests/test_task_repair_ablation.py
```

四类手写轨迹与逐步预期位于`event_replay_cases.py`；独立校验器位于`event_replay_validation.py`，不调用状态转换内部函数。实际结果见[回放实测](../reports/benchmarks/event_task_protocol_replay_2026-11-09.md)。通过协议回放只说明本版规则满足这些测试，不是感知准确率、真实定位/监护证明或方法先进性比较。
