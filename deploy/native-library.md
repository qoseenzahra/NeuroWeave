# 原生 Skill / Method / Pipeline 资源库

## 当前状态（2026-09-23）

当前分支定义 249 个独立 Method、105 个正式 Skill（另保留 70 个旧名称别名）、28 个内置 Pipeline。用户保存的 Pipeline 存储于当前部署的 SQLite 数据库，不写入这些内置目录。数量表示定义覆盖，不表示全部软件及其全部参数已经接入或通过真实数据验证。

`/opt` 是本次软件覆盖范围；目前尚未完成穷尽接入。初步扫描 8,982 个带执行权限的条目，其中脚本 1,862、ELF 1,777、不能识别为命令 5,341、不可读 2。脚本和 ELF 候选仍包括重复安装、GUI、环境管理及内部辅助程序。扫描排除了数据、库、文档等目录，不能把结果当作精确命令总数。详见 `software-contracts/opt-inventory.json`。

本批新增 58 个 MRtrix Method，依据服务器 MRtrix 3.0.8 原始帮助建立有类型的输入、输出和参数。110 份原始命令帮助及覆盖报告保存在 `software-contracts/mrtrix3/`。存在可变参数、特殊语法、目录型输入和重复选项未开放的情况，每个 Method 的 `execution.contract.omitted_options` 和详情界面明确列出。不得称为“全参数覆盖”。

新增 Method 的基本真实执行已检查 mrconvert、mrcheckerboardmask、maskfilter、5tt2vis、sh2power、mrhistogram；其余新增命令目前只有定义/注册/构建检查，不宣称全部执行通过。原有六个 MRtrix 命令及独立 tckgen → SIFT2 链路仍通过合成数据检查。所有选项组合与科研正确性不在这些微型测试的证明范围内。

## 定义所有权

- `methods/<group>/<id>/method.json`：最小执行单元，拥有参数、条件、输入输出、版本和 Runner 标识。前端不能上传任意命令或代码。
- `skills/<id>/skill.json`：描述所管理 Method/Pipeline 的用途、选择规则和语义范围。`scope` 区分具体工具与领域任务，防止指定工具时扩大推荐。运行时不再从旧 SKILL.md 读取执行契约。
- `pipelines/<id>/pipeline.json`：引用 Method 的版本、连接关系和参数映射。已有固定多步组合已经独立存储于此。

Runner 仍是明确注册的 Python 适配器。增加 JSON 文件不等于自动获得任意程序执行权；命令通过参数数组调用，文件输入及输出继续经过既有授权检查。

## 使用

侧栏分为 Skill、Method、Pipeline，各自提供分类树、搜索、分页和详情。Skill 可加入或移出当前会话，Method 详情展示参数与运行环境。

在 Pipeline 页面选择“拖拽创建 Pipeline”，拖入 Method（也可点击添加），通过输入输出端口连线，或连接两个输入端口以共享文件；拖动标题自由布局，执行顺序由依赖关系确定。未连接的端口成为整体输入，未被消费的输出成为整体输出。每个步骤可指定参数，继承 Method 的显示、启用、条件必填及互斥规则。

先校验再保存。保存创建不可覆盖的版本；编辑使用版本校验，历史版本保留。已有流程也可以用“保存为可复用 Pipeline”导出，导出时展开真实执行单元并移除原样本文件路径。Pipeline 的整体文件输入在下次调用时重新选择。

“创建流程并配置运行”生成普通工作流，不提交计算。文件绑定、输出目录、参数复核、dry run、确认和 Slurm 资源选择沿用原有流程。当前仅支持从前序步骤到后序步骤的有类型连接，不支持循环。条件输出可内部连接，保存与运行前按上游有效参数检查是否生成；多文件聚合输入暂需作为外部输入。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/library?kind=skill\|method\|pipeline&q=&cursor=0&limit=100` | 分页目录 |
| GET | `/api/library/methods/{id}` | 完整 Method 与环境状态 |
| GET | `/api/library/pipelines/{id}?version=1` | Pipeline 或指定版本 |
| POST | `/api/library/pipelines/validate` | 校验连接并推导整体接口 |
| POST | `/api/library/pipelines` | 保存新 Pipeline |
| PUT | `/api/library/pipelines/{id}` | 以 expected_version 保存新版本 |
| POST | `/api/library/pipelines/{id}/workflows` | 创建待复核工作流 |
| POST | `/api/library/from-workflow/{workflow_id}` | 按 expected_revision 导出当前流程 |

写接口沿用同源来源检查和维护模式。没有新增通用 Shell、软件安装、系统服务管理或提权接口。

## 验证与部署

后端目录运行 `python -m pytest tests -q`；前端目录运行 `npm test`、`npm run lint`、`npm run build`。服务器合成检查：

```bash
/opt/neuroweave/envs/scientific-py311/bin/python scripts/smoke_mrtrix_commands.py --work-dir /明确指定的新测试目录
```

该脚本拒绝复用非空目录，不扫描用户数据。测试服务仅使用 3002。发布前核对变更文件旧哈希，发现服务器不同修改则停止；先建隔离副本执行验证。Worker 发布到新目录，保留旧目录给已有任务，不原地删除旧输出。仅在测试运行队列为空时重启测试后端。生产 3000 和运行中的任务保持不变。

## 仍需完成

1. 对 `/opt` 其余 FSL、ANTs、FreeSurfer、Python 环境入口等逐项确认正式 CLI、内部程序和重复安装。
2. 按真实软件接口补齐缺失 Method 及参数条件，并分别完成命令构建、执行和 Slurm 验证。
3. MRtrix 尚未开放的复杂参数与目录型方法需专门适配器；不要用自由字符串或 Shell 替代。
4. 在真实浏览器继续检查大型分类树、拖拽和低分辨率布局；构建与单元测试不能替代浏览器验收。


## 本次发布验证结果

- 本地后端：285 项测试、678 个子用例通过，3 项环境相关跳过；随后增加的 HTTP 集成及格式复核共 17 项通过。
- Linux 完整副本：289 项测试、678 个子用例通过；最后八份输出格式修正单独复核 17 项通过。
- 前端：32 项测试、lint、TypeScript 和生产构建通过。构建有单个 JS 包超过 500 kB 的体积提示。
- 合成 MRtrix：12 个命令及 tckgen → SIFT2 链路完成，不代表每种参数组合均已验证。
- 两步 mrconvert Pipeline 在 node01 上以每步 1 CPU、2 GB、3 分钟限制执行；作业 6340、6341 均 COMPLETED / 0:0，输出体素数值与输入一致。
- 首次 Slurm 验证脚本遗漏正式制品解析，第二步预检失败；脚本改用 RunService._resolve_runtime_bindings 后重测通过。没有修改生产制品解析来绕过检查。
- 测试入口：http://192.10.84.6:3002/ ，未提交 GitHub，生产 3000 未变更。发布后资源目录实际返回 Skill=175、Method=249、内置 Pipeline=28。
- 服务器备份：`/home/hipeson/.cache/neuroweave/library-validation-bsckh70w/publish-backup`。
- Worker：`/home/data/neuroweave/testing/methods-20260922/code-library-20260922T094532Z`；旧 Worker 保留。
- Slurm 证据：`/home/data/neuroweave/testing/methods-20260922/smoke-library-20260922T094959Z/evidence.json`。

复现两步子节点检查（只对这次测试部署使用）：

```bash
/opt/neuroweave/envs/scientific-py311/bin/python scripts/smoke_library_slurm.py /home/data/neuroweave/testing/methods-20260922/code-library-20260922T094532Z
```


## 节点画布更新

Pipeline 编辑器已改为节点画布：从左侧将 Method 拖到画布，自由移动节点标题，从右侧输出端口拖线到目标节点左侧输入端口；也可以依次点击两个端口。选中节点后在右侧设置参数。支持平移、缩放、自动排列、选中连线后删除，以及移除节点。

连接按真实端口类型校验，拒绝自环、循环依赖和缺失端口；条件输出按有效参数校验，不再一律禁止连线。保存时根据连接拓扑排序，不按画面左右位置决定执行顺序。移除上游节点后，消费者端口恢复为整体输入。

节点位置按 Pipeline ID/版本保存在当前浏览器；步骤、连接和参数仍保存服务器。位置数据不发送给执行接口，不影响正在运行的任务。浏览器存储不可用时，流程保存仍成功，界面提示下次使用默认布局。

修复 HTTP 内网页面没有 crypto.randomUUID 时在 React 状态更新中抛错导致白屏的问题。ID 生成改用 HTTP 可用的 getRandomValues，并在更新 React 状态前生成；编辑器增加局部错误边界。

验证：前端 39 项测试通过，含 HTTP ID、循环与类型约束、拓扑排序、布局恢复、实际组件渲染和保存请求检查；构建与 lint 通过。浏览器自动化访问内网地址失败，未完成真实浏览器拖拽验收。此次只发布前端与文档，后台正在处理数据，不重启后台、不改 Worker。


### 条件响应函数连接修复

响应函数估计的白质输出无条件生成，灰质和脑脊液响应仅在 Dhollander 下生成。画布现在允许同时连接这三个端口；若参数改成 Tournier，保留连线并提示需要 Dhollander，阻止保存无效配置。服务端保存/校验也检查有效参数；保存后在工作流中修改参数，现有 RecipeCompiler 仍在 dry run 和创建运行之前重新校验输出。

三组织响应用于 FOD 时，选择响应算法 Dhollander、FOD 算法 MSMT-CSD。单组织 Tournier → CSD 仅连接白质响应仍可使用。本次不修改算法、软件命令或执行 Runner。


### 共享输入（输入 ↔ 输入）

在画布中从一个输入端口拖到另一输入端口，或依次点击两个输入端口，建立紫色虚线共享组。组内步骤只需绑定一个公共文件输入，按样本选择及历史结果绑定也复用同一组引用。共享不增加执行先后依赖，不复制文件。点击虚线或右侧输入的“解除共享”可退出共享组；移除节点会保留其余成员的共享关系。

编辑协议的 `shared_inputs` 是输入端口组数组，成员为 `{step_id,input_slot_id}`。服务端校验真实端口、唯一成员、类型、文件/目录形式、文件数量及共同格式/来源，再把各消费者的已有 `workflow_input` 绑定指向同一公共输入。已经绑定上游输出的端口需先解除原连接，防止静默覆盖。共享输入的格式取交集，校验和 companion 要求取并集；必需性为消费者必需条件的 OR，以 `required_when_any` 保留参数切换时的动态判断。算法方法与软件调用均保持原定义。
