"""Reviewed invocation contracts added while auditing the planning catalog."""
from pathlib import Path


def register(b):
    add, inp, param = b.add, b.inp, b.param
    native = 'bakend/app/execution/planning_native_worker.py'
    for op in ['inspect','join']:
        inputs=[inp('input','CSV/TSV 表格')]
        parameters=[]
        if op=='join':
            inputs.append(inp('right','右侧 CSV/TSV 表格'))
            parameters=[param('keys','subject_id',label='连接键（逗号分隔）'),
                param('how','left',choices=['left','inner','outer']),
                param('validate','one_to_one',choices=['one_to_one','many_to_one'])]
        add('dataset-inspector' if op=='inspect' else 'scan-skill','table-'+op,
            '表字段、缺失和主键候选检查' if op=='inspect' else '按显式键连接已批准的表格',
            'bakend/app/execution/table_inspection_worker.py',inputs,parameters,
            fixed=['--operation',op],modules=['pandas'],expected=['table_report.json']+(['joined.csv'] if op=='join' else []))
    fsl = '/opt/software/fsl/bin/'
    mr = '/opt/software/mrtrix3-master/bin/'
    spec = add('dwi-skill', 'sift-existing', 'MRtrix SIFT（筛选已有纤维）', native,
        [inp('input', '已有 tractogram'), inp('fod', '同空间白质 FOD'), inp('five-tt', '同空间 5TT', False)],
        [param('term-number', 1000, 'integer', minimum=1, maximum=100000000, label='保留纤维数量')],
        fixed=['--operation','sift'], modules=[], expected=['tracks.tck'], executables=[mr+'tcksift'])
    spec['input_artifact_types'] = {'input':'tractogram', 'fod':'fod_image', 'five_tt':'five_tt_image'}
    spec['output_artifact_types'] = {'tracks.tck':'tractogram'}
    add('fsl-tool', 'fsl-anat', 'FSL 完整结构预处理（fsl_anat）', native, [inp('input', 'T1w NIfTI')],
        fixed=['--operation','fsl-anat'], modules=[], expected=['structural.anat/T1_biascorr_brain.nii.gz'],
        executables=[fsl+x for x in ['fsl_anat','fsl_sub','fslreorient2std','robustfov','bet','fast','flirt','fnirt','run_first_all']],
        aliases=['smri-skill'])
    spec = add('dwi-skill', 'bedpostx', 'FSL BEDPOSTX 纤维方向采样', native,
        [inp('input', '预处理 DWI NIfTI'), inp('mask','脑掩膜'), inp('bval','bval'), inp('bvec','bvec')],
        [param('fibres',2,'integer',minimum=1,maximum=3), param('burnin',1000,'integer',minimum=0,maximum=100000),
         param('jumps',1250,'integer',minimum=25,maximum=100000),param('sample-every',25,'integer',minimum=1,maximum=1000)],
        fixed=['--operation','bedpostx'], modules=['nibabel'], expected=['data.bedpostX/merged_th1samples.nii.gz','data.bedpostX/merged_ph1samples.nii.gz','data.bedpostX/merged_f1samples.nii.gz'],
        executables=[fsl+x for x in ['bedpostx','fsl_sub','bedpostx_preproc.sh','bedpostx_single_slice.sh','bedpostx_postproc.sh','xfibres']],
        aliases=['fsl-tool'])
    spec['input_artifact_types'] = {'input':'preprocessed_dwi'}
    spec = add('dwi-skill','probtrackx-existing','FSL ProbtrackX（已有方向采样，输出纤维密度图）',native,
        [inp('samples','BEDPOSTX 结果目录',folder=True),inp('mask','脑掩膜'),inp('seed','种子掩膜')],
        [param('nsamples',5000,'integer',minimum=1,maximum=100000),param('nsteps',2000,'integer',minimum=1,maximum=100000),
         param('step-length',.5,'number',minimum=.01,maximum=10),param('curvature',.2,'number',minimum=0,maximum=1)],
        fixed=['--operation','probtrackx'],modules=[],expected=['fdt_paths.nii.gz','waytotal'],executables=[fsl+'probtrackx2'],aliases=['fsl-tool'])
    spec['input_artifact_types'] = {'samples':'generated_folder','seed':'seed_mask'}
    add('nibabel-skill','save-existing','NiBabel NIfTI 保存／格式转换','bakend/app/execution/image_summary_worker.py',
        [inp('image','已有影像')],fixed=['--operation','save'],modules=['nibabel','numpy'],expected=['image.nii.gz'])
    add('meg-skill','evoked-existing','MNE 已有 Epochs 平均诱发响应','bakend/app/execution/evoked_worker.py',
        [inp('input','已分段 Epochs FIF')],modules=['mne'],expected=['average-ave.fif'])
    for op in ['metadata','stage']:
        inputs = [inp('input','源数据集目录',folder=True)]
        if op=='stage':
            inputs += [inp('mapping','显式文件映射 JSON（源相对路径 → BIDS 相对路径）')]
        add('bids-organizer','explicit-'+op,
            'BIDS 元数据生成' if op=='metadata' else '按用户文件映射整理 BIDS（文件名检查）',
            'bakend/app/execution/bids_mapping_worker.py',inputs,[param('name','NeuroWeave dataset',label='数据集名称')],
            fixed=['--operation',op],modules=['bids_validator'] if op=='stage' else [],
            expected=['dataset_description.json','staging_report.json'])
    add('brain-visualization','original-region-summary','原脚本 BOLD 频带波动区域摘要（STD 指标）',
        'skills/brain-visualization/scripts/zalff_summary_reference.py',
        [inp('bold','原脚本所需 4D BOLD'),inp('atlas','同空间分区图谱'),inp('labels','图谱标签'),inp('mask','分析掩膜')],
        [param('tr',1.,'number',minimum=.01,maximum=100),param('top-n',10,'integer',minimum=1,maximum=10000)],
        modules=['numpy','nibabel','pandas','nilearn'],expected=['TOP_active_regions.csv','top_coordinates.csv','all_brain_regions_activity.csv'])

    original = 'skills/mne-eeg-tool/scripts/eeg_pipeline_reference.py'
    for op, label, output, extra, apis in [
        ('bands','原脚本 Welch 频带功率与分频文件','band_power.csv',[],[]),
        ('erp','原脚本 ERP 峰值、潜伏期与 AUC','erp_features.csv',[],[['numpy','trapezoid']]),
        ('alpha-ratio','原脚本 F3/F4 滤波后均值比值（非对数功率差）','alpha_asymmetry.npy',[],[]),
        ('features','原脚本 CSP、频带、Hjorth 与熵特征','features.npz',['pyentrp'],[['pyentrp.entropy','sample_entropy']]),
        ('microstates','原脚本 mne_microstates 分析','microstates.fif',['mne_microstates'],[['mne_microstates','Microstates']]),
    ]:
        spec = add('mne-eeg-tool','original-'+op,label,'bakend/app/execution/original_eeg_worker.py',
            [inp('input','Epochs FIF' if op in {'erp','features'} else '原始 EEG 文件')],
            fixed=['--operation',op],modules=['mne','numpy','pandas','scipy','mne_connectivity',*extra],
            expected=[output],required_files=[original])
        spec.update(original_entrypoint=original, original_required_apis=apis)

    for model in ['bnt','brainnetcnn','combraintf']:
        original = 'models/brainnetcnn/scripts/train.py' if model=='brainnetcnn' else 'skills/'+model+'/scripts/train_reference.py'
        files = [original, 'models/bnt/scripts/data_adapter.py', 'models/'+model+'/net/'+model+'.py']
        if model == 'combraintf':
            files += ['models/combraintf/scripts/data_adapter.py','models/bnt/net/bnt.py']
        # Only common arguments present in each original trainer are exposed here.
        parameters = [param('atlas', None, label='原始图谱目录名'),
            param('subject-col','subject_id'),param('label-col','label'),
            param('task','classification',choices=['classification','regression']),
            param('fold',0,'integer',minimum=0,maximum=99),param('kfold',5,'integer',minimum=2,maximum=100),
            param('seed',123,'integer',minimum=0,maximum=2147483647),
            param('n-epochs',50,'integer',minimum=1,maximum=10000),param('batch-size',8,'integer',minimum=1,maximum=2048),
            param('lr',.001,'number',minimum=.00000001,maximum=1),param('nclass',2,'integer',minimum=2,maximum=1000)]
        if model in {'bnt','combraintf'}:
            parameters += [param('nhead',4,'integer',minimum=1,maximum=64),param('dec-weight',.1,'number',minimum=0,maximum=100)]
        if model=='bnt':
            parameters += [param('pos-embed-dim',8,'integer',minimum=0,maximum=128)]
        if model=='combraintf':
            parameters += [param('hidden-size',512,'integer',minimum=4,maximum=4096),
                param('n-clusters',8,'integer',minimum=2,maximum=512),param('n-communities',None,'integer',minimum=1,maximum=100,required=False),
                param('wd',.0005,'number',minimum=0,maximum=1)]
        if model=='brainnetcnn':
            parameters += [param('device','auto',choices=['auto','cpu','cuda']),
                param('dropout',.5,'number',minimum=0,maximum=.99),param('weight-decay',.0001,'number',minimum=0,maximum=1)]
        spec = add(model,'original-trainer',model.upper()+' 原项目训练脚本', 'bakend/app/execution/original_training_worker.py',
            [inp('fmri-root','原始 FC 数据根目录（内含 atlas/sub-*.pt）',folder=True),inp('labels-csv','完整样本标签 CSV')],
            parameters,fixed=['--model',model],profile='torch',modules=['torch','numpy','pandas','sklearn'],
            expected=['training.log','execution.json'],required_files=list(dict.fromkeys(files)))
        spec['original_entrypoint'] = original

    # The original harmonization CLI already defines these alternatives. Missing
    # imports remain visible as runtime blockers and become ready after installation.
    from copy import deepcopy
    base = next(s for s in b.METHODS if s['runner_id']=='reviewed.harmonization-tool.site-covar')
    for name, modules in [('none',[]),('combat',['neuroCombat']),('combat-gam',['neuroHarmonize']),('covbat',['covbat'])]:
        spec = deepcopy(base)
        spec.update(runner_id='reviewed.harmonization-tool.'+name,method_id='reviewed-'+name,
                    label='原项目多站点校正：'+name,fixed_args=['--method',name],aliases=[],replaces_operations=[])
        spec['modules'] += modules
        b.METHODS.append(spec)
