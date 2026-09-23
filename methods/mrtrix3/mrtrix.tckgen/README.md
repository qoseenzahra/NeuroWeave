# MRtrix3 基于已有 FOD 的纤维追踪

使用已有 FOD 调用 tckgen 生成流线。ACT 按参数绑定已有 5TT；本方法不生成 5TT、不运行 SIFT2。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
