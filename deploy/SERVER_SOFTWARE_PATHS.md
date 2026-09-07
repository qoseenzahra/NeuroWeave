# 服务器软件路径清单

检查时间：2026-09-05  
服务器：`mgr`  
用户：`hipeson`

该文件记录部署时验证过的软件位置。NeuroWeave 原生后端只能通过
受审核 Runner 白名单调用其中已接入的程序；模型输出和 Skill 文档中的命令文本
不会被直接执行。

## 系统与部署工具

| 软件 | 路径或版本 |
| --- | --- |
| Docker | `/usr/bin/docker`，29.6.1 |
| Docker Compose | v5.3.1 |
| Python | `/usr/bin/python3` |
| Git | `/usr/bin/git` |
| rsync | `/usr/bin/rsync` |
| Miniconda | `/opt/miniconda3` |
| NeuroWeave 独立后端环境 | `/home/hipeson/LocalFlow/.conda/backend`（Python 3.12） |

## 神经影像软件

| 软件 | 安装根目录 | 已验证入口 |
| --- | --- | --- |
| ANTs 2.6.5 | `/opt/software/ants-2.6.5` | `/opt/software/ants-2.6.5/bin/antsRegistration`、`antsApplyTransforms` |
| FSL 6.0.7.22 | `/opt/software/fsl` | `bin/fslmaths`、`flirt`、`bet`、`dtifit`、`eddy`、`eddy_cpu`、`eddy_cuda`、`probtrackx2`、`dcm2niix` |
| MRtrix3 3.0.8 | `/opt/software/mrtrix3-master` | `bin/mrconvert`、`dwidenoise`、`dwifslpreproc`、`tckgen`、`tcksift2` |
| FreeSurfer 7.4.1 | `/opt/software/freesurfer-7.4.1/usr/local/freesurfer/7.4.1` | `SetUpFreeSurfer.sh`、`bin/recon-all` |

当前 SSH 非交互环境没有自动设置 `FSLDIR`、`FREESURFER_HOME`、`ANTSPATH` 或 MRtrix3 `PATH`。
这些变量由 `deploy/native-backend.env` 和各 Runner 显式构造，不依赖用户的交互式 shell。
已有 Conda `base`、`midcc`、`sp` 及 FSL 自带 Python 环境保持不变；NeuroWeave 仅使用自己的
后端环境运行 FastAPI，再按 Runner 配置调用上表程序。

## 公共 Python 环境（2026-09-07 新增）

| 用途 | 路径 | 验证结果 |
| --- | --- | --- |
| 科学计算、统计、神经影像、EEG | `/opt/neuroweave/envs/scientific-py311/bin/python` | 主要库导入和合成数据测试通过；Slurm 作业 8 成功 |
| PyTorch CUDA 12.8 深度学习 | `/opt/neuroweave/envs/torch-cu128-py311/bin/python` | PyTorch 2.11.0、CPU测试通过；Slurm 作业 9 成功；三个计算节点均能识别CUDA设备 |

环境由 `hipeson` 维护，其他用户可读取/执行。`/opt` 已通过 NFS 共享到 `node01–03`。
每个计算节点有一张 RTX 5060（约8GB），但 Slurm 节点当前为 DOWN 且未登记 GPU GRES，
尚不能提交 GPU 作业。本次未更改生产 Runner 的解释器配置或 Slurm 配置。
依赖锁定、验证记录和调度接入说明见 [公共环境文档](python-environments/README.md)。
