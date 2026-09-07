# Slurm 接入发布验证记录

记录时间：2026-09-07，mgr 发布版本 `c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02`。

## 已完成

- `/opt/neuroweave/envs/scientific-py311`、`torch-cu128-py311` 安装完成；科学环境补齐 Pydantic 和 python-dotenv，`pip check` 通过，精确版本清单已更新。
- 既有 Python Runner 已切换到公共科学环境。生产健康接口显示 22 个注册 Runner、19 个就绪；新增就绪项为 `dipy.tensor_fit`。fMRIPrep、QSIPrep、nii2dcm 仍未配置执行入口。
- Slurm 提交、状态、取消、持久恢复与网页资源选择代码已发布。完整后端回归 95 项及 160 个子测试通过；此后新增的 GPU 预检延期边界测试也通过。最后修改后的 Slurm 35 项专项检查、TypeScript 检查和前端构建通过。
- 固定 Worker 路径为 `/opt/neuroweave/worker/c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02`。三个计算节点均能用公共 Python 导入 Worker 并注册 22 个 Runner；共享输出 `/home/data/neuroweave/runs/hipeson` 可写。
- 网页 `/`、`/api/health`、`/api/execution/backends` 返回 HTTP 200。前端容器健康，网关已刷新连接，原生后端正常运行。
- 该发布包的 545 个公开源码文件与服务器逐字节一致。原生产数据库保留 10 条历史任务（6 failed、4 succeeded），发布前后没有活动任务。
- 变更前备份位于 `/home/hipeson/.cache/neuroweave/deploy/c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02-20260907T031641.600130Z`，环境备份仅账号所有者可读。原前端镜像保留为 `localflow-frontend:pre-slurm-c58b185`。

## 尚待管理员步骤与实际调度验证

本次最后检查时，三个 GPU 节点仍为 DOWN 且未登记 GPU GRES。因此生产 `LOCALFLOW_SLURM_ENABLED=false`，网页暂不允许提交 Slurm 作业。未将模拟测试、只读 GPU 检测或 Worker 导入检查当作真实 GPU 调度通过。

已将管理员脚本同步到 `/opt/neuroweave/admin/` 并通过语法检查。由 hipeson 在 mgr 交互终端执行：

```bash
bash /opt/neuroweave/admin/enable_slurm_gpu.sh
```

完成后按 [管理员说明](slurm-admin.md) 核查 GPU 节点及实际 CUDA 运算。随后执行隔离集成测试（只使用合成数据和独立数据库）：

```bash
cd /home/hipeson/LocalFlow
LOCALFLOW_SLURM_ENABLED=true \
LOCALFLOW_SLURM_WORKER_ROOT=/opt/neuroweave/worker/c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02 \
LOCALFLOW_SLURM_PYTHON=/opt/neuroweave/envs/scientific-py311/bin/python \
/opt/neuroweave/envs/scientific-py311/bin/python -B scripts/smoke_slurm_execution.py
```

脚本验证成功、输入缺失、取消排队作业、重启后同一 Job ID 恢复四种情况，保存 `/home/data/neuroweave/smoke/<时间标记>/evidence.json`。测试通过且生产无活动任务后，以同一发布脚本加 `--enable-slurm` 更新配置，再核查网页分区和 GPU 可用状态：

```bash
python3 /home/hipeson/LocalFlow/scripts/deploy_slurm_release.py \
  --source /home/hipeson/.cache/neuroweave/releases/c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02 \
  --revision c58b1858c0f5f74b5b3b3e63785d2efd7fe24f02 --enable-slurm
```

使用方式、共享路径、GPU 训练模板和规划型 Skill 的执行边界见 [Slurm 执行文档](slurm-execution.md)。
