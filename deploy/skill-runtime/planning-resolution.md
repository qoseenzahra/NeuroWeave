# 规划入口如何成为可执行流程

2026-09-08 完成对原有 358 个规划入口的逐项核对。191 个入口可以指向已有命令、原始脚本或明确的已有 Runner 组合；其余 167 个保留具体缺项。一个方法目录可以展开为多个具体方法，因此不能把映射条数当作独立算法数，也不能把其中一个可执行阶段当成整套研究方案已实现。

## 在界面中使用

1. 选择原数据集和需要的操作，在方法列表选择标为可执行的具体方法。组合方法会显示实际子步骤数量和顺序。
2. 锁定流程后，按所选方法的真实输入槽位绑定文件。已有中间结果可手动选择，也可点“从历史运行结果选择”，按原数据集和样本标识复用。
3. 检查参数、运行 Dry-run；选择 Slurm、节点、每个作业的 CPU/内存/GPU/时限，以及批量样本的并行数量，再提交。
4. 主节点负责提交和监控。CPU/GPU 运算在分配的节点执行，结果和日志写入共享运行目录。

已锁定的旧流程保留原输入、参数和方法快照。需要使用新映射时，先解锁流程并重新选择方法、绑定输入和审核；发布不会替用户改变已批准的算法。

## 主要新增入口

| 需求 | 实际调用与边界 |
| --- | --- |
| 已有 FOD、5TT，进行 ACT + SIFT2 | `tckgen -act` → `tcksift2`；5TT 始终由用户提供 |
| 重建 FOD，再用已有 5TT 追踪 | `dwi2response dhollander` → `dwi2fod msmt_csd` → ACT + SIFT2；预处理 DWI、梯度和掩膜为输入 |
| 上述流程后生成连接矩阵 | 另一个明确标注的组合继续调用 `tck2connectome`，额外需要同空间分区图谱；不会默认加到纯追踪任务 |
| 筛选已有纤维 | 原 `tcksift` 命令，FOD 与纤维可从历史组合任务输出中选择 |
| FSL 概率追踪 | 可直接输入已有 BEDPOSTX 结果，或明确选择 `bedpostx` → `probtrackx2`；输出是纤维密度图，不是 MRtrix tractogram |
| FSL 结构处理 | 原 `fsl_anat` 命令；其子任务使用 FSL shell 后端，留在当前 Slurm 分配内 |
| BNT、BrainNetCNN、ComBrainTF | 调用原项目训练脚本和模型，保留原训练循环、损失及优化器；只适配输入根目录、安全读取、日志、设备和输出位置 |
| EEG/MEG | 原 EEG 脚本中可独立调用的频带、ERP、F3/F4 均值比值、CSP/Hjorth/熵特征，以及 MNE 已定义的 Epochs 平均 |
| 文件与表格 | NiBabel 已有保存/转换 API，pandas 表结构检查和显式键连接，显式映射整理 BIDS 文件 |
| 原区域摘要、站点校正 | 原区域 STD 摘要与原 harmonization CLI；界面明确具体指标/校正方法，缺少对应包的选项不能执行 |

MRtrix 组合中的参数按步骤单独路由，固定的 ACT/SIFT2 选项不会被其他阶段覆盖。MSMT-CSD 的 WM 阶数公开给用户，GM/CSF 使用原软件要求的各向同性 `lmax=0`。无需生成的响应文件、非选中分支的参数不会作为必填项出现。

原训练器读取 `<数据根>/<atlas>/sub-<subject_id>.pt`，张量字典包含原接口要求的 `fc_matrix`（或 `node_features`），并需完整的样本标签 CSV。ComBrainTF 还需原格式的 `roi_names` 或匹配的 `n_rois`。不能把任意 CSV/NPZ 自动当成这些模型的原输入。BrainNetCNN 保留其 checkpoint；BNT、ComBrainTF 的原参考训练脚本不保存 checkpoint，平台只登记其原日志和执行信息。

原 EEG 的 F3/F4 指标是滤波后均值比值，不能标成对数功率差；原脑区脚本是 STD 指标，不能标成新实现的 FFT ALFF。BIDS 整理只核对显式映射、文件名和元数据，不等于完整 BIDS Validator 检查。

## 仍有执行条件缺口的内容

| 原规划入口状态 | 数量 | 需要补充的条件 |
| --- | ---: | --- |
| 缺软件/环境 | 30 | 如原图模型的 PyG/图算子、HCP 工具链、MATLAB/SPM/CONN、WMH 软件与权重 |
| 缺原始实现 | 19 | 原项目未提供的完整引擎、模型服务或任务入口；不能由平台补写算法 |
| 需要具体方案 | 12 | 明确统计设计、协变量、端点、过滤规则或实际批处理方法 |
| 原接口有问题 | 11 | 原文命令参数或原脚本 API 不存在/语义不符；不能用相似算法代替 |
| 需要交互管理 | 66 | 确定仓库、安装目标、命令或研究讨论；这些不是固定科学计算任务 |
| 外部服务/数据访问 | 28 | 已授权账户、客户端、数据批准和明确访问范围 |
| 平台已管理 | 1 | 批量失败清单已由运行监控提供，无需额外影像算法 |

此外，37 个已有执行契约的候选入口尚缺运行条件，涉及 7 个独立 Runner：fMRIPrep、QSIPrep、nii2dcm、neuroCombat、neuroHarmonize、CovBat、原 `mne_microstates.Microstates`。已有契约在准确的软件/API 就绪后可以通过探测；只有规划说明的条目仍需审核具体入口。安装一个同名或类似包不能保证原 API 存在。

逐入口原因及三个节点的运行条件以 [readiness.json](readiness.json) 为准。就绪表示解释器、现有入口、依赖/API 和源码校验通过；具体数据仍须通过输入检查与 Dry-run，不代表所有方法都已经在真实研究数据上验证。

## 后续增加或修改 Skill

映射定义在 [build_planning_resolution.py](../../scripts/build_planning_resolution.py)，生成到 [planning_resolution.json](../../bakend/resources/planning_resolution.json)。单独方法优先引用已有 Runner；多个阶段使用显式输入/输出与参数映射。不会执行从 Skill 文档提取的任意命令，也不会根据方法名自动猜测调用关系。

1. 核对原软件命令、库 API 或原脚本，写清输入格式、参数、条件输出、依赖和来源。
2. 已有 Runner 可以直接引用；缺少调用适配时只增加固定调用、输入输出和调度管理，登记到审核清单，不能补写研究算法。
3. 若组合已有方法，列出实际顺序、固定参数、每个阶段的参数映射与输出引用；不要生成用户已有的上游制品。
4. 重新生成并检查目录，运行受影响的方法测试及节点审计，再发布。

```bash
python scripts/build_reviewed_execution.py
python scripts/build_planning_resolution.py
python scripts/build_capability_tree.py
python scripts/check_release.py
PYTHONPATH=bakend python -m pytest bakend/tests -q
```

每条规划映射保存原输入/输出/参数和说明的指纹；源定义变化后先回到未审核状态。原代码与调用适配也有源码校验，修改后必须重新核对来源。生成器与发布检查会阻止目录漂移。原 BNT、BrainNetCNN、ComBrainTF 的模型和训练文件另有回归测试，确保其内容仍与已登记来源一致。

```bash
# 在 mgr 用生产服务的公共环境配置探测指定计算节点；不输出私有配置值。
/home/hipeson/LocalFlow/.conda/backend/bin/python scripts/audit_skill_execution.py \
  --runtime-env /home/hipeson/LocalFlow/deploy/native-backend.env \
  --slurm-node node01 \
  --output /home/data/neuroweave/development/node01-readiness.json
```

来源参考：[MRtrix SIFT](https://mrtrix.readthedocs.io/en/latest/reference/commands/tcksift.html)、[FSL ProbtrackX](https://fsl.fmrib.ox.ac.uk/fsl/docs/diffusion/probtrackx.html)、[NiBabel 读写](https://nipy.org/nibabel/reference/nibabel.loadsave.html)、[MNE Epochs](https://mne.tools/stable/generated/mne.Epochs.html)。本轮 NumPy `trapz` → `trapezoid` 和 Nilearn 返回形状适配仅处理版本兼容，不改变原计算定义。
