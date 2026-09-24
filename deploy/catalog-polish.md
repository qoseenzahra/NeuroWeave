# 数据集分类、目录清理与双语说明（2026-09-24）

当前目录：105 个规范 Skill、328 个 Method、28 个内置 Pipeline，以及保留历史选择所需的 70 个轻量别名。

## 分类与说明

- 29 个数据集专属 Skill（ABCD、ABIDE、UKB、HCP、SEED 等）以 `scope: dataset` 标识，单列在“数据集专属 / 数据集适配与质控”。Method 仍按实际处理功能分类；分类不限制全库检索，也不代表执行权限。
- 163 个旧适配 Method 的说明根据现有源码、argparse 帮助和实际注册端口补充了用途、输入是文件还是目录、固定调用模式及输出位置。
- 另按固定版本帮助补全 FSL fsl_glm、FreeSurfer mri_mask/mri_binarize 的 13 个原本空泛的布尔参数说明。
- 保留 DWI 等领域的专门规则：输入复用必须符合用户本轮要求，重新生成 FOD 不自动追加 5TT。
- 澄清原脚本的科学含义：名为 zALFF 的区域摘要实际使用滤波后信号 STD；原 alpha-asymmetry 函数计算 F3/F4 信号均值比值。未修改这些原有算法。
- 新方法详情不再假定所有软件都提供 MRtrix 格式的选项总数。没有完整上游统计时显示已登记参数数目，不虚构总覆盖率。

## 已清理内容

本地删除 570 个已检查引用的冗余文件，包括旧 planning/execution/tool manifests、重复 OVERVIEW、仅重复 method.json 的 README、退出运行链路的生成器/数据汇总及旧 Skill 加载器。精确文件清单保存在本次 Git 删除记录中。

仍被 WorkflowService 使用的 `skills/dwi-skill/workflow.manifest.json`、Method 引用的实现源码、原始帮助、来源记录和运行验证证据均保留。Skill 的 functions 详情由当前 Method/Pipeline 契约动态生成，不再维护一份重复说明；Skill JSON 每次刷新只读取一次。

本次没有删除服务器部署文件、研究数据、任务记录或输出，也没有重启 3000/3002 服务。服务器只使用独立临时目录完成已授权的公开文本翻译，以及三个方法的微型合成验证。

## 双语边界

前端使用系统语言，后端按 `Accept-Language` 或 `language=zh|en` 投影显示文本。覆盖分层目录、说明、参数帮助、输入输出、条件提示、运行状态，以及 Pipeline 校验和 Workflow 参数变更后的方法元数据。

ID、CLI 参数、默认值、选项值、条件表达式、路径绑定、用户 Pipeline 名称/描述、对话和历史内容不翻译。切换语言不调用模型，也不改数据库或执行快照。原始参考文档和版本帮助保留原文，便于核查来源。

离线词典含英文 3,411 条、中文 2,709 条；当前提取的 5,937 项目标翻译全部覆盖，占位符检查无缺项。批量翻译后检查了英文残留、路径与命令保护，以及关键科学表述。新增元数据必须重新运行覆盖检查；这不替代专业术语的持续人工校对。

## 后续维护

```powershell
python scripts/catalog_translation.py export --output translation-jobs.json
```

仅在授权将公开元数据发送至已配置模型服务后执行以下离线命令。环境文件在进程内读取，不写入词典或日志；禁止将研究数据、会话、密钥加入清单。

```bash
python scripts/catalog_translation.py translate \
  --jobs translation-jobs.json \
  --output bakend/resources/catalog-locales \
  --env-file /path/to/backend.env \
  --allow-provider
python scripts/catalog_translation.py check
python scripts/build_capability_tree.py --check
python scripts/check_release.py
```

翻译脚本缓存已完成条目、限制并发和重试、保护命令/路径/占位符。翻译结果仅从白名单显示字段读取，不参与 Runner 权限判定。生成树后若产生新文案，再导出增量清单。

## 验证

- 完整后端回归：350 passed、3 skipped、694 subtests passed；最后参数说明变更另通过定向回归。前端：47 项通过，生产构建通过。
- 三个受影响命令的默认用例及 13 个布尔参数变体共 16/16 合成验证通过，见 `deploy/method-verification/reports/catalog-flags-synthetic.json`。已更新这三个 Method 的真实运行指纹。
- 分类、全部契约显示投影、用户命名保护、Pipeline POST/Workflow PATCH 双语响应、动态路径保留、源码引用存续均有回归测试。
- 1,223 个登记参数均有说明，输入输出无空描述，328 个 Method 契约有效。
- 92 个 Method 保留与当前执行代码匹配的合成运行证据；其余 236 个没有当前版本运行证据。本次没有把文档完善当成新的算法执行验证。
- 前端组件测试与生产构建通过；没有启动需要遗留关闭的本地前后端服务。未完成真实浏览器交互验收。

本次要求的 GitHub 分支更新不替代服务器发布。后续部署前仍须比较本地与服务器差异，保留运行中的 Worker 和输出；若需要删除服务器旧文件，先审核精确清单和进程引用。
