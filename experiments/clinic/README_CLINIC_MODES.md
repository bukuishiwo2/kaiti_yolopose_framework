# Clinic独立实验模式

统一入口继续为`clinic_experiment.sh`，默认`benchmark`。不改医院、机器人、Nav2、服务/ACK或MILP研究后端。

| 模式 | 常态/应急服务 | 下一周期 | 用途 |
| --- | ---: | --- | --- |
| Benchmark | 18/4 | 固定900秒 | 保持冻结条件，正式同口径对照 |
| Standard v2026-11-17.1 | 18/4 | max(650秒,实际事件关闭+15秒) | 去掉部分固定周期等待 |
| Fast v2026-11-17.1 | 12/4 | 实际事件关闭+15秒 | 首周期9项保持，下一周期只保留每机首项 |

三种配置在`config/clinic_modes/*.json`，记录版本、种子、原场景哈希、目标时间窗和完整任务数。Fast的300–500、Standard的600–850仿真秒是尝试目标，不是通过条件；当前保持路线和90秒常态服务，可能达不到目标。仅减少下一周期任务，不伪造成功。

先运行离线门禁（新输出目录），再检查、短集成及最小闭环；失败停止，不自动循环重跑：

```bash
cd /home/yhc/clinic_planning_ws
/home/yhc/kaiti_yolopose_framework/.venv/bin/python tools/verify_experiment_modes.py --out verification/clinic_modes/mode_offline_gate_new01
./clinic_experiment.sh check --out verification/clinic_runtime/modes_check_new01
./clinic_experiment.sh smoke --name modes_smoke_new01 --domain 79 > modes_smoke_new01.log 2>&1
./clinic_experiment.sh run --name fast_new01 --domain 79 --policy local_impact --experiment-mode fast > fast_new01.log 2>&1
python3 tools/clinic_run_status.py --name fast_new01
./clinic_experiment.sh report runs/fast_new01 --out verification/clinic_runtime/fast_review_new01 --no-render
```

当前离线门禁发现范围为`verification/*/mode_offline_gate*/summary.json`，检查配置和执行/审计适配的哈希；请按此结构命名输出。完整run还要求匹配执行核心的短集成通过。先确认实际result与独立审计通过，再启动下一个配置：

```bash
./clinic_experiment.sh run --name standard_new01 --domain 79 --policy local_impact --experiment-mode standard > standard_new01.log 2>&1
./clinic_experiment.sh report runs/standard_new01 --out verification/clinic_runtime/standard_review_new01 --no-render
```

Benchmark不更换任务、起点、原时间约束或床扰动规则：

```bash
./clinic_experiment.sh run --name benchmark_local_new01 --domain 79 --policy local_impact --experiment-mode benchmark > benchmark_local_new01.log 2>&1
./clinic_experiment.sh run --name benchmark_full_new01 --domain 80 --policy full_warm --experiment-mode benchmark > benchmark_full_new01.log 2>&1
```

上面两行应顺序启动并分别审计；不为验证本次模式增加而重复Benchmark。Fast/Standard的结果只能说明其自身配置的运行情况，不与旧Benchmark作为同口径算法性能比较。

## 小影响范围离线配对

```bash
/home/yhc/kaiti_yolopose_framework/.venv/bin/python tools/benchmark_sparse_repair.py --out verification/sparse_pairs_new01 --cases 12 --budget 5 > sparse_pairs_new01.log 2>&1
```

12个固定种子，3台机器人、9/12/15项后缀任务，两类扰动：末端资源占用延长、单机器人可用时间延后。局部范围为1/15～1/3。每对相同输入哈希、变化权重、共同种子与预算；策略执行顺序交错。原MILP/闭包函数直接复用，独立外层5秒墙钟截止：届时结束自有CBC子进程并返回已验证共同种子，不让CBC软限时超时改变公平预算。终止时未验证的中间解不使用。

首次可行时间指完整共同种子返回并经约束验证的时间，非CBC内部首次发现时间，亦不意味着在线控制器已经提交此解。表内求解时间包含建模、种子和搜索；外部进程总墙钟另记。截止后的杀进程/序列化有毫秒级开销。原始CBC/模型文件和失败日志留文件，状态工具只读取尾部最多64KiB，不输出历史轨迹数组。

本轮结果与边界见项目`reports/benchmarks/clinic_sparse_repair_and_modes_2026-11-17.md`及`verification/scoped_modes_2026-11-17/`。Token用量仅在平台提供真实计数时报告，本次无可核实接口，不估算。
