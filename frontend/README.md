# NeuroWeave frontend

React/Vite 前端，迁入自 `frontend-new` 分支 6ab1c5c，并包含其后在本地和 3001 验证的功能对齐、弹窗、运行控制及流程收起改动。后端、Skill 和 Runner 接口沿用 main。

```bash
npm ci
npm test
npm run lint
npm run build
npm run dev -- --host 127.0.0.1 --port 5173
```

使用 Node.js 24（CI）或 >=22.13 的 Node 22。开发模式 `/api` 代理到 127.0.0.1:8010；生产由原有 3000 网关转发 API，静态页面由 nginx 提供。`npm run build` 包含 TypeScript 检查。

测试写操作使用独立数据库、合成数据和输出目录，结束后关闭本地测试服务。生产构建可设置 `VITE_LOCALFLOW_API_URL`，默认使用同源 `/api`；前端环境变量不能放密钥。

功能验证记录见 [main-parity.md](docs/main-parity.md)；服务器发布和回退见 [frontend-migration.md](../deploy/frontend-migration.md)。历史记录中的“仅测试端口”“未提交”说明当时的测试阶段，本次 PR 将该实现替换到 main 的 frontend 目录。
