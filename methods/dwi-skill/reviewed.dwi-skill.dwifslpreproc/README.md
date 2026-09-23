# MRtrix/FSL DWI 预处理（无反向相位编码）

调用现有实现：/opt/software/mrtrix3-master/bin/dwifslpreproc, /opt/software/fsl/bin/eddy_cpu。输入保持只读，输出写入独立任务目录。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
