# MRtrix3 MP-PCA DWI 去噪

独立调用 MRtrix3 3.0.8 的 dwidenoise；保留原软件计算，参数按原版本帮助定义。

dMRI noise level estimation and denoising using Marchenko-Pastur PCA
DWI data denoising and noise map estimation by exploiting data redundancy in the PCA domain using the prior knowledge that the eigenspectrum of random covariance matrices is described by the universal Marchenko-Pastur (MP) distribution. Fitting the MP distribution to the spectrum of patch-wise signal matrices hence provides an estimator of the noise level 'sigma', as was first shown in Veraart et al. (2016) and later improved in Cordero-Grande et al. (2019). This noise level estimate then determines the optimal cut-off for PCA denoising.
Important note: image denoising must be performed as the first step of the image processing pipeline. The routine will fail if interpolation or smoothing has been applied to the data prior to denoising.
Note that this function does not correct for non-Gaussian noise biases present in magnitude-reconstructed MRI images. If available, including the MRI phase data can reduce such non-Gaussian biases, and the command now supports complex input data.

本目录的 `method.json` 是唯一执行契约。参数、输入输出和执行条件均从该文件读取。Skill 只引用方法 ID，不复制契约。
