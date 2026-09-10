# 服务器工作区管理

工作区表示对话允许查询、管理和保存输出的服务器目录。数据集仍表示处理输入；两者分别保存。网页右上角“选择工作区 / 工作区文件”进入管理面板，不使用客户端文件上传控件。

## 使用

1. 浏览允许的服务器根目录，或填写服务器绝对路径。目录仅按层读取，文件夹优先；可筛选、排序、显示隐藏项、刷新、使用面包屑和上级目录。默认一页 80 项，滚动到底自动继续加载。
2. 选择“当前目录作为工作区”，填写名称。已有工作区可在下拉框切换；对话保存 `workspace_id`，历史对话恢复该关联。没有工作区的旧对话继续使用原行为。根路径不可直接修改，避免把旧对话静默关联到别的目录。
3. 选中文件查看大小、修改时间、权限和完整路径。文本预览按段读取；影像只展示元数据，内容分析继续使用现有 Skill/Runner。路径支持悬浮、横向滚动和复制。面板左边缘可拖动，聚焦后也可用左右方向键调整宽度。
4. 新建目录、复制、移动、重命名、删除先显示待确认卡片。复制/移动目标必须包含最终文件或文件夹名称。模型没有“确认”工具；只能由网页用户确认。普通对话不提供模型写工具，但用户可以在文件面板手动管理文件。
5. 删除默认进入回收站。恢复可以使用原位置或填写另一个工作区内目标；占用的位置不会被静默覆盖。永久删除必须显式勾选并确认。移除工作区记录只隐藏记录，目录、文件、对话和任务输出全部保留。
6. “关联当前数据集”只保存关联，不修改数据集目录。锁定流程后不能从页面切换工作区或数据集。新流程默认输出到 `工作区/outputs/运行ID/步骤/`，可在流程卡片中调整输出子目录；历史流程保留原输出配置。已提交运行保存根目录快照，不随之后的对话切换或流程修改迁移。

## 配置

本地示例（PowerShell，在启动后端前设置；目录应已存在）：

```powershell
$env:WORKSPACE_ALLOWED_ROOTS='D:\data;D:\reference_projects\LocalFlow\workspaces'
$env:WORKSPACE_DEFAULT_ROOT='D:\reference_projects\LocalFlow\workspaces'
$env:WORKSPACE_PAGE_SIZE='80'
$env:WORKSPACE_TEXT_MAX_CHARS='12000'
$env:WORKSPACE_TRASH_DIR='.neuroweave-trash'
```

未配置时只允许项目的 `workspaces` 目录；开发环境会创建这个默认目录。它被 Git 和发布复制规则排除，不打包用户文件。

服务器在 `deploy/native-backend.env` 中设置：

```dotenv
WORKSPACE_ALLOWED_ROOTS=/home/data
WORKSPACE_DEFAULT_ROOT=/home/data/neuroweave/workspaces/hipeson
WORKSPACE_PAGE_SIZE=80
WORKSPACE_TEXT_MAX_CHARS=12000
WORKSPACE_TRASH_DIR=.neuroweave-trash
```

Linux 多根目录可使用 `:` 或 `;` 分隔；Windows 使用 `;`。如果管理员设置 `WORKSPACE_ALLOWED_ROOTS=/`，可以浏览后端账户有权限读取的服务器路径，仍遵守特殊目录、敏感文件和工作区边界。代码没有默认开放 `/`。发布脚本只补充缺失的配置项，保留已有管理员设置。

Slurm 工作区和输出目录必须在目标计算节点上以相同绝对路径挂载、可由任务账户访问。通常使用 `/home/data` 共享存储。工作区配置写入冻结的 Slurm payload 环境白名单，控制端和 Worker 都验证输出范围。选择不共享的目录不会使它自动同步到计算节点。

回收站默认位于每个工作区的 `.neuroweave-trash`。配置相对目录时仍位于工作区内；配置绝对目录时按工作区 ID 分隔，且必须处于允许根目录内。移动和回收站操作使用同文件系统原子重命名；跨文件系统移动会失败并保留源文件，可先复制，再分别确认删除。不要把不同挂载点的数据统一移到另一个文件系统上的回收站。

## API

| 方法与路径 | 用途 |
|---|---|
| `GET /api/workspaces` | 工作区列表 |
| `POST /api/workspaces` | 登记已有目录：name、root_path、description |
| `PATCH /api/workspaces/{id}` | 修改名称、说明或 active/archived 状态 |
| `DELETE /api/workspaces/{id}` | 移除记录，保留磁盘及历史关联 |
| `GET /api/fs/roots` | 允许根目录、默认目录和分页/文本限制 |
| `GET /api/fs/list` | 一层分页列表 |
| `GET /api/fs/inspect` | 存在性、类型、大小、修改时间、权限、规范化路径 |
| `GET /api/fs/read-text` | UTF-8 文本：offset、max_chars、truncated、next_offset |
| `GET /api/fs/search` | 文件名/扩展名 glob，限定深度与结果数量 |
| `POST /api/fs/mkdir` | 创建文件夹提议 |
| `POST /api/fs/copy` | 复制提议 |
| `POST /api/fs/move` | 移动提议 |
| `POST /api/fs/rename` | 重命名提议，destination 只接受新名称 |
| `POST /api/fs/delete` | 回收站删除提议；permanent 默认为 false |
| `POST /api/fs/read-sensitive` | 单次敏感文本预览提议，仅人工网页入口 |
| `GET /api/fs/operations/{id}` | 持久化操作状态 |
| `POST /api/fs/operations/{id}/confirm` | 显式 `confirmed: true` 和匹配 conversation_id 后执行 |
| `GET /api/workspaces/{id}/trash` | 最近 500 条未恢复回收站记录 |
| `POST /api/fs/trash/{id}/restore` | 恢复提议，可另指定 destination；仍须确认 |
| `GET /api/workspace-tool-events?turn_id=...` | 当前对话工具进度 |
| `PATCH /api/conversations/{id}` | 新增 workspace_id 字段，null 表示解除关联 |
| `PATCH /api/datasets/{id}/workspace` | 可选关联，不改变数据输入目录 |
| `PATCH /api/workflows/{id}/output` | expected_revision + 工作区 relative_path |

列表参数：`workspace_id` 或 `root_path`、`path`（默认 `.`，可为范围内绝对路径）、`cursor`、`limit`（1–200）、`sort`（name/size/modified）、`filter`、`show_hidden`。返回 `items/has_more/next_cursor`。游标绑定目录修改状态及筛选参数，失效时需刷新。为了排序会枚举当前层，但只保留一页条目，不递归读取整棵树。

文件写请求字段：`workspace_id/path/destination/conversation_id/overwrite/permanent`。POST 返回 pending，不等于完成；确认有效期 10 分钟，单次消费。结果包括成功或失败状态，失败原因可查询。确认请求在线程池执行，浏览器断开不取消已经开始的文件操作，更不会取消 Runner。

## 模型工具

真正注册到模型 API 的函数为：

- `list_workspace_directory`
- `inspect_workspace_path`
- `search_workspace_files`
- `read_workspace_text`
- `create_workspace_directory`
- `copy_workspace_path`
- `move_workspace_path`
- `rename_workspace_path`
- `delete_workspace_path`

另有内部路由函数 `continue_workflow_planning`，把处理需求交回已有能力树、Skill 和规划系统。上述工具不能指定其他 workspace_id/root_path，范围从当前对话注入。没有通用 Shell 或模型确认函数。每轮最多 8 个模型回合、16 次调用；模型列表/搜索默认最多 20 项、文本最多 8000 字符，可继续分页或缩小检索范围。HTTP 文件面板的配置上限独立保留。

只读结果进入工具观察，按事件保存到对话时间线；文本内容按需发送给当前配置的模型提供商，因此工作区应选择允许该模型处理的数据目录。敏感文本例外：需要独立人工确认，只在确认响应返回网页，不发送给模型，不把文本持久化到操作记录或审计。

## 权限与一致性

- `Path.resolve()` 检查允许根和工作区边界，拒绝 `..`、越界符号链接、循环链接与非普通文件。写操作拒绝任何路径组件的符号链接；Windows 同时拒绝 reparse point。
- 即使根为 `/`，仍屏蔽 `/proc`、`/sys`、`/dev`、`/run`、`/boot` 等特殊目录；隐藏 `.env`、凭据/token、私钥、敏感系统文件。Linux 权限由后端账户本身决定，不使用 sudo。
- Linux 文件内容打开及写入使用逐层 `O_NOFOLLOW` 目录描述符，重命名使用 `renameat2(RENAME_NOREPLACE)`；不能覆盖确认后新出现的目标。复制先建立同目录暂存副本，成功后再原子替换；旧目标先进入回收站。
- 文件操作使用 Python/OS 文件接口，不拼接 Shell。影像、压缩文件、NUL/控制字节以及无法严格 UTF-8 解码的内容不能作为文本返回。搜索最多深度 5、200 个结果、20000 个扫描项、5 秒，达到限制明确返回 truncated。
- 每次实际写入记录开始/成功/失败、后端账户、会话、工具、源/目标、时间与确认状态。确认前重新检查源/目标指纹。普通对话不给模型写工具，模型生成的“完成”文本不能替代操作成功状态。
- 活动任务的数据集、已绑定输入及输出目录不能移动、改名、删除或覆盖。文件操作先保留路径，新的 Runner 不能占用同一路径；长时间复制不会持有 Runner 进度锁。
- 文件确认独立于 LLM，来自不允许网页 Origin 的写请求被拒绝。当前平台沿用单一后端账户和既有网络入口，不提供用户级身份隔离；审计中的 actor 是服务器账户，conversation_id 区分会话。不要将其当作多租户沙箱。

## 验证及发布

```powershell
cd D:\reference_projects\LocalFlow\bakend
python -m pytest -q
cd ..\frontend
npx tsc --noEmit
npm run lint
node --experimental-strip-types --test --test-concurrency=1 tests/*.test.mjs
npm run build
```

Linux 必须执行 `tests/test_workspaces.py`，覆盖 Windows 开发账户可能无权创建的符号链接测试。实际模型验收需要当前模型支持 OpenAI 兼容结构化 function calling；失败会显示接口错误，不会假装执行。

发布沿用 `scripts/package_release.py`、`scripts/deploy_slurm_release.py` 和 `scripts/deploy_frontend_release.py`。先比较生产公共文件与上一个发布包的 SHA-256，保存任何服务器独有改动，再部署已提交归档。数据库采用增量加列/新表，不清理既有对话、任务或输出。

服务器命令示例，`RELEASE` 指已校验解压的具体版本目录：

```bash
mkdir -p /home/data/neuroweave/workspaces/hipeson
python3 "$RELEASE/scripts/deploy_frontend_release.py" --source "$RELEASE" --revision "$REVISION" --build-only
python3 "$RELEASE/scripts/deploy_slurm_release.py" --source "$RELEASE" --revision "$REVISION" --enable-slurm
python3 "$RELEASE/scripts/deploy_frontend_release.py" --source "$RELEASE" --revision "$REVISION" --activate-only
```

发布脚本先检查活动 Runner、后台检查和文件操作，并在维护标记建立后再次检查；存在活动任务时拒绝发布。不要绕过检查强制重启。仅在确认无活动任务、只是修改配置时使用：

```bash
systemctl --user restart localflow-backend.service
```

前端重新构建/切换不取消已经提交的后台任务。本地临时前后端测试结束后必须关闭。

## 操作限制与故障恢复

- 工作区是文件范围和任务输出配置，不替代科学软件自己的参数验证。已有数据集输入选择和历史样本绑定规则保留；输入选择器优先数据集，没有数据集时从工作区所对应的授权数据根开始。工作区若不属于已配置的数据输入根，不会自动扩大科学 Runner 的输入许可。
- 单次递归复制/目录修改限制 100000 项。跨文件系统 move/restore 不做隐式复制后删除。大型数据不使用 Git checkpoint。
- 进程异常中断的文件操作保留 running 记录，不会自动重放；需检查 operation、源/目标和回收站后处理。复制的暂存路径记录为 staging_path，失败时可保留部分副本，原目标不会因复制失败被先删除。回收站 prepared 记录也保留，以支持中断后的人工核查。
- Windows 使用原生文件权限及规范化/reparse 检查；Linux 服务器另有目录描述符防护。本功能不是针对可任意重命名挂载点、改变目录所有权或修改数据库的本机管理员的安全隔离。

## 主要修改文件

后端新增 `app/workspace_models.py`、`workspace_paths.py`、`workspace_io.py`、`workspace_service.py`、`workspace_routes.py`、`workspace_tools.py`；更新 `main.py`、`models.py`、`chat_service.py`、`local_store.py`、`conversation_models.py`、`conversation_service.py`、`dataset_models.py`、`dataset_service.py`、`run_models.py`、`workflow_models.py`、`workflow_service.py`、`execution/run_service.py`、`execution/slurm_backend.py`、`execution/slurm_worker.py`。

前端新增 `components/workspace-panel.tsx`、`components/workflow/workspace-output.tsx`；更新 `app/page.tsx`、`lib/workflow.ts`、`components/dataset/artifact-path-picker.tsx`、`components/workflow/workflow-card.tsx`、`components/workflow/run-panel.tsx`。

验证和部署：`bakend/tests/test_workspaces.py`、`bakend/tests/test_run_service.py`、`scripts/deploy_slurm_release.py`、`.gitignore`、`README.md` 和本文。
