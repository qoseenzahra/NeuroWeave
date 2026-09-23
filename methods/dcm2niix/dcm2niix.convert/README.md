# dcm2niix 实际转换

调用服务器现有 dcm2niix，将只读 DICOM 输入转换到隔离输出目录并生成 JSON sidecar。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
