# 分支文档索引

这些指南描述当前仓库的使用和维护边界。任务管理开发分支的完整变更与清理范围见 [审阅说明](task-management-review.md)。当前执行定义以 Method JSON 和注册 Runner 为准，运行环境以目标服务器的实时探测和 Dry-run 为准。带日期的测试报告、版本标识及备份路径是当时的记录，不能作为另一版本的就绪证明。

## 使用与维护

| 主题 | 文档 |
| --- | --- |
| 开发环境、项目入口 | [项目说明](../README.md)、[前端开发](../frontend/README.md) |
| Skill / Method / Pipeline 定义及扩展 | [原生结构](structured-skill-methods.md)、[参考资料边界](../skills/README.md)、[参考资料整理](skill-references.md)、[专属指导整理](skill-guidance.md) |
| 分类目录、节点画布与 Pipeline 使用 | [资源库](native-library.md)、[可靠性与编排](reliability-and-pipeline-authoring.md)、[方法参数与转换预设](pipeline-parameters-and-presets.md) |
| 用户已发布 Pipeline 的删除与恢复 | [发布删除](published-pipeline-deletion.md) |
| 任务管理、独立 Pipeline 任务和分支审阅 | [任务管理](task-management.md)、[审阅说明](task-management-review.md) |
| 需求理解、候选检索与流程验证 | [检索链路](library-upgrade.md)、[需求契约](task-planning-contracts.md)、[灵活对话](flexible-dialogue.md) |
| 方法语义与规划邀请 | [方法契约与邀请](method-contracts-and-invitations.md) |
| 数据集、输出目录与文件授权 | [目录管理](workspaces.md) |
| 历史消息与旧输出复用 | [历史加载](history-and-existing-inputs.md)、[历史结果输入](historical-run-inputs.md) |
| 运行环境、节点和资源 | [运行条件](skill-runtime/README.md)、[Slurm 执行](slurm-execution.md) |
| 双语维护与执行证据 | [目录文案](catalog-polish.md)、[质量检查](catalog-quality.md) |
| 模块边界及 CI | [代码维护](code-architecture.md) |

## 配置与部署记录

- [公共 Python 环境](python-environments/README.md) 记录环境安装方式和初始验证；[Slurm 管理](slurm-admin.md) 与 [记账及备份](reliability-upgrade.md) 记录集群维护。
- [3002 可靠性发布](reliability-and-pipeline-authoring.md)、[编辑器发布](pipeline-editor-ui.md) 和 [画布发布](pipeline-canvas-ui.md) 保留各自的发布范围、备份及回退信息。不能把其中某次前端发布理解为同时更新了后端。
- [main 前端迁移](frontend-migration.md) 与 [当时的功能对齐验收](../frontend/docs/main-parity.md) 是旧迁移记录，不是本分支 3002 的部署清单。
- `method-verification/`、`software-contracts/`、`skill-runtime/*.json` 保存方法验证、软件帮助或历史探测证据；只有与当前方法和执行依赖匹配的证据才计入当前验证状态。

发布前比较本地与服务器差异，不覆盖服务器有效改动。不要清理活跃任务引用的代码、数据库、输出或运行记录；服务器文件删除需要先核对精确清单及使用情况。本文不授权执行历史报告里的集群重启或清理命令。
