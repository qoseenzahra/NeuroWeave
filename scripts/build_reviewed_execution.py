"""Build explicit execution manifests from reviewed implementations, never shell examples."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
import pathlib
import re
from parameter_documentation import enrich as enrich_parameter_documentation

ROOT = pathlib.Path(__file__).resolve().parents[1]
METHODS = []
SOURCES = json.loads((ROOT/'bakend/resources/existing_implementation_sources.json').read_text(encoding='utf-8'))['files']

# These are existing callable APIs, not algorithm names inferred from a Skill.
EEG_APIS = {
    'inspect': [('mne.io','read_raw_fif'), ('mne.io','read_raw_edf'), ('mne.io','read_raw_bdf'), ('mne.io','read_raw_eeglab')],
    'bad-channels': [('mne.preprocessing','find_bad_channels_lof'), ('mne.io','BaseRaw.interpolate_bads')],
    'filter': [('mne.io','BaseRaw.filter'), ('mne.io','BaseRaw.notch_filter'), ('mne.io','BaseRaw.resample')],
    'ica': [('mne.preprocessing','ICA.fit'), ('mne.preprocessing','ICA.apply'), ('mne.preprocessing','ICA.find_bads_eog'), ('mne.preprocessing','ICA.find_bads_ecg')],
    'epoch': [('mne','Epochs'), ('mne','make_fixed_length_epochs')],
    'autoreject': [('autoreject','AutoReject.fit_transform')],
    'connectivity': [('mne_connectivity','spectral_connectivity_epochs')],
    'time-frequency': [('mne','Epochs.compute_tfr')],
    'maxwell': [('mne.preprocessing','maxwell_filter')],
    'source': [('mne.minimum_norm','make_inverse_operator'), ('mne.minimum_norm','apply_inverse_raw')],
}


def implementation_source(spec):
    script = spec['script']
    operation = spec['fixed_args'][1] if spec['fixed_args'][:1] == ['--operation'] else None
    apis = []
    if script.endswith('/eeg_worker.py'):
        apis = EEG_APIS[operation]
        origin = dict(kind='library_api', entrypoints=['.'.join(api) for api in apis])
    elif script.endswith('/image_summary_worker.py'):
        apis = {'inspect': [('nibabel','load'), ('nibabel','aff2axcodes')],
                'save': [('nibabel','load'), ('nibabel','save')],
                'surface': [('nibabel.freesurfer','read_geometry'), ('nibabel.freesurfer','read_annot')]}[operation]
        origin = dict(kind='library_api', entrypoints=['.'.join(api) for api in apis])
    elif script.endswith('/evoked_worker.py'):
        apis = [('mne','read_epochs'), ('mne','Epochs.average'), ('mne','Evoked.save')]
        origin = dict(kind='library_api', entrypoints=['.'.join(api) for api in apis])
    elif script.endswith('/bids_mapping_worker.py'):
        apis = [('json','dump'), ('shutil','copyfile')]
        if operation == 'stage':
            apis.append(('bids_validator','BIDSValidator.is_bids'))
        origin = dict(kind='library_api', entrypoints=['.'.join(api) for api in apis])
    elif script.endswith('/table_inspection_worker.py'):
        apis = [('pandas','read_csv'), ('pandas','DataFrame.merge' if operation=='join' else 'DataFrame.duplicated')]
        origin = dict(kind='library_api', entrypoints=['.'.join(api) for api in apis])
    elif script.endswith(('/native_worker.py', '/planning_native_worker.py')):
        origin = dict(kind='software_command', entrypoints=spec['executables'])
    elif spec.get('original_entrypoint'):
        original = spec['original_entrypoint']
        origin = dict(kind='existing_project_script', entrypoints=[original], source=SOURCES[original])
        apis = spec.get('original_required_apis', [])
    else:
        if script not in SOURCES:
            raise ValueError('No existing implementation source: '+script)
        origin = dict(kind='existing_project_script', entrypoints=[script], source=SOURCES[script])
    origin['dependencies'] = {name: SOURCES[name] for name in spec['required_files']}
    origin['adapter_scope'] = 'Existing calls, argument/input validation, scheduling and output collection only; no replacement algorithm.'
    spec['required_apis'] = apis
    spec['implementation_source'] = origin
    spec['implementation_files'] = [{
        'path': name,
        'sha256': hashlib.sha256((ROOT/name).read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest(),
    } for name in [script, *spec['required_files']]]


def inp(name, label=None, required=True, folder=False, path_list=False, flag=None, many_args=False):
    return dict(id=name.replace('-', '_'), flag=flag or '--'+name, label=label or name,
                required=required, binding='folder' if folder else 'file', type='analysis_input', path_list=path_list, many_args=many_args)


def param(name, default=None, kind='string', choices=(), minimum=None, maximum=None, required=True, **kw):
    return dict(id=name.replace('-', '_'), flag=kw.pop('flag', '--'+name), argument=name, label=kw.pop('label', name),
                type=kind, default=default, required=required, options=[dict(value=x,label=str(x)) for x in choices],
                minimum=minimum, maximum=maximum, **kw)


def add(skill, name, label, script, inputs, parameters=(), *, modules=('numpy','pandas','nibabel','nilearn'),
        expected=(), aliases=(), profile='scientific', fixed=(), outputs=(('--output-dir','.'),),
        operations=(), required_files=(), executables=()):
    spec=dict(runner_id='reviewed.'+skill+'.'+name, skill_id=skill, method_id='reviewed-'+name,
              label=label, script=script, inputs=list(inputs), parameters=list(parameters), modules=list(modules),
              expected=list(expected), profile=profile, fixed_args=list(fixed), outputs=list(outputs),
              aliases=list(aliases), replaces_operations=list(operations), required_files=list(required_files),
              executables=list(executables))
    METHODS.append(spec)
    return spec


def scientific():
    base='skills/nilearn-tool/scripts/'
    tr=param('tr',2.0,'number',minimum=0.01,maximum=100,label='TR（秒）')
    mask=inp('mask','脑掩膜',False)
    bold=inp('bold','预处理 BOLD 影像')
    lists=inp('input-list','影像路径清单',path_list=True)
    out=lambda name:base+name+'_reference.py'
    add('nilearn-tool','denoise','混杂回归与去趋势',out('denoise_timeseries'),
        [bold,inp('confounds','混杂变量表',False),mask], [tr,param('detrend',True,'boolean'),param('no-standardize',False,'boolean')],
        expected=['cleaned_bold.nii.gz'],aliases=['detrending'])
    add('nilearn-tool','preprocess','BOLD 平滑与时间滤波（保持原空间）',out('preprocess_bold'),[bold],
        [tr,param('fwhm',6.0,'number',minimum=0,maximum=30),param('high-pass',0.01,'number',minimum=0.00001,maximum=1),param('low-pass',0.1,'number',minimum=0.001,maximum=1),param('n-dummies',0,'integer',minimum=0,maximum=100)],
        aliases=['filtering'],outputs=[['--output','preprocessed_bold.nii.gz']],expected=['preprocessed_bold.nii.gz'])
    add('nilearn-tool','connectome','ROI 时间序列与功能连接',out('connectome'),[bold,inp('atlas','分区图谱'),inp('labels','图谱标签',False)],
        [tr],expected=['connectome.npy','roi_timeseries.csv'],aliases=['fmri-skill'],operations=['roi-time-series-extraction','functional-connectivity-clean'])
    add('nilearn-tool','task-glm','任务态一级 GLM',out('task_glm'),[bold,inp('events','事件表'),inp('confounds','混杂变量',False),mask],
        [tr,param('contrast',None,label='对比表达式')],expected=['z_map.nii.gz','effect_map.nii.gz'],aliases=['glm','fmri-skill'],operations=['first-level-glm-task-based'])
    add('nilearn-tool','group-glm','组水平 GLM',out('second_level_glm'),[inp('contrast-maps','对比影像路径清单',path_list=True),inp('design-matrix','组设计矩阵'),mask],
        [param('contrast',None,label='对比表达式')],expected=['second_level_z_map.nii.gz'],aliases=['glm','fmri-skill'],operations=['group-level-analysis'])
    for name,alias in [('rest_ica','ica'),('rest_dictlearning','dictlearning')]:
        add('nilearn-tool',alias,'静息态 '+alias.upper(),out(name),[lists,mask],
            [param('n-components',10,'integer',minimum=2,maximum=200)],expected=['components.nii.gz'],aliases=[alias])
    for name in ('kmeans','hierarchical'):
        add('nilearn-tool',name,name+' 空间分区',out(name+'_parcellation'),[lists,inp('mask','脑掩膜')],
            [param('n-clusters',10,'integer',minimum=2,maximum=1000)],expected=['parcel_labels.nii.gz'],aliases=[name])
    add('nilearn-tool','svm','SVM 分类与交叉验证',out('svm_classifier'),[inp('features','特征表'),inp('labels','标签表')],
        [param('target',None,label='目标列'),param('cv',5,'integer',minimum=2,maximum=20)],expected=['metrics.csv','predictions.csv'],modules=['numpy','pandas','sklearn'])
    add('nilearn-tool','spacenet','SpaceNet 空间正则分类',out('spacenet_classifier'),[lists,inp('labels','标签表'),inp('mask','脑掩膜')],
        [param('target',None,label='目标列')],expected=['coef_map.nii.gz'],aliases=['spacenet'])
    add('brain-visualization','connectome','脑连接图', 'skills/brain-visualization/scripts/connectome_reference.py',
        [inp('atlas','分区图谱'),inp('template','背景模板'),inp('matrix','连接矩阵')],
        [param('top-k',20,'integer',minimum=0,maximum=100000),param('node-size',30,'integer',minimum=1,maximum=1000),param('brain-opacity',0.2,'number',minimum=0,maximum=1)],
        outputs=[['--output','connectome.png']],expected=['connectome.png'],operations=['3d-connectome-figure','publication-ready-snapshots'])
    add('brain-visualization','surface-ply','FreeSurfer 表面导出 PLY','skills/brain-visualization/scripts/freesurfer_ply_reference.py',
        [inp('surf','FreeSurfer 表面'),inp('annot','分区标注',False)],modules=['numpy','nibabel'],outputs=[['--output','surface.ply']],expected=['surface.ply'],operations=['freesurfer-surface-export'])
    add('dipy-tool','mask','DWI 载入与脑掩膜','skills/dipy-tool/scripts/load_and_mask_reference.py',
        [inp('dwi','DWI'),inp('bval','bval'),inp('bvec','bvec')],[param('b0-threshold',50,'number',minimum=0,maximum=500)],
        modules=['numpy','nibabel','dipy'],expected=['brain_mask.nii.gz'],operations=['load-dwi-gradients','brain-mask'])
    add('dipy-tool','roi-stats','分区影像统计','skills/dipy-tool/scripts/roi_stats_reference.py',
        [inp('metric','标量影像'),inp('roi','分区图谱'),inp('labels','标签表',False)],
        [param('min-voxels',1,'integer',minimum=1,maximum=100000)],outputs=[['--output','roi_stats.csv']],expected=['roi_stats.csv'],
        aliases=['dwi-skill','smri-skill'],operations=['roi-stats','roi-wise-diffusion-features','roi-wise-feature-extraction'])
    add('nibabel-skill','atlas-coordinates','图谱坐标提取','skills/nibabel-skill/scripts/atlas_coordinate_reference.py',
        [inp('atlas','分区图谱'),inp('labels','图谱标签文本')],outputs=[['--output','coordinates.csv']],expected=['coordinates.csv'],operations=['atlas-coordinate-extraction'])


def learning():
    common=[param('folds',5,'integer',minimum=2,maximum=20),param('seed',123,'integer',minimum=0,maximum=2147483647),param('subject-col','subject_id')]
    features=inp('features','特征 CSV')
    script=lambda skill:'skills/'+skill+'/scripts/train_reference.py'
    basic=['numpy','pandas','scipy','sklearn','joblib']
    for task, models in [('classification',['logistic','ridge','elastic_net','svm','random_forest','extra_trees','hist_gradient_boosting','xgboost']),
                         ('regression',['ols','ridge','elastic_net','svm','random_forest','extra_trees','hist_gradient_boosting','xgboost'])]:
        add('statistical-ml',task,'统计学习：'+('分类' if task=='classification' else '回归'),script('statistical-ml'),[features],
            [param('operation',models[0],choices=models,flag='--model',label='模型'),param('target',None,label='目标列'),param('group-col',None,required=False),*common],
            modules=[*basic,'xgboost'],fixed=['--task',task],expected=['metrics.json','predictions.csv'],required_files=['models/statistical_ml/train.py'])
    add('cpm','train','连接组预测模型 CPM',script('cpm'),[inp('connectomes','NPZ 连接矩阵（X、subject_id）'),inp('labels','标签 CSV')],
        [param('task','regression',choices=['regression','classification']),param('target',None,label='目标列'),param('p-threshold',0.01,'number',minimum=0.000001,maximum=1),*common],
        modules=basic,expected=['metrics.json','predictions.csv'],required_files=['models/cpm/train.py'])
    add('brain-age-modeling','train','脑龄预测与偏差校正',script('brain-age-modeling'),[features],
        [param('model','ridge',choices=['ridge','svm','random_forest','extra_trees','hist_gradient_boosting']),param('age-col','age'),*common],
        modules=basic,expected=['metrics.json','predictions.csv'],required_files=['models/brain_age/train.py'])
    add('subject-subtyping','cluster','受试者分型',script('subject-subtyping'),[features],
        [param('operation','kmeans',choices=['kmeans','gmm','spectral','nmf','consensus'],flag='--model',label='分型方法'),param('n-clusters',2,'integer',minimum=2,maximum=100),param('subject-col','subject_id'),param('seed',123,'integer',minimum=0,maximum=2147483647)],
        modules=basic,expected=['metrics.json'],required_files=['models/subtyping/train.py'])
    add('imaging-genetics-models','association','影像遗传关联',script('imaging-genetics-models'),[inp('input','NPZ 矩阵数据')],
        [param('operation','association',choices=['association','lmm','prs','cca','pls'],flag='--model',label='关联方法'),param('components',2,'integer',minimum=1,maximum=100)],
        modules=basic,expected=['metrics.json'],required_files=['models/imaging_genetics/train.py'])
    for skill,models,extra in [('temporal-models',['lstm','gru','tcn','transformer'],[param('hidden-dim',32,'integer',minimum=4,maximum=512),param('layers',1,'integer',minimum=1,maximum=8)]),
                               ('cnn3d',[],[param('base-channels',8,'integer',minimum=2,maximum=64)])]:
        parameters=[param('task','classification',choices=['classification','regression']),param('epochs',20,'integer',minimum=1,maximum=1000),param('batch-size',4,'integer',minimum=1,maximum=256),param('lr',0.001,'number',minimum=0.000001,maximum=0.1),param('device','auto',choices=['auto','cpu','cuda']),*common[:2],*extra]
        if models: parameters.insert(0,param('operation','gru',choices=models,flag='--model',label='时序模型'))
        add(skill,'train','时序模型训练' if models else '3D CNN 训练',script(skill),[inp('input','NPZ 训练数据（X、y）')],parameters,
            modules=[*basic,'torch'],profile='torch',expected=['metrics.json','predictions.csv'],required_files=['models/'+('temporal_models' if models else 'cnn3d')+'/train.py'])


def more_learning():
    basic=['numpy','pandas','scipy','sklearn','joblib']
    common=[param('folds',5,'integer',minimum=2,maximum=20),param('seed',123,'integer',minimum=0,maximum=2147483647),param('subject-col','subject_id')]
    features=inp('features','特征 CSV')
    for models,profile,modules in [(['cox','rsf','xgb_cox'],'scientific',basic+['statsmodels','sksurv','xgboost']),(['deepsurv'],'torch',basic+['torch'])]:
        add('survival-models','survival-'+profile,'生存模型（'+profile+'）','skills/survival-models/scripts/train_reference.py',[features],
            [param('operation',models[0],choices=models,flag='--model',label='生存模型'),param('duration-col',None,label='随访时间列'),param('event-col',None,label='事件列'),
             param('epochs',50,'integer',minimum=1,maximum=1000),param('device','auto',choices=['auto','cpu','cuda']),*common],
            modules=modules,profile=profile,expected=['metrics.json','predictions.csv'],required_files=['models/survival_models/train.py'])
    add('causal-treatment-models','cate','处理效应估计','skills/causal-treatment-models/scripts/train_reference.py',[features],
        [param('operation','t_learner',choices=['ipw','s_learner','t_learner','x_learner','doubly_robust','policy_learner','tarnet','dragonnet'],flag='--model',label='效应估计方法'),
         param('treatment-col',None,label='处理列（0/1）'),param('outcome-col',None,label='结局列'),param('epochs',50,'integer',minimum=1,maximum=1000),param('device','auto',choices=['auto','cpu','cuda']),*common],
        modules=basic+['torch'],profile='torch',expected=['metrics.json','predictions.csv'],required_files=['models/causal_treatment/train.py'])
    script='skills/neuroimaging-decoding/scripts/train_reference.py'
    add('neuroimaging-decoding','mvpa','ROI 多变量解码',script,[features],
        [param('task','classification',choices=['classification','regression']),param('target',None,label='目标列'),param('model','svm',choices=['svm','ridge','random_forest']),*common],
        fixed=['--mode','mvpa'],modules=basic+['nilearn'],expected=['metrics.json','predictions.csv'])
    add('neuroimaging-decoding','roi-glm','ROI GLM 与 FDR',script,[features,inp('design','设计矩阵 CSV')],
        [param('subject-col','subject_id'),param('contrast-index',1,'integer',minimum=0,maximum=100)],fixed=['--mode','roi-glm'],modules=basic+['statsmodels','nilearn'],expected=['roi_glm_results.csv'])
    add('neuroimaging-decoding','searchlight','SearchLight 分类',script,[inp('images-list','影像路径清单',path_list=True),features,inp('mask','脑掩膜')],
        [param('target',None,label='标签列'),*common[:2]],fixed=['--mode','searchlight'],modules=basic+['nilearn'],expected=['searchlight_scores.nii.gz'])
    add('harmonization-tool','site-covar','站点协变量校正','skills/harmonization-tool/scripts/harmonize.py',
        [inp('features','NPY 特征矩阵'),inp('meta','样本协变量 CSV')],
        [param('batch','site'),param('protected','age,sex',split=True),param('split','site-stratified',choices=['none','site-stratified','leave-site-out']),param('seed',123,'integer',minimum=0,maximum=2147483647)],
        fixed=['--method','site-covar'],outputs=[['--out','.']],modules=basic,expected=['harmonized_features.npy','manifest.json'],operations=['site-covar'],aliases=['rest-mneta-mdd-skill'])
    add('ukb-skill','survival-dataset','UKB 生存分析数据表','skills/ukb-skill/scripts/build_ukb_survival.py',[inp('input','UKB 原始表')],
        [param('disease',None,label='疾病名称/ICD 前缀'),param('censor-date','2023-10-31'),param('baseline-col','p53_i0')],
        modules=['numpy','pandas'],outputs=[['--output','survival.csv']],expected=['survival.csv'],operations=['survival-dataset'])
    for name,label in [('analyze_lesions','病灶负荷统计'),('longitudinal_lesion','纵向病灶变化')]:
        add('mschallenge-skill',name.replace('_','-'),label,'skills/mschallenge-skill/scripts/'+name+'.py',[inp('input','病灶影像目录',folder=True)],
            modules=['numpy','pandas','nibabel','scipy'],outputs=[['--output','lesions.csv']],expected=['lesions.csv'],operations=['lesion-analysis'] if name=='analyze_lesions' else ['longitudinal-analysis'])


def native():
    base='bakend/app/execution/native_worker.py'
    software={'bet':'bet','fast':'fast','mcflirt':'mcflirt','slicetimer':'slicetimer','fnirt':'fnirt','applywarp':'applywarp'}
    for op in [*software,'dwidenoise','mrdegibbs','mrconvert','dwibiascorrect','dwifslpreproc','ants-apply']:
        inputs=[inp('input','输入影像')]; params=[]
        family='fsl-tool' if op in software else 'smri-skill' if op=='ants-apply' else 'dwi-skill'
        programs=[('/opt/software/fsl/bin/' if op in software else '/opt/software/ants-2.6.5/bin/' if op=='ants-apply' else '/opt/software/mrtrix3-master/bin/')+('antsApplyTransforms' if op=='ants-apply' else op)]
        if op=='bet':params=[param('fraction',.5,'number',minimum=.01,maximum=.99)]
        if op=='fast':params=[param('classes',3,'integer',minimum=2,maximum=6)]
        if op=='slicetimer':params=[param('tr',2.,'number',minimum=.01,maximum=100),param('slice-axis',3,'integer',choices=[1,2,3]),param('slice-order','ascending',choices=['ascending','descending','interleaved'])]
        if op in {'fnirt','applywarp','ants-apply'}:
            inputs+=[inp('reference','参考影像'),inp('transform','变换/形变场',op!='fnirt')]
            if op!='fnirt':params.append(param('interp','linear',choices=['linear','nearest']))
        if op in {'dwidenoise','mrdegibbs','mrconvert','dwibiascorrect','dwifslpreproc'}:
            inputs+=[inp('bval','bval',op in {'dwibiascorrect','dwifslpreproc'}),inp('bvec','bvec',op in {'dwibiascorrect','dwifslpreproc'})]
        if op=='dwifslpreproc':params+=[param('pe-dir','AP',choices=['AP','PA','LR','RL','IS','SI']),param('readout',.05,'number',minimum=.00001,maximum=1)]
        if op=='dwibiascorrect':programs+=['/opt/software/ants-2.6.5/bin/N4BiasFieldCorrection']
        if op=='dwifslpreproc':programs+=['/opt/software/fsl/bin/eddy_cpu']
        aliases=['smri-skill'] if op in {'bet','fast','fnirt','applywarp'} else ['fmri-skill'] if op in {'mcflirt','slicetimer'} else []
        add(family,op,{'bet':'FSL 脑提取','fast':'FSL 组织分割','mcflirt':'FSL 运动校正','slicetimer':'FSL 层间时间校正','fnirt':'FSL 非线性配准','applywarp':'FSL 应用形变','dwidenoise':'MRtrix MP-PCA 去噪','mrdegibbs':'MRtrix Gibbs 校正','mrconvert':'MRtrix 格式转换','dwibiascorrect':'MRtrix/ANTs 偏置场校正','dwifslpreproc':'MRtrix/FSL DWI 预处理（无反向相位编码）','ants-apply':'ANTs 应用变换'}[op],
            base,inputs,params,modules=[],fixed=['--operation',op],expected=['tissue_seg.nii.gz'] if op=='fast' else ['image.nii.gz','dwi.bval','dwi.bvec'] if op in {'dwibiascorrect','dwifslpreproc'} else ['image.nii.gz'],executables=programs,aliases=aliases)


def eeg():
    mapping={
        'inspect':('EEG/MEG 数据检查',['loadeeg','load-validation','load-basic-validation']),
        'bad-channels':('MNE LOF 坏导联检测与插值',[]),
        'filter':('EEG/MEG 滤波与降采样',['preprocessfiltering','downsampling-filtering','filtering']),
        'ica':('MNE ICA 分解与指定成分去除',[]),
        'epoch':('重参考与分段',['rereferenceandepoch','re-referencing-epoching','epoching']),
        'autoreject':('Epoch AutoReject 自动质控',[]),
        'connectivity':('传感器 PLV/相干/wPLI',['computeconnectivity','sensor-level-connectivity']),
        'time-frequency':('Morlet 时频功率与 ITC',['time-frequency-analysis']),
        'maxwell':('MEG Maxwell 滤波',['maxwell-filtering']),
        'source':('dSPM 源定位（需前向模型和噪声协方差）',['source-localization']),
    }
    for operation,(label,operations) in mapping.items():
        inputs=[inp('input','EEG/MEG 原始文件（FIF/EDF/BDF/SET）')]
        parameters=[]
        if operation == 'filter':
            parameters.extend([param('high-pass',.5,'number',minimum=0,maximum=100),param('low-pass',40.,'number',minimum=1,maximum=1000),param('notch',0.,'number',minimum=0,maximum=120),param('sfreq',0.,'number',minimum=0,maximum=10000)])
        if operation == 'ica':
            parameters.extend([param('components',10,'integer',minimum=2,maximum=200),param('exclude-components','',required=False)])
        if operation in {'epoch','autoreject','connectivity','time-frequency'}:
            inputs.append(inp('events','MNE 事件文件',False))
            parameters.extend([param('epoch-seconds',2.,'number',minimum=.1,maximum=60),param('tmin',-.2,'number',minimum=-10,maximum=0),param('tmax',.8,'number',minimum=.01,maximum=60)])
        if operation in {'connectivity','time-frequency'}:
            parameters.extend([param('freq-min',8.,'number',minimum=.1,maximum=1000),param('freq-max',13.,'number',minimum=.2,maximum=2000)])
        if operation=='source': inputs.extend([inp('forward','前向模型 FIF'),inp('noise-cov','噪声协方差 FIF')])
        expected={'inspect':'processed-raw.fif','bad-channels':'processed-raw.fif','filter':'processed-raw.fif','ica':'processed-raw.fif',
                  'epoch':'processed-epo.fif','autoreject':'processed-epo.fif','connectivity':'connectivity.npz',
                  'time-frequency':'time_frequency.npz','maxwell':'processed-raw.fif','source':'source.npz'}[operation]
        modules=['numpy','mne']
        if operation=='autoreject': modules.append('autoreject')
        if operation=='connectivity': modules.append('mne_connectivity')
        add('mne-eeg-tool',operation,label,'bakend/app/execution/eeg_worker.py',inputs,parameters,modules=modules,
            fixed=['--operation',operation],expected=[expected],aliases=['eeg-skill','meg-skill'] if operation not in {'bad-channels'} else ['eeg-skill'],operations=operations)


def auxiliary():
    add('kg-link-prediction','complex','ComplEx 知识图谱链路预测','skills/kg-link-prediction/scripts/train_reference.py',[inp('kg','知识图谱 JSON（concepts、edges）')],
        [param('epochs',50,'integer',minimum=1,maximum=1000),param('embedding-dim',64,'integer',minimum=4,maximum=512),param('negatives',5,'integer',minimum=1,maximum=100),
         param('device','auto',choices=['auto','cpu','cuda']),param('seed',123,'integer',minimum=0,maximum=2147483647)],
        fixed=['--model','complex'],profile='torch',modules=['torch','numpy','pandas','sklearn'],expected=['metrics.json','checkpoint.pt'],required_files=['models/kg_link_prediction/vendor/complex_scorer.py'])
    image='bakend/app/execution/image_summary_worker.py'
    add('nibabel-skill','inspect','NIfTI 头信息与空间检查',image,[inp('image','NIfTI')],fixed=['--operation','inspect'],modules=['numpy','pandas','nibabel','scipy'],expected=['inspection.json'],operations=['nifti-inspection'])
    add('nibabel-skill','surface','FreeSurfer 表面与分区读取',image,[inp('surf','表面'),inp('annot','标注')],fixed=['--operation','surface'],modules=['numpy','pandas','nibabel','scipy'],expected=['surface.npz'],operations=['freesurfer-io'])
    for skill in ['seed-iv-skill','seed-vig-skill']:
        short=skill.removesuffix('-skill').replace('-','_')
        add(skill,'features','SEED 频带特征提取','skills/'+skill+'/scripts/extract_'+short+'_features.py',[inp('input','EEG 数据目录',folder=True)],
            [param('epoch-duration',4.,'number',minimum=.5,maximum=60)],fixed=['--feature-type','both'],modules=['numpy','pandas','scipy','mne'],
            outputs=[['--output','.']],expected=[short+'_features_both.csv'],operations=['feature-extraction'])
        add(skill,'classify','SEED 按受试者留一交叉验证','skills/'+skill+'/scripts/classify_'+short+'.py',[inp('input','特征与标签 CSV')],
            [param('method','both',choices=['svm','rf','both'])],modules=['numpy','pandas','sklearn'],outputs=[['--output','metrics.json']],expected=['metrics.json'],operations=['classification','vigilance-classification','emotion-classification'])


def dataset_scripts():
    # Reviewed standalone table/QC/validation scripts only. No in-place ADNI conversion,
    # network fetchers, model-generated commands, or destructive reorganization.
    files=[]
    for directory in sorted((ROOT/'skills').glob('*-skill')):
        for path in sorted((directory/'scripts').glob('*.py')):
            if path.name.startswith(('extract_','validate_','reorganize_')) or path.name.endswith('_qc_summary.py'):
                if directory.name != 'adni-skill' and not ('seed' in directory.name and path.name.startswith('extract_')):
                    files.append(path)
    files += [ROOT/'skills/beautiful-log/scripts/beautiful_log.py']
    input_names={'input','root','phenotype','phenotype-dir','phenotype-file','phenotype-files','imaging-ids','fmriprep-dir','freesurfer-dir','raw-qc','stimulus-dir','events-dir','custom-mapping','data-dir','bids-dir','manifest','participants','participants-file','subjects-file','labels-file','nsd-dir','coco-dir'}
    output_names={'output','exclude-output','manifest-output'}
    folder_names={'root','phenotype-dir','fmriprep-dir','freesurfer-dir','stimulus-dir','events-dir','data-dir','bids-dir','nsd-dir','coco-dir'}
    for path in files:
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        inputs=[]; parameters=[]; outputs=[]; unknown=[]; reorganize=path.name.startswith('reorganize_')
        for call in ast.walk(tree):
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute) or call.func.attr!='add_argument': continue
            try:
                flags=[ast.literal_eval(x) for x in call.args]
                flag=next(x for x in flags if x.startswith('--')); name=flag[2:]
                values={k.arg:ast.literal_eval(k.value) for k in call.keywords if k.arg not in {'type'} and isinstance(k.value,(ast.Constant,ast.List,ast.Tuple))}
            except (ValueError,StopIteration): continue
            required=values.get('required',False)
            if name in input_names:
                if values.get('nargs') in ('+','*'):
                    inputs.append(inp(name,'文件路径清单（每行一项）',required,path_list=True,many_args=True)); continue
                if reorganize and name=='participants':
                    # Subject-list values are used as path components by HCP scripts.
                    # Prefer their automatic subject discovery in the platform contract.
                    continue
                inputs.append(inp(name,values.get('help',name),required,folder=name in folder_names or (name=='input' and (reorganize or path.name.startswith('validate_') or path.name=='mschallenge_qc_summary.py'))))
            elif name in output_names:
                suffix='html' if path.parent.parent.name=='beautiful-log' else 'json' if path.name.startswith('validate_') and 'json.dump' in path.read_text(encoding='utf-8') else 'csv'
                outputs.append([flag,('bids' if name=='output' else 'manifest.tsv') if reorganize else name.replace('-','_')+'.'+suffix])
            elif values.get('action') in ('store_true','store_false'):
                if reorganize:continue
                # Validation flags have no mutating side effects.
                parameters.append(param(name,values.get('default',False),'boolean',required=False,flag_when=values.get('action')=='store_true'))
            else:
                kind=next((k.value.id for k in call.keywords if k.arg=='type' and isinstance(k.value,ast.Name)), 'str')
                default=values.get('default')
                if kind in ('Path',): unknown.append(name); continue
                parameters.append(param(name,default,{'int':'integer','float':'number'}.get(kind,'string'),choices=values.get('choices',()),required=required,
                                        minimum=0 if kind in ('int','float') else None,maximum=1000000 if kind in ('int','float') else None,
                                        split=values.get('nargs') in ('+','*')))
        if unknown or not outputs or not inputs: continue
        skill=path.parent.parent.name
        name=path.stem.replace('_','-')
        label=skill.replace('-skill','')+' '+('复制整理为 BIDS 目录' if reorganize else '质控汇总' if 'qc_summary' in path.name else '数据校验' if path.name.startswith('validate') else '表型/刺激提取' if path.name.startswith('extract') else '日志报告')
        add(skill,name,label,path.relative_to(ROOT).as_posix(),inputs,parameters,modules=['pandas','numpy'],outputs=outputs,
            fixed=['--copy'] if reorganize and skill=='aomic-skill' else [],
            expected=['bids/**/*.nii*'] if reorganize else [outputs[0][1]],operations=['bids-reorganization','data-reorganization'] if reorganize else ['qc-summary'] if 'qc_summary' in path.name else ['bids-validation','data-validation','eeg-validation'] if path.name.startswith('validate') else ['phenotype-extraction','stimulus-extraction'])


def emit():
    manifests={}
    for spec in METHODS:
        enrich_parameter_documentation(spec, ROOT)
        implementation_source(spec)
        if spec['skill_id'] in {'statistical-ml','cpm','brain-age-modeling','subject-subtyping','imaging-genetics-models','temporal-models','cnn3d','survival-models','causal-treatment-models','brainnetcnn','bnt','combraintf','neuroimaging-decoding'}:
            spec['aliases'].append('run_models')
        for item in spec['inputs']:
            item['type']=spec.get('input_artifact_types',{}).get(item['id']) or {'bold':'bold_image','atlas':'label_image','roi':'label_image','mask':'brain_mask',
                          'dwi':'preprocessed_dwi','bval':'b_values','bvec':'b_vectors'}.get(item['id'],'analysis_input')
        spec['artifact_types']={name:{'cleaned_bold.nii.gz':'bold_image','preprocessed_bold.nii.gz':'bold_image',
            'brain_mask.nii.gz':'brain_mask','z_map.nii.gz':'z_stat_map','effect_map.nii.gz':'contrast_image',
            'connectome.npy':'connectome_matrix','roi_timeseries.csv':'roi_timeseries'}.get(name,'generated_file') for name in spec['expected']}
        spec['artifact_types'].update(spec.get('output_artifact_types', {}))
        for skill in [spec['skill_id'],*spec['aliases']]:
            parameters=[{k:v for k,v in p.items() if k not in {'flag','flag_when','split'}} for p in spec['parameters']]
            inputs=[{k:v for k,v in p.items() if k not in {'flag','path_list','many_args'}} for p in spec['inputs']]
            method=dict(capability='skill.'+re.sub('[^a-z0-9]+','-',skill.lower()).strip('-'),method_id=spec['method_id']+'-'+spec['skill_id'],label=spec['label'],
                        description='调用现有实现：'+', '.join(spec['implementation_source']['entrypoints'])+'。输入保持只读，输出写入独立任务目录。',
                        runner_id=spec['runner_id'],execution_mode='runner',structure_level='reviewed',
                        parameters=parameters,input_slots=inputs,output_slots=[dict(id='results',type='generated_folder',label='分析结果',primary=True,path_template='results/')],
                        input_types=['analysis_input'],output_types=['generated_folder'],default_recommended=True,
                        replaces_operations=spec['replaces_operations'],
                        source_references=[dict(path=spec['script'],kind='script',label='现有实现调用入口',line_start=1),
                                           dict(path='bakend/resources/existing_implementation_sources.json',kind='script',label='实现来源与原始源码校验记录',line_start=1)])
            method['output_slots'].extend(dict(id='file_'+re.sub('[^a-zA-Z0-9_]+','_',name),type=spec['artifact_types'][name],label=name,path_template='results/'+name)
                for name in spec['expected'] if not any(c in name for c in '*?['))
            manifests.setdefault(skill,[]).append(method)
    # Expose existing trusted primitives under their owning Skill, so selecting
    # the Skill directly can reach the same implementation as a DWI workflow.
    extras={'dataset.inspect':['scan-skill','adni-skill','image-batch-processing'],
            'dcm2niix.convert':['scan-skill','adni-skill'],
            'freesurfer.recon_all':['smri-skill'],'bids.prepare':['scan-skill']}
    for path in sorted([*(ROOT/'skills').glob('*/tool.manifest.json'),*(ROOT/'skills').glob('*/execution.manifest.json')]):
        payload=json.loads(path.read_text(encoding='utf-8'))
        for original in payload.get('provides',[]):
            if original.get('execution_mode','runner')!='runner' or original['runner_id'].startswith('reviewed.') or original['method_id'].startswith('linked-'):continue
            destinations=[] if original['capability'].startswith('skill.') else [path.parent.name]
            destinations+=extras.get(original['runner_id'],[])
            for skill in destinations:
                method=copy.deepcopy(original)
                method.update(capability='skill.'+re.sub('[^a-z0-9]+','-',skill.lower()).strip('-'),method_id='linked-'+original['method_id'],default_recommended=False)
                manifests.setdefault(skill,[]).append(method)
    # Clean every previous generated manifest, including Skills that lost all
    # runners. Otherwise withdrawn methods survive a catalog regeneration.
    for path in (ROOT/'skills').glob('*/execution.manifest.json'):
        manifests.setdefault(path.parent.name, [])
    for skill,methods in manifests.items():
        path=ROOT/'skills'/skill/'execution.manifest.json'
        previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(schema_version=1,skill_id=skill,provides=[])
        previous['provides']=[m for m in previous['provides'] if not m['runner_id'].startswith('reviewed.') and not m['method_id'].startswith('linked-')]+methods
        if path.exists() and json.loads(path.read_text(encoding='utf-8')) == previous:
            continue
        path.write_text(json.dumps(previous,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'bakend/resources/reviewed_execution.json').write_text(json.dumps(dict(schema_version=1,methods=METHODS),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(METHODS)} reviewed implementations across {len(manifests)} skills')


if __name__=='__main__':
    import sys
    from planning_runtime_additions import register
    scientific(); learning(); more_learning(); native(); eeg(); auxiliary(); dataset_scripts()
    register(sys.modules[__name__])
    emit()
