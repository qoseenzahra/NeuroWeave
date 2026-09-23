# 表字段、缺失和主键候选检查

调用现有实现：pandas.read_csv, pandas.DataFrame.duplicated。输入保持只读，输出写入独立任务目录。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
