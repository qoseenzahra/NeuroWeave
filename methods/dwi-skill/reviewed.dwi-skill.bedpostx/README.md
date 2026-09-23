# FSL BEDPOSTX 纤维方向采样

调用现有实现：/opt/software/fsl/bin/bedpostx, /opt/software/fsl/bin/fsl_sub, /opt/software/fsl/bin/bedpostx_preproc.sh, /opt/software/fsl/bin/bedpostx_single_slice.sh, /opt/software/fsl/bin/bedpostx_postproc.sh, /opt/software/fsl/bin/xfibres。输入保持只读，输出写入独立任务目录。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
