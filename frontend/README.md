# NeuroWeave 前端

本目录是当前 main 的 React 19 / TypeScript / Vite 前端，使用 React Query 管理服务端查询、Zustand 管理界面状态。前端依赖配套的 Skill / Method / Pipeline、Workflow、文件管理与运行 API，发布时核对 API 契约和版本。

## 开发和验证

CI 使用 Node.js 24；从本目录运行：

```bash
npm ci
npm run lint
npm test
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

`npm run build` 包含 TypeScript 检查。开发模式 `/api` 代理到 `127.0.0.1:8010`；生产默认同源，也可在构建时设置 `VITE_LOCALFLOW_API_URL`。前端变量会进入浏览器，模型密钥与服务器凭据只存后端。

## 功能与模块

- `features/conversations/`、`features/chat/`：历史列表、搜索、分页与缓存，对话工具进度和消息容器滚动。
- `features/library/`：技能侧栏中的 Skill / Method、独立 Pipeline 侧栏、详情、只读画布、独立副本、草稿、发布版本及删除恢复。参数和条件输入输出来自后端契约；“生成说明”按钮显式触发模型。
- `features/workflows/`、`features/tasks/`、`features/runs/`：任务管理、输入绑定、参数审核、资源配置、预检、确认、日志和运行历史。目录创建任务的上下文独立于当前对话。
- `features/datasets/`、`features/workspace/`：服务器数据集浏览、输出目录选择与文件操作确认。页面操作仍由后端重新检查目录权限。

界面发送 `X-NeuroWeave-Contract: 2`，并按系统语言请求目录文本。ID、命令选项、文件路径、用户自定义内容和对话保留原值。共享查询与缓存失效规则见 [代码维护](../deploy/code-architecture.md)。

主站为 3000，现有 3002 开发副本使用独立数据及自己的部署版本。准确服务路径与版本检查见 [服务器部署](../deploy/server-deployment.md)；画布说明见 [Pipeline 画布](../deploy/pipeline-canvas-ui.md)，其余指南见 [文档索引](../deploy/README.md)。
