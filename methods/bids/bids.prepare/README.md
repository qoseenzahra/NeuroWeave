# BIDS Organizer

把已有 NIfTI/BIDS 数据复制到隔离输出目录，补齐 dataset_description.json、清理敏感 sidecar 字段并执行基础结构校验。DICOM 应先使用 dcm2niix 转换。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
