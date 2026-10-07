# Skill 历史兼容层清理

当前目录只接受原生 `skills/<id>/skill.json`。105 个 Skill、328 个 Method 和 28 个内置 Pipeline 的规范 ID 不变；旧 `software-*` 别名不再转发到规范 ID，旧 ID 查询返回 404。部分规范 ID 本身以 `software-` 开头，仍正常保留。

移除的内容：

- 70 个只有 `alias_of` 的 Skill 别名定义，以及 Loader、MethodRegistry、能力检索中的别名处理。
- DWI 的 `workflow.manifest.json` 及其启动依赖、固定排序规则。能力流程按已注册 Method 的输入输出类型排序；没有依赖关系的步骤保留请求顺序。原生 Method/Pipeline 图继续按显式连线编译。
- 未被当前运行链调用的 FreeSurfer `recipes.manifest.json`、claw-shell `handler.js` 和两个 `agents/openai.yaml`。
- 旧 Markdown DAG 解析模块及 `/api/skills/graph` 接口；当前目录和画布使用原生 Skill/Method/Pipeline 接口。

保留当前 Method 的实现、参数与端口定义、模型读取的 Skill 指导资料和第三方来源文件。能力检索中的语义关键词，以及有效的历史结果输入功能，继续使用。

开发服务器中的旧 `capability-tree:*` / `dynamic:*` 测试任务可以清理，连同关联运行、事件、执行草稿、异步操作和只包含这些旧任务的测试会话。保留当前 `method-contract:*` 和 `pipeline-library` 任务、用户 Pipeline 和草稿、数据集、输出目录及磁盘科研文件。本次按用户要求不创建数据备份；清理在无活跃任务时执行，使用维护锁和 SQLite 事务，并检查外键及保留记录的一致性。
