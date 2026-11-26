# Clinic 优先级配对实验

本实验对应当前论文主线的三个优先问题。

1. 常态任务执行中插入一个应急事件。
2. 固定地图位置和机器人状态，只改变事件语义状态。
3. 在真实 YOLO Pose + LSTM 日志上回放短时缺失、持续低质量和恢复观测。

入口脚本为 `run.py`。它只读取已保存的 Clinic 工作区快照和真实模型因果日志，不启动 ROS/Gazebo，不派发任务，不修改原始运行证据。

```bash
.venv/bin/python experiments/clinic_priority/run.py \
  --out /home/yhc/clinic_planning_ws/verification/priority_NEW
```

输出目录必须不存在。正式结果保存在 Clinic 实际工作区，因为其中包含求解器日志、问题快照和哈希协议。脚本输出 `protocol.json`、`planning.csv`、`quality.json`、`semantic/` 和每个方法的独立求解证据。

方法含义：

- `B1`：最早可服务插入，保持常态任务原有归属和顺序。
- `retime`：固定应急角色和常态归属，保留常态任务相对顺序，允许选择插入位置和时间。
- `fixed_owner`：固定应急角色和常态归属，允许后缀重排与调时。
- `local_owner`：开放应急角色和原归属失效任务的合法归属。其余常态任务保持原归属，后缀仍可调整时间与顺序。
- `impact_closure`：按依赖、机器人序列和资源传播释放完整影响闭包。
- `full`：开放全部合法后缀归属和时间。

`local_owner` 与 `impact_closure` 分开报告。不能把完整影响闭包称为最小局部修复。

所有结果均为离线模型或协议回放证据。`execution_authorized=false`，不能直接作为新的实体派发计划。

## 四格配对与工作台

新入口使用两份已保存的 `assignment_insert_2026-11-18_h1/formal_01` 快照，分别对比应急响应与 240 秒 G1 预约。两份资格撤销样例单独列为机制检查。原 `run.py` 保留上一轮的语义状态和质量回放复现入口。

```bash
out=/home/yhc/clinic_planning_ws/verification/factorial_NEW
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python experiments/clinic_priority/factorial.py --out "$out"
.venv/bin/python scripts/serve_clinic_review.py --port 8766
```

打开 `http://127.0.0.1:8766/factorial.html`。新批次生成 `viewer.json` 后刷新可选。审计或添加实际记录后，用 `publish.py "$out"` 重建工作台数据。

固定角色执行见证及视频观测导出：

```bash
source /home/yhc/clinic_planning_ws/support/clinic_runtime/environment.sh
v=/home/yhc/clinic_planning_ws/verification/visual_positive_2026-11-18_c1
.venv/bin/python scripts/run_clinic_visual_execute.py --gate "$v/offline_gate_current" \
  --certificate "$v/a_qualification_audit/A.json" --region A --video fall-01-cam0 \
  --verdict "$v/fall01_explicit_review.json" --out "$out/gazebo_fixed_reference" --domain 96 --timeout 850
.venv/bin/python scripts/audit_clinic_visual_positive.py --run "$out/gazebo_fixed_reference" \
  --out "$out/gazebo_fixed_reference_standard_audit" --no-controlled-cancel
.venv/bin/python experiments/clinic_priority/evidence.py "$out"
```

该 Gazebo 入口复跑 A 区固定角色短队列，使用空闲域。同条件的固定与改派配对需要保留匹配计划和对应的路径、资源及服务资格证据。详见[四格结果与用例筛查](../../reports/benchmarks/clinic_factorial_2026-11-25.md)。

## 同阶段 Gazebo 在线协同配对

`online_pair.py` 读取 `runs/dense_loop_a13/00_normal` 的已接受巡检计划，采用当前 Clinic Gazebo、Nav2 和服务资源进程。两组均在三台 W1 和 R1 W2 完成后安排核验，在核验服务开始时派发 R2 W2。真实核验成功 ACK 接收时注入预先声明的阳性结论并提交 G1 的 240 仿真秒预约。预约收到资源管理器确认后，由快照和最新任务图进行响应规划。固定分工组保留未派发常态归属，允许改派组开放共同资格域内的常态归属。

使用匹配签名的 A 区角色证书，另读取已审计的 R2 访问 DL、接收服务 ACK 并驶离释放的记录。仅开放该站的 R2 常态跨机候选，实际方案中的跨机转换在计划提交前查询 Nav2，派发及服务继续经过原有门禁。在线样本使用受控场景证据和真实服务回执。

```bash
source /home/yhc/clinic_planning_ws/support/clinic_runtime/environment.sh
pair=/home/yhc/clinic_planning_ws/verification/online_pair_NEW
mkdir -p "$pair"
.venv/bin/python experiments/clinic_priority/online_pair.py run --out "$pair/fixed_NEW" --policy fixed --domain 96
.venv/bin/python experiments/clinic_priority/online_pair.py run --out "$pair/full_NEW" --policy full --domain 97
.venv/bin/python experiments/clinic_priority/audit_online_pair.py "$pair" --shadow
.venv/bin/python scripts/serve_clinic_review.py --port 8767
```

只使用空闲 ROS 域，输出叶目录名在同时运行的 Gazebo 实例中须唯一，现有启动器用该名字生成分区标识。审计从运行日志复核初始计划、任务域、承诺、预约和实际服务反馈。结果可在工作台的「在线协同配对」页查看。

## 路径拒绝反馈重规划

回放使用两次实际 Nav2 路径查询拒绝。只禁用被拒的任务衔接，在同一快照分别重算允许改派和固定分工，输出独立验证、求解日志和工作台数据。两种重算均为离线预测。使用新的输出目录。

```bash
v=/home/yhc/clinic_planning_ws/verification
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python experiments/clinic_priority/feedback_repair.py \
  --out "$v/feedback_repair_NEW" --runs \
  "$v/online_pair_2026-11-26_06/full_a6" "$v/online_pair_2026-11-26_07/full_a7"
```

在线入口的 `--repair-path-rejection` 仅在提交前一次路径查询中止且返回空路径时启用同一重算，并重新执行跨机路径查询与提交校验。路径校验超时、事件或资源状态变化、前缀冲突均停止提交。替代计划进入 Gazebo 配对前，仍需核验新的跨机衔接与 R3 在监护占位期间进入 EPW2 的执行条件。[两份回放结果](../../reports/benchmarks/clinic_feedback_repair_2026-11-26.md)

## EPW2 进站资格对照

在空闲 ROS 域顺序运行两个条件。探针将 R2 和 R3 放回历史实测位置，分别将 R1 放在监护位和核验位，保留 G1 预约、事件占区及原 PW2 到达、租约和服务门禁。输出用新路径。

```bash
source /home/yhc/clinic_planning_ws/support/clinic_runtime/environment.sh
v=/home/yhc/clinic_planning_ws/verification
batch="$v/epw2_qualification_NEW"
for condition in occupied vacant; do
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
    experiments/clinic_priority/qualify_epw2.py --condition "$condition" --domain 96 \
    --out "$batch/epw2_${condition}_NEW"
done
.venv/bin/python experiments/clinic_priority/publish_epw2.py "$batch" \
  --audit "$v/visual_bed_2026-11-18_d1/bed_audit_04/summary.json"
```

工作台默认读取本机验证目录。远端克隆也可通过工作台服务读取库内的只读发布摘要。[实测结果](../../reports/benchmarks/clinic_epw2_qualification_2026-11-26.md)

## A 区空间站位分阶段验收

先查询预登记基线、两个备选点和占用栅格负对照，再按预设次序实跑首个通过的新站位。筛选与跟踪、停稳、同任务服务回执分字段记录。入口使用原 Nav2、到达守卫和 worker，输出 `fixture.json`、`summary.json`、`trace.jsonl` 与工作台摘要。

```bash
source /home/yhc/clinic_planning_ws/support/clinic_runtime/environment.sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  experiments/clinic_priority/qualify_spatial_stand.py --domain 96 \
  --out /home/yhc/clinic_planning_ws/verification/spatial_stand_NEW
```

使用空闲 ROS 域与新输出目录。工作台「在线协同配对」可查看坐标、筛选结果和代表点轨迹。[实测报告](../../reports/benchmarks/clinic_spatial_stand_2026-11-26.md)

## 人体占区与正式核验目标切换

同一个 Gazebo 回合依次改变登记人体位置，读取 R1 的实际人体安全占区和 Nav2 查询。用同一任务协议更新核验目标。通过筛选的方案分别提交原 Clinic MILP，目标为空的任务保持待核验。随后恢复切换条件，重新查询并真实执行一次核验任务。输出保留原生请求、求解、实际导航命令和回执。

```bash
source /home/yhc/clinic_planning_ws/support/clinic_runtime/environment.sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  experiments/clinic_priority/verify_stand_switch.py --domain 96 \
  --out /home/yhc/clinic_planning_ws/verification/verify_stand_switch_NEW
```

使用空闲 ROS 域和新目录。受控人体占区只在该实验进程内启用。工作台「在线协同配对」读取实测摘要。[实测报告](../../reports/benchmarks/clinic_verify_stand_switch_2026-11-26.md)

## 站位切换后的 A 区三机应急响应

加 `--response` 复用站位选择和正式核验。R3 先接受原 TL 巡检，R1 在南侧完成核验，随后按原工作区 MILP 安排 R1 监护和 R2 取送。响应提交前记录新衔接的 Nav2 查询，核对续行计划并保护 R3 已派发任务的身份和工位。通过的回合用 `--after-patrol` 让 R1 在 TL 巡检驶离和实际释放后再去 M1。完成条件为核验、监护、取送、交付、巡检和租约释放均有回执。

```bash
source /home/yhc/clinic_planning_ws/support/clinic_runtime/environment.sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
  experiments/clinic_priority/verify_stand_switch.py --response --after-patrol --domain 98 \
  --out /home/yhc/clinic_planning_ws/verification/stand_switch_response_NEW
```

使用空闲 ROS 域和新输出目录。工作台以 `stand_switch_response_*` 读取此实验。[报告](../../reports/benchmarks/clinic_stand_switch_response_2026-11-26.md)
