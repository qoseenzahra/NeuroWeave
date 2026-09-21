# Skill 分层与命令契约

2026-09-21，分支 `codex/structured-skill-methods`。在现有架构上增量修改，保留原 Skill、方法身份、能力树、规划映射和 Runner。原始 Skill 文档与科学算法实现没有被改写。

## 结构和读取方式

```text
skills/<skill>/
  OVERVIEW.md                 # 简短入口，默认模型上下文使用这一层
  SKILL.md                    # 保留原始参考，按需分页读取
  planning.manifest.json      # 原规划契约
  tool.manifest.json          # 原工具契约（若有）
  execution.manifest.json     # 原审核执行契约（若有）
  commands/<command>.json     # 新增的独立命令契约；显式白名单
  references/<version>/      # 对应软件版本的原始帮助和类型信息
```

103 个 Skill 都有概览。381 个原始方法定义统一进入目录，列表只返回摘要；详情才读取该方法的参数、输入输出及运行环境。列表合并同一 Skill 内契约完全相同的别名，旧身份仍可解析。原始定义数量包含别名，不是 381 种独立算法。

模型在查阅参数之前先检索方法，选定后分页读取参数/输入/输出；背景资料另行读取。新增工具只读，不运行计算、不接受自由 Shell。执行仍经过现有规划、参数审核、Dry-run、确认和 Runner。未选择数据集时也可以询问命令说明。

前端 Skill 详情提供“概览 / 命令与方法 / 原始参考 / 相关文件”，支持检索、加载更多、参数折叠和参考文档翻页。查看不改变会话所选 Skill。

## API 与模型工具

| API | 用途 |
| --- | --- |
| `GET /api/skills/{id}` | 简短概览、参考长度和文件索引；原全文改由 reference 接口读取 |
| `GET /api/skills/{id}/methods?q=&cursor=&limit=20` | 方法摘要；limit 最大 50，可选 executable_only |
| `GET /api/skill-methods/{capability}/{method_id}` | 选定方法完整契约、定义哈希、环境探测和覆盖情况 |
| `GET /api/skills/{id}/reference?offset=0&max_chars=6000` | 原 Skill 参考文本；单次最大 12000 字符 |

模型函数：`list_skill_methods`、`read_skill_method`、`read_skill_reference`。模型方法读取仅允许 overview/parameters/inputs/outputs 分节，不允许全量 all。参数类型与分页范围在后端检查；不接收调用方传入的任意文件路径。工具事件复用现有对话时间线，查询结果可交给后续规划。

## 参数规则

保留 `visible_when`，增加 `required_when`、`enabled_when`、`conflicts_with`、`condition_help`、`usage`、`software_default`、`documentation_url`。规则采用明确的 JSON 值比较，不执行表达式；0、false 和未设置分开处理。

草稿允许先选模式，再填写该模式要求的参数；正式审核仍验证完整性。隐藏/禁用参数可以保留草稿，但不会传入命令。前后端执行同样的生效条件，Runner 另作独立校验。互斥参数拒绝同时提交，非有限数值拒绝提交。

例：mrthreshold 选择 abs 才显示并要求绝对阈值；tckresample 选择 line 才要求 num/start/end；tcksift2 启用 fd_scale_gm 必须绑定已有 ACT 5TT，并不会自行补入 5TT 生成步骤。

## 新增实际执行入口

以下 6 项依据服务器安装的 MRtrix3 3.0.8 原始帮助定义，每项有独立输入输出和参数契约；方法详情保留原帮助的用途与使用前提，参数保留多行说明：

| 命令 | 作用 |
| --- | --- |
| `dwidenoise` | DWI MP-PCA 去噪，可选择保存噪声图 |
| `mrdegibbs` | Gibbs 振铃校正 |
| `5tt2gmwmi` | 从已有 5TT 生成灰白质界面种子 |
| `tcksift2` | 对已有流线与 FOD 赋权，可选择保存 mu、系数等 |
| `mrthreshold` | 自动、绝对值、百分位、最高/最低体素数阈值 |
| `tckresample` | 上/下采样、步长、点数、端点、直线和圆弧重采样 |

原有 tckgen/ACT/5TT 等 Runner 保留，未改写其算法。此次不是所有软件所有命令的全覆盖。6 项命令的原始选项均有“开放”或“排除原因”的登记：force/config 等由平台管理，tcksift2 的 output_debug 未接入输出槽位。精确覆盖见 `deploy/skill-runtime/method-documentation.json`。

执行通过固定可执行文件与 argv 数组；路径绑定独立于参数，不接收任意命令、目标文件名或配置键。输出位于本次运行目录，复用已有授权路径检查。Slurm CPU 分配在提交前及节点执行时检查；MRtrix nthreads=0 按软件定义为关闭多线程。运行版本不等于 3.0.8 时拒绝使用该版本的契约，需要重新审核。

## 现有文档补齐与边界

从原脚本的 argparse help、必需文件声明和入口位置补回 142 处原先空白的参数说明（包含别名计数），不凭参数名称编造算法含义。扫描器只做 AST 静态读取，不导入或执行训练脚本。

当前 276 个 Runner 方法定义共有 850 个登记参数项，其中 384 项仍缺少足够的语义说明，已列为 needs_review，未用模板文案冒充完整说明。后续应逐项依据原代码/对应版本官方文档补齐。方法的运行就绪、参数说明完整和真实数据验证是三个独立状态。

## 维护与复现

在仓库根目录运行；生成器输出应随源码一起提交：

```bash
python scripts/build_mrtrix_commands.py
python scripts/build_reviewed_execution.py
python scripts/build_planning_resolution.py
python scripts/build_skill_layers.py
python scripts/audit_method_documentation.py --output deploy/skill-runtime/method-documentation.json
python scripts/check_release.py
PYTHONPATH=bakend python -m pytest bakend/tests -q
cd frontend
npm test
npm run lint
npm run build
```

新增其他软件命令时，先固定实际软件版本和原始帮助、确认输入输出与所有路径选项，再增加显式命令契约和可信适配器；环境里出现一个可执行文件不会自动开放它。新增命令须有参数/路径/资源校验和合成输入验证。Pipeline 保存及拖拽编辑不属于本次实现。

MRtrix 路径由 `LOCALFLOW_MRTRIX_ROOT` 配置；服务器现有值对应 `/opt/software/mrtrix3-master`。Windows 上没有对应命令时，目录与参数说明仍可查看，运行探测会明确不可用。

安装 nibabel/numpy 的科学环境可复现六命令验证，work-dir 必须不存在或为空；脚本不提交 Slurm、不访问用户数据：

```bash
/opt/neuroweave/envs/scientific-py311/bin/python scripts/smoke_mrtrix_commands.py \
  --work-dir /home/hipeson/.cache/neuroweave/一次新的合成测试目录
```

## 验证与部署状态

- 后端完整回归：265 个测试、610 个子用例通过；之后增加的模型工具调度和参数类型测试另行执行。
- 本地工作流回归：66 通过、2 个平台相关用例跳过；Slurm/Skill 最终定向回归 29 通过；服务器最后一轮受影响模块回归 52 通过、17 个子用例通过；保留多行帮助的新用例加入后，Skill/命令契约 15 个测试通过。
- 前端：构建、ESLint、30 个测试通过。Vite 有现存大包体积提示；没有构建错误。
- 实际组件浏览器测试：方法检索/详情、原参考 6000 字符分页、模式切换、条件必填、零值保留；390×600 视口无横向溢出，关闭按钮和底部操作可见；无浏览器控制台错误。API 响应使用真实契约生成的隔离夹具，未操作用户会话。
- 服务器合成数据：六命令均产生预期数量的非空制品；绝对阈值结果逐体素匹配、重采样每条流线 10 点、SIFT2 权重数匹配流线且数值有限。这证明调用链和基本输出约定，不代表所有参数组合或科研数据有效性均已验证。
- 模型工具调度使用模拟模型返回函数调用验证，包括向后续规划传递只读观察；未调用付费模型评估自然语言选择质量。
- 测试目录：`/home/hipeson/.cache/neuroweave/skill-layers-20260921`。未替换 `/home/hipeson/LocalFlow`，未重启生产后端，未提交真实 Slurm 任务；本地临时前端已关闭。
- 原 3001 容器 `neuroweave-frontend-new-frontend-new-1` 已停止，restart=no；未删除容器、源码、运行记录或输出。3000 HTTP 200，生产后端 PID/启动时间保持不变。

本分支同时修改前后端接口，不能只把新前端覆盖到旧后端。生产激活尚未执行；后续发布需要先比较服务器有效改动、完整回归，再按现有发布流程更新兼容前后端，并在确认没有受影响的活动任务后安排后端切换。数据库字段不变，旧 Workflow 可通过模型默认值读取；运行记录及旧输出不做迁移清理。
