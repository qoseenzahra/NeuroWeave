# 使用与维护文档

这些指南描述当前 main 的功能、配置和维护方式。执行契约以 Method JSON 与注册 Runner 为准，运行可用性以目标环境和本次 Dry-run 为准。

## 产品与开发

| 主题 | 文档 |
| --- | --- |
| 项目入口与开发检查 | [项目说明](../README.md)、[前端开发](../frontend/README.md) |
| Skill / Method / Pipeline 定义 | [原生结构](structured-skill-methods.md)、[Skill 指导](../skills/README.md)、[按需资料](skill-references.md)、[专属指导](skill-guidance.md) |
| 目录、画布与复用 | [资源库](native-library.md)、[Pipeline 画布](pipeline-canvas-ui.md)、[编排与预检](reliability-and-pipeline-authoring.md)、[参数与转换预设](pipeline-parameters-and-presets.md) |
| 任务创建、配置和运行历史 | [任务管理](task-management.md)、[流程裁剪](workflow-scope-editing.md) |
| 用户 Pipeline 生命周期 | [发布删除与恢复](published-pipeline-deletion.md) |
| 模型意图、检索和规划校验 | [多轮对话](flexible-dialogue.md)、[检索链路](library-upgrade.md)、[需求契约](task-planning-contracts.md)、[输出语义与规划邀请](method-contracts-and-invitations.md) |
| 文件访问与权限 | [数据集和输出目录](workspaces.md) |
| 历史加载与输入复用 | [历史加载](history-and-existing-inputs.md)、[历史结果输入](historical-run-inputs.md) |
| 模块职责与 CI | [代码维护](code-architecture.md) |

## 服务器与运行维护

| 主题 | 文档 |
| --- | --- |
| 当前服务拓扑、版本核对与发布边界 | [服务器部署](server-deployment.md)、[前端发布工具](frontend-migration.md) |
| 软件与 Python 环境 | [软件路径](SERVER_SOFTWARE_PATHS.md)、[公共 Python 环境](python-environments/README.md) |
| 运行条件与科学证据 | [方法运行条件](skill-runtime/README.md)、[质量检查](catalog-quality.md)、[双语维护](catalog-polish.md) |
| Slurm 调度、共享 Worker 和资源 | [Slurm 执行](slurm-execution.md)、[GPU 管理](slurm-admin.md) |
| 监控、重试、记账和备份 | [运行与备份维护](reliability-upgrade.md) |
| FreeSurfer 特定验证误报恢复 | [恢复接口](freesurfer-recovery.md) |

`method-verification/`、`software-contracts/`、`skill-runtime/*.json`、`slurm-test-results.json` 和 `python-environments/locks/` 保留原始帮助、依赖锁及带版本的验证证据。历史证据不等于当前环境或所有算法已验证。旧迁移、单次发布和分支审阅过程通过 Git 历史追溯，不作为当前操作步骤。

服务器更新前比较本地与远端有效改动；保留数据库、科研输入输出、旧资源和被任务引用的 Worker。版本、端口及路径的实时核对集中在服务器部署指南。本文档不触发部署、配置变更或计算任务。
