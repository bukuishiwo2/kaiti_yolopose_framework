# Minimal Experiment Spec

## 1. Scenario

本实验冻结三机器人动态家居主案例，用于静态 MILP、动态事件完整重规划和局部修复统一复现。

## 2. Robots

- `R1`: start `A`, battery `80`, capabilities `move,camera,patrol`
- `R2`: start `C`, battery `70`, capabilities `move,camera,patrol,carry`
- `R3`: start `D`, battery `35`, capabilities `move,charge`

## 3. Tasks

- `T1`: `patrol` at `A`, duration `20`, deadline `120`, weight `1`
- `T2`: `patrol` at `C`, duration `20`, deadline `120`, weight `1`, needs `corridor_H`
- `T3`: `verify_fall` at `B`, release `30`, duration `15`, deadline `90`, weight `10`, needs `corridor_H,event_zone_B`
- `T4`: `deliver_supply` from `S` to `B`, release `30`, duration `25`, deadline `120`, weight `8`, needs `corridor_H,supply_point_S,event_zone_B`
- `T5`: `charge` at `D`, release `0`, duration `40`, deadline `180`, weight `4`, needs `charger_D`

前驱关系：

- `T3 -> T4`

## 4. Resources

- `corridor_H`: capacity `1`, initial `free`
- `charger_D`: capacity `1`, initial `available`
- `event_zone_B`: capacity `1`, initial `available`
- `supply_point_S`: capacity `1`, initial `available`

## 5. Dynamic Script

- `t=30`: 产生 `fall_confirmed@B`
- `t=45`: `corridor_H -> temporary_occupied`
- `t=80`: `corridor_H -> free`

## 6. Metrics

- 任务完成率
- 事件响应开始时间
- 加权延误
- 共享资源冲突次数
- 充电可行性
- 完整重规划时间
- 局部修复时间
- 被修改任务数

## 7. Acceptance Commands

```bash
python3 scripts/run_milp_planner.py --config configs/planner_minimal_experiment.yaml --backend pulp
python3 scripts/eval_planner_baselines.py --config configs/planner_minimal_experiment.yaml
python3 scripts/replay_dynamic_planning_case.py --config configs/planner_minimal_experiment.yaml
python3 scripts/eval_local_repair.py --config configs/planner_minimal_experiment.yaml
```

## 8. Local Repair Comparison Case

最小主实验用于验证冻结主链路，但不足以稳定区分 `Full-Replan` 与 `LocalRepair`。为此补一个扩展对比场景：

- 配置文件：`configs/planner_local_repair_comparison.yaml`
- 新增 `T6 / T7`
  - 都位于 `A`
  - `release=50`
  - `duration=25`
  - `resources=[supply_point_S]`
- 用途：制造一个“同一未受扰动资源上的未来对称任务对”，让 `Full-Replan` 可以自由打乱后续顺序，而 `LocalRepair` 通过冻结未受影响任务前缀保留既有安排。

推荐命令：

```bash
python3 scripts/eval_local_repair.py \
  --config configs/planner_local_repair_comparison.yaml \
  --backend pulp \
  --regions configs/planner_regions.yaml \
  --spatial-replay configs/planner_spatial_replay.yaml
```
