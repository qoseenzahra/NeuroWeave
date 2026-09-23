# 规划入口与实际执行

本分支已取消旧 planning_resolution.json 和 manifest 兼容层。当前结构与维护方式见 [Skill / Method / Pipeline](../structured-skill-methods.md)。

Skill 引用独立方法和显式组合流程。MRtrix ACT/SIFT2、重建 FOD、连接组、FSL BEDPOSTX/ProbtrackX、FreeSurfer 分阶段流程均从 pipelines/ 中读取方法引用与输入输出映射。SIFT2 是独立方法，不再隐藏在 tckgen 中。

已有数据不足不会禁止用户选方法，也不会自动补入不需要的上游步骤；用户可以绑定已有文件或历史制品。缺少真实软件/API/原脚本实现的条目保留为 planning_capabilities。模型不能根据文档命令块补造接口。

创建新执行入口需要维护 methods/ 中的真实契约及 Runner，并通过契约、路径、参数、编译和隔离执行验证。参考文档、环境探测、算法正确性三者不能互相替代。
