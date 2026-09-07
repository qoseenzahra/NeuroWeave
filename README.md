# NeuroWeave

NeuroWeave 是以 NeuroClaw 为上游能力库的本地神经影像智能工作流平台，通过自然语言组织分析需求，编排处理步骤，并由经过审核的可信 Runner 调用服务器现有软件，形成可追溯的分析流程。

项目原名 LocalFlow。当前产品名称统一为 **NeuroWeave**；为兼容现有部署，源码目录 `D:\reference_projects\LocalFlow`、服务器目录 `/home/hipeson/LocalFlow`、SSH 别名 `localflow-server`、`localflow-backend.service`、数据库/Socket 文件名以及 `LOCALFLOW_*` 环境变量继续沿用。API 中的 Skill 来源值 `LocalFlow` 保留为兼容标识，界面显示为 NeuroWeave。

当前功能：

2026-09-07 已新增 `/opt/neuroweave/envs/` 公共 Python 环境，覆盖科学计算、神经影像、EEG
和 PyTorch CUDA；环境安装与 Slurm 实测状态见 [公共环境与调度说明](deploy/python-environments/README.md)。
Slurm 执行已启用：主节点提交，三个 RTX 5060 计算节点执行 GPU 作业，实际 CUDA 运算、取消和重启恢复均已通过验证。使用方式见 [Slurm 执行文档](deploy/slurm-execution.md)，证据见 [验证记录](deploy/slurm-verification.md)。

- Web 对话工作台
- 普通对话与任务两种交互模式
- 从 `skills/*/SKILL.md` 自动发现、搜索并选择 Skill
- 完整导入 NeuroClaw 的 103 个 Skill、配套脚本和离线中英文摘要
- 复用 NeuroClaw SkillLoader 与依赖图校验模块
- FastAPI 健康检查、Skill 列表/详情和对话接口
- 受限数据根目录浏览、数据集登记与只读元数据扫描
- SQLite 持久化的数据集、Workflow、完整对话消息与审计事件
- 可切换的对话历史列表：自动标题、最近消息预览、消息数、新建与历史恢复
- Codex 风格会话记忆：较早消息压缩为工作摘要，同时保留近期原始消息
- 独立的工具能力清单（`tool.manifest.json`）、统一制品类型目录和输入/输出兼容性过滤
- 覆盖全部 103 个 Skill 的分层能力树、planning Manifest、方法依据追踪、按需检索和动态单步/组合任务规划
- 无模型配置时可用的本地对话演示模式
- 可选的 OpenAI-compatible 模型接口
- 未手动选择时，按 NeuroClaw 的名称匹配规则识别消息中明确提到的 Skill
- DWI 样例垂直流程：模型规划、兼容方法选择、流程锁定、参数审核、Dry-run 和最终确认
- 可信 Runner 注册表、后台执行队列、取消、进度/日志、制品校验与 SQLite 运行审计
- 本地或 Slurm 执行选择、CPU/内存/GPU/时限申请、Job ID 展示与持久恢复监控

当前目录共有 103 个 Skill（99 个 NeuroClaw 上游 Skill 和 4 个 NeuroWeave Skill），每个 Skill 都有 `planning.manifest.json`，因此都能进入任务卡并选择受约束参数。生成器会优先从 `SKILL.md` 的方法表、快速参考和命令块中提取操作选项，再补充适合该能力类别的常用与高级规划参数；当前 103 个 planning manifest 都有来源依据，60 个 Skill 提取出了方法级操作选项，共登记 330 条只读参考命令。运行时会把命中 Skill 的多值 `operation` 选项展开为独立候选方法，而不修改能力树或一次读取全部 Skill；当前 114 个能力、346 个原始方法可展开为 669 个可选择方法（包括同一实现的模型选项和跨 Skill 入口）。任务卡可以展开查看 Skill、脚本和命令的来源位置，参数下拉项也可以显示选项说明。

平台只调用或管理原有项目实现、现有库 API 和已有软件命令；不根据方法名称、文档公式或基础库可用性补写算法。上一轮超出此范围的 12 个接口已撤回，缺少原始可用入口的内容保留规划。Manifest 的 `runner_id` 只是执行契约，不等于已经有执行代码。只有同时出现在后端可信 Runner 注册表、并通过服务器运行时探测的方法才会在 Dry-run 后标记为可执行。从文档提取的命令始终是只读参考，不会被模型或后端直接运行。当前显式注册 164 个经过审核的 Runner；服务器公共环境中 161 个已就绪。103 个 Skill 中，72 个至少有一项可运行方法，共 305 个就绪的候选方法入口；其余条目包含规划流程和缺少运行条件的方法。fMRIPrep、QSIPrep 和 nii2dcm 尚未配置执行入口，HCP Pipelines 仍无可执行适配。详细范围、输入要求及测试证据见 [Skill 执行配置](deploy/skill-runtime/README.md) 和 [逐方法清单](deploy/skill-runtime/readiness.json)。输入只读，本地结果写入 `LOCALFLOW_OUTPUT_ROOT/run_*/step/`，Slurm 结果写入共享的 `/home/data/neuroweave/runs/hipeson/run_*/step/`，并记录命令日志、进度、校验和与运行事件。

## 目录

```text
LocalFlow/
├─ frontend/              # React + Vinext + shadcn/ui
├─ models/                # 复用的模型代码、训练与评估实现
├─ bakend/                # FastAPI（保留了现有目录名）
│  ├─ app/
│  └─ data/localflow.db   # 运行后生成，不提交版本库
├─ skills/
│  └─ <skill-name>/       # SKILL.md / workflow.manifest.json / tool.manifest.json
├─ scripts/               # 上游 Skill 同步脚本
└─ THIRD_PARTY_NOTICES/   # NeuroClaw MIT 许可证
```

## 本地启动

后端：

```powershell
cd D:\reference_projects\LocalFlow\bakend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

前端：

```powershell
cd D:\reference_projects\LocalFlow\frontend
npm run dev
```

## Linux 服务器部署（原生 Conda 后端）

当前服务器架构是“原生 Conda 后端 + Docker 前端/Nginx”。FastAPI 在宿主机上
直接调用 `/opt/software` 中的 FreeSurfer、FSL、ANTs 和 MRtrix3，避免将完整科学
软件树映射进后端容器。项目只新建独立前缀环境
`/home/hipeson/LocalFlow/.conda/backend`，不修改 Conda `base`、`midcc`、`sp` 或 FSL
自带的 Python 环境。Docker Compose 仅管理前端和 Nginx 网关，不再包含已废弃的后端容器配置。

```bash
cd /home/hipeson/LocalFlow
cp .env.deploy.example .env
cp bakend/.env.example bakend/.env
mkdir -p runtime datasets outputs
/opt/miniconda3/bin/conda create \
  --prefix /home/hipeson/LocalFlow/.conda/backend python=3.12 pip -y
/home/hipeson/LocalFlow/.conda/backend/bin/python -m pip install \
  -r bakend/requirements.txt
cp deploy/native-backend.env.example deploy/native-backend.env
chmod 600 deploy/native-backend.env bakend/.env
mkdir -p ~/.config/systemd/user
ln -sfn /home/hipeson/LocalFlow/deploy/localflow-backend.service \
  ~/.config/systemd/user/localflow-backend.service
systemctl --user daemon-reload
systemctl --user enable --now localflow-backend.service
loginctl enable-linger "$USER"
docker compose up -d --build frontend gateway
```

真实模型配置仅写入 `bakend/.env`，不要把 API Key 提交到版本库。Nginx 通过
`runtime/localflow-backend.sock` 访问原生后端，不对外暴露 Uvicorn TCP 端口。日常管理命令：

```bash
systemctl --user status localflow-backend.service
systemctl --user restart localflow-backend.service
journalctl --user -u localflow-backend.service -f
docker compose ps
```

部署文件使用 AWS ECR Public 中的 Docker Official Images，以避免服务器本地 Docker Hub
镜像加速器配置异常时阻断前端或网关构建。

校园网内可直接访问当前部署地址：`http://192.10.84.6:3000/`。如果服务器改为只监听
回环地址，或需要从不直通该校园网的设备访问，再在 Windows 本机建立 SSH 隧道：

```powershell
ssh -N -L 3000:127.0.0.1:3000 localflow-server
```

保持该窗口打开，然后访问 `http://localhost:3000/`。无论采用校园网直连还是 SSH 隧道，后端都通过同源 `/api` 访问，
不需要在浏览器中直接暴露 8010 端口。

文件夹选择器由原生后端直接读取宿主机路径。当前 `deploy/native-backend.env`
将 `/` 登记为“服务器根目录”，因此可从根目录开始浏览；Linux 权限仍按
`hipeson` 用户执行，隐藏目录默认禁止访问。要缩小可访问范围，修改：

```text
LOCALFLOW_DATA_ROOTS=数据目录::/希望允许访问的数据目录
```

修改后运行 `systemctl --user restart localflow-backend.service` 生效。输入数据只用作
Runner 的受审核输入，产物仍限定写入项目 `outputs` 目录。网页支持
面包屑导航、相对路径跳转、当前目录筛选和文件/文件夹计数，但拒绝绝对路径、`..` 和
逃逸授权根目录的符号链接。即使从服务器 `/` 开始浏览，也不会显示或接受 `.ssh` 等隐藏
路径；只有显式设置 `LOCALFLOW_ALLOW_HIDDEN_PATHS=true` 才会解除这层限制，不建议启用。

启动前后端后，可以先选择交互模式：

- **普通对话**：只返回文字回答，后端强制绕过 Workflow 推荐与创建。
- **任务模式**：先由本地混合检索从全部 Skill 的名称、关键词、说明、方法与参数选项中生成最多 8 个候选，再由模型把自然语言标准化为一个或多个数据处理操作，并且只能从后端给出的具体能力 ID 中选择。高置信度且覆盖完整时直接生成单步或组合流程；覆盖不完整时才从根节点逐层读取“当前节点的直接子项”。到达叶子能力后，后端才加载对应 Skill 摘要。叶子分为 `structured`（已有受审 runner 方法）和 `planning`（已有结构化方法与参数、但没有 runner）两类；两者都能生成任务卡。

浏览器首次发言时，后端自动创建 `conversation_id`。后续请求只提交该 ID 和当前
消息，历史由 SQLite 管理；达到配置阈值后，较早内容会整理为
`Conversation Working Summary`，保留目标、约束、选择、稳定 ID、已完成工作、
未解决事项和下一步。完整原始消息不会因压缩而删除。

左侧栏的“对话”页通过 `GET /api/conversations` 按最近活动列出本地历史；选择一条记录后，
前端通过 `GET /api/conversations/{conversation_id}` 恢复完整消息，并根据消息元数据恢复最近
使用的普通/任务模式、Skill 选择和数据集关联。历史回复引用的 Workflow 会通过其持久化 ID
重新载入，因此方法选择、参数、输入绑定和流程状态仍可继续操作。新建对话不会预先创建空
记录，第一次发送成功后才写入 SQLite，并使用首条用户消息生成标题。

对话历史支持按标题或消息正文搜索、重命名、归档与恢复。`GET /api/conversations` 接受 `q`
和 `archived` 查询参数，`PATCH /api/conversations/{conversation_id}` 用于更新标题或归档状态。
归档是可逆操作，不会删除原始消息、工作摘要或 Workflow 引用；前端可在“最近对话”和
“已归档”之间切换。旧版 SQLite 数据库会在启动时自动增加归档字段，无需重建数据库。

对话列表首次加载 20 条，滚动接近列表底部会自动追加下一页；也可以点击“加载更多”。
`GET /api/conversations` 默认 `limit=20`（最大 50），返回 `conversations`、`has_more` 和
`next_cursor`；继续请求时传入 `cursor=next_cursor`。排序使用活动时间与唯一 ID，配合复合索引
进行游标查询，避免同一时间戳或删除记录造成翻页重复/漏项。列表不传完整历史摘要；完整消息
仍在打开具体会话时读取。搜索和归档筛选会从第一页开始，并取消过时的列表请求。

已归档对话的管理菜单提供“永久删除”，二次确认后调用
`DELETE /api/conversations/{conversation_id}`。服务端在同一事务内检查归档状态并删除会话，
其消息和摘要一并删除；未归档会话返回 409，不存在的会话返回 404，成功返回 204。
删除会话不会删除数据集、Workflow、运行审计或输出文件；被删除的对话无法通过网页恢复。

需要处理数据时，先点击顶部“选择数据集”，在允许的根目录中浏览并登记一个文件夹，切换到“任务模式”，再在对话中输入：

```text
请对 DWI 做预处理并计算 FA 和 MD
```

模型会结合数据集扫描结果返回一张结构化流程卡片。先只选择各步骤的方法并点击“确定流程链”；锁定后页面才显示输入绑定与参数选项。随后补齐必需输入、审核参数、运行 Dry-run，最后点击“最终确认方案”。若所有步骤都已接入可信 Runner，卡片才显示“开始运行”；运行中的步骤、进度、日志、取消状态和输出制品均会持久化。Workflow 与每次变更事件写入 SQLite，重启后端后仍可通过 API 查询。

推荐步骤依据现有方法声明的输入输出关系及已有流程模板排序；独立步骤保持相对顺序，排序本身不会补回被移除的步骤。方法列表仍匹配当前任务，扫描未识别输入或用户移除上游步骤时，相关方法不会因此被禁用或隐藏。锁定后按已有输入槽位手动绑定文件，必需输入未补齐不能通过审核。方法内部包含被移除操作时显示明确提示，用户仍可手动选择，实际执行保持该方法原有定义；不会为它增加原本不存在的“跳过算法”接口。缺少可信 Runner 或真实运行环境时仍保留执行限制。

当前流程锁定后，顶部数据集选择同步禁用，输入配置、参数审核和 Dry-run 阶段均不能更换数据集。先点击“解锁流程”才能更换；更换后保留兼容的方法及参数，清除旧文件绑定和审核结果，并重新检查方法兼容性。已确认流程的数据集不可更改，可新建对话处理其他数据。重新打开历史对话时，顶部显示最新流程持久化的数据集快照，而非旧消息中的数据集记录。更换使用 `PATCH /api/workflows/{workflow_id}/dataset`，携带 `dataset_id` 和 `expected_revision`；后端拒绝锁定状态和过期版本的请求。

数据集登记时会建立样本索引：BIDS 数据按 `sub-*` / `ses-*` 识别，普通目录默认将一级子目录视为样本。锁定流程后，输入路径选择器从当前数据集目录开始浏览；从一个代表样本选择文件或目录后，后端会推断 `{subject}`、`{session}` 或 `{sample}` 相对路径模板，逐样本验证匹配结果，并在全部样本匹配成功后保存为批量输入绑定。

任务规划分为两个受约束阶段：

```text
用户需求 + 工作摘要 + 最近 4 条消息
  → 本地稀疏检索：在 103 个 Skill 的短元数据中匹配名称、能力、模态、方法与参数选项
  → 只把最多 8 个 Skill 候选和已审核具体操作交给语义理解层
  → 语义理解：标准化操作、目标和输入/输出概念，只允许返回候选目录中的 ID
  → 完整且高置信度：把具体能力作为语义锚点，直接进入 Skill 规划
  → 部分覆盖：从根节点逐层发送当前节点的直接子项，并始终保留语义锚点
  → 操作确实存在歧义：先向用户提出一个简短澄清问题
  → 到达一个或多个 capability 叶子（不向模型发送整棵树）
  → 后端只读取命中的 SKILL.md 摘要
  → 方法展开：把命中 Skill 的 operation 任务选项转换为独立、稳定的方法候选
  → 本地方法过滤：先排除与当前操作无关的病种、模态、阶段和运行选项
  → 方法排序：模型只看到过滤后的同类候选，返回一个推荐方法和相关备选，后端再次校验 ID
  → structured：读取 tool.manifest.json，推荐受审 runner 方法并生成任务卡
  → planning：读取 planning.manifest.json，生成可选参数的规划型任务步骤
  → Dry-run：校验 Manifest 契约、路径、Runner 运行时与方法级输入内容检查
  → 显式运行：仅确认后且 execution_enabled=true 的不可变流程快照可进入 Worker
  → 后端不从 SKILL.md 或模型文本直接拼接命令
```

当前能力树文件为 `skills/capability.tree.json`，结构化规划文件由以下命令生成：

```powershell
python scripts/build_structured_skill_manifests.py
python scripts/build_capability_tree.py
```

生成器要求 103 个 Skill 全部且仅被分类一次；
新增或删除 Skill 后若分类表没有同步，生成会直接失败。例如：

```text
只整理并校验为 BIDS
  → 单步任务：dwi.bids

先整理为 BIDS，再做图像配准
  → 组合任务：dwi.bids → image.registration

只做纤维追踪
  → 默认只生成：dwi.tractography
  → 若预处理 DWI 输入不足：选择已有制品，或点击“补充最小上游”生成 dwi.preprocess → dwi.tractography

从预处理到纤维追踪
  → 组合任务：dwi.preprocess → dwi.tractography
```

模型只能返回能力树中的叶子 ID。对于 `structured` 叶子，它还只能从
`tool.manifest.json` 的注册方法中选择；对于 `planning` 叶子，后端先将命中
`planning.manifest.json` 方法中的多值 `operation` 选项展开为独立方法，再让模型从这个受约束
列表中返回推荐项和相关备选项。模型返回的未知方法 ID 会被丢弃，推荐项也必须包含在备选列表中。
规划型步骤会显示 `PLAN` 参数快照，
不会伪装成命令。当前图像配准复用现有 `fsl-tool` Skill 中的 FLIRT 能力；DWI
纤维追踪除 MRtrix3 全流程与 FSL probtrackx 规划方法外，还提供“复用已有 FOD/5TT”的 MRtrix3 可执行方法；它只运行 tckgen，并按需运行 SIFT2。

经过人工审核的规划选项可以在同一 Skill 目录增加 `recipes.manifest.json`。配方只允许引用
`tool.manifest.json` 中已经注册的 Runner 方法，并显式声明固定参数、工作流输入、步骤输出和
公开输出映射。用户仍然在方法阶段选择一个方案；锁定后只配置配方公开的输入和参数，Dry-run
会把方案展开成实际 Runner 步骤。运行时每一步产生的真实制品路径会替换上游占位符，再交给
下一 Runner。FreeSurfer 的“Fast subcortical + basic surfaces”是首个样例，会在同一
`SUBJECTS_DIR` 中依次运行 `autorecon1 → autorecon2 → autorecon3`，只有第一步导入 T1w。
T2、FLAIR、线程数等属于 Runner 参数，不再作为独立任务方法；没有受审核配方的选项仍保持
规划型，模型不能把参考命令自动提升为执行权限。

Prompt 使用 `planner-v4-recipe-aware` 分为任务语义标准化、分层能力路由和受约束方法排序三段。当前消息定义本轮任务范围，历史摘要和已选 Skill 仅是弱提示；缺少输入或软件被视为执行约束，不再自动扩大成完整上游流程；当用户要求实际处理时，模型优先排序语义匹配的 Runner 或受审核 Runner 配方，并优先复用数据集中已经检测到的 FOD/5TT 等中间制品。配方内部步骤由后端固定，模型不能改写或重排。`GET /api/health` 会返回当前 `prompt_version`。

当用户在当前消息中明确写出软件或 Skill 名称时，该显式名称优先于之前选择的无关 Skill；
具体工具名也优先于同时出现的宽泛模态名，例如 `MNE + EEG` 会先定位 `mne-eeg-tool`。
界面中之前选择的 Skill 只作为弱偏好，不能覆盖当前需求。后端还会对未明确写出软件名的
需求做本地稀疏召回，并把最多 8 个 planning Skill 连同从 `SKILL.md` 提取的任务选项临时
加入精确语义目录；不会把全部 103 个 Skill 一次发送给模型。能力定位完成后只展开命中 Skill
的方法；方法较多时先在本地按当前需求过滤明显无关的病种、模态和运行选项，再由模型排序。
疾病、数据集或生物标志物专用
Skill 只有在当前需求提供相应语义时才能优先命中；同一目标的多个实现如果无法可靠区分，
系统在任务卡中展示推荐方法与备选方法供用户选择，而不是误拼成多步流程。例如“用 FreeSurfer 对 T1 做组织分割”
会定位 `freesurfer-tool`，而只有包含 WMH、白质高信号或 FLAIR 病灶语义时才优先选择
`wmh-segmentation`；“组织分割”也不会再被解释为整理 BIDS 文件。

每个方法还带有 `structure_level`：`reviewed` 表示人工审核过的方法结构，`evidence`
表示由 Skill 文档、脚本或命令示例支撑的规划结构，`profile` 表示只有类别级规划模板。
`source_references` 记录依据文件与行号，`command_references` 记录经过脱敏的命令示例并固定
设置 `executable: false`，`delegate_skill_ids` 记录该方法可能需要协作的其他 Skill。前端在
流程锁定后显示这些依据，便于用户判断当前卡片是可执行工具还是文档驱动的规划建议。

参数声明支持 `required`、`level`（`basic` / `advanced`）、`group`、`control`、数值
`minimum` / `maximum` / `step` 以及 `visible_when`。非必选参数可以保持空值，此时命令
预览不会生成对应参数，而是交由软件使用默认行为。前端默认只展示常用参数；展开
“高级参数”后按组显示方法细节。后端只校验并预览当前条件下可见的参数，模型不能添加
manifest 未声明的参数。批量规划 manifest 的参数模板维护在
`scripts/build_structured_skill_manifests.py`，修改后重新运行生成器即可同步全部 Skill。

### DWI 输入与输出声明

全局制品类型定义在 `skills/artifact-types.json`。DWI 预处理和纤维追踪相关方法在各自
manifest 中通过 `input_slots` / `output_slots` 声明：

- 输入槽包含制品类型、用途说明、允许格式、文件或文件夹绑定方式、伴随文件和条件必选规则。
- 输出槽包含制品类型、格式、逻辑路径模板和条件生成规则，可自动绑定到后续步骤。
- `required: false` 表示始终可选；`required_when` 表示只有选中 ACT、连接组等功能时才必选。
- 输入来源可以是已登记数据集、用户从授权目录选择的已有文件/文件夹，或同一流程中上游步骤的输出。

MRtrix3 的完整规划方法始终要求预处理 DWI；“已有 FOD”可执行方法只要求 FOD，并在 ACT
开启时要求 5TT、在 ROI 播种时要求种子影像。SIFT2 权重只在对应后处理启用时生成。文件型
输入不会因为扫描器发现了某种文件就自动绑定整个数据集目录，用户仍需在流程锁定后选择一次
明确的文件；多样本数据集则由路径模板预览扩展到各样本。

### 服务器现有软件 Runner

原生后端直接使用服务器的 `/opt/software`、`/usr/bin`、`/lib` 和 `/usr/lib`，
不再需要把 `tcsh`、`bc`或共享库逐个映射进容器。
FreeSurfer Runner 会按 `FreeSurferEnv.sh` 的非交互等价配置注入 FS-FAST、MNI/MINC、FSL、
PERL 与辅助库路径，不再只检查和加载 `recon-all` 主程序。MRtrix 只额外指定系统 `libpng16`；不会把整个 FSL `lib` 注入 MRtrix，
以免 FSL 的 `libstdc++/libgcc` 覆盖 MRtrix 构建时使用的系统 ABI。默认使用：

```text
FSL:        /opt/software/fsl
MRtrix3:    /opt/software/mrtrix3-master
FreeSurfer: /opt/software/freesurfer-7.4.1/usr/local/freesurfer/7.4.1
```

`GET /api/health` 的 `execution.runners` 会逐个返回 `available`、`reason` 和实际可执行文件路径。
后端运行时不会创建或修改科学软件环境，也不会运行模型生成的任意命令；每个 Runner 都用固定
可执行文件与参数白名单组装 `argv`，并以 `shell=false` 启动。

部署或更换服务器软件后，可在原生后端环境中执行一次完整静态审计：

```bash
cd /home/hipeson/LocalFlow/bakend
set -a; . ../deploy/native-backend.env; set +a
../.conda/backend/bin/python -m app.execution.runtime_audit
```

审计会列出所有注册 Runner 的可用状态，并检查主程序、FreeSurfer/MRtrix/FSL 已知委托程序、
脚本解释器、系统辅助命令与 ELF 动态库；FreeSurfer 还会启动 `UpdateNeeded` 和
`nu_correct -version` 做无数据探针，以覆盖 csh 与 MINC/PERL 模块问题。它不会启动影像处理
任务；返回码非零表示已启用环境仍有阻断项。未配置环境而安全禁用的 Runner 会单独列出。
如需在部署或软件升级后扫描各软件 `bin` 目录下的全部可执行文件及动态库，可追加
`--deep`；深度结果包含可执行文件数量、缺失 shebang 解释器和缺失共享库清单。

当前可信 Runner 覆盖：数据集巡检、BIDS 安全整理、DICOM 转 NIfTI、ANTs/FLIRT 配准、
FSL eddy 与 dtifit、MRtrix3 响应函数/FOD/5TT/纤维追踪/连接组、FreeSurfer recon-all、
ASL CBF、PET SUVR、Nibabel 检查、表格清洗和可复现性报告。DIPY、fMRIPrep、QSIPrep 与
nii2dcm 已具备完整输入输出、参数和 Runner 契约，但只有在其环境探测通过后才允许执行。

缺少软件时采用 NeuroClaw 式“环境入口配置”，不在 NeuroWeave 中创建或修改环境。把已有
环境中的解释器或入口程序配置到根目录 `.env`，重启 Compose 即可，不需要修改 Skill：

```dotenv
LOCALFLOW_SKILL_PYTHON=/已有环境/bin/python
LOCALFLOW_DIPY_PYTHON=/已有DIPY环境/bin/python
LOCALFLOW_FMRIPREP_EXECUTABLE=/已有环境/bin/fmriprep
LOCALFLOW_QSIPREP_EXECUTABLE=/已有环境/bin/qsiprep
LOCALFLOW_NII2DCM_EXECUTABLE=/已有环境/bin/nii2dcm
```

前端 Skill 列表按探测结果显示“可运行”“待配置环境”或“可规划”；待配置项的悬停提示会
说明缺少的解释器、模块或可执行文件。NeuroClaw 中只有说明、数据入口、研究设计或模型训练
用途的 Skill 仍保留为规划能力，不会把其文档中的示例命令自动提升为服务器执行权限。

对于包含 `wmfod_norm.mif` 与 `5TT.mif` 的数据集，可在任务模式输入：

```text
使用这个数据集中已有的 FOD 和 5TT 做 1000 条 iFOD2 纤维追踪，启用 ACT，不运行 SIFT2。
```

选择“MRtrix3 基于已有 FOD 的纤维追踪”后锁定流程，分别绑定 FOD 与 5TT 文件，再依次完成
参数审核、Dry-run、最终确认和“开始运行”。完整 FreeSurfer 通常耗时数小时；建议先用
`autorecon1` 验证 T1 输入和运行环境，并优先选择原始全头 T1w，而不是已经脑提取的影像。

`POST /api/chat` 的任务模式响应包含 `capability_routing`：记录标准化任务、语义候选、
置信度、本次展开层数、每层选择和候选载荷占整树载荷的比例。该字段用于调试和前端
提示，不包含模型思考过程或 SKILL.md 正文。数据集扫描结果不会发送给新增的语义理解
调用，避免“缺少输入”改变用户实际要求的操作。模型接口失败时，本地高精度匹配继续
提供具体能力锚点；只有没有可靠候选时才保持对话或要求补充目标。

推荐状态流：

```text
awaiting_method_choice
  → chain_ready（全部方法已选择，可以确定流程链）
  → awaiting_input_binding（锁定后且当前方法缺少必需输入）
  → awaiting_parameter_review
  → awaiting_dry_run
  → ready
  → confirmed
```

锁定后仍可“解锁流程”重新选择方法；未锁定时可要求模型“重新规划”。所有修改都携带 `expected_revision`，旧页面提交过期版本时会收到 `409 revision_conflict` 和最新 Workflow 快照。

样例工作流接口：

```text
POST  /api/workflows/draft
GET   /api/workflows
GET   /api/workflows/{workflow_id}
GET   /api/workflows/{workflow_id}/events
PATCH /api/workflows/{workflow_id}/steps/{step_id}/method
PATCH /api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}
POST  /api/workflows/{workflow_id}/complete-dependencies
POST  /api/workflows/{workflow_id}/lock
POST  /api/workflows/{workflow_id}/unlock
POST  /api/workflows/{workflow_id}/replan
PATCH /api/workflows/{workflow_id}/steps/{step_id}/parameters
POST  /api/workflows/{workflow_id}/review-parameters
POST  /api/workflows/{workflow_id}/dry-run
POST  /api/workflows/{workflow_id}/confirm
POST  /api/workflows/{workflow_id}/runs
GET   /api/runs?workflow_id=...
GET   /api/runs/{run_id}
GET   /api/runs/{run_id}/events?after_event_id=...
POST  /api/runs/{run_id}/cancel
```

数据集接口：

```text
GET  /api/datasets/roots
GET  /api/datasets/directories?root_id=...&relative_path=...
GET  /api/datasets
POST /api/datasets/register
GET  /api/datasets/{dataset_id}
POST /api/datasets/{dataset_id}/inspect

GET  /api/capabilities/tree
GET  /api/artifacts/types

POST /api/conversations
GET  /api/conversations/{conversation_id}
POST /api/conversations/{conversation_id}/compact
```

未设置 `LOCALFLOW_LLM_BASE_URL` 和 `LOCALFLOW_LLM_MODEL` 时，后端使用演示回复。需要连接本机或局域网内的 OpenAI-compatible 服务时，可参考 `bakend/.env.example` 配置环境变量。

## 模型 API 配置

后端启动时会通过 `python-dotenv` 自动读取 `bakend/.env`。先复制示例文件：

```powershell
cd D:\reference_projects\LocalFlow\bakend
Copy-Item .env.example .env
```

然后编辑 `.env`：

```dotenv
LOCALFLOW_LLM_BASE_URL=https://api.deepseek.com
LOCALFLOW_LLM_API_KEY=替换为自己的APIKey
LOCALFLOW_LLM_MODEL=deepseek-v4-flash
LOCALFLOW_LLM_MAX_TOKENS=800
LOCALFLOW_LLM_THINKING=disabled
LOCALFLOW_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
LOCALFLOW_DATA_ROOTS=D:\data;E:\research-data
LOCALFLOW_DATABASE_PATH=./data/localflow.db
LOCALFLOW_OUTPUT_ROOT=../outputs
LOCALFLOW_RUN_WORKERS=2
LOCALFLOW_HISTORY_COMPACT_TRIGGER_TOKENS=12000
LOCALFLOW_HISTORY_KEEP_RECENT_MESSAGES=8
```

重新启动后端后，`GET /api/health` 的 `mode` 应为 `model`，前端顶部会显示当前模型名称。删除或留空 `LOCALFLOW_LLM_BASE_URL` / `LOCALFLOW_LLM_MODEL` 后会回到本地对话演示模式。

面向普通前端对话时建议保持 `LOCALFLOW_LLM_THINKING=disabled`，避免有限的输出额度被思考内容耗尽。如果需要复杂推理，可改为 `enabled`，并相应提高 `LOCALFLOW_LLM_MAX_TOKENS`。

`bakend/.env` 已加入根目录 `.gitignore`，真实密钥不应写入前端代码、`NEXT_PUBLIC_*` 变量、README 或版本库。前端只连接本地 FastAPI，由后端向模型服务发送带密钥的请求。

`LOCALFLOW_DATA_ROOTS` 使用英文分号分隔多个绝对目录。前端不能提交任意绝对路径，只能通过 `root_id + relative_path` 浏览；后端会解析真实路径并拒绝 `..`、符号链接等越界结果。未设置时仅开放项目的 `data` 目录。

`LOCALFLOW_HISTORY_COMPACT_TRIGGER_TOKENS` 是混合中英文的本地保守估算阈值，不是
DeepSeek 官方 tokenizer 的精确计数。压缩默认保留最近 8 条原始消息；摘要失败时
后端不会推进 `summarized_through_sequence`，因此不会静默丢失历史。

## 上游复用与改造边界

Skill 目录、SkillLoader、依赖图校验、离线摘要、103 个 Skill 及其配套文件直接复用自同级 NeuroClaw 项目。NeuroWeave 在外层增加缓存、来源标记、检索 API 和对话适配。具体清单见 `UPSTREAM.md`。

环境管理类 Skill 和上游命令 handler 虽已保留，但只作为说明文件展示；后端不会执行其中的任意命令。样例流程使用独立的 `tool.manifest.json` 声明 capability、输入输出类型、参数和 `runner_id`，实际执行还必须由 `bakend/app/execution/runner_registry.py` 显式注册经过代码审查的 Runner。模型文本、SKILL.md 命令块和前端命令预览都不能越过这个白名单。NeuroClaw 使用 MIT License，许可证副本位于 `THIRD_PARTY_NOTICES/NeuroClaw-LICENSE.txt`。
