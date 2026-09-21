# 新前端替换与独立发布

main 的 `frontend/` 使用 React 19、Vite、React Query 和 Zustand。后端、数据模型、Skill 和 Runner 保持原接口；流程推荐、参数审核、历史输入、节点资源、运行监控及输出目录均调用现有 API。

生产入口仍是 `http://192.10.84.6:3000`。网关继续把 `/api/` 转发到原来的 Unix socket，其余请求转发到 `frontend:3000` 的静态 nginx。3001 测试部署独立保留。两者共享后端数据库。

## 开发和验证

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

开发代理为 127.0.0.1:8010；生产默认同源。不要把凭据放进 VITE_* 变量。前端的模式提示和存储面板版本展示沿用测试版行为。功能验证记录见 `frontend/docs/main-parity.md`。

## 仅替换前端

1. 从已提交的源码生成版本包：`python scripts/package_release.py --output runtime/releases`，核对 SHA-256 后解压到 mgr 的 `/home/hipeson/.cache/neuroweave/releases/<完整前端提交号>`。先比较服务器 `frontend/`、compose 及将更新的文档/部署脚本；保存所涉文件的原始 SHA-256 JSON 清单，新文件用 null 表示原本不存在。传入 `--expected-files` 可在激活前再次拒绝服务器上的并发改动。
2. 明确当前兼容的后端提交号：读取 `/api/health?include_runtime=false` 的 `release.backend_revision`。这次迁移复用 26951be1e8d9a7c691b10a9ed5e7009413924f81 后端，无需后端部署或 Worker 重启。
3. 在 mgr 使用发布包内的新脚本构建。新前端就绪前，旧前端继续服务：

```bash
release=/home/hipeson/.cache/neuroweave/releases/完整前端提交号
python3 "$release/scripts/deploy_frontend_release.py" \
  --source "$release" --revision 完整前端提交号 --build-only
```

如果服务器无法访问 npm/Node 镜像，可使用本地完成 `npm ci && npm test && npm run lint && npm run build` 的同一提交产物。把 dist 放入发布包的 frontend/dist，`__frontend-version.json` 的 revision 必须等于该提交；frontend-dist.json 记录 dist 内每个文件的 SHA-256。附加 `--prebuilt` 使用固定 nginx 镜像构建；脚本会校验文件清单、哈希和提交标记，不接受混入其他文件的构建结果。

4. 激活时指定兼容后端；不会停止 Slurm 作业或重启后端：

```bash
python3 "$release/scripts/deploy_frontend_release.py" \
  --source "$release" --revision 完整前端提交号 \
  --backend-revision 当前兼容后端提交号 \
  --expected-files /已比较的/server-files.json --activate-only
```

使用预构建产物时，激活命令同样加 `--prebuilt`。没有 `--backend-revision` 时仍要求前后端同提交，保留完整应用发布的原有检查。

脚本将旧 frontend 目录整体移到受限备份目录，保留其中所有本地文件和缓存；只安装新 frontend、compose 和清单内的部署文档/脚本，不删除数据库、输出或旧镜像。只有 frontend 容器被替换，gateway 仅执行 nginx 配置校验和优雅 reload，以更新上游地址。脚本检查后端 PID/启动时间没有变化。

## 验证和回退

验证 3000 首页、/assets 文件、缺失资源返回 404、API 健康及 /__frontend-version.json；检查后端和 Worker 的版本仍为预期。用只读操作验证对话、Skill、数据集和方案展开，不在升级验收时提交科研任务。

失败会恢复旧源码/compose 和旧镜像。手动回退使用激活时打印的备份目录：

```bash
python3 "$release/scripts/deploy_frontend_release.py" \
  --rollback /home/hipeson/.cache/neuroweave/frontend-backups/具体备份目录
```

回退同样只操作前端和网关 reload，不回滚运行数据库，不停止计算任务。新源码也会保留在备份中供检查。旧版仅镜像备份仍可使用。
