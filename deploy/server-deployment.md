# 服务器部署与维护

本文记录现有部署拓扑和核对方法。表中版本与路径于 **2026-10-08 16:29（Asia/Shanghai）** 只读核实；后续操作前重新检查，不依据快照覆盖服务器文件。

## 服务拓扑

服务器为 `mgr`，访问地址 `192.10.84.6`，账户 `hipeson`，本机 SSH 别名为 `localflow-server`。

| 项目 | 主站 | 开发副本 |
| --- | --- | --- |
| 地址 | `http://192.10.84.6:3000` | `http://192.10.84.6:3002` |
| 源码 | `/home/hipeson/NeuroWeave` | `/home/hipeson/NeuroWeave-task-management` |
| 分支 | `main` | `codex/task-management-pipeline-ui` |
| 已部署提交 | `e514c8634675997a2b8347e7518a3df9bd8e975f` | `64a811fd8620b2b4d914f9eb192616bfe19cfbb5` |
| systemd 用户服务 | `neuroweave-backend.service` | `neuroweave-task-management-backend.service` |
| nginx 容器 | `neuroweave-frontend` | `neuroweave-task-management-frontend` |
| 发布环境文件 | `runtime/main.env` | `runtime/branch.env` |
| 数据库 | `runtime/localflow.db` | `runtime/localflow.db` |
| Worker | `/home/data/neuroweave/worker/<该站提交>` | `/home/data/neuroweave/worker/<该站提交>` |
| 默认输出根 | `/home/data/neuroweave/testing/methods-20260922/results` | `/home/data/neuroweave/testing/task-management-20261005/results` |

表中 runtime 路径分别相对于各站源码目录。两站独立保存对话、任务、草稿及用户 Pipeline，不进行数据库同步。3002 仍为较早的开发部署，不能据其端口判断运行的是最新开发分支。3001、3003 及旧 `methods-webtest` 路径不作为当前发布目标。

两站后端复用 `/home/hipeson/NeuroWeave/.venv/bin/python`（Python 3.11）。科学与 Slurm Python 为 `/opt/neuroweave/envs/scientific-py311/bin/python`。静态 nginx 挂载各站 `frontend/dist`，将 `/api/` 转发到各自 `runtime/socket/backend.sock`；端口仅绑定 `192.10.84.6`，不能用 `127.0.0.1:3000` 的拒绝连接推断站点故障。

`runtime/model.env`、`native.env`、`selected.env` 保存对应配置；`release.json`、`deployment-state.json` 保存版本及发布结果。核实两站健康接口为 `status=ok`、`mode=model`、模型 `deepseek-chat`，各站前端/后端/worker 标识一致，维护状态为 false。不要打印环境文件全文或将密钥加入文档。

## 权限与集群边界

当前两站 `WORKSPACE_ALLOWED_ROOTS=/`，`LOCALFLOW_DATA_ROOTS` 也指向服务器根目录。可访问范围仍受后端账户权限、敏感/特殊目录屏蔽、只读数据集和文件操作确认约束；这是一项既有管理员配置，代码默认值并不开放 `/`。当前没有用户级登录、对象归属和多租户隔离，具体文件授权见 [目录管理](workspaces.md)。

Slurm 21.08.5 的 `all` 分区包含 mgr 和 node01–03；计算节点各登记 `gpu:1`。持久记账使用 `accounting_storage/slurmdbd` 与 `jobacct_gather/linux`，当前 `TaskPlugin=task/none`、`ProctrackType=proctrack/linuxproc`，没有 cgroup 资源强制隔离。

集群存在应用之外的 ADNI FreeSurfer 作业。应用 runs 为零不代表集群空闲；检查 `squeue` 后，用 `scontrol show job <id>` 核对脚本、工作目录和节点。应用发布不应停止这些作业或删除其代码与结果。

## 只读核对

在服务器执行：

```bash
git -C /home/hipeson/NeuroWeave status --short
git -C /home/hipeson/NeuroWeave rev-parse HEAD
git -C /home/hipeson/NeuroWeave-task-management status --short
git -C /home/hipeson/NeuroWeave-task-management rev-parse HEAD
systemctl --user is-active neuroweave-backend.service neuroweave-task-management-backend.service
docker ps --format '{{.Names}} {{.Status}} {{.Ports}}'
curl -fsS 'http://192.10.84.6:3000/api/health?include_runtime=false'
curl -fsS 'http://192.10.84.6:3002/api/health?include_runtime=false'
squeue -u hipeson
sinfo -N
```

同时检查本地分支、未提交改动、`runtime/release-maintenance.lock`、活跃 runs / operations / chat_turns。健康接口的版本来自进程配置；前端发布还要核对实际入口、资源哈希和发布记录。

## 发布与恢复

开发发布应指定独立分支、端口、数据库和输出目录。推送代码不改变线上部署。主站更新前须：

1. 核对目标站及源码差异、依赖和测试结果，生成带提交与校验和的候选包。
2. 保留有效环境配置与数据，建立新的固定共享 Worker 目录；维护锁阻止新写入后，再检查目标站活跃执行、规划、检查及文件操作。
3. 在允许的维护窗口切换目标后端和静态入口，核对资源哈希、接口、前后端/worker 标识及数据完整性。旧哈希资源、Worker 和已保存结果继续保留。
4. 失败时按当次发布清单恢复源码、配置和静态入口；恢复数据库前单独检查期间的新写入，不用旧快照覆盖有效数据。

仓库中的 `deploy_slurm_release.py`、`deploy_frontend_release.py` 等旧发布脚本包含 `/home/hipeson/LocalFlow` 等固定目标，缓存中的单次脚本还可能固定旧 SHA。使用前必须审阅并调整目标，不能直接当作上述两站的通用发布命令。

主站备份定时器 `neuroweave-backup.timer` 指向当前主站数据库；范围与恢复方法见 [运行与备份维护](reliability-upgrade.md)。未核实开发副本有自动备份，不应假定主站定时器同时覆盖 3002。

## 模型连接排查

先核对模型配置、当前 DNS 路由及 `resolvectl query api.deepseek.com`，再按需验证 HTTPS。DeepSeek 使用 CDN 别名 `api.deepseek.com.eo.dnse1.com`；公共域名与集群内网解析需要同时保留。现有 DNS 修复已完成，勿重跑历史修复脚本或将全服务器默认 DNS 改成公共 DNS。
