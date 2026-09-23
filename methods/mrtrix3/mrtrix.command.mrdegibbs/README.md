# MRtrix3 Gibbs 振铃校正

独立调用 MRtrix3 3.0.8 的 mrdegibbs；保留原软件计算，参数按原版本帮助定义。

Remove Gibbs Ringing Artifacts
This application attempts to remove Gibbs ringing artefacts from MRI images using the method of local subvoxel-shifts proposed by Kellner et al. (see reference below for details).
This command is designed to run on data directly after it has been reconstructed by the scanner, before any interpolation of any kind has taken place. You should not run this command after any form of motion correction (e.g. not after dwifslpreproc). Similarly, if you intend running dwidenoise, you should run denoising before this command to not alter the noise structure, which would impact on dwidenoise's performance.
For best results, any form of filtering performed by the scanner should be disabled, whether performed in the image domain or k-space. This includes elliptic filtering and other filters that are often applied to reduce Gibbs ringing artifacts. While this method can still safely be applied to such data, some residual ringing artefacts may still be present in the output.
Note that this method is designed to work on images acquired with full k-space coverage. If this method is executed on data acquired with partial Fourier (eg. "half-scan") acceleration, it may not fully remove all ringing artifacts, and you may observe residuals of the original artifact in the partial Fourier direction. Nonetheless, application of the method is still considered safe and worthwhile. Users are however encouraged to acquired full-Fourier data where possible.

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
