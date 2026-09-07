# NeuroWeave Slurm 执行

NeuroWeave 保留原来的本地执行，并为已经接入可信 Runner 的流程增加 Slurm 执行方式。网页完成 Dry-run 和最终确认后，在运行位置选择 Slurm，再设置分区、CPU、内存、GPU 和时限。流程中每个实际执行步骤提交一个单节点作业；前一步成功且产物验证通过，才提交下一步。当前不支持一个步骤跨节点分布式训练。

## 主节点不需要 GPU

mgr 上的 API 只负责 `sbatch` 提交、状态查询、结果登记和 `scancel`。选择 GPU=1 后会请求 `--gres=gpu:1`，由 Slurm 将任务安排到已登记 GPU 的 node01–03。Worker 在计算节点检测输入、软件和 GPU，再调用既有可信 Runner。分区资源设置不会改变已经确认的方法参数；方法的线程参数不得超过申请的 CPU 数。

`Slurm` 分配 GPU 并设置 `CUDA_VISIBLE_DEVICES` 的行为见 [Slurm GRES 官方说明](https://slurm.schedmd.com/gres.html)。本集群的 GPU 注册及节点恢复见 [管理员步骤](slurm-admin.md)。当前配置不新增 cgroup 设备隔离，不能据此声称阻止用户通过直接 SSH 占用其他作业的设备。

## 共享路径和部署配置

计算节点的 `/opt` 来自 mgr 的 NFS，`/home/data` 来自公共存储。`/home/hipeson/LocalFlow` 只在 mgr 存在，因此远端 Worker 使用发布版本目录，输入和输出使用共享路径。

在 mgr 的 `deploy/native-backend.env` 设置以下非密钥变量，保留原数据库、API 密钥和本地输出设置：

```dotenv
LOCALFLOW_SLURM_ENABLED=true
LOCALFLOW_SLURM_WORKER_ROOT=/opt/neuroweave/worker/<发布版本>
LOCALFLOW_SLURM_PYTHON=/opt/neuroweave/envs/scientific-py311/bin/python
LOCALFLOW_SLURM_OUTPUT_ROOT=/home/data/neuroweave/runs/hipeson
LOCALFLOW_SKILL_PYTHON=/opt/neuroweave/envs/scientific-py311/bin/python
LOCALFLOW_DIPY_PYTHON=/opt/neuroweave/envs/scientific-py311/bin/python
```

Worker 发布目录包含 `bakend/app`、`bakend/resources` 和 `skills`，不包含 `.env`、数据库或应用运行目录。已提交作业引用固定发布路径；旧版本在相关作业全部结束之前必须保留。公共 Python 环境对用户可读可执行，作业目录与结果默认仅 hipeson 可访问。环境变量使用显式白名单，提交脚本清理登录环境，模型 API 密钥不会复制到作业文件。

当前使用一个 FastAPI 进程、一个 SQLite 数据库，进程内锁防止重复提交和取消时覆盖 Job ID。不要直接增加 Uvicorn workers 或启动第二个 API 实例访问同一数据库；多进程部署需要数据库层的任务领取与唯一约束改造。

## 状态、取消和恢复

- `GET /api/execution/backends`：分区、节点、GPU 可调度状态及不可用原因。
- `POST /api/workflows/{id}/runs`：在原 `expected_revision` 外增加 `execution` 对象。
- `GET /api/runs/{id}`：返回运行资源及每步 `scheduler.job_id/state/node_list/reason`。
- 原取消接口调用 `scancel`；确认远端终态后才显示已取消。
- API 正常关闭会停止监控并保留 Slurm 作业，启动后从持久 Job ID 恢复。不得把恢复监控理解为重新执行。
- 临时监控中断时保持任务活动状态。可调用 `POST /api/runs/{id}/resume-monitoring` 重连，或者使用取消按钮。
- 网页的“恢复监控”按钮调用同一恢复接口；重复点击不会再次提交已有作业。

请求示例：

```json
{
  "expected_revision": 3,
  "execution": {
    "backend": "slurm", "partition": "all", "cpus": 4,
    "memory_gb": 16, "gpus": 1, "time_minutes": 60
  }
}
```

成功必须同时具备 Slurm 的 COMPLETED/ExitCode=0:0、Worker 原子结果文件，以及经过路径和完整性验证的非空产物。调度器失败、超时、OOM 或 Worker 失败均不能登记成功。

本集群目前未配置 Slurm 数据库记账。后端会持久保存查询到的终态；如果后端停机太久，`scontrol` 终态已经过期且没有 `sacct` 历史，则保留待核查状态，不依据单独的结果文件推断整个作业成功。提交中断后只有提交标记而没有 Job ID 时，也禁止自动重提；按日志中的 `nw-<标记>` 核查队列及作业文件。长期运行建议另行部署 slurmdbd 记账，以改善历史可追溯性。

## 深度学习脚本与规划型 Skill

GPU Python 位于 `/opt/neuroweave/envs/torch-cu128-py311`。下面的模板支持从 mgr 提交用户自己的训练或推理脚本；数据、脚本、日志与检查点必须放在共享目录，模型权重需要自行准备：

```bash
#!/usr/bin/env bash
#SBATCH --job-name=neuroweave-training
#SBATCH --partition=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --gres=gpu:1
#SBATCH --time=01:00:00
#SBATCH --chdir=/home/data/your-project
#SBATCH --output=/home/data/your-project/slurm-%j.out
set -euo pipefail
export PYTHONNOUSERSITE=1
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
srun /opt/neuroweave/envs/torch-cu128-py311/bin/python train.py
```

保存后在 mgr 运行 `sbatch train.sbatch`；通过 `squeue -u "$USER"` 查看，通过 `scancel <Job ID>` 取消。每个节点只有一张约 8 GB 显存的 RTX 5060，模型大小、batch size 和训练方案必须适应该显存；申请的 `--mem` 是主机内存，不会增加显存。

安装 Python 库和 Slurm 支持不会自动把规划型 Skill 变为可执行方法。未注册的深度学习方法仍需实现并审查 Runner、结构化输入输出、权重和参数验证后，才能由网页运行；平台不接受模型生成的任意 shell/Python 命令。
