# Pipeline 编辑器前端部署 — 2026-09-27

- 入口：http://192.10.84.6:3002/
- 前端版本：`pipeline-ui-7dc6b997b7be`。
- 范围：Method 按需详情卡片、分类标题滚动吸顶、窄窗口列表高度与摘要修正、说明仅由“生成说明”按钮触发，以及这些界面依赖的前端组件拆分。
- 生成说明不会由添加步骤、连线、参数修改、保存草稿、校验或发布触发。按钮会替换当前说明，之后可手动编辑。

## 发布结果

发布前逐文件比较本地前端、服务器前端和上次发布基线。更新 14 个前端源码文件、5 个静态文件；未覆盖服务器独立修改，未删除文件。新资源先安装，index.html 最后原子切换。旧哈希资源保留，已打开的页面可继续加载。

后端维持 `reliability-4e98f88d8543`，Worker 和主站 3000 均未变更。本次只部署前端；本地后端模块拆分没有随本次发布部署。两项后端服务的 PID/启动时间与三个相关容器的身份/启动时间均保持不变。未重启服务、未提交或停止计算任务，也未修改数据库、运行记录或输出。

实际前端版本以 `/__frontend-version.json` 和前端存储面板为准。既有 `/api/health` 的 frontend_revision 来自后端启动环境，本次未重启后端，因此该字段仍返回旧发布标识。

## 验证

- 前端 49 项测试、TypeScript/Vite 生产构建和改动文件 ESLint 已通过。
- 本地浏览器验证：Method 详情、参数展开、关闭、添加节点、分类吸顶和更替；说明接口只在点击按钮时调用，参数修改、校验和发布不额外调用。
- 服务器：所有 5 个静态文件经 HTTP 返回的 SHA-256 均与发布包相同；API health、中文/英文 Method、Pipeline 和草稿查询通过。
- 发布后自动浏览器无法直连校园网页面，线上浏览器交互没有重复验收；服务端 HTTP 验证已通过。
- 该次部署未启动本地常驻服务；相应源码已随后纳入分支提交 `9370fed`。GitHub 提交不改变本文所记后端部署范围。

## 回退

发布记录与比较清单位于：
`/home/hipeson/.cache/neuroweave/pipeline-ui-7dc6b997b7be/`

备份：
`/home/hipeson/.cache/neuroweave/pipeline-ui-7dc6b997b7be/backup-20260927T092334738913Z`

```bash
python3 /home/hipeson/.cache/neuroweave/pipeline-ui-7dc6b997b7be/publish.py --rollback /home/hipeson/.cache/neuroweave/pipeline-ui-7dc6b997b7be/backup-20260927T092334738913Z
```

回退前会拒绝覆盖后续部署的文件；只恢复本次覆盖的旧文件，保留新增源码、哈希资源和备份，不回滚数据库、不重启服务。