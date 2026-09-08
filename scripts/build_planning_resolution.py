"""Build reviewed planning-to-existing-entrypoint mappings and explicit blockers.

This file is a reviewed catalog, not a fuzzy method matcher. A changed source
contract invalidates its saved fingerprint until the mapping is reviewed again.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bakend'))
from app.capability_registry import CapabilityRegistry
from app.planning_resolution import source_fingerprint

REGISTRY = CapabilityRegistry(ROOT/'skills')
CATALOG = {cap: REGISTRY.selectable_methods_for(cap,resolve_planning=False)
           for cap in REGISTRY.capabilities()}
LOOKUP = {(m.capability,m.method_id):m for methods in CATALOG.values() for m in methods}


def existing(capability, method_id):
    method = LOOKUP.get((capability,method_id))
    if method is None or method.execution_mode != 'runner':
        raise ValueError('Not an existing executable method: '+capability+'/'+method_id)
    return method


def reference(capability, method_id, *, label=None):
    method = existing(capability, method_id)
    return dict(key=method_id, capability=capability, method_id=method_id,
                label=label or method.label, description=method.description)


def choices(skill):
    capability = 'skill.'+skill.replace('_','-')
    return [reference(capability,m.method_id) for m in CATALOG.get(capability,[])
            if m.execution_mode=='runner']


def recipe(key, label, stages, exports=None):
    """Route existing typed inputs and parameters, materializing fixed conditions."""
    parameters, inputs, outputs, steps = {}, {}, [], []
    definitions = {}
    multi = len(stages)>1

    def conditions(slot, fixed, route, field):
        slot = copy.deepcopy(slot)
        remaining = {}
        for name, values in slot.get(field,{}).items():
            if name in fixed:
                if fixed[name] not in values:
                    return None
            else:
                remaining[route.get(name,name)] = values
        if slot.get(field) and not remaining and field=='required_when':
            slot['required'] = True
        slot[field] = remaining
        return slot

    for stage in stages:
        sid, cap, mid = stage['id'], stage['capability'], stage['method_id']
        definition = existing(cap,mid)
        definitions[sid] = definition
        fixed = stage.get('fixed',{})
        route = {p.id: (sid+'_'+p.id if multi and p.id!='threads' else p.id)
                 for p in definition.parameters if p.id not in fixed}
        for p in definition.parameters:
            if p.id in fixed:
                if p.options and fixed[p.id] not in [o.value for o in p.options]:
                    raise ValueError('Invalid fixed option: '+sid+'/'+p.id)
                continue
            public = conditions(p.model_dump(mode='json'),fixed,route,'visible_when')
            if public is None:
                route.pop(p.id,None)
                continue
            public['id'] = route[p.id]
            public['group'] = definition.label if multi else public['group']
            if route[p.id] in parameters and parameters[route[p.id]]!=public:
                # Shared thread counts use the first reviewed declaration.
                if p.id!='threads':
                    raise ValueError('Inconsistent recipe parameter')
                continue
            parameters[route[p.id]] = public
        bindings = {}
        for slot in definition.input_slots:
            public = conditions(slot.model_dump(mode='json'),fixed,route,'required_when')
            if public is None:
                continue
            source = stage.get('inputs',{}).get(slot.id,slot.id)
            if isinstance(source,tuple):
                upstream, output_id = source
                output = next(o for o in definitions[upstream].output_slots if o.id==output_id)
                if output.type!=slot.type:
                    raise ValueError('Recipe input/output types differ: '+key+'/'+sid+'/'+slot.id)
                bindings[slot.id] = dict(source='step_output',step_id=upstream,output_slot_id=output_id)
            else:
                public['id'] = source
                if source in inputs and inputs[source]['type']!=public['type']:
                    raise ValueError('Recipe input types differ: '+source)
                inputs.setdefault(source,public)
                bindings[slot.id] = dict(source='workflow_input',slot_id=source)
        steps.append(dict(id=sid,title=definition.label,capability=cap,method_id=mid,
            fixed_parameters=fixed,parameter_bindings=route,inherit_parameters=False,
            input_bindings=bindings,workspace=sid))
    last = stages[-1]
    if exports is None:
        exports = {o.id:(last['id'],o.id) for o in definitions[last['id']].output_slots if o.type!='execution_log'}
    output_bindings = {}
    for public_id,(sid,slot_id) in exports.items():
        definition = definitions[sid]
        stage = next(s for s in steps if s['id']==sid)
        slot = next(o for o in definition.output_slots if o.id==slot_id)
        public = conditions(slot.model_dump(mode='json'),stage['fixed_parameters'],stage['parameter_bindings'],'generated_when')
        if public is None:
            continue
        public['id'] = public_id
        public['primary'] = sid == last['id'] and slot.primary
        outputs.append(public)
        output_bindings[public_id] = dict(step_id=sid,output_slot_id=slot_id)
    target = reference(last['capability'],last['method_id'],label=label)
    target.update(key=key,description='依次调用：'+' → '.join(s['title'] for s in steps)+'。仅执行列出的步骤；已有输入可手动绑定或从历史结果选择。',
        included_capabilities=list(dict.fromkeys(s['capability'] for s in stages)),
        recipe=dict(recipe_id='reviewed-'+key,label=label,operation_value=key,
            interface_capability=target['capability'],interface_method_id=target['method_id'],
            parameters=list(parameters.values()),input_slots=list(inputs.values()),output_slots=outputs,
            steps=steps,output_bindings=output_bindings))
    return target


def stage(sid,cap,mid,fixed=None,inputs=None):
    return dict(id=sid,capability=cap,method_id=mid,fixed=fixed or {},inputs=inputs or {})


def preset(cap,mid,fixed,label=None):
    method=existing(cap,mid)
    return recipe(mid+'-'+'-'.join(str(v).lower() for v in fixed.values()),label or method.label,
                  [stage('execute',cap,mid,fixed)])


def fod_stages():
    return [stage('response','dwi.response','mrtrix-dwi2response',{'algorithm':'dhollander'}),
        stage('fod','dwi.fod','mrtrix-dwi2fod',{'algorithm':'msmt_csd'},
              {x+'_response':('response',x+'_response') for x in ['wm','gm','csf']})]


def tracking_variants(connectome=False):
    alternatives=[]
    for rebuild in [False,True]:
        steps=fod_stages() if rebuild else []
        steps += [stage('tracking','dwi.tractography','mrtrix3-existing-fod',
                        {'act_enabled':True,'postprocessing':'sift2'},
                        {'fod':('fod','wm_fod')} if rebuild else {})]
        exports={'tractogram':('tracking','tractogram'),'weights':('tracking','weights')}
        if rebuild: exports['wm_fod']=('fod','wm_fod')
        if connectome:
            steps += [stage('connectome','dwi.connectome','mrtrix-tck2connectome',{'use_weights':True},
                       {'tractogram':('tracking','tractogram'),'weights':('tracking','weights')})]
            exports['connectome']=('connectome','connectome')
        key=('rebuild-fod' if rebuild else 'existing-fod')+('-connectome' if connectome else '-act-sift2')
        label=('重建 FOD → ' if rebuild else '已有 FOD → ')+'ACT + SIFT2'+(' → 连接矩阵' if connectome else '')+'（复用已有 5TT）'
        alternatives.append(recipe(key,label,steps,exports))
    return alternatives


def blocked(state,reason,*requirements):
    return dict(state=state,reason=reason,requirements=list(requirements))


def mapped(alternatives, reason='已核对到现有实现；选择具体入口后按其真实输入、参数和输出执行。'):
    if not alternatives:
        raise ValueError('Empty reviewed mapping')
    return dict(state='mapped',reason=reason,alternatives=alternatives)


# These generic Skill wrappers describe a menu, not an additional algorithm.
MENUS = set('abcd-skill abide-skill adhd200-skill adni-skill aibl-skill aomic-skill beautiful-log bnt bold5000-skill brain-age-modeling brainnetcnn causal-treatment-models cnn3d cobre-skill combraintf cpm detrending dictlearning dmt-har-med-skill filtering glm hbn-skill hierarchical ica imaging-genetics-models ixi-skill kg-link-prediction kmeans neuroimaging-decoding nilearn-tool run_models spacenet statistical-ml subject-subtyping survival-models temporal-models'.split())
MANAGEMENT = set('claw-shell conda-env-manager dependency-planner docker-env-manager experiment-controller git-manager git-essentials git-workflows method-design paper-writing research-idea skill-updater harness harness-core'.split())
HCP = set('hcppipeline-tool'.split())


def resolve(m):
    sk, op = m.skill_id, m.method_id.partition('--')[2]
    direct=lambda cap,mid: mapped([reference(cap,mid)])
    if sk in MENUS and not op:
        return mapped(choices(sk),'此条是方法目录；已展开为原有具体实现，逐项显示真实输入和输出，不将目录整体当作一个算法。')
    if sk in MANAGEMENT:
        return blocked('interactive','此 Skill 是交互式管理/讨论流程，依赖用户指定命令、仓库、安装目标或研究方案，没有固定科学任务契约；现有平台仍负责审批、环境管理、日志和任务调度。','明确管理对象与动作；不能把文档中的任意 shell 命令直接注册为算法')
    if sk in {'academic-research-hub','multi-search-engine','overleaf-skill'}:
        return blocked('external_service','该步骤依赖外部检索/文档服务；公共计算环境不包含其完整客户端、账户会话和联网配置。安装科学库不能满足这个执行条件。','arxiv / semanticscholar / Biopython 客户端及联网' if sk=='academic-research-hub' else '搜索或 Overleaf 服务连接、授权会话')
    if sk in {'braingnn','ibgnn','lggnn'}:
        return blocked('missing_runtime','原项目图模型训练需要 torch_geometric 及匹配 PyTorch/CUDA 的图算子；当前公共环境缺失这些依赖。','torch_geometric','匹配版本的 torch_scatter / torch_sparse 等原训练入口依赖')
    if sk in {'connectome-discovery','fm_app','neurostorm'}:
        return blocked('missing_implementation','原内容是实验/研究编排说明，或调用未完成的原始入口；缺少可直接执行的完整任务实现。基础 Python/PyTorch 可用不代表该研究流程已定义。','原始可调用实现、模型/服务资产及明确输入输出；不补写替代算法')
    if sk=='knowledge-graph-builder':
        return blocked('missing_implementation','原文调用的 neurooracle 软件包、ingest/batch_extract/phase3 入口未随当前项目提供；现有 scripts 是使用参考和辅助函数，不能代替完整图谱引擎。','原始 neurooracle 实现及其数据/服务配置')
    if sk=='dcm2nii':
        if op=='keep-slice-timing-philips-diff':
            return blocked('source_error','原参考的 -t y 不是已安装 dcm2niix 的切片时序开关；转换器默认从有效 DICOM 写入相应 JSON 字段，无法用该选项保证缺失时序得到恢复。','正确的原始 DICOM 时序元数据；可选择普通 dcm2niix 转换检查 sidecar')
        if op=='only-convert-specific-series':
            return mapped([reference('skill.dcm2nii','dcm2niix-convert',label='dcm2niix 转换所选单序列目录')],'按用户选择的序列目录转换；原参考 -m 不能充当系列筛选条件，不猜测 SeriesInstanceUID。')
        fixed={'compression':'y'}
        if op in {'bids-like-naming-json-sidecar','4d-fmri-dwi-perfusion'}: fixed['bids_sidecar']=True
        if op=='anonymize-remove-most-phi': fixed['anonymize']=True
        return mapped([preset('skill.dcm2nii','dcm2niix-convert',fixed,m.label)])
    if sk=='dataset-inspector':
        if op=='table-schema':
            return direct('skill.dataset-inspector','reviewed-table-inspect-dataset-inspector')
        return direct('dwi.inspect','dataset_inspector')
    if sk=='report-builder':
        return direct('dwi.report','report_builder')
    if sk=='table-cleaning':
        return direct('skill.table-cleaning','pandas-clean')
    if sk=='bids-organizer':
        if op=='create-datasetdescription-json': return direct('skill.bids-organizer','reviewed-explicit-metadata-bids-organizer')
        if op=='existing-nifti-to-bids':
            return direct('skill.bids-organizer','reviewed-explicit-stage-bids-organizer')
        if op=='validate-bids-dataset':
            return blocked('missing_runtime','原流程要求完整 bids-validator CLI；已安装的 Python bids_validator 只验证文件名，不能替代整个 BIDS 数据集验证器。','完整 BIDS Validator CLI（包括 schema/元数据检查）')
        if op=='eeg-to-bids':
            return blocked('missing_runtime','BIDS EEG 写入需要 mne-bids 及明确的受试者、任务、事件和电极元数据；当前未安装 mne_bids。','mne_bids.write_raw_bids','BIDS EEG 实体和采集元数据')
        return blocked('needs_protocol','原文没有定义 DICOM 序列到 BIDS 实体的确定映射。dcm2niix 转换和显式文件映射整理已可分别运行；完整自动组织还需采集规则和完整 BIDS 验证器。','序列/样本/会话/任务映射','完整 BIDS Validator CLI')
    if sk=='dipy-tool':
        return direct('dwi.tensor_metrics','dipy')
    if sk=='freesurfer-tool':
        return mapped([preset('skill.freesurfer-tool','freesurfer-recon-all',
            {'processing_stage':'stats' if op=='generate-statistics-only' else 'autorecon3'},m.label)])
    if sk=='smri-skill':
        if op=='dicom-nifti': return direct('skill.dcm2nii','dcm2niix-convert')
        if op in {'fast-structural-preprocessing'}: return direct('skill.fsl-tool','reviewed-fsl-anat-fsl-tool')
        stages={'freesurfer-autorecon1-volumetric-preprocessing':'autorecon1',
                'freesurfer-autorecon2-subcortical-segmentation-surface-extraction':'autorecon2',
                'freesurfer-autorecon3-spherical-registration-parcellation':'autorecon3',
                'full-freesurfer-pipeline-all-3-stages':'all','surface-based-morphometry-quick':'all'}
        if op in stages:
            return mapped([preset('skill.freesurfer-tool','freesurfer-recon-all',{'processing_stage':stages[op]},m.label)])
    if sk=='fsl-tool':
        if op=='structural': return direct('skill.fsl-tool','reviewed-fsl-anat-fsl-tool')
        if op=='functional': return direct('skill.fsl-tool','reviewed-mcflirt-fsl-tool')
        if op=='diffusion':
            return direct('dwi.preprocess','fsl_eddy')
    if sk=='dwi-skill':
        if m.method_id=='fsl-probtrackx':
            return mapped([
                reference('skill.dwi-skill','reviewed-probtrackx-existing-dwi-skill'),
                recipe('bedpostx-probtrackx','DWI → BEDPOSTX → ProbtrackX（种子纤维密度图）',[
                    stage('bedpostx','skill.dwi-skill','reviewed-bedpostx-dwi-skill'),
                    stage('tracking','skill.dwi-skill','reviewed-probtrackx-existing-dwi-skill',inputs={'samples':('bedpostx','results')})])])
        if m.method_id=='mrtrix3-act-sift2':
            return mapped(tracking_variants(False)+tracking_variants(True))
        if op=='dicom-nifti': return direct('skill.dcm2nii','dcm2niix-convert')
        if op=='tensor-metrics':
            return mapped([reference('dwi.tensor_metrics','dipy'),reference('dwi.tensor_metrics','fsl_dtifit')])
        if op=='fiber-orientation-distribution-fod':
            return mapped([reference('dwi.fod','mrtrix-dwi2fod'),recipe('response-fod','预处理 DWI → 响应函数 → MSMT-CSD FOD',fod_stages())])
        if op=='anatomically-constrained-tractography-act':
            return mapped([preset('dwi.tractography','mrtrix3-existing-fod',{'act_enabled':True},'ACT 纤维追踪（已有 FOD 和 5TT）')])
        if op=='tractography-connectome-mrtrix3-based':
            return mapped([reference('dwi.connectome','mrtrix-tck2connectome'),*tracking_variants(True)])
        if op=='sift-streamline-filtering': return direct('skill.dwi-skill','reviewed-sift-existing-dwi-skill')
        if op=='manual-fsl-preprocessing': return direct('dwi.preprocess','fsl_eddy')
        if op=='best-practice-dwi-preprocessing-recommended': return direct('dwi.preprocess','qsiprep')
    if sk=='nibabel-skill':
        return direct('skill.nibabel-skill','reviewed-save-existing-nibabel-skill' if op=='nifti-save-export' else 'reviewed-surface-nibabel-skill')
    if sk=='brain-visualization':
        return mapped([reference('skill.brain-visualization','reviewed-original-region-summary-brain-visualization')],
            '复用原脚本的滤波后标准差区域排序。它需要 4D BOLD；此 STD 指标不声明为另一个频域 ALFF 算法。')
    if sk=='mne-eeg-tool':
        target={'extractfrequencybands':'bands','extracterpfeatures':'erp','computealphaasymmetry':'alpha-ratio',
                'extractfeatures':'features','runmicrostateanalysis':'microstates'}
        if op in target: return direct('skill.mne-eeg-tool','reviewed-original-'+target[op]+'-mne-eeg-tool')
        return blocked('source_error','原脚本依赖不存在的 mne.preprocessing.find_bad_channels / AutoReject，且连续 Raw 的 AutoReject 调用不符合该 API；不得用 LOF 或另一种清理算法替代原定义。','修复原 Skill 的算法/API 定义并重新审核；可另选已提供的独立 MNE 方法')
    if sk=='eeg-skill':
        if op=='waveform-to-mel-spectrogram':
            return blocked('missing_runtime','原 Skill 使用 torchaudio.transforms.MelSpectrogram；当前 Torch 环境没有 torchaudio。','与当前 PyTorch/CUDA 匹配的 torchaudio')
        if op=='frequency-band-energy-extraction':
            return blocked('source_error','原 CWT 片段使用未定义的 low_idx/high_idx，且不能把它替换成 Welch 频带功率来宣称同一算法可执行。','完整可调用的原 CWT 频带定义')
        return blocked('source_error','该组合依赖原 EEG 清理或特征接口中的未定义调用，或者缺少 pyentrp/mne_microstates。已就绪的独立 MNE 操作仍可选择，不能作为整个原组合的替代。','原始清理/特征定义修正','pyentrp / mne_microstates（按所选功能）')
    if sk=='meg-skill':
        if op=='evoked-responses': return direct('skill.meg-skill','reviewed-evoked-existing-meg-skill')
        if op=='ica-artifact-removal':
            return mapped([reference('skill.meg-skill','reviewed-ica-mne-eeg-tool')],'调用现有 MNE ICA；输出为清理后的 Raw 和成分选择记录。Epochs 可另选分段方法，按实际需求加入。')
        return blocked('needs_protocol','原文要求源空间 parcel 连接；当前连接入口处理传感器 Epochs，不能当作源空间结果。需要源估计、分区与连接方式的明确契约。','源空间/分区定义','源时间序列及连接方式')
    if sk=='harmonization-tool':
        return direct('skill.harmonization-tool','reviewed-'+op+'-harmonization-tool')
    if sk=='asl-skill':
        if op=='cbf-quantification': return direct('skill.asl-skill','compute-cbf')
        if op=='roi-based-cbf-extraction': return direct('skill.dipy-tool','reviewed-roi-stats-dipy-tool')
        if op=='asl-to-mni-normalization': return direct('skill.fsl-tool','reviewed-applywarp-fsl-tool')
        return blocked('missing_implementation','原表中的 ASLPREPCORE、单独 M0 归一化、PVC 或 --qc 没有对应完整可调用入口；现有 compute_cbf 仅实现其声明的 CBF 量化，不冒充这些独立操作。','原始可调用实现；ASL 采集参数/组织分割/校准约定')
    if sk=='pet-skill':
        if op=='pet-to-t1w-coregistration':
            return mapped([preset('image.registration','fsl_flirt',{'transform':'rigid'},'PET → T1w 刚体配准')])
        if op=='suvr-computation': return direct('skill.pet-skill','compute-suvr')
        if op=='t1w-to-mni-normalization':
            return mapped([reference('skill.fsl-tool','reviewed-fnirt-fsl-tool'),reference('skill.fsl-tool','reviewed-applywarp-fsl-tool')],
                '选择生成 T1w 形变或应用已有形变的具体步骤；复用配准结果时只运行 applywarp。')
        return blocked('needs_protocol','原文仅说明参考区/PVC/动态模型或示踪剂策略，没有给出完整现有调用和必要的分区、时序/输入函数约定。不能用简单 SUVR 代替这些算法。','参考区与示踪剂/时间窗','对应 PVC 或动力学原实现')
    if sk=='ukb-skill':
        if op=='case-extraction': return direct('skill.ukb-skill','reviewed-extract-ukb-cases-ukb-skill')
        if op=='predictive-modeling-on-ukb-brain-features': return mapped(choices('statistical-ml'))
        if op in {'cognitive-phenotype-association','brain-mri-phenotype-association'}:
            return direct('skill.neuroimaging-decoding','reviewed-roi-glm-neuroimaging-decoding')
        if op=='neurological-survival-analysis':
            return mapped(choices('survival-models'),'已有事件/时间表可进入原生存模型；疾病事件提取可单独选择，端点与删失日期由用户明确。')
        if op=='propensity-score-analysis':
            return mapped([reference('skill.causal-treatment-models','reviewed-cate-causal-treatment-models--ipw')],
                '支持原项目定义的 IPW；不声称提供未实现的匹配算法。')
        return blocked('needs_protocol','该研究问题需先确定分组、交互/中介模型或敏感性过滤规则；原文没有固定可执行的完整分析契约。','明确统计模型、协变量、分组/过滤与报告指标')
    if sk=='image-batch-processing':
        if op=='format-conversion': return direct('skill.nibabel-skill','reviewed-save-existing-nibabel-skill')
        if op=='spatial-validation': return direct('skill.nibabel-skill','reviewed-inspect-nibabel-skill')
        if op=='failure-manifest':
            return blocked('platform_managed','样本成功/失败清单由现有运行监控和运行审计统一生成；它不是需要额外对影像执行的算法。','在运行监控中查看样本状态和日志')
        return blocked('needs_protocol','批量是调度方式；先选明确的预处理方法、输入匹配规则和每节点并行数量，平台按样本执行。','具体预处理方法')
    if sk in {'fmriprep-tool','qsiprep-tool','nii2dcm'}:
        cap,mid={'fmriprep-tool':('skill.fmriprep-tool','fmriprep-local-environment'),
                 'qsiprep-tool':('dwi.preprocess','qsiprep'),
                 'nii2dcm':('skill.nii2dcm','nii2dcm-local-environment')}[sk]
        return mapped([reference(cap,mid)],'已指向现有软件适配；公共环境缺少该软件，界面和 Dry-run 会显示实际缺项。具体可用参数以该适配声明为准。')
    if 'hcp' in op or sk in HCP:
        return blocked('missing_runtime','HCP Pipelines、Workbench/MSM/FIX 及其模板/分类器尚未完整配置；已有 FSL/FreeSurfer 不能替代 HCP 的完整流程。','HCP Pipelines','Workbench / MSM / ICA-FIX（按阶段）','模板、配置与分类器')
    if 'wmh' in op or sk=='wmh-segmentation':
        return blocked('missing_runtime','原 WMH 分割软件和对应模型权重未部署；不能用现有通用分割库代替。','原 WMH 软件/容器','匹配的模型权重')
    if 'bids-anatomical' in op:
        return direct('skill.fmriprep-tool','fmriprep-local-environment')
    if 'fmriprep' in op:
        return direct('skill.fmriprep-tool','fmriprep-local-environment')
    if 'organize-to-bids'==op or op=='bids-organization' or op=='stage-or-validate-bids':
        return mapped([reference('skill.bids-organizer','reviewed-explicit-stage-bids-organizer')],
            '支持显式文件映射整理；完整数据集验证仍需 BIDS Validator CLI，不把文件名检查当作完整验证。')
    if op=='bids-staging':
        alternatives=[a for a in choices(sk) if 'reorganize' in a['method_id']]
        if alternatives: return mapped(alternatives)
    if op in {'data-access','data-download'}:
        return blocked('external_service','此步骤需要数据提供方账户、访问批准和明确下载范围；本地处理环境不能代替数据访问条件。','数据提供方授权及已批准导出/下载')
    if op in {'smri-processing','t1w-t2w-or-flair-processing'}:
        return mapped([reference('skill.fsl-tool','reviewed-fsl-anat-fsl-tool'),
                       preset('skill.freesurfer-tool','freesurfer-recon-all',{'processing_stage':'all'})],
                      '选择原文委托的具体结构处理入口；不同流程分别列出，按用户所需范围执行。')
    if op=='dmri-processing':
        return mapped([reference('dwi.preprocess','fsl_eddy'),reference('dwi.tensor_metrics','dipy'),
                       *tracking_variants(True)],'选择原文委托的具体扩散处理阶段，已有上游结果直接绑定；完整采集流程需明确相位编码/图谱。')
    if op in {'rs-fmri-processing','fmri-processing','task-fmri-processing','resting-task-fmri-processing'}:
        return mapped([reference('skill.fmriprep-tool','fmriprep-local-environment'),
                       *[reference('skill.nilearn-tool','reviewed-'+name+'-nilearn-tool')
                         for name in ['denoise','connectome','task-glm']]],
                      '完整预处理需要 fMRIPrep 环境；已有预处理 BOLD 可直接选择所需的原去噪、连接或任务 GLM。')
    if sk in {'conn-tool'} or 'conn' in op:
        return blocked('missing_runtime','原流程要求 MATLAB/SPM/CONN 环境与对应项目设计；当前未配置。Nilearn 同名操作不能充当 CONN 算法。','MATLAB / SPM / CONN','原项目设计')
    if op in {'eeg-preprocessing','meg-processing'}:
        return mapped(choices('meg-skill' if op=='meg-processing' else 'eeg-skill'),
                      '选择原文委托的具体 EEG/MEG 方法；未修复的原端到端清理组合仍不可执行。')
    if 'xcp-d' in op or 'full-adni' in op:
        return blocked('missing_runtime','XCP-D（以及组合中的 fMRIPrep）未安装；普通滤波/回归不能替代 XCP-D 的既定完整协议。','XCP-D','fMRIPrep derivatives')
    if op=='atlas-alignment-to-t1w-mni152':
        return mapped([preset('image.registration','fsl_flirt',{'interpolation':'nearestneighbour'}),
                       preset('skill.fsl-tool','reviewed-applywarp-fsl-tool',{'interp':'nearest'})],
                       '明确选择配准或应用已有形变；离散标签使用最近邻，不自动增加上游配准。')
    if sk=='scan-skill':
        if op=='inventory-approved-export': return mapped([preset('dwi.inspect','dataset_inspector',{'compute_checksums':True})])
        if op=='convert-approved-dicom': return direct('skill.dcm2nii','dcm2niix-convert')
        if op=='asl-perfusion-processing': return direct('skill.asl-skill','compute-cbf')
        if op=='amyloid-tau-or-fdg-pet-processing': return direct('skill.pet-skill','compute-suvr')
    if op=='site-harmonization':
        return mapped(choices('harmonization-tool'))
    if sk=='scan-skill' and op=='join-nacc-phenotype-tables':
        return direct('skill.scan-skill','reviewed-table-join-scan-skill')
    if sk=='hcpa-skill' and op=='asl-processing':
        return direct('skill.asl-skill','compute-cbf')
    return blocked('needs_protocol','该条目前只有高层研究/流程说明，没有确定完整调用所需的设计、模型或输入输出约定；已实现的独立方法仍保留可选。','核对原 Skill 中此操作的具体执行协议：'+m.label)


def build():
    records=[]
    for capability, methods in CATALOG.items():
        for method in methods:
            if method.execution_mode!='planning': continue
            records.append(dict(capability=capability,method_id=method.method_id,skill_id=method.skill_id,
                source_fingerprint=source_fingerprint(method),source_references=[r.model_dump(mode='json') for r in method.source_references],
                **resolve(method)))
    return dict(schema_version=1,methods=records)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    path=ROOT/'bakend/resources/planning_resolution.json'
    payload=build()
    if args.check:
        if not path.is_file() or json.loads(path.read_text(encoding='utf-8'))!=payload:
            raise SystemExit('Planning resolution differs from reviewed source; review and regenerate it.')
    else:
        path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from collections import Counter
    print(dict(Counter(m['state'] for m in payload['methods'])))
