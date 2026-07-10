# 序列 MILP 模型规范 v2

本文件描述 `model_version: sequence_arc_v2` 的正式模型。六月历史配置仍走 legacy solver，只用于复现旧 benchmark，不再代表论文最终模型。

## 1. 集合与数据语义

- `I`：机器人；`J`：当前活动服务任务；`R`：共享资源；
- 每台机器人有虚拟起点 `0_i` 和虚拟终点 `n_i`；
- `c_uv`：节点 u 到 v 的实际 travel time；
- `route_resources[u,v]`：路径与资源 region 相交得到的进入/离开比例和安全缓冲；
- task 的 `resources` 只表示服务阶段占用，走廊等移动资源写在 route arc；
- `P`：任务前驱；动态 event task 由 WorldState 创建，不预置在初始问题中。

solver 与 validator 共用 `PlanningProblem`、`TaskAssignment` 和 `ResourceReservation`，不再分别解释 YAML。

## 2. 变量

- `x_ij ∈ {0,1}`：任务分配；
- `a_iuv ∈ {0,1}`：直接后继 arc，包括 start→task、task→task、task→end 和 start→end；
- `q_ij`：MTZ 顺序；
- `s_j/f_j/L_j`：开始、完成和加权延误；
- `E_before_ij/E_after_ij`：逐任务电量；
- `charge_ij`：不超过充电任务最大增益的实际充电量；
- `wait_iuvr`：选中路径在资源 r 前的等待；
- `z_kk'`：两个候选预约区间的顺序；
- `reassigned_j/shift_j`：相对 incumbent plan 的分配和时间变化。

## 3. 序列、时间与同机配送

每个被分配任务恰有一个前驱和一个后继：

```text
Σ_u a_iuj = x_ij
Σ_v a_ijv = x_ij
Σ_v a_i0v = 1
Σ_u a_iun = 1
```

MTZ 与正 travel/service time 共同消除子回路。选中 arc 时：

```text
s_v ≥ f_u + c_uv + Σ_r wait_iuvr
```

任务前驱仍满足 `s_after ≥ f_before`。对于同一 event：

```text
x_i,pickup(event) = x_i,deliver(event), ∀i
```

因此模型不允许隐式物资交接。

## 4. 路径资源预约

路径资源进入/离开时间由 departure、travel offset 和累计等待计算：

```text
enter_iuvr = departure_iu + enter_fraction_uvr * c_uv + cumulative_wait
exit_iuvr  = enter_iuvr + (exit_fraction_uvr-enter_fraction_uvr) * c_uv
```

服务资源使用 `[s_j,f_j]`。两类区间统一输出为：

```text
resource_id, robot_id, task_id, route_arc,
enter_time, exit_time, safety_buffer
```

容量为 1 的资源对选中的预约区间做 disjunctive 互斥。temporary resource 的 `available_from/wait_time` 进入约束与路径相关目标；persistent blocked 且无模型内替代路径时返回 `INFEASIBLE_ROUTE_BLOCKED`，不抛异常。

## 5. 逐任务电量

选中 start→j 或 u→v 时，电量沿直接后继递推：

```text
E_before_v = E_initial - e_move*c_0v
E_before_v = E_after_u - e_move*c_uv
E_after_v  = E_before_v - e_service_v + charge_v
```

并满足：

```text
E_safe ≤ E_before/E_after ≤ E_full
E_after_last - e_return_to_nearest_charger ≥ E_safe
```

充电量是有上界的决策变量，因此不会超过满电上限，也不会因固定增益导致虚假不可行。

## 6. 目标与求解状态

目标包含选中 arc 的 travel、优先级延误、路径相关 resource wait、低电量风险，以及 incumbent 的 reassigned/shifted/order-changed 代价。结果逐项报告 `objective_components`。

Big-M 根据 planning horizon、任务时长和最大 travel 自动计算；正式三车配置默认 CBC `time_limit=5s`、`mip_gap=1%`。输出状态限定为：

```text
OPTIMAL
FEASIBLE
TIME_LIMIT_FEASIBLE
WAITING_FOR_RESOURCE
INFEASIBLE_ROUTE_BLOCKED
INFEASIBLE
ERROR
```

同时记录 runtime、time limit、gap 和 best bound；CBC 日志无法提供字段时使用 `null`，不伪造数值。

## 7. Validator 反例门禁

validator 必须拒绝：缺失/重复分配、能力不符、前驱错误、机器人时空重叠、pickup/deliver 跨车、预约重叠、blocked/未开放资源、电量递推错误、截止时间错误和冻结前缀变化。

运行正式 demo：

```bash
make sequence-milp-demo
make test
```
