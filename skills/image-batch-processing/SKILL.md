---
name: image-batch-processing
display_name: 影像批处理
description: 规划医学或科研影像的批量转换、预处理、质量控制与结果目录。
layer: workflow
skill_type: image-processing
runtime: External tools / Python
status: draft
---

# 影像批处理

先识别输入格式、空间信息与命名规则，再选择已经安装的软件或开源方法。任何批处理都应先对单个样本试运行，并保留输入输出映射和失败清单。

## 安全约束

- 不覆盖原始影像
- 在运行前展示计划和输出目录
- 对失败样本允许单独重试

