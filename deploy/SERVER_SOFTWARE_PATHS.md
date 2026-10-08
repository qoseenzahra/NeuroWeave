# 服务器软件路径

服务工具与 API 环境于 **2026-10-08** 核对；科学软件表列出现有登记和验证证据使用的路径/版本基线，升级或切换节点后应重新探测。软件存在不表示所有命令和选项已接入，执行仍受 Method 和 Runner 契约限制。

## 服务工具与后端环境

| 用途 | 路径或版本 |
| --- | --- |
| Docker / Compose | Docker 29.6.1、Compose v5.3.1 |
| 系统 Python / Git | `/usr/bin/python3`、`/usr/bin/git` |
| Miniconda | `/opt/miniconda3` |
| 两站 API Python | `/home/hipeson/NeuroWeave/.venv/bin/python`（Python 3.11） |
| 主站 / 开发副本 | `/home/hipeson/NeuroWeave` / `/home/hipeson/NeuroWeave-task-management` |
| 共享固定 Worker | `/home/data/neuroweave/worker/<部署提交>` |

API、nginx、环境文件、数据库及各站当前版本集中记录在 [服务器部署](server-deployment.md)。两站不能共用同一个 SQLite 或据端口推断代码版本。

## 科学软件基线

| 软件 | 安装根目录 | 已登记入口示例 |
| --- | --- | --- |
| ANTs 2.6.5 | `/opt/software/ants-2.6.5` | `bin/antsRegistration`、`bin/antsApplyTransforms` |
| FSL 6.0.7.22 | `/opt/software/fsl` | `bin/fslmaths`、`flirt`、`bet`、`dtifit`、`eddy`、`probtrackx2`、`dcm2niix` |
| MRtrix3 3.0.8 | `/opt/software/mrtrix3-master` | `bin/mrconvert`、`dwidenoise`、`dwifslpreproc`、`tckgen`、`tcksift2` |
| FreeSurfer 7.4.1 | `/opt/software/freesurfer-7.4.1/usr/local/freesurfer/7.4.1` | `SetUpFreeSurfer.sh`、`bin/recon-all` |

Runner 使用环境文件中的绝对入口和受审阅的环境映射，不依赖交互 shell 自动设置 `FSLDIR`、`FREESURFER_HOME`、`ANTSPATH` 或 MRtrix PATH。已有私人 Conda 和软件自带环境分别维护。

## 公共 Python 与共享路径

| 用途 | Python |
| --- | --- |
| 科学计算、统计、神经影像和 EEG | `/opt/neuroweave/envs/scientific-py311/bin/python` |
| PyTorch CUDA 深度学习 | `/opt/neuroweave/envs/torch-cu128-py311/bin/python` |

环境由 hipeson 维护，其他用户可读/执行。计算节点通过 NFS 访问 `/opt` 与 `/home/data`；输入、输出、模型和 Worker 必须使用目标节点可见的相同绝对路径。node01–03 各登记一张 GPU，主节点没有 GPU。

依赖锁、探测与安装维护见 [公共环境](python-environments/README.md)，节点和执行资源见 [Slurm 执行](slurm-execution.md)。CPU 导入成功、GPU 最小用例和方法科研验证分别记录，不互相替代。
