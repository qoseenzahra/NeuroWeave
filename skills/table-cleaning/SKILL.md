---
name: table-cleaning
display_name: 表格清洗
description: 为 CSV、TSV 或 Excel 数据设计缺失值、类型、重复项和异常值处理流程。
layer: workflow
skill_type: data-cleaning
runtime: Python / pandas
status: ready
---

# 表格清洗

先确认主键、目标字段和不可修改字段。生成清洗方案时保留原始文件，记录每个规则影响的行数，并在输出前执行模式和行数校验。

## 推荐顺序

1. 编码与分隔符识别
2. 字段类型推断
3. 缺失值与重复项检查
4. 异常值规则确认
5. 输出与清洗报告

