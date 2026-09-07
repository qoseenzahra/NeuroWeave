# Skill 现有实现调用与验证

2026-09-07 按“只调用或管理已有内容，不补写缺失算法”的要求收紧运行范围。平台只负责输入/参数校验、调用已有入口、Slurm 调度、日志与产物管理。不会因为安装了 NumPy、PyTorch 或其他基础库，就自行实现缺失算法、改变训练损失或补出新的训练流程。

## 当前范围

| 项目 | 数量 |
| --- | ---: |
| Skill 总数 | 103 |
| 至少一项方法就绪的 Skill | 72 |
| 注册的独立执行器 | 164 |
| 当前服务器依赖与入口就绪的执行器 | 161 |
| 本轮保留的现有实现调用适配 | 142 |
| 就绪的可选择方法入口 | 305 |
| 有执行声明、但运行条件不足的入口 | 6 |
| 原有规划选项 | 358 |

同一实现可以被多个 Skill 引用，也可以展开为已有模型的选项。规划选项仍可保存方案；只有实际注册并通过预检的入口可以执行。恢复了此前因某个 Skill 有部分执行方法而被误隐藏的原始规划选项。完整快照见 [readiness.json](readiness.json)。

## 实现来源边界

- **原有项目脚本**：复用运行环境扩展前 `70b681c` 中已经存在的 Skill 参考脚本，以及用户提供的 NeuroClaw 源码中已有的模型/训练入口。源码来源、原路径和 SHA-256 记录在 [existing_implementation_sources.json](../../bakend/resources/existing_implementation_sources.json)。NeuroClaw 模型是项目已有实现，不全部等同于某个第三方库自带的模型。
- **现有 Python API**：MNE、AutoReject、mne-connectivity、NiBabel 的入口使用明确的模块与函数/类名称；运行探测实际导入并检查调用对象，不能只检查库是否安装。
- **现有软件命令**：固定调用 FSL、ANTs、MRtrix3 和既有 FreeSurfer 等命令，不接受用户或模型生成的可执行文件路径。
- **来源与代码一致性**：每个新增调用适配记录入口及所需源码的校验值；文件变化后预检拒绝执行，需先重新核对来源。参数、文件读写和兼容性修复不得引入算法替代。

逐适配的来源、实际 API/软件入口及源码校验记录见 [reviewed_execution.json](../../bakend/resources/reviewed_execution.json)。生成器只接受已登记的原脚本或明确列出的 API/软件适配；缺少现成实现时保留规划，不根据文档公式补写实现。

## 本次撤回

上一轮有 12 个接口自行实现、替换了原参考计算，或额外组合了训练/分析流程。本次已从注册表和所有 Skill 的生成清单中撤回，旧流程引用这些接口时也不能执行：

| 撤回内容 | 当前处理 |
| --- | --- |
| 自写 zALFF FFT 计算 | 撤回运行入口，恢复原始参考脚本，保留规划 |
| EEG 微状态、Mel 滤波器 | 删除平台自写计算；原文提到的算法仍需其真实软件入口 |
| EEG 频带/Hjorth 特征、Alpha 不对称、ERP 特征、连续清理组合 | 撤回替代原定义的实现，不以部分功能顶替原流程 |
| BrainNetCNN / BNT / ComBrainTF 通用 NPZ 训练器 | 撤回额外编写的训练循环；保留上游模型源码及原始规划 |
| 连接图排序与置换组合入口 | 撤回额外组合的 CLI；保留上游既有函数和原始规划 |

清单见 [withdrawn_execution.json](../../bakend/resources/withdrawn_execution.json)。三个原始 EEG/zALFF 参考文件已恢复；其中尚不满足实际接口要求的内容不会注册执行。两个被撤回的模型适配文件仅保留明确拒绝运行的兼容提示，防止旧路径继续调用旧实现。

## 保留的调用

- **fMRI / Nilearn**：原脚本中的混杂回归、去趋势、平滑/滤波、连接矩阵、GLM、CanICA、DictLearning、KMeans、AgglomerativeClustering、SVM、SpaceNet、SearchLight 等调用。聚类保留原来的跨受试者平均，只修正调用库所需的轴顺序和输出标签格式。
- **结构像 / DWI**：FSL BET、FAST、MCFLIRT、SliceTimer、FNIRT、ApplyWarp，ANTs 应用变换，MRtrix 去噪、Gibbs 校正、偏置场校正、转换与 Eddy 预处理，以及既有配准、DTI、FOD、追踪、连接组和 FreeSurfer 入口。
- **EEG / MEG**：MNE 数据读取、LOF 坏导联检测/插值、滤波/重采样、ICA、分段、Maxwell、dSPM；AutoReject；mne-connectivity 的 PLV/coh/wPLI；MNE Morlet 功率与 ITC。LOF 入口明确标注实际方法；ICA 子功能不替代完整伪迹清除规划。
- **既有模型与数据脚本**：原有统计学习、CPM、脑龄、分型、影像遗传、生存、处理效应、时序模型、3D CNN、ComplEx、解码、站点协变量校正，以及已有表型提取、QC、校验、目录复制整理和 SEED 脚本。模型的训练步骤来自上游原实现；环境、读取和设备适配不改动算法。

## 输入与调度

在平台选择具体方法、绑定其要求的输入、审核参数并通过 Dry-run 后执行。源数据只读，结果写入本次任务目录。多文件清单为 UTF-8 文本，每行一个路径；每个文件都检查授权数据根。NPZ 不加载 Pickle 对象。输出包含日志、产物与校验信息，兼容的上下游输出槽可以自动绑定。

BOLD GLM 仍需预处理影像、TR、事件表/设计矩阵和对比设置；源定位仍需匹配的前向模型与噪声协方差；Maxwell 仍需真实 MEG 传感器几何和坐标变换。DWI 校正同时输出对应的梯度表。软件已安装并不代表任何输入都适用。

GPU 任务选择 **Slurm → all → GPU 1**。原有训练入口的 `device=auto` 使用 Slurm 分配的 CUDA 设备；GPU 0 时隐藏 GPU。已用原有 CNN 训练入口分别验证 CPU 和 GPU 作业。需要图学习依赖、专用软件、权重、外部账户或尚无原始可用入口的方法继续保留为规划。

## 验证与发布

本次后端回归 **119 项测试、467 项子测试通过**；受影响的 **15 项现有调用合成测试通过**；另重新验证原有 CNN 的 Slurm CPU/GPU 作业。之前未改变实现的方法保留原有验证记录，撤回方法的记录从当前范围清单移除。完整验证汇总见 [verification.json](verification.json)。测试使用合成数据和独立数据库，不能据此宣称真实研究数据上的科学有效性或模型性能。

```bash
/opt/neuroweave/envs/scientific-py311/bin/python scripts/audit_skill_execution.py \
  --runtime-env /home/hipeson/LocalFlow/deploy/native-backend.env \
  --output /home/data/neuroweave/development/skill-readiness.json
```

发布使用 `scripts/deploy_slurm_release.py`：检查无活动任务、备份变更、发布版本化共享 Worker，再更新原生后端。生产数据库、数据集、运行历史、已有环境与服务器私有配置保留。
