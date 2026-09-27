# 模块边界与维护指南

本次在 `codex/structured-skill-methods` 上整理既有实现。API 路径、请求/响应契约、运行方式和模型 Prompt 保持不变；Skill、Method 和 Pipeline 的科研定义不因代码拆分改变。

## 后端职责

| 模块 | 负责什么 | 不负责什么 |
| --- | --- | --- |
| `bakend/app/main.py` | 暴露 `app`，保持 `uvicorn app.main:app` 启动方式 | 初始化细节和业务逻辑 |
| `settings.py`、`bootstrap.py`、`application_services.py` | 配置、服务依赖装配、共享锁与路径保护接线 | 请求处理或模型规划 |
| `application.py`、`api/` | FastAPI 生命周期、按资源分类的路由、HTTP 错误转换 | 保存另一份领域校验规则 |
| `chat_coordinator.py` | 恢复可信上下文、安排对话/工具/规划调用 | 提交计算任务 |
| `chat_service.py`、`llm/` | 模型传输；需求解析、能力路由、方法规划、记忆摘要与有限重试 | 文件写入和 Runner 执行 |
| `workflow_service.py` | 流程生命周期、乐观修订、审核状态与提交保存 | 完整检索、建图或文件映射实现 |
| `workflows/contracts.py`、`inputs.py`、`warnings.py` | 确定性的参数、端口、输入解析与提示计算 | 模型请求、数据库写入 |
| `workflows/catalog.py`、`selector.py` | 方法选项投影、能力提示与顺序 | 自动执行用户尚未确认的任务 |
| `workflows/state.py`、`session.py` | 派生界面状态；共享修订锁和持久化边界 | 任意 Shell |
| `workflows/routing.py`、`planning.py` | 需求路由、按真实输入输出构建并校验流程 | 在生成说明文字时绕过图校验 |
| `workflows/bindings.py`、`preflight.py` | 当前/历史样本输入绑定；Dry-run 证据 | 启动作业 |
| `pipeline_models.py`、`pipeline_compiler.py` | 请求结构；纯内存编译注册方法组成的图 | 依赖完整应用或临时伪造服务对象 |
| `pipeline_repository.py`、`pipeline_management.py` | 不可变发布版本；草稿、归档和迁移审阅 | 从用户字符串拼接软件命令 |
| `pipeline_library.py` | 目录检索与普通 Workflow 集成 | 通过继承隐式共享存储属性 |
| `local_store.py`、`store_schema.py` | 持久化接口；可重复执行的增量建表/迁移 | 清理研究数据和运行输出 |
| `execution/` | 编译确认后的执行契约、权限检查、Runner、样本队列及 Slurm | 把模型回答直接作为命令执行 |

依赖从应用装配指向业务组件，再指向模型、纯计算或持久化接口。`llm` 仅通过 `ModelGateway` 调用模型；`workflows` 不反向导入 `WorkflowService`；Pipeline 编译器不导入数据库或 API。本次拆出的组件构造参数显式声明所需依赖，不使用 `__getattr__` 转发或拆文件式的业务 mixin。

跨模块写操作使用公开边界：`LocalStore.transaction()` 保证一次读、检查、写入的事务，`RunService.mutation_lock` 与 `WorkflowService.mutation_lock` 协调提交与文件操作。共享锁只能在应用装配处统一连接，不应在路由里新建另一个锁。关闭 Web 监控不等于取消 Slurm 作业。

## 前端职责

- `App.tsx` 保留当前对话和数据集/输出目录的协调；`ConversationHistoryPanel` 负责历史列表渲染和翻页观察。
- `useMessageViewport` 管理消息容器滚动及前插历史时的锚点恢复，向界面提供操作函数，不暴露内部跟随标记。
- `PipelineEditor` 组织编排操作；`PipelineMethodPalette` 只展示和选择注册方法，`PipelineNodeInspector` 根据实际契约展示条件输入与参数。
- `pipelineGraph.ts` 保留连线、共享输入和拓扑顺序的规则；`PipelineCanvas` 负责画布交互，不能自行重写一份类型或条件规则。
- `usePipelineDraft` 负责持久草稿、浏览器恢复、撤销/重做；`usePipelineDescription` 只在用户点击生成按钮时请求说明，负责取消过期请求和保护手动编辑；保存、校验与发布不生成说明。
- 各文件的注释解释数据所有权、并发边界、失效规则和异常恢复，避免为明显的赋值逐行写重复说明。

## 本次清理

删除无调用者的旧 `assess_workflow_need`、`plan_dwi`、`_heuristic_dwi_plan` 与旧流程辅助分支；这些入口已由当前需求契约、方法检索和建图链路替代。移除重复 Skill 查询订阅、未使用导入、路由内的工作流索引 SQL，以及依赖 `object.__new__(PipelineLibrary)` 的编译调用。

删除的是经过引用核查的代码，不是数据、命令定义、上游许可证或历史执行证据。没有新建算法，也没有删除数据库、正在使用的输出或服务器文件。工作区中本来存在的功能修改继续保留。

## 新增功能应该改哪里

1. 新增方法或条件参数：修改 `methods/` 中的真实契约；必要时修改受信任执行适配器。复用条件计算，不在 Prompt 或前端硬编码第三份规则。
2. 修改需求理解或回答策略：修改对应 `llm/` 策略和验证器；模型 HTTP 行为放在 `ChatService`。错误仍须保留低置信度及有限重试。
3. 修改流程规划：在 `workflows/routing.py` 或 `planning.py` 中处理；审核、锁定和修订提交放在流程服务，不由规划器直接保存。
4. 扩展 Pipeline：数据结构放在 `pipeline_models.py`，图规则放在编译器，草稿/版本放在各自存储组件；发布前仍校验注册方法和真实接口。
5. 新增 API：添加到相应资源路由并通过依赖容器访问服务，不重新往 `main.py` 添加端点。
6. 扩展界面：把纯规则、异步状态和展示组件分开；一个组件不要同时负责画布、模型调用、历史恢复及列表加载。

## 验证与启动

```powershell
# 从项目根目录；Python 应已安装后端 requirements 和测试依赖。
$env:PYTHONPATH='bakend'
python -m pytest bakend/tests -q

# 从 frontend/ 目录。
npm test
npm run build
```

`test_module_boundaries.py` 检查依赖方向、重构前的 API 路径/状态/响应类型、模型实际 Prompt 内容，以及输出目录修改后的修订和对话关联。Prompt 指纹仅用于防止文件迁移意外改变指令；有意修改 Prompt 时，应先审阅语义并补充行为测试，再更新对应快照。

启动命令和环境变量保持原样，不要求重建环境或迁移业务数据。API 测试使用临时数据库及进程内 ASGI 客户端，不启动本地前后端监听服务。服务器更新仍应遵循既有发布流程：先比较版本，保留运行任务所用的代码、输出和运行记录，再执行受控发布。

## 2026-09-27 本地验证结果

- 后端完整测试：**415 passed、694 subtests passed、3 skipped**。三个跳过项分别需要符号链接权限或真实 POSIX 权限，应在 Linux 环境继续保留这些测试。
- 前端：**49 项测试全部通过**；TypeScript 与 Vite 生产构建通过。
- 本次改动文件的 Python Ruff、前端 ESLint 检查通过；后端全量源码 AST 解析与差异空白检查通过。
- 70 个原有 API 的路径、状态码和声明的响应模型保持一致；模型策略 Prompt 内容保持一致。
- 构建仍提示单个前端压缩块超过 500 kB。这是体积提示，当前没有为消除提示而修改加载方式。
- 本轮没有进行浏览器端人工交互验收，也没有重新提交服务器科学计算测试；测试结果不等同于每条科研命令的执行验证。
- 本次整理未推送 GitHub、未替换服务器部署或重启其服务；未启动本地常驻前后端服务，未操作正在运行的任务。

## GitHub 提交前检查（2026-09-27）

本次汇总当前分支尚未提交的需求解析/规划、方法语义、可靠性、模块拆分和 Pipeline 编辑器改进。画布改动与 3002 前端部署记录见 [Pipeline 画布说明](pipeline-canvas-ui.md)。提交前另修复分类导航和草稿 Hook 的 React lint 问题，移除无作用的异常转抛，并把 19 条已有前端翻译同步到后端目录翻译表；这些收尾改动没有重新部署服务器。

- 完整后端回归首次为 414 passed、694 subtests passed、3 skipped，唯一失败为新增翻译缺项。补齐后对应的目录/翻译文件 8 项测试全部通过，其余后端实现未再改变。
- 前端完整 ESLint、53 项测试、TypeScript/Vite 构建通过。构建仍有现存的大包提示。
- 发布一致性检查通过：328 个 Method、28 个静态 Pipeline、105 个 Skill；翻译和依赖锁完整。
- 浏览器隔离复核：草稿名称修改、撤销、重做、显式保存正常，后端确认保存的新修订，无浏览器错误；测试服务已关闭。
- 提交范围限源码、定义、测试、文档与合成验证证据，不包含 `.env`、数据集、数据库、运行输出、依赖安装目录或前端构建产物。
