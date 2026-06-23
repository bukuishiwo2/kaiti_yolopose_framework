# MILP Model Spec

## 1. Core Sets And Parameters

- `I`: 机器人集合
- `J`: 任务集合
- `R`: 共享资源集合
- `P`: 前驱关系集合，`(j, j') in P` 表示 `j` 必须先于 `j'`
- `c_i0j`: 机器人 `i` 从初始位置到任务 `j` 的路径代价
- `c_jj'`: 任务 `j` 到任务 `j'` 的路径代价
- `d_j`: 任务持续时间
- `D_j`: 任务截止时间
- `w_j`: 任务延误权重
- `E_i`: 机器人初始电量
- `e_task_j`: 任务服务能耗
- `e_move`: 单位时间行驶能耗
- `M`: Big-M

## 2. Frozen Variables

- `x_ij in {0,1}`: 机器人 `i` 是否执行任务 `j`
- `s_j >= 0`: 任务 `j` 开始时间
- `f_j >= 0`: 任务 `j` 完成时间
- `L_j >= 0`: 任务 `j` 延误量
- `y_jj'^i in {0,1}`: 在机器人 `i` 上 `j` 是否先于 `j'`
- `z_jj'^r in {0,1}`: 在资源 `r` 上 `j` 是否先于 `j'`
- `b_i >= 0`: 机器人 `i` 计划末尾剩余电量
- `m_j in {0,1}`: 任务 `j` 是否偏离旧计划
- `delta_j >= 0`: 任务 `j` 相对旧计划的时间偏移

## 3. Objective

最小化：

`J = alpha*C_travel + beta*C_delay + gamma*C_interrupt + delta*C_resource + eta*C_energy + mu*C_change`

其中：

- `C_travel`: 分配与排序引起的总行驶代价
- `C_delay`: 按优先级加权的截止时间延误
- `C_interrupt`: 中断巡检等常规任务的代价
- `C_resource`: 资源等待或冲突代价
- `C_energy`: 低电量风险与充电代价
- `C_change`: 完整重规划或局部修复时的计划偏移代价

## 4. Frozen Constraints

### 4.1 Unique Assignment

`sum_i x_ij = 1`，对所有必须完成任务成立。

### 4.2 Capability Matching

若 `C_j` 不是 `C_i` 的子集，则 `x_ij = 0`。

### 4.3 Time Consistency

- `f_j = s_j + d_j`
- `L_j >= f_j - D_j`
- `L_j >= 0`

### 4.4 Initial Travel

若 `x_ij = 1`，则：

`s_j >= c_i0j - M * (1 - x_ij)`

### 4.5 Precedence

若 `(j, j') in P`，则：

`s_j' >= f_j`

### 4.6 Same-Robot Non-Overlap

若 `j != j'` 且二者均分配给机器人 `i`，则：

- `s_j' >= f_j + c_jj' - M * (3 - x_ij - x_ij' - y_jj'^i)`
- `s_j >= f_j' + c_j'j - M * (2 - x_ij - x_ij' + y_jj'^i)`

### 4.7 Shared Resource Non-Overlap

若任务 `j` 和 `j'` 均占用资源 `r`，则：

- `s_j' >= f_j + g_r - M * (1 - z_jj'^r)`
- `s_j >= f_j' + g_r - M * z_jj'^r`

其中 `g_r` 是资源释放缓冲。

### 4.8 Dynamic Resource Availability

- `blocked`：对应资源时间窗内禁止任务开始。
- `temporary_occupied`：任务开始时间必须不早于该资源当前的 `available_from`。
- `free`：不增加额外等待。

### 4.9 Energy Safety

- `b_i = E_i - sum_j (e_task_j + e_move * c_i0j) * x_ij + e_charge_i`
- `b_i >= E_safe`

第一版采用保守近似，将任务分配的起点路径代价计入能耗，后续可再细化为顺序相关能耗。

### 4.10 Event Response And Recovery

- 对 `verify_fall`：`s_verify <= t_event + D_response`
- 对被中断但未取消的巡检任务：动态重规划后仍必须回到任务集合。

## 5. Local Repair Rules

- 已完成任务：冻结，不再参与优化。
- 已开始且允许继续执行的任务前缀：冻结。
- 未受影响任务：默认冻结旧分配与旧开始时间。
- 受影响任务：允许重新分配、重排和资源重预约。
- 若局部子问题不可行：回退到完整重规划。

## 6. Solver Policy

- 默认后端：`PuLP + CBC`
- 可选后端：若本机存在 `Gurobi`，允许作为可选求解器
- 不将 `CP-SAT` 作为第一实现主线
