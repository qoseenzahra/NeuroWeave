# FSL 完整结构预处理（fsl_anat）

调用现有实现：/opt/software/fsl/bin/fsl_anat, /opt/software/fsl/bin/fsl_sub, /opt/software/fsl/bin/fslreorient2std, /opt/software/fsl/bin/robustfov, /opt/software/fsl/bin/bet, /opt/software/fsl/bin/fast, /opt/software/fsl/bin/flirt, /opt/software/fsl/bin/fnirt, /opt/software/fsl/bin/run_first_all。输入保持只读，输出写入独立任务目录。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
