# Slurm 接入发布验证记录

记录时间：2026-09-07。Slurm 已在生产启用；固定 Worker 版本为 `c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02`，后续管理员校验修复和本验证记录另行同步。

## 已完成

- `/opt/neuroweave/envs/scientific-py311`、`torch-cu128-py311` 安装完成；科学环境补齐 Pydantic 和 python-dotenv，`pip check` 通过，精确版本清单已更新。
- 既有 Python Runner 已切换到公共科学环境。生产健康接口显示 22 个注册 Runner、19 个就绪；新增就绪项为 `dipy.tensor_fit`。fMRIPrep、QSIPrep、nii2dcm 仍未配置执行入口。
- Slurm 提交、状态、取消、持久恢复与网页资源选择代码已发布。完整后端回归 95 项及 160 个子测试通过；此后新增的 GPU 预检延期边界测试也通过。最后修改后的 Slurm 35 项专项检查、TypeScript 检查和前端构建通过。
- 固定 Worker 路径为 `/opt/neuroweave/worker/c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02`。三个计算节点均能用公共 Python 导入 Worker 并注册 22 个 Runner；共享输出 `/home/data/neuroweave/runs/hipeson` 可写。
- 网页 `/`、`/api/health`、`/api/execution/backends` 返回 HTTP 200。前端容器健康，网关已刷新连接，原生后端正常运行。
- 首次发布包的 545 个公开源码文件与服务器逐字节一致。原生产数据库保留 10 条历史任务（6 failed、4 succeeded），真实调度测试使用独立数据库；生产启用前后没有活动任务。
- 变更前备份位于 `/home/hipeson/.cache/neuroweave/deploy/c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02-20260907T031641.600130Z`，环境备份仅账号所有者可读。原前端镜像保留为 `localflow-frontend:pre-slurm-c58b185`。

## GPU 配置与真实调度结果

管理员已在四台主机应用 GPU 配置并重启相应服务，执行 `--finalize` 后三个计算节点均已恢复调度。最终核查原先因 mgr 多一个空行而误报；已修复空白行比较、内核版本 `#` 字符解析，以及未启用 GPU 记账时对 `CfgTRES` 的误判。新增 12 项测试、15 个子测试通过，三个节点完整只读核查通过。

以下均为实际提交的 Slurm 作业，结果汇总见 [结构化测试记录](slurm-test-results.json)。

| 验证内容 | Job ID | 节点或结果 |
| --- | --- | --- |
| PyTorch CUDA 运算 | 12 | node01，COMPLETED，退出码 0:0 |
| PyTorch CUDA 运算 | 13 | node02，COMPLETED，退出码 0:0 |
| PyTorch CUDA 运算 | 14 | node03，COMPLETED，退出码 0:0 |
| 平台 Runner 成功执行 | 15 | succeeded，报告产物校验通过 |
| 输入缺失失败处理 | 16 | 按预期 FAILED，退出码 1:0，无产物 |
| 取消排队作业 | 17 | CANCELLED，平台状态确认一致 |
| 重启后恢复监控 | 18 | 恢复前后 Job ID 相同，新增提交数为 0，最终成功 |
| 平台申请 1 张 GPU | 19 | dataset.inspect 在 node01 完成，共享 Worker 与产物回传通过 |

GPU 作业 12–14 使用 PyTorch `2.11.0+cu128`、CUDA 12.8，在各节点的 RTX 5060 上实际执行矩阵乘法并同步 CUDA；设备计算能力为 `(12, 0)`，库包含 `sm_120` 支持。Job 19 单独验证平台资源申请与节点分派，所用数据检查 Runner 本身不执行深度学习训练。

原始证据保存在共享目录中：

- `/home/data/neuroweave/smoke/gpu-20260907T035944Z/evidence.json`
- `/home/data/neuroweave/smoke/20260907T040028Z-2429c14b/evidence.json`
- `/home/data/neuroweave/smoke/gpu-runner-20260907T040314Z/evidence.json`

## 生产启用状态

2026-09-07 12:04（北京时间），确认生产无活动任务后，已备份原生后端环境文件、将 `LOCALFLOW_SLURM_ENABLED` 改为 `true` 并重启后端。固定 Worker 路径和其他配置保持不变。环境备份位于 `/home/hipeson/.cache/neuroweave/deploy/slurm-enable-20260907T040441Z/native-backend.env`，仅账号所有者可读。

线上 `/api/execution/backends` 确认 `slurm.enabled=true`、`available=true`、`gpu_available=true`，分区为 `all`。mgr 无 GPU；node01–03 均登记 `gpu:1` 并可调度。网页可在方案最终确认后选择 Slurm，设置 CPU、内存、时限及 GPU 数量；申请 1 张 GPU 时由 Slurm 分派至具备 GPU 的计算节点。

当前未启用 Slurm accounting 和 cgroup GPU 设备隔离；长期历史查询与强制设备隔离仍需后续配置。规划型 Skill 仍需注册可信 Runner、准备数据和模型权重后才能自动执行；安装 Python 库不代表所有规划方法均已接入。fMRIPrep、QSIPrep、nii2dcm 的执行入口仍未配置。

## 重复验证

如后续修改调度代码，可运行以下隔离集成测试，仅使用合成数据和独立数据库：

```bash
cd /home/hipeson/LocalFlow
LOCALFLOW_SLURM_ENABLED=true \
LOCALFLOW_SLURM_WORKER_ROOT=/opt/neuroweave/worker/c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02 \
LOCALFLOW_SLURM_PYTHON=/opt/neuroweave/envs/scientific-py311/bin/python \
/opt/neuroweave/envs/scientific-py311/bin/python -B scripts/smoke_slurm_execution.py
```

脚本验证成功、输入缺失、取消排队作业、重启后同一 Job ID 恢复四种情况，保存 `/home/data/neuroweave/smoke/<时间标记>/evidence.json`。GPU 配置核查与 CUDA 探针见 [管理员说明](slurm-admin.md)。

使用方式、共享路径、GPU 训练模板和规划型 Skill 的执行边界见 [Slurm 执行文档](slurm-execution.md)。
