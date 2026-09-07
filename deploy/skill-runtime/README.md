# Skill 执行配置与验证

2026-09-07 在原项目上补齐执行入口，复用 `/opt/neuroweave/envs/` 公共环境与现有 Slurm。没有重建平台、修改生产数据集或清空运行历史。

## 范围与计数

| 项目 | 本次补齐后的数量 |
| --- | ---: |
| Skill 总数 | 103 |
| 至少一项方法就绪的 Skill | 76 |
| 注册的独立执行器 | 176 |
| 当前服务器依赖满足的执行器 | 173 |
| 本次新增的实现 | 154 |
| 就绪的可选择方法入口 | 333 |
| 有执行声明、但运行条件不足的入口 | 6 |
| 保留的规划选项 | 307 |

一个实现可被多个 Skill 引用，一个训练器也可展开为不同模型选项。因此 333 个方法入口不等于 333 个独立算法。完整快照见 [readiness.json](readiness.json)。快照描述软件与接口就绪状态；具体数据仍需通过预检，合成测试通过也不代表真实研究数据上的科学有效性或模型性能。

## 已接入的分析

- **fMRI / Nilearn**：混杂回归、去趋势、滤波、平滑、ROI 时间序列与连接矩阵、一级/组水平 GLM、ICA、字典学习、K-means/层次分区、SVM、SpaceNet、SearchLight、zALFF。
- **结构像与 DWI**：FSL BET、FAST、MCFLIRT、SliceTimer、FNIRT、ApplyWarp，ANTs 应用变换，MRtrix 去噪、Gibbs 校正、偏置场校正、格式转换与 Eddy 预处理。既有配准、DTI、FOD、追踪、连接组和 FreeSurfer 执行器也已关联到对应 Skill 入口。
- **EEG / MEG**：数据读取、坏导联、滤波、ICA、分段、AutoReject、频带功率、Hjorth、PLV/相干/wPLI、ERP、Alpha 不对称、微状态、Morlet 功率与 ITC、Mel 频谱、Maxwell 和 dSPM 源定位。
- **机器学习**：统计分类/回归、CPM、脑龄、分型、影像遗传、生存模型、处理效应、时序 LSTM/GRU/TCN/Transformer、3D CNN、BrainNetCNN、BNT、ComBrainTF、ComplEx、连接图相似度与置换检验。
- **数据集工具**：表型和刺激提取、数据校验、QC、病灶与纵向统计、UKB 生存数据构建、SEED 特征与按受试者交叉验证，以及多种队列目录复制整理。SCAN、ADNI 的已获准本地导出可使用巡检和 DICOM 转换入口。

原有参考脚本中的无效 MNE 接口、NumPy/Pandas 兼容问题、聚类维度、ICA 输出、表格列名冲突、错误文件扩展名、HCP/IXI 命名和日志序列化等已修复。上游 `models` 源码按 MIT 许可复用；ComplEx 的必要 NeuroOracle 组件放在 `models/kg_link_prediction/vendor/`，不加载其智能体运行时。

## 输入与运行方式

在平台选择方法、绑定输入、审核参数并通过 Dry-run 后，选择本地或 Slurm 执行。所有新实现使用固定脚本和参数清单，不执行从文档或模型回答中提取的任意命令。输入保持只读；整理脚本复制到本次任务目录。

| 数据/方法 | 必须提供的条件 |
| --- | --- |
| BOLD GLM | 已预处理的 4D BOLD、TR、事件表和对比表达式；可选混杂表/掩膜 |
| zALFF | 已配准到同一网格的 BOLD、掩膜、图谱和有序区域标签；不隐式执行空间配准 |
| 多影像/多表型输入 | 一个 UTF-8 路径清单，每行一个文件；清单中的每个文件都检查授权数据根 |
| 常规模型 | CSV 特征/目标列，或方法指定的 NPZ；默认交叉验证，训练产物含预测、指标与配置 |
| 时序 / CNN | NPZ `X`、`y`，可选 Unicode `subject_id`；CNN 输入各空间维度至少 16 |
| BrainNetCNN / BNT | NPZ `X[N,R,R]` 对称连接矩阵与 `y` |
| ComBrainTF | 上述输入，并提供与 ROI 顺序一致的 `community_ids` |
| ERP / 源定位 | ERP 必须提供事件；源定位必须提供匹配的前向模型和噪声协方差 |
| Maxwell | 合法 MEG 传感器几何及设备到头坐标变换；不适用于 EEG |
| 连接图置换 | 用户明确图谱、节点顺序与坐标空间；当前采用交换性零模型，不保持空间自相关 |
| HCP / IXI 目录整理 | 符合方法声明的源目录；HCP 已处理影像保留 derivative 属性，不冒充原始影像 |

NPZ 不加载 Pickle 对象。现有文件如果把 ID 存成 `dtype=object`，请先在可信的数据准备环节转换成 Unicode 数组。缺少输入、模型标签或匹配空间会导致预检/执行失败，不生成“成功”占位结果。

需要 GPU 时，选择 **Slurm → all → GPU 1**；可从 CPU 2–4、内存 8 GB 起按数据规模调整。模型的 `device=auto` 会在分配到 GPU 的节点使用 CUDA。GPU 0 的作业即使落在 GPU 节点，也会隐藏 GPU，避免自动占用未申请的设备。当前每个计算节点只有约 8 GB 显存，大体积训练需相应减少批大小。

结果文件带稳定的输出槽和校验信息。相容方法之间可以自动绑定上游产物；例如去噪产生的 BOLD 可供下游 GLM 使用。DWI 校正同时输出影像与对应梯度表。查看任务内的日志、模型配置及 Slurm Job ID 可确认实际执行位置和状态。

## 仍保留规划的内容

以下不因基础 Python/GPU 环境存在就自动成为完整分析任务：

- fMRIPrep、QSIPrep、XCP-D、HCP Pipelines、CONN/MATLAB、nii2dcm 的对应软件入口未齐备。
- BrainGNN、IBGNN、LG-GNN 的图学习依赖，以及 NeuroSTORM/FM-APP 的独立工程/专用依赖尚未接入；MARS-WMH 还需要其容器与模型。
- ComBat 系列专用包未齐备；目前提供站点协变量校正。
- 数据访问/下载、文献检索、Overleaf、Git/Docker/Conda 管理、论文写作和实验设计涉及外部连接、账户或交互式管理流程。
- “全流程”“队列模态处理”“高级分析”等规划可引用已就绪的具体方法，但仍需要确定输入、具体步骤、科学设置与外部模型；不会把一项子功能冒充完整流程。

## 检查与复现

```bash
# 仅输出公开的就绪信息；运行配置中的密钥不会写入清单。
/opt/neuroweave/envs/scientific-py311/bin/python scripts/audit_skill_execution.py \
  --runtime-env /home/hipeson/LocalFlow/deploy/native-backend.env \
  --output /home/data/neuroweave/development/skill-readiness.json
```

实现目录由 `scripts/build_reviewed_execution.py` 生成。更新后运行该生成器和 `scripts/build_capability_tree.py`，再执行后端回归及受影响方法的合成测试。`smoke_reviewed_execution.py` 使用独立合成数据；`smoke_reviewed_slurm.py` 使用独立数据库并提交真实 Slurm 作业。不要将这些脚本指向生产输入或生产数据库。验证汇总见 [verification.json](verification.json)。

发布使用 `scripts/deploy_slurm_release.py`：检查无活动任务、保留配置备份、发布包含 `models/` 的版本化共享 Worker，再更新原生后端服务。数据库、运行产物、环境目录和服务器私有配置均保留。
