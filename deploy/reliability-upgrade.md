# 2026-09-08 可靠性与维护改进

按原审查编号落实 3、5、6、7、8、10、11、13、14。沿用现有项目、部署和可信 Runner；没有新增算法实现，也没有修改 Skill 的方法定义。

## 本次实现

| 原编号 | 改进 | 使用方式和边界 |
| --- | --- | --- |
| 3 | 失败/取消任务按步骤重试；复用已核验的成功上游；SlurmDBD 持久记账 | 监控区点击“重试未完成步骤”，或展开失败步骤选择“重试此步骤及后续”。生成新 Run，保留原记录。API 也支持 sample_ids。状态不确定的 Slurm 作业必须先恢复监控，不能盲目重提。 |
| 5 | 日志游标、实时尾部与历史翻页 | 初始读取最新 200 条，持续从 event_id 之后拉取；页面显示最近 20 条，可以向前翻页及回到实时。历史页不会随轮询跳走。 |
| 6 | 扫描、重扫与 Dry-run 后台检查队列 | 返回任务 ID，显示进度并可取消；两个检查 Worker，最多 16 个活动/排队检查，同一检查去重。检查提交前复核流程版本，避免旧结果覆盖新参数。普通阻塞接口改在线程池执行，目录统计也按需后台执行。 |
| 7 | 增量运行状态存储和读取 | 流程快照只保存一次，步骤分别保存；轮询仅传变更步骤。普通进度每步骤最多每秒保存一次，原始日志和终态事件仍完整保存。旧 JSON 记录可读取，并在更新时迁移。 |
| 8 | 每节点共享样本队列 | 同一节点的并行槽位完成一个样本后立即领取该节点下一个样本；保持每个样本的步骤依赖顺序、节点分配和并行上限。不同节点之间不自动搬迁已分配样本。 |
| 10 | 对话正文分页、历史流程按需加载 | 默认最近 40 条，向前加载并保持阅读位置；仅自动获取最近流程，其他卡片展开时加载，最多同时请求两个流程。即使当前流程消息尚未加载，也保留流程入口和数据集锁定。模型的工作摘要机制继续沿用。 |
| 11 | 运行资源草稿持久保存 | 节点、CPU、内存、GPU、时限、每节点并行数等设置自动保存。刷新后恢复；旧任务可回填最后一次运行设置。多页面修改通过草稿版本冲突保护，避免静默覆盖。 |
| 13 | 依赖锁、CI、版本化发布和回退 | 后端生产/测试依赖锁、前端 npm lock；GitHub Actions 检查后台、前端和发布结构。发布使用 Git 提交包、校验和与不可变 Worker/镜像；健康接口和“存储与备份”显示版本。 |
| 14 | 在线备份、恢复校验、保留策略、磁盘统计 | 侧栏“存储与备份”查看磁盘余量、最近备份和前 20 个大运行目录。SQLite 使用 Backup API，每份执行完整性、外键和独立文件恢复校验；保留最近 14 份。后台检查结果保留 14 天；科研输入、输出与 Run 审计不自动删除。 |

重试复用要求：成功步骤的输入文件哈希、方法声明及相关实现指纹、输出文件路径/大小/哈希均可核对，而且必要上游已复用。旧记录缺乏证据、目录输入/输出、文件被更换、实现改变时，会重做所需上游；这不等于软件内部迭代的任意断点续算。长任务应使用 Slurm；本地执行进程仍会随后端停止而取消，之后可以显式重试。

后台取消是协作式取消：遍历和各样本/步骤之间设检查点；已在运行的外部只读预检命令可能需要等其退出或超时，页面显示“等待当前检查退出”。一旦检查结果已经提交，晚到的取消不会把成功结果伪装成未提交。

## Slurm 持久记账

管理员在 mgr 执行了：

```bash
bash /opt/neuroweave/admin/enable_slurm_accounting.sh
```

现为 Slurm 21.08.5 + 匹配版本 SlurmDBD + MariaDB 专用库 `neuroweave_slurm_acct`。配置为 `AccountingStorageType=accounting_storage/slurmdbd`、`JobAcctGatherType=jobacct_gather/linux`，保留原 GPU、分区和进程隔离设置。数据库凭据只在服务器受限配置中生成和保存，不进入源码或发布包。

三个节点分别提交作业 266、267、268，使用共享输出目录和 `/opt/neuroweave/envs/torch-cu128-py311/bin/python`；实际 CUDA 矩阵运算通过，`sacct` 返回 `COMPLETED`、`ExitCode=0:0`。前面的配置验证失败作业同样可查。启用之前未存入 SlurmDBD 的历史无法补造；NeuroWeave 原有 Run 和 Worker 终态证据继续保留。

```bash
sacct -j 266,267,268 --parsable2 --format=JobID,JobName,State,ExitCode,Elapsed,AllocCPUS,NodeList
```

各主机配置备份在 `/var/backups/neuroweave-accounting/<host>-<timestamp>`。需要撤销时，先停提交、确认空队列，再在各主机运行：

```bash
sudo python3 /opt/neuroweave/admin/configure_slurm_accounting.py --rollback /var/backups/neuroweave-accounting/具体备份目录
```

核对四台配置一致后，重启控制器和各 slurmd。回退配置不删除 MariaDB 或已有作业历史。应用 SQLite 备份不包含 MariaDB 的物理文件；SlurmDBD 数据库应另外纳入管理员的 SQL 备份策略，可使用 MariaDB 自带的 `mariadb-dump --single-transaction neuroweave_slurm_acct`，将输出写入受限备份目录。不要在线直接复制 MariaDB 数据文件。

## 发布和回退

1. 开发检查：`PYTHONPATH=bakend python -m pytest bakend/tests -q`、前端 lint / TypeScript / 组件回归 / build、`python scripts/check_release.py`。CI 使用 Python 3.11、Node 24；服务器前端继续使用 Node 22 基础系列，Node/nginx 镜像已固定到核对过的 SHA-256，前端依赖由 package-lock 锁定。
2. 后端按 `bakend/requirements.lock` 安装，并运行 `pip check`。锁文件记录的是 API 环境，科学和 PyTorch 环境分别由 `deploy/python-environments/locks/` 管理。更新依赖时要重新生成锁并跑同样检查；发布脚本会拒绝与锁不符的后端环境。
3. 提交已审核代码后运行 `python scripts/package_release.py --output runtime/releases`。把 SHA-256 核对后的包解压到 mgr 的 `/home/hipeson/.cache/neuroweave/releases/<完整提交号>`，包中带 `revision.txt`。不要把 .env、数据库、输入、输出或本地环境放入源码包。
4. 先构建前端，当前服务继续运行：

```bash
python3 scripts/deploy_frontend_release.py --source /home/hipeson/.cache/neuroweave/releases/完整提交号 --revision 完整提交号 --build-only
```

5. 确认无活动 Run 后发布后端。脚本检查依赖、保留源码/环境和数据库备份，发布新的共享 Worker，健康/版本检查通过后退出维护状态：

```bash
python3 scripts/deploy_slurm_release.py --source /home/hipeson/.cache/neuroweave/releases/完整提交号 --revision 完整提交号 --enable-slurm
python3 scripts/deploy_frontend_release.py --source /home/hipeson/.cache/neuroweave/releases/完整提交号 --revision 完整提交号 --activate-only
```

6. 后端发布出错会停止并保留现场；前端切换出错会尝试恢复原镜像。主动回退时先停止新提交，核查无活动任务，使用对应发布打印的备份目录：

```bash
python3 scripts/deploy_frontend_release.py --rollback /home/hipeson/.cache/neuroweave/frontend-backups/具体备份目录
python3 scripts/deploy_slurm_release.py --rollback /home/hipeson/.cache/neuroweave/deploy/具体备份目录
```

后端回退先备份当前数据库，再把增量 Run 记录转换成旧版可读的完整 JSON，保留最新任务和科研输出；不会直接用旧数据库覆盖。新增源码文件移到备份目录保存，原文件按校验和恢复。此兼容转换适用于本次增量存储升级，未来有破坏性 schema 变化时必须另写迁移方案。回退也要核查后台检查队列，没有数据库写入工作后再执行。

## 备份操作

用户级 systemd 单元为 `neuroweave-backup.service` 和 `neuroweave-backup.timer`，每天服务器时间 02:30 左右运行，错过的计划在下次启动时补做。数据写到共享存储 `/home/data/neuroweave/backups/hipeson`，目录 0700、文件 0600。

```bash
systemctl --user status neuroweave-backup.timer
systemctl --user start neuroweave-backup.service
python3 scripts/maintain_storage.py verify --backup /具体路径/nw-db-时间戳.sqlite3
python3 scripts/maintain_storage.py restore --backup /具体路径/nw-db-时间戳.sqlite3 --destination /独立验证目录/restored.sqlite3
```

`restore` 只创建新文件，目标存在就拒绝覆盖。生产恢复应先暂停提交和后台检查、停止 API、验证备份并保存当前 DB，然后由管理员切换已校验的文件；不要遗漏 WAL，也不要在活跃进程旁直接替换 DB。备份不包含实际 MRI 数据、科研结果、软件环境或模型权重；共享存储仍需自己的灾备/快照。每天 14 份是基础保留策略，长期归档需按课题要求另定。

## 暂不实施的五项：原因、步骤和验收

### 1. 用户身份、对象归属和数据根目录

**为什么做：** 在多人访问时，“能打开网页”不应意味着可以查看、修改或取消别人的流程。当前服务主要按服务器账号的权限访问文件；根目录若允许 `/`，可浏览范围会比数据目录大很多。单人内网工具可以暂缓完整账号体系，多人共享前应优先处理。

**怎么做：** 首先列出真正需要访问的目录（如经确认的 `/home/data/xy`），将数据根缩到白名单并重新检查已有文件绑定；不要直接改路径导致原任务失效。接入机构现有登录或小型本地账号，服务端为对话、数据集引用、Workflow、Run 增加 owner/project 归属；读取、修改、取消、日志和输出接口都检查归属。管理员负责共享资源配置，普通用户只管理自己的任务。旧记录迁移到明确的管理员或项目名下，不能根据最后访问者猜归属。

**怎么验收：** 两个测试账号 A/B，A 不能通过猜 ID 查看 B 的对话、路径、日志或取消 B 的 Job；白名单外路径与符号链接绕过都被拒绝。API 权限和实际 Linux/Slurm 账号策略需一起设计；只在前端隐藏按钮不够。

### 2. Slurm 的 CPU、内存和 GPU 强制隔离

**为什么做：** 资源申请影响调度，但仅靠“申请了 8 核、32 GB”不能保证程序只使用这些资源。当前 `TaskPlugin=task/none`、`ProctrackType=proctrack/linuxproc`；环境变量可以控制常见线程库，不能替代操作系统的限制。记账服务记录用量，也不等于限制用量。

**怎么做：** 先检查各节点 cgroup v1/v2、systemd、Slurm 21.08 与驱动的兼容性，选择支持的配置或安排升级。维护窗口中先排空一台测试节点，配置 task/cgroup、proctrack/cgroup，并按适用版本启用 CPU、RAM、设备约束。校准 `RealMemory`，给操作系统留余量，避免把节点物理内存全部分给作业。测试通过后逐节点推广，每次保留配置回退点。

**怎么验收：** 提交限 2 核的小程序检查允许的 CPU 集合；提交明确超过内存限额的合成任务，确认受限任务被终止而其他任务继续；不申请 GPU 的作业不能访问 GPU，申请后的作业只看到获分配设备。还要验证取消时没有残留子进程。这里会改变已有程序运行约束，所以本次仅解释，没有直接启用。

### 4. 输入文件身份、空间关系和不可变快照

**为什么做：** 路径存在、扩展名正确不能证明它属于当前样本。FOD 与 5TT 可以来自不同受试者或不同物理空间，软件有时仍能运行并产生不可信结果；确认后同一路径的文件也可能被替换。

**怎么做：** 记录样本/会话、图像维度、数据类型、仿射与物理空间、上游来源，以及文件大小/修改时间和按需 SHA-256；绑定时核对样本映射，执行前复查快照。DWI 还要核对 bval/bvec 数量与图像体积、梯度约定。FOD/5TT 不应机械要求矩阵和体素大小完全相同：分辨率不同仍可能处于同一物理空间，要检查空间来源、覆盖范围及已有配准链，并提供叠加 QC。缺少证据时说明不确定性，让用户确认输入或选择已有配准步骤，不能暗中添加算法。

**怎么验收：** 用错样本、错空间、输入被更换的合成用例检查是否拦截/失效；用“同一物理空间但不同分辨率”的合法用例防止误拦截。本次重试已加入输入/输出哈希核验，但没有完成这套影像身份和空间验证系统。

### 9. 逐方法、逐节点的可用性与结果质量证据

**为什么做：** 库能导入与一个方法在指定节点上能正确处理数据是两层要求；还可能缺图谱、权重、许可证，或存在驱动/版本差异。命令退出 0 也不必然意味着科学结果合格。

**怎么做：** 建立“方法 × 节点 × 环境版本”的证据表，区分未接入、依赖可用、已完成最小执行、已有标准数据验证等状态。以普通 Slurm 作业运行小型预检，记录软件/模型/图谱版本与结果，版本变化后使旧证据失效。为关键方法准备脱敏或公开标准数据，按原软件文档检查输出格式、结构和可解释的 QC 指标；重要流程保留人工查看叠加图、掩膜、配准及追踪结果的入口。

**怎么验收：** 在故意移除权重或改变某节点环境后，只把受影响的方法/节点标为待验证；测试样例能区分“程序能启动”和“输出通过验证”。不能把一次 GPU 矩阵运算等同于所有深度学习方法验证，也不应为缺失的原算法编写替代实现。

### 12. 流程规划的语义回归集

**为什么做：** 修好“已有 5TT，只重算 FOD 并追踪”这一句话，不能保证“别重做分割”“保留现有组织图”等换一种表达仍正确。模型、提示词或 Skill 变化可能重新引入过度推荐。

**怎么做：** 将典型请求整理成脱敏案例，每例标明用户已有制品、需要重做的步骤、禁止添加的步骤、期待依赖和缺失输入处理方式。至少覆盖否定句、部分重做、手动移除步骤、系统未识别已有输入、多样本映射，以及确实缺少必要上游的情况。自动比较 DAG 节点和顺序、复用输入及澄清行为；模型版本/提示词变化后重新跑真实模型评估，关键案例必须通过。离线固定响应测试可用于代码回归，但不能冒充真实模型语义测试。

**怎么验收：** “重算 FOD + 用已有 5TT 追踪”只包含用户需要的流程并绑定 5TT；如果 5TT 未找到，应请求选择它或明确说明缺什么，而不是静默推荐生成。单独统计多推荐、漏推荐、错误复用和未澄清的比例，让一次改动是否变好有可比较的依据。

## 技术依据

- [Slurm accounting](https://slurm.schedmd.com/accounting.html)：SlurmDBD 与作业记账。
- [Slurm cgroup 配置](https://slurm.schedmd.com/cgroup.conf.html)：资源约束需结合实际 Slurm/cgroup 版本实施。
- [SQLite Online Backup API](https://www.sqlite.org/backup.html)：在线生成一致数据库备份。
- [pip 可重复安装](https://pip.pypa.io/en/latest/topics/repeatable-installs/)：锁定传递依赖并校验环境。
