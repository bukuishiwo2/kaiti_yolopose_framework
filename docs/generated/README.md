# Generated Graduation Documents

本目录只保存由脚本生成的毕业设计交付文档和同步 manifest。

人工维护源：

- `../graduation_research_plan_v2.md`

生成与检查：

```bash
make docs-setup
make docs-build
make docs-check
```

不要直接修改 DOCX。任何内容变更必须先修改 Markdown，再重新生成 DOCX 和 manifest。
