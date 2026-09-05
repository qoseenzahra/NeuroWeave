---
name: dataset-inspector
display_name: 数据集巡检
description: 扫描数据集结构，识别文件类型、规模、字段和常见质量问题。
layer: workflow
skill_type: data-understanding
runtime: Python
status: ready
---

# 数据集巡检

在开始处理前建立数据概况。先确认用户允许访问的根目录，再汇总文件数量、扩展名、大小和目录层级；对表格抽取字段与缺失率，对影像只读取必要的元数据。

## 输出

- 数据集概览
- 潜在质量问题
- 后续处理建议

LocalFlow 已为该 Skill 接入受信任的只读 `dataset.inspect` Runner。流程确认且
Dry-run 通过后，用户可显式启动扫描；Runner 只读取所选数据集，并把
`dataset_profile.json` 写入隔离的运行输出目录，不修改源数据。
