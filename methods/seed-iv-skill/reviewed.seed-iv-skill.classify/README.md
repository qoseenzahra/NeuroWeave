# SEED 按受试者留一交叉验证

调用现有实现：skills/seed-iv-skill/scripts/classify_seed_iv.py。输入保持只读，输出写入独立任务目录。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
