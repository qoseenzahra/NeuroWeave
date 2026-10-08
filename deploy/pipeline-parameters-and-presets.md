# Pipeline 方法参数与转换预设

详情画布和草稿编辑器共用 `PipelineMethodParameters`。节点选择后显示相同的下拉框或输入框、全部可选值及说明、方法默认值、取值范围和参数条件。只读详情额外显示 Pipeline 预设值、固定参数标记，并展示当前条件下不生效的参数以便检查完整契约。草稿继续按原有条件显示和编辑参数。显式 `null`、`false`、`0` 不会被方法默认值覆盖。

内置 Pipeline 仍然只读；查看不保存草稿、不修改参数、不启动任务。通过“基于此 Pipeline 创建”生成独立副本后才能编辑。Pipeline 固定值来源于原始步骤的 `fixed_parameters`，方法默认值来源于 Method 契约，两者不会混为一谈。

## dcm2niix 去重

逐一比较原有 7 条定义，除 `id`、`label`、`description` 外，包括版本、分类、全部参数契约、输入输出、步骤、固定参数、参数映射、输入输出绑定和工作目录在内的完整 JSON 完全相同才判定为重复。保留 3 条，静态 Pipeline 总数由 28 降为 24：

| 保留标识 | 职责 | 固定参数 | 可配置参数 |
| --- | --- | --- | --- |
| `reviewed-dcm2niix-convert-y-aaf8accb64` | DICOM → NIfTI（GZip 转换） | `compression=y` | JSON sidecar、sidecar 匿名化、文件名模板 |
| `reviewed-dcm2niix-convert-y-true-989e0368fb` | DICOM → NIfTI（固定生成 JSON） | `compression=y, bids_sidecar=true` | sidecar 匿名化、文件名模板 |
| `reviewed-dcm2niix-convert-y-true-4ca43bff7b` | DICOM → NIfTI（固定匿名化 sidecar） | `compression=y, anonymize=true` | JSON sidecar、文件名模板 |

删除的 Custom output filename（`77efa6bba1`）、Lossless compression（`ca0833fa79`）、Merge 2D slices into 3D volume（`fe7c1a2a51`）与通用 GZip 转换完全相同；BIDS-like naming + JSON sidecar（`0e093727e9`）与原 4D fMRI/DWI/perfusion（`989e0368fb`）完全相同。它们没有独立的步骤、实现或额外参数约束。

保留定义的标签、描述、Skill 引用职责和功能树说明一致。通用转换包含命名和压缩设置；序列维度的识别由 dcm2niix 完成。固定生成 JSON 的预设不代表完整 BIDS 数据集整理。sidecar 匿名化不代表图像去面部处理。

现有开发站点的待配置任务引用 `989e0368fb`，因此保留该标识及执行契约；删除的 4 个标识没有保存的任务、用户 Pipeline 或草稿引用。无需删除数据库条目或新增历史别名。存量任务保留创建时的标题和执行快照。
