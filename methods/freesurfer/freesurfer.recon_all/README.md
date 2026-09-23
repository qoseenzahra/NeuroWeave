# FreeSurfer recon-all（可执行）

使用服务器现有 FreeSurfer 7.4.1 执行完整 recon-all，或在同一 SUBJECTS_DIR 中连续执行 autorecon1/2/3，并登记受试者目录制品。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
