# NeuroWeave 公共 Python 环境与 Slurm 接入

## 环境安装

目标目录由管理员创建一次，然后由 `hipeson` 维护，其他用户仅可读取/执行：

```bash
sudo install -d -o hipeson -g hipeson -m 0755 /opt/neuroweave /opt/neuroweave/envs
```

在 `mgr` 上运行（不会修改现有 base、FSL、sp、midcc 或 FastAPI 环境）：

```bash
cd /home/hipeson/LocalFlow
bash scripts/install_shared_python.sh scientific
bash scripts/install_shared_python.sh torch
```

| 环境 | Python 入口 | 主要用途 |
| --- | --- | --- |
| scientific | `/opt/neuroweave/envs/scientific-py311/bin/python` | NumPy/SciPy/Pandas、统计学习、生存分析、Nilearn/DIPY、MNE/EEG、影像格式和可视化 |
| torch | `/opt/neuroweave/envs/torch-cu128-py311/bin/python` | PyTorch CUDA 12.8、MONAI、TorchIO、Lightning、Transformers |

两个环境均使用 Python 3.11。安装完成时执行 `pip check`，并在各自环境根目录
保存 `requirements.lock.txt` 和 `conda-explicit.txt`。安装器拒绝覆盖已有前缀；
中断后的环境需要先查明失败原因再定向续装，不应直接删除或反复重建。
安装器只调整新环境自身的读/执行权限，不开放已有私人 Conda 父目录。

CPU 与导入验证：

```bash
PYTHONNOUSERSITE=1 MPLBACKEND=Agg /opt/neuroweave/envs/scientific-py311/bin/python scripts/probe_shared_python.py --profile scientific
PYTHONNOUSERSITE=1 MPLBACKEND=Agg /opt/neuroweave/envs/torch-cu128-py311/bin/python scripts/probe_shared_python.py --profile torch
```

GPU 验证必须在分配到 GPU 的计算节点上执行 `--profile torch --require-cuda`。
主节点没有 GPU，因此主节点返回 `cuda_available=false` 不代表环境安装失败。
模板、图谱、预训练权重和用户数据不在依赖安装过程中自动下载；需要按具体方法准备。
TensorFlow 不混装进 PyTorch 环境，避免不同 CUDA 依赖互相替换。

### 已完成的安装与验证（2026-09-07）

- 两个环境安装完成并通过 `pip check`；科学环境约 2.6GB，PyTorch 环境约 7.8GB。
- 科学环境主要库导入通过，合成回归、NIfTI 读写、MNE 数据对象检查通过。
- 深度学习环境主要库导入通过，PyTorch `2.11.0+cu128`，CPU 矩阵检查通过。
- Slurm 作业 `8`（科学环境）和 `9`（PyTorch CPU）在 `mgr` 上完成，
  均为 `COMPLETED`，`ExitCode=0:0`；这些不是计算节点 GPU 作业。
- 三个计算节点通过共享环境的只读设备检查均返回 `cuda_available=true`，
  识别 RTX 5060，设备能力 `(12, 0)`。未绕过 Slurm 运行 GPU 计算任务。
- 新环境的文件公共读取、目录公共遍历检查通过；其他用户没有环境修改权限。
- GPU `sbatch --test-only --gres=gpu:1` 返回
  `Invalid generic resource (gres) specification`；当前 GPU 调度尚未通过。
- 锁定清单保存在本目录 `locks/`；详细安装/验证日志位于服务器
  `/home/hipeson/LocalFlow/runtime/environment-install/`，Slurm 测试日志位于
  `/opt/neuroweave/jobs/hipeson/gpu-probe/`。

本次仅安装独立环境与完成验证，未修改现有 Runner 环境配置或重启 FastAPI；
后续接入时可将经过验证的 Python Runner 指向相应入口。未修改 Slurm 管理配置。

## 2026-09-07 集群只读检查结果

- 主节点：`mgr`；Slurm 21.08.5，`all` 为唯一分区，`mgr` 为 IDLE。
- `node01`、`node02`、`node03` 的系统均可通过 SSH 访问。
- 每个计算节点有 1 张 RTX 5060，显存 8151 MiB，驱动 580.173.02。
- 三个计算节点在 Slurm 中均为 DOWN，原因是未预期重启；未在本次检查中恢复节点。
- `GresTypes=(null)`，所有节点 `Gres=(null)`，GPU 尚未纳入 Slurm 资源登记。
- `SelectType=select/cons_tres`，`SelectTypeParameters=CR_CORE_MEMORY`。
- `AccountingStorageType=accounting_storage/none`，`JobAcctGatherType=jobacct_gather/none`；
  不能假设 `sacct` 可以提供持久作业历史。
- 计算节点的 `/opt` 为 `mgr:/opt` NFS 挂载，可以共享新环境。
- 计算节点的 `/home/data` 为 `storage:/home/data` NFS 挂载。
- `/home/hipeson/LocalFlow` 在计算节点不存在，不能直接作为远程工作目录或脚本路径。

**因此：主节点提交、计算节点执行在架构上可行，但当前 GPU Slurm 执行尚未就绪。**

## 管理员需要补齐的调度条件

1. 核查各节点 slurmd、MUNGE、配置一致性、时间同步及重启原因，然后恢复可调度状态。
2. 在 Slurm 主配置登记 `GresTypes=gpu` 和对应节点的 `Gres=gpu:1`；
   各计算节点通过 `gres.conf` 绑定本机设备（例如经实际确认的 `/dev/nvidia0`）。
   可使用原 `all` 分区，或由管理员建立专用 GPU 分区；没有配置前不可假设存在 `gpu` 分区。
3. 核验 GPU 设备隔离和 `CUDA_VISIBLE_DEVICES`；必须通过 Slurm 申请资源，
   不能仅用 `--nodelist` 代替 GPU 资源申请。
4. 为作业准备所有计算节点可见的脚本、输入、输出和日志目录，检查 UID/权限一致性。
5. 建议配置作业记账；如果继续没有 `sacct`，平台必须保存终态和退出码，
   不能把作业从 `squeue` 消失当作成功。

这些调度管理操作未由环境安装器执行。

## GPU 提交示例（调度条件修复后）

将验证脚本复制到共享目录后再提交，保持绝对路径。以下只创建自己的验证目录：

```bash
mkdir -p /opt/neuroweave/jobs/hipeson/gpu-probe
cp /home/hipeson/LocalFlow/scripts/probe_shared_python.py /opt/neuroweave/jobs/hipeson/gpu-probe/
cd /opt/neuroweave/jobs/hipeson/gpu-probe
sbatch --parsable /home/hipeson/LocalFlow/deploy/python-environments/gpu-probe.sbatch.example
```

`sbatch` 会传送作业脚本文本，但不会自动传送 Python 脚本、数据或模型权重。
成功提交仅表示获得 Job ID，需继续查看状态、退出码、日志和实际产物。
示例为 `all` 分区申请 1 GPU、4 CPU、16GB 内存；16GB 是主机内存，不是显存。
RTX 5060 的约 8GB 显存对较大 3D 模型可能需要较小 batch、混合精度或滑窗推理。

## NeuroWeave 接入位置

当前 `RunService` 和 `ExternalCommandRunner.execute` 在主节点启动本地进程。
环境安装不会自动改变调度方式，也不会将 planning 方法自动变成 Runner。
部分环境检查也需调整，例如 FSL eddy 当前通过主节点 `/dev/nvidia0` 判断 CUDA，
Slurm 模式应查询执行目标的 GPU 能力，不能继续使用主节点是否有显卡作为判断条件。

应新增受审核的 Slurm 执行后端：

1. 由可信 Runner 生成参数数组和资源请求，将步骤快照及所需代码放入共享工作区。
2. 用 `sbatch --parsable` 提交并将 Job ID 写入运行审计。
3. 使用 `squeue`/`scontrol` 跟踪 PENDING/RUNNING 等状态；有记账时使用 `sacct`
   核对最终 State 和 ExitCode，无记账时使用受控包装器写入原子终态文件并交叉检查。
4. 日志留在共享文件系统；收到取消请求时调用 `scancel` 并确认远程作业停止。
5. 作业成功退出后，仍由 Runner 验证实际输出，再登记制品和触发下游步骤。
6. 后端重启时用持久 Job ID 重新关联作业，避免重跑或把仍在运行的远程任务直接判失败。

官方参考：
- [Slurm sbatch](https://slurm.schedmd.com/sbatch.html)
- [Slurm GRES/GPU 资源](https://slurm.schedmd.com/gres.html)
- [PyTorch 版本及 CUDA 安装命令](https://pytorch.org/get-started/previous-versions/)
- [PyTorch Blackwell 支持](https://pytorch.org/blog/pytorch-2-7/)
