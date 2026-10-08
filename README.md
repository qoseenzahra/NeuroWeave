# NeuroWeave

NeuroWeave 是面向服务器文件系统的神经影像工作流平台。用户通过对话或节点画布组织处理步骤，选择输入、输出目录和运行资源，审核后由受信任 Runner 调用已有软件命令、库 API 或已接入的脚本。

本文描述当前 `main` 的产品与开发方式。当前静态目录包含 **328 个 Method、105 个规范 Skill、24 个内置 Pipeline**；用户发布的 Pipeline 另存于各部署的 SQLite，不计入静态数量。数量表示已登记的定义，不能证明所有软件已安装、全部选项已接入或每种方法已经过科研验证。

## 能力组织

| 对象 | 职责 | 定义位置 |
| --- | --- | --- |
| Method | 最小执行单位，拥有版本、参数、条件输入输出和执行适配器 | `methods/<group>/<id>/method.json` |
| Skill | 描述功能、适用范围和方法选择规则，引用已有 Method/Pipeline | `skills/<id>/skill.json` |
| Pipeline | 可复用的有向无环流程，引用方法版本、参数映射和端口连接 | `pipelines/<id>/pipeline.json` 或用户数据库 |

技能侧栏包含 Skill 和 Method，Pipeline 使用独立侧栏；三类目录均支持分类浏览、软件筛选、搜索和详情。Skill 分为任务、软件工具、数据集专属三类，描述方法角色和选择依据。原始参考文档只供按需查阅，不会因其中出现命令而获得执行权限。维护说明见 [原生契约结构](deploy/structured-skill-methods.md) 和 [资源库使用](deploy/native-library.md)。

## 工作方式

- **对话与规划**：模型结合当前数据集、输出目录和已选流程理解本轮需求，区分解释、文件查询、新建或修改流程。需求契约记录目标、允许复用的输入和禁止复用的结果；能力树、方法语义与真实输入输出共同检索。候选不匹配时给出原因，不强制推荐第一个方法。
- **任务管理**：统一显示对话规划与 Pipeline 目录创建的任务，支持搜索、来源/最新运行状态筛选、分页、输入输出摘要及运行历史。“从 Pipeline 创建任务”先选择版本、本次输入数据集和输出目录；创建后进入配置，不提交计算，也不改变当前对话上下文。数据集可稍后手动绑定，输出目录必须先选定。
- **流程编辑**：确认步骤后锁定数据集，再绑定文件和调整参数。参数变化同步更新条件输入输出；可以移除步骤并手动提供中间文件。方案和步骤均可折叠。
- **Pipeline 画布**：支持端口连线、共享输入、有序多来源、参数详情、缩放/平移、自动布局和校验。内置及已发布版本以只读画布展示，“基于此 Pipeline 创建”生成独立副本。草稿与用户发布 Pipeline 均可删除和恢复；已有任务保留不可变执行快照。只有点击“生成说明”才调用模型生成描述。
- **文件管理**：数据集用于受限、只读的数据访问；独立选择的输出目录用于保存和管理结果。浏览的是服务器目录，不是浏览器所在电脑的文件。文件操作使用结构化接口、路径授权、确认和回收站。
- **历史结果**：按原数据集及样本标识绑定旧输出；覆盖不完整时可以仅运行输入齐全的样本，无需复制整理原结果。
- **执行与监控**：审核参数、完成 Dry-run 和检查限制确认后提交本地或 Slurm。单样本也能选择计算节点；多样本可分配多节点，并分别设置并行数、CPU、内存、GPU 和时限。时限针对每个样本的每一步作业，不是整个数据集的总时间。
- **历史与语言**：对话列表加载摘要，正文按页读取；任务分组分页监控。非对话界面随系统语言切换，用户对话、路径、命令标识和自定义内容保留原值。

浏览器断开不取消已接受的后台计算。Slurm 使用固定版本 Worker；停止本地后端可能影响其直接管理的本地执行进程，因此发布前必须检查任务状态。Dry-run 检查契约、文件和部分影像头信息，不证明空间对齐或科研结论正确。

## 源码结构

```text
frontend/                  React 19 / TypeScript / Vite 页面
bakend/app/                FastAPI、对话、工作流、文件接口和 Runner
bakend/tests/              后端契约、安全与行为回归
bakend/resources/          能力树、类型、翻译与可信执行登记
methods/                   独立方法契约
skills/                    skill.json 指导、登记的按需参考资料及既有脚本
pipelines/                 内置 Pipeline
models/                    方法引用的已有模型实现
scripts/                   检查、打包、发布及合成验证工具
deploy/                    使用、配置、维护及带日期的验证记录
THIRD_PARTY_NOTICES/       第三方许可证
```

`bakend` 是实际目录名。原有 `LOCALFLOW_*` 环境变量、`workspace_id` API 字段和部署路径仍在使用，不应根据产品名称自行改名。模块职责和扩展入口见 [代码维护指南](deploy/code-architecture.md)。

## 本地开发

CI 使用 Python 3.11 和 Node.js 24。后端使用仓库锁文件安装依赖；科学软件环境与 API 环境分开管理。以下 PowerShell 命令从项目根目录开始：

```powershell
python -m venv bakend/.venv
./bakend/.venv/Scripts/python -m pip install --no-deps -r bakend/requirements-dev.lock
./bakend/.venv/Scripts/python -m pip check
if (!(Test-Path bakend/.env)) { Copy-Item bakend/.env.example bakend/.env }
```

编辑 `bakend/.env`，按实际目录设置 `LOCALFLOW_DATA_ROOTS`、`LOCALFLOW_RUN_INPUT_ROOTS` 和输出目录访问范围。模型配置使用 `LOCALFLOW_LLM_BASE_URL`、`LOCALFLOW_LLM_MODEL`、`LOCALFLOW_LLM_API_KEY`；密钥仅保存在后端。未配置模型时的演示回答不等于真实模型规划验收。完整目录权限配置见 [数据集与输出目录](deploy/workspaces.md)。

```powershell
# 终端一：后端
cd bakend
./.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

```powershell
# 终端二：从项目根目录启动前端
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Linux 使用对应的 `.venv/bin/python`。打开 `http://127.0.0.1:5173`；Vite 将 `/api` 代理到 `127.0.0.1:8010`。测试结束后在两个终端按 Ctrl+C 关闭服务。开发页面连接的仍是后端账户可访问的文件系统。

## 检查与发布

```powershell
# 从项目根目录，使用与 CI 一致的锁定依赖
$env:PYTHONPATH='bakend'
$env:LOCALFLOW_SLURM_ENABLED='false'
./bakend/.venv/Scripts/python -m pytest bakend/tests -q --tb=short
./bakend/.venv/Scripts/python scripts/check_release.py
./bakend/.venv/Scripts/python scripts/build_capability_tree.py --check

cd frontend
npm run lint
npm test
npm run build
```

后端测试使用隔离的临时数据库和合成文件；命令的真实执行证据另见 [质量检查与证据](deploy/catalog-quality.md)。发布检查会验证原生契约、Runner 登记、参数绑定、双语覆盖和依赖锁。不要用早期 bootstrap 生成器覆盖已经人工完善的 Method JSON。

主站使用 **3000**；已有 **3002** 开发副本使用独立数据库和输出目录，版本可能落后于 main。新增开发部署应使用独立分支、端口和数据目录，具体目标在当次发布前确定。GitHub 推送不会替换服务器部署；当前服务、路径及发布检查见 [服务器部署与维护](deploy/server-deployment.md)。

平台目前使用单一后端账户；目录白名单、只读数据集、文件操作确认和 Runner 登记构成现有权限边界，尚无用户级登录、对象归属或多租户隔离。模型建议仍须经过契约校验和用户确认。

当前使用、维护和历史发布记录见 [文档索引](deploy/README.md)。原有实现来源与许可证见 [来源记录](UPSTREAM.md) 和 [第三方声明](THIRD_PARTY_NOTICES/)；实现仍按当前 Method、Runner 和权限契约接入。
