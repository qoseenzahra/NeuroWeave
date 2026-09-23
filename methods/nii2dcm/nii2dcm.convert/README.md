# nii2dcm 实际转换

把一个 3D NIfTI 转换为研究用途的单帧 DICOM 序列；可从参考 DICOM 复制元数据。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
