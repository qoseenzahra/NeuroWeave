# EEG/MEG 数据检查

调用现有实现：mne.io.read_raw_fif, mne.io.read_raw_edf, mne.io.read_raw_bdf, mne.io.read_raw_eeglab。输入保持只读，输出写入独立任务目录。

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
