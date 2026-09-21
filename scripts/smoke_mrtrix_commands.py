"""Run only tiny synthetic inputs in this isolated checkout; no dataset or Slurm access."""
from pathlib import Path
from threading import Event
import argparse,json,os,sys,subprocess
import numpy as np
import nibabel as nib
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--work-dir',type=Path,required=True,help='New empty directory for synthetic inputs, outputs and report')
args=parser.parse_args()
work=args.work_dir.resolve()
if work.exists() and any(work.iterdir()):raise SystemExit('Refusing to reuse a nonempty work directory')
work.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'bakend'))
from app.execution.runners.mrtrix_commands import command_runners
from app.execution.base import RunnerContext
from app.execution.runners.mrtrix import MrtrixTckgenRunner
from app.workflow_models import Workflow,WorkflowStep,InputBinding

data=work/'synthetic-inputs';data.mkdir(exist_ok=True)
os.environ['LOCALFLOW_RUN_INPUT_ROOTS']=str(data)
os.environ['LOCALFLOW_DATA_ROOTS']=str(data)
os.environ['SLURM_CPUS_PER_TASK']='1'
rng=np.random.default_rng(42)
def save(name,array):
    path=data/name;nib.save(nib.Nifti1Image(array.astype('float32'),np.eye(4)),path);return path
scalar=save('scalar.nii.gz',rng.uniform(0,1,(12,12,12)))
dwi=save('dwi.nii.gz',rng.normal(100,5,(8,8,8,30)))
five=np.zeros((12,12,12,5));five[...,0]=.5;five[...,2]=.5
five_path=save('five.nii.gz',five)
fod=np.zeros((12,12,12,6));fod[...,0]=1;fod_path=save('fod.nii.gz',fod)
tracks=data/'tracks.tck'
streamlines=[np.array([[x,3+i*.1,5] for x in np.linspace(2,9,20)],dtype='float32') for i in range(30)]
nib.streamlines.save(nib.streamlines.Tractogram(streamlines,affine_to_rasmm=np.eye(4)),tracks)
config={
 'mrthreshold':({'input':scalar},{'mode':'abs','abs':.5}),
 'mrdegibbs':({'in':scalar},{'axes':'0,1'}),
 'dwidenoise':({'dwi':dwi},{'extent':'3,3,3','save_noise':True}),
 '5tt2gmwmi':({'5tt_in':five_path},{}),
 'tckresample':({'in_tracks':tracks},{'mode':'num_points','num_points':10}),
 'tcksift2':({'in_tracks':tracks,'in_fod':fod_path},{'min_iters':1,'max_iters':3,'save_out_mu':True}),
}
results=[]
for runner in command_runners():
    name=runner.contract['command'];bindings,params=config[name]
    output=work/'synthetic-outputs'/name;output.mkdir(parents=True,exist_ok=True)
    params={'nthreads':1,**params}
    step=WorkflowStep(id=name,order=1,title=name,description='',capability='skill.dwi-skill',status='confirmed',
        selected_method_id=runner.method.id,method_options=[runner.method],selected_parameters=params,
        input_bindings={key:InputBinding(slot_id=key,artifact_type=next(s.type for s in runner.method.input_slots if s.id==key),source='existing_path',absolute_path=str(path)) for key,path in bindings.items()})
    workflow=Workflow(workflow_id='synthetic-'+name,template_id='smoke',title=name,summary='',original_request='synthetic test',status='confirmed',steps=[step],created_at='',updated_at='')
    context=RunnerContext(run_id='synthetic-'+name,workflow=workflow,step=step,method=runner.method,output_directory=output,cancel_event=Event(),log=lambda *args:None)
    problems=runner.preflight(context)
    if problems:raise RuntimeError(name+': '+str(problems))
    result=runner.run(context)
    if name=='tckresample':assert all(len(s)==10 for s in nib.streamlines.load(output/'resampled.tck').streamlines)
    if name=='tcksift2':
        weights=np.loadtxt(output/'weights.txt');assert len(weights)==len(streamlines) and np.isfinite(weights).all()
    if name=='mrthreshold':
        converted=output/'validation.nii.gz'
        subprocess.run([str(runner.executable.parent/'mrconvert'),str(output/'threshold.mif'),str(converted),'-quiet'],check=True,env={**os.environ,**MrtrixTckgenRunner._environment()})
        actual=nib.load(converted).get_fdata()
        expected=nib.load(scalar).get_fdata()>=.5
        assert np.array_equal(actual,expected), 'Threshold output does not match the requested absolute threshold'
    results.append(dict(command=name,success=True,artifacts=len(result.artifacts)))
    print(json.dumps(results[-1]),flush=True)
(work/'synthetic-smoke.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
