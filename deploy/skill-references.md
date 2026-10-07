# Skill 按需参考资料

本次整理取消特殊 `SKILL.md` 文件。105 个规范 Skill 的加载、选择和执行仍依据 JSON；参考资料只补充背景和结果解释。

## 内容处理

- 103 份旧文档移除；其中 95 个 Skill 的背景、科学限制、方法解释、数据集特征及来源整理到 `references/notes.md`。
- `dataset-inspector`、`table-cleaning`、`report-builder`、`image-batch-processing`、`beautiful-log`、`claw-shell`、`skill-updater`、`harness-core` 的旧说明主要重复当前目录或描述旧执行架构，使用现有 JSON 概览，不为数量补写文档。
- 为原来没有 Markdown 的 `software-ants`、`software-mrtrix3` 补充空间变换、插值、梯度、降噪、连接组检查和能力边界说明，引用官方文档及当前方法契约。
- DWI 已有 7 份 MRtrix3 3.0.8 原生帮助保持原字节与来源哈希，同时登记为可按主题读取的资料。方法实现、执行契约、Pipeline 和原始来源清单不改写。
- 清除 JSON 规划能力里指向已删除文档的 568 条来源/命令引用。旧行号和哈希不重定向到新说明；规划能力仍可讨论，不因参考资料增加执行能力。
- 没有独立实现来源的 94 个规划入口引用当前 `skill.json` 作为规划定义来源，不将其标记为执行验证。
- 清除规划能力中的旧 `claw-shell` 委派与环境条件，保留规划入口的身份和当前能力边界。

原始说明的作者、许可和来源保留在整理后的资料及仓库归属记录中；历史来源清单记录导入快照，而不是当前文件是否存在。

未保留独立参考资料的 `beautiful-log`、`claw-shell`、`skill-updater`、`harness-core` 原说明作者均为 chengwang96，原标注许可为 MIT License；来源快照和许可记录继续保留。其余四份简短中文说明未单独署名或标注许可。

## 登记与读取

`skill.json` 的 `references` 是包含 `id`、`title`、`path` 的列表。ID 在本 Skill 内唯一，路径必须是 `references/` 下的 Markdown；无补充资料时使用空列表。

`read_skill_reference(skill_id, reference_id?, offset?, max_chars?)` 不接受文件路径。省略 ID 读取首篇，结果包含可选主题列表；明确 ID 时仅读取相应资料。没有登记资料时返回 JSON 概览。默认 6000 字符、最多 12000 字符，按 `next_offset` 继续阅读同一主题。

HTTP 接口仍为 `/api/skills/{id}/reference`，使用 `reference_id` 选择主题。未登记 ID 返回 404，参数超出声明范围返回 422，读取时路径越界或文件丢失返回 400。Skill 详情仅返回主题元数据，避免目录加载时读取全文。

目录加载验证登记字段，发布检查验证文件存在与目录边界；读取时再次检查解析后的路径，阻止符号链接跳出当前 Skill 的参考目录。没有 Markdown 不妨碍 Skill 加载，已登记但丢失的文件应修正登记，不能静默当作正常参考。

## 维护

在 JSON 维护当前适用范围、选择规则和方法引用。在 Methods 维护准确参数与端口，在 Pipelines 维护步骤连接。参考资料保留独有知识，删除与契约重复或冲突的操作说明；新工具有必要时补充原理、前提、质量检查及来源，不复制整套软件手册。

修改原生帮助或实现时仍需要审阅相应 Method 和执行证据；整理参考文案不代表所有科学流程已在真实数据上验证。
