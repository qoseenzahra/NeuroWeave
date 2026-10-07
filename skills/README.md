# Skill 指导与参考资料

当前平台从 `*/skill.json` 加载原生 Skill。Skill 描述可以完成的任务、适用条件、选择规则和方法角色，通过 `method_refs` / `pipeline_refs` 引用独立定义。执行参数和输入输出以 `methods/` 为唯一来源；组合关系由 `pipelines/` 或用户保存的 Pipeline 维护。

分类包含 task（任务统筹）、tool（软件选择）和 dataset（数据集专属）。仅保留规范 Skill ID，不再解析旧版本的 Skill 别名。

`SKILL.md`、原始帮助和参考脚本包含导入时的科学说明与示例；其中旧产品名、环境名、委托层级、安装建议和 Shell 示例属于原始参考语境，不是本分支的运行策略，也不证明相关选项已接入。它们保留来源及许可证信息，模型只能按需读取，不能据此执行任意命令。

修改当前功能说明应编辑 `skill.json`；修改参数契约应编辑对应 `method.json` 并检查依赖 Pipeline。不得对原始脚本、模型类名、来源路径或哈希做产品名的全局替换。被 Method 引用的实现仍按来源和执行契约验证。

维护流程见 [原生结构](../deploy/structured-skill-methods.md)；原始实现归属见 [来源记录](../UPSTREAM.md)。
