# Reports Directory

本目录只保留适合长期提交到仓库的结果摘要，不保存运行中间产物。

## 1. 应放在这里的内容

- benchmark 摘要
- 模型对比结论
- 阶段性实验结论
- 值得长期引用的结果说明

## 2. 不应放在这里的内容

- 原始评估 `csv/json`
- 可视化视频
- 调参中间结果
- 临时分析草稿

这类内容应保留在本地 `outputs/`，需要长期保留时再整理成 Markdown 摘要。

## 3. 命名规则

推荐使用：

- `reports/benchmarks/<topic>_YYYY-MM-DD.md`

当前已归档：

- [UR Fall Benchmark 摘要](benchmarks/urfall_comparison_2026-04-09.md)
- [UR Fall Rule / LSTM / TCN 对比摘要](benchmarks/urfall_rule_lstm_tcn_comparison_2026-04-10.md)

目录索引见：

- [benchmarks/README.md](benchmarks/README.md)
