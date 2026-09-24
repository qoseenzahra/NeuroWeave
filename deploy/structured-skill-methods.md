# Skill 统筹、Method 执行、Pipeline 组合

本分支 `codex/structured-skill-methods` 采用新的唯一契约结构，不兼容旧 manifest、方法 ID 或历史工作流快照。测试应使用独立数据库、输出目录及 Worker release，不能把本分支直接覆盖到仍在运行旧任务的生产目录。

## 三种对象

| 对象 | 职责 | 不承担的职责 |
| --- | --- | --- |
| Method | 一项已接入的命令、库操作或原有不可拆脚本；定义参数、条件、输入输出和可信适配器 | 不选择其他方法，不隐式追加处理阶段 |
| Skill | 描述能完成的功能，说明方法角色、适用条件、选择规则；引用多个方法或流程 | 不复制方法参数，不成为计算执行器 |
| Pipeline | 引用方法版本，连接端口、映射参数、声明整体输入输出 | 不生成新算法，不使用任意 Shell |

方法是平台调度的最小执行单位，并不等同于原软件中的每一个内部函数。原有科学脚本保持原实现；不能为了拆分而发明新的算法 API。单命令参数预设可以是单步骤 Pipeline。

```text
methods/<software-or-group>/<method-id>/
  method.json                    # 唯一参数、端口、执行适配器契约
skills/<skill>/
  skill.json                     # selection_rules / method_refs / pipeline_refs
  SKILL.md                       # 原始参考，按需分页读取
  references/                    # 固定版本原始帮助与来源
pipelines/<pipeline-id>/
  pipeline.json                  # 显式步骤、参数和端口连线
```

目前有 328 个独立方法、105 个规范 Skill、28 个内置组合流程（2026-09-24）。原来的两套去噪/Gibbs 入口已合并；169 个缺少可审核实现的规划条目单独保存在 Skill 的 planning_capabilities，不能伪装成可执行方法。方法数量不代表全部已安装软件的命令覆盖率，更不代表所有方法已通过真实数据验证。

## 调用链

能力树定位需求 → Skill 选择规则/方法角色 → 按需读取独立方法或流程 → 用户选择与参数输入 → 输入绑定与 Dry-run → 确认 → Pipeline 展开为独立方法 → Runner 白名单 → 本地/Slurm 执行。

同一方法可被多个 Skill 引用，其输入输出和参数只维护一份。Skill 中的 method_id 是该任务语境中的候选入口标识；definition_id 才是全局方法标识。新项目无需迁移旧候选标识；执行、详细参数查询和 Pipeline 引用均以全局定义为准。

`mrtrix.tckgen` 现在只生成流线；`mrtrix.command.tcksift2` 单独接收已有流线和 FOD，并生成权重。ACT 可以复用已有 5TT，不默认生成 5TT。明确需要的组合由 Pipeline 连接，前端可以查看每一步和参数映射，运行结果仍按实际子步骤记录。

## API 和模型读取

- `GET /api/skills/{skill}/methods?kind=method|pipeline|capability&q=...&cursor=...&limit=20`
- `GET /api/methods/{method_id}`
- `GET /api/pipelines/{pipeline_id}`
- `GET /api/skills/{skill}` 返回 orchestration 与紧凑概览。
- `GET /api/skills/{skill}/reference` 分页读取原文。

模型工具：`list_skill_methods`、`read_skill_method`（全局 method_id，参数/端口分页）、`read_skill_pipeline`、`read_skill_reference`。这些只读工具不会运行科学计算。前端目录区分“独立方法 / 组合流程 / 待接入能力”。环境探测只表明当前机器的入口状态；远端节点、输入和资源仍须 Dry-run 检查。

## 增加或修改方法

1. 固定软件版本和官方帮助/原脚本来源，审核具体真实入口。
2. 在 methods 中增加或修改 method.json：描述用途，声明带说明的参数、输入输出、条件和执行适配器。语义变更增加 version，并显式更新相关 Pipeline 的 method_version。
3. 新命令必须有受信 Runner 和固定 argv/API 映射；发现可执行文件不自动授权执行。已有 command/reviewed 适配器仍受参数、路径、源码审核和环境检查约束。
4. 在一个或多个 skill.json 的 method_refs 中引用全局 ID，用 role 解释该 Skill 使用它的目的。禁止在这里声明 parameters/input_slots/output_slots。
5. 组合操作放进 pipelines，不写入单个方法 Runner。必须显式声明 public inputs、参数映射、固定参数、上游输出连接与整体输出；步骤必须按拓扑顺序排列。不允许向前引用或循环。
6. 更新紧凑概览，运行契约、编译、参数边界测试，并在隔离环境验证实际软件调用。

```bash
python scripts/build_mrtrix_commands.py --check
python scripts/build_skill_layers.py
python scripts/build_capability_tree.py
python scripts/audit_method_documentation.py --output deploy/skill-runtime/method-documentation.json
python scripts/check_release.py
PYTHONPATH=bakend python -m pytest bakend/tests -q
cd frontend
npm test
npm run lint
npm run build
```

MRtrix 命令及新增的 FSL、ANTs、FreeSurfer 命令由审核定义和版本帮助快照生成。`force/config` 等选项由平台管理或禁止，排除原因有明确记录。其他方法契约直接在 methods 中审核维护，不再通过旧 planning/execution manifest 生成器反向生成。

## 边界与部署

507 个已登记参数中，199 项仍需补充足够的语义说明，详见 method-documentation.json；本次结构迁移没有编造说明，也没有声称所有常用软件命令均已接入。可执行性、参数文档完整性、真实数据正确性是独立状态。

Pipeline 在本次是受审核的目录对象；用户保存流程和拖拽编辑器仍未实现。旧 Skill 原文中提及的能力不会自动获得执行权限。

当前仅修改本地分支并在隔离测试目录验证，不更新 GitHub、不重启生产前后端、不影响运行中的任务。后续部署必须在维护窗口或单独测试服务使用全新运行数据库，并包含 methods/、pipelines/ 和 skills/；Slurm release 打包脚本已纳入这些目录。

迁移清理说明：运行时已不读取旧 manifest/规划映射。自动审批暂未允许删除本地 206 个旧文件，当前保留待用户确认；它们不属于新的执行契约来源。隔离测试包仅包含新结构。


## 本次验证（2026-09-22）

- Linux 隔离副本完整后端：275 项测试、606 个子用例通过（当时共 275 项）；最后增加的就绪状态回归另测 Skill/HTTP 接口 17 项通过。
- 本地新结构/模型目录/流程编译定向回归：32 项、65 个子用例通过。
- 前端 32 项测试、ESLint、TypeScript/Vite 构建通过；保留大包体积提示。
- 发布结构、固定 MRtrix 帮助生成器、103 个 Skill 概览一致性检查通过。
- 服务器隔离目录实际运行六个 MRtrix 命令；另以合成 FOD 执行独立 tckgen，生成 20 条流线，通过生产制品绑定函数交给独立 SIFT2，生成 20 个有限权重。该测试不代表 ACT 或临床数据正确性验证。
- 未开启本地前后端服务；未修改生产部署或 GitHub，未停止后台任务。
