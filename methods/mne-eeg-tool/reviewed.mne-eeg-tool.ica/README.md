# MNE ICA 分解与指定成分去除

调用现有实现：mne.preprocessing.ICA.fit, mne.preprocessing.ICA.apply, mne.preprocessing.ICA.find_bads_eog, mne.preprocessing.ICA.find_bads_ecg。输入保持只读，输出写入独立任务目录。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
