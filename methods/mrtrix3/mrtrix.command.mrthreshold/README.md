# MRtrix3 影像阈值处理

独立调用 MRtrix3 3.0.8 的 mrthreshold；保留原软件计算，参数按原版本帮助定义。

Create bitwise image by thresholding image intensity
The threshold value to be applied can be determined in one of a number of ways:
- If no relevant command-line option is used, the command will automatically determine an optimal threshold;
- The -abs option provides the threshold value explicitly;
- The -percentile, -top and -bottom options enable more fine-grained control over how the threshold value is determined.
The -mask option only influences those image values that contribute toward the determination of the threshold value; once the threshold is determined, it is applied to the entire image, irrespective of use of the -mask option. If you wish for the voxels outside of the specified mask to additionally be excluded from the output mask, this can be achieved by providing the -out_masked option.
The four operators available through the "-comparison" option ("lt", "le", "ge" and "gt") correspond to "less-than" (<), "less-than-or-equal" (<=), "greater-than-or-equal" (>=) and "greater-than" (>). This offers fine-grained control over how the thresholding operation will behave in the presence of values equivalent to the threshold. By default, the command will select voxels with values greater than or equal to the determined threshold ("ge"); unless the -bottom option is used, in which case after a threshold is determined from the relevant lowest-valued image voxels, those voxels with values less than or equal to that threshold ("le") are selected. This provides more fine-grained control than the -invert option; the latter is provided for backwards compatibility, but is equivalent to selection of the opposite comparison within this selection.
If no output image path is specified, the command will instead write to standard output the determined threshold value.

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
