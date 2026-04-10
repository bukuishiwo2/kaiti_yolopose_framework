# Outputs Directory

本目录是本地运行目录，不属于正式源码内容。

## 1. 典型内容

- 推理输出 `jsonl`
- 可视化视频
- 评估 `csv/json`
- 调参中间结果

## 2. 管理规则

- 这里的内容默认不提交
- 长期需要保留的结论，应整理成 Markdown 摘要后移入 `reports/benchmarks/`
- 临时联调产物保留在本地即可

## 3. 清理方式

```bash
bash scripts/clean_outputs.sh
```
