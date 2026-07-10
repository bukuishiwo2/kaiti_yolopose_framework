# LTLf 工具门禁

本项目只使用 LTLf 做有限执行轨迹的规格与验收，不参与 MILP 分配，也不自行实现 LTL 解析器或自动机构造算法。

## 冻结工具链

- 生成环境：独立 Conda 环境 `kaiti-ltlf-spot`；
- 生成器：Spot 2.15.1；
- 流程：`from_ltlf → deterministic complete Büchi/sbacc → to_finite`；
- 运行时：仅加载 `configs/generated/ltlf_transition_tables.json`，不导入 Spot；
- 语义：未结束前缀输出 `SATISFIED / VIOLATED / INCONCLUSIVE`，轨迹结束后只输出 satisfied 或 violated；
- scope：event 公式按 event ID 实例化，robot 公式按 robot ID 实例化。

Spot 官方文档明确给出了 `from_ltlf()`、`translate()` 和 `to_finite()` 的有限语义转换流程：<https://spot.lre.epita.fr/tut12.html>。

## 复现命令

```bash
make ltlf-env
make ltlf-build
make ltlf-check
make test
```

冻结的四条公式位于 `configs/ltlf_specifications.json`。任何公式变更都必须重新生成 transition table；`ltlf-check` 会核对源文件 SHA256 和表结构完整性。

## 门禁结论

- 正例：confirmed 后 verify 完成，终止判定为 `SATISFIED`；
- 负例：confirmed 后在 verify 前结束，判定为 `VIOLATED`；
- 未完成前缀：confirmed 后尚未 verify，判定为 `INCONCLUSIVE`；
- scope 隔离：E1 的 `verify_done` 不会满足 E2 的实例。

因此 Spot 路线可用，后续无需降级为手写 trace 条件，也不允许在 ROS Python 环境中增加 Spot 依赖。
