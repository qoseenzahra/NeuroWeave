# NeuroWeave 前端

本目录是 `codex/structured-skill-methods` 的 React 19 / TypeScript / Vite 前端，使用 React Query 管理服务端查询、Zustand 管理界面状态。它依赖本分支的 Skill / Method / Pipeline、Workflow、文件管理及运行 API，不能假定与任意旧版 main 后端兼容。

## 开发和验证

CI 使用 Node.js 24；从本目录运行：

```bash
npm ci
npm run lint
npm test
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

`npm run build` 包含 TypeScript 检查。开发模式 `/api` 代理到 `127.0.0.1:8010`；生产默认使用同源 `/api`，也可在构建时设置 `VITE_LOCALFLOW_API_URL`。前端环境变量会进入浏览器，不能放模型密钥或服务器凭据。测试结束后关闭临时服务。

## 功能与模块

- `features/conversations/`：历史列表、搜索、分页与缓存；正文按需分页。
- `features/chat/`：对话内容、工具进度及消息容器滚动。
- `features/library/`：Skill / Method / Pipeline 分类、详情、节点画布、草稿和版本。参数与输入输出条件来自后端契约；“生成说明”按钮才触发模型调用。
- `features/workflows/`、`features/runs/`：流程审核、文件绑定、运行资源及分页监控。
- 数据集及输出目录浏览使用服务器结构化文件 API；浏览器原生选文件不能替代服务器目录选择。

界面发送 `X-NeuroWeave-Contract: 2`，并按系统语言请求目录显示文本。ID、命令选项、文件路径、用户自定义内容和对话不由显示翻译改写。

本分支测试入口为 3002，主站为 3000。发布时核对 API 契约与前后端版本，不能仅根据页面打开成功判定功能兼容。画布交互及已完成部署的范围见 [画布说明](../deploy/pipeline-canvas-ui.md)；全部文档见 [索引](../deploy/README.md)。[main 对齐记录](docs/main-parity.md) 只保留历史验收事实。
