"""Scoped checks of authorized inputs; file metadata is not proof of scientific quality."""
import json,math,os,subprocess
from pathlib import Path
from .check_cache import checked_file
from ..artifact_semantics import IMAGE_TYPES

def image_header(path):
    if not path.name.lower().endswith(('.nii','.nii.gz','.mgz','.mgh')):
        return dict(status='not_checked',code='format_not_checked')
    python=Path(os.getenv('LOCALFLOW_SKILL_PYTHON','/opt/neuroweave/envs/scientific-py311/bin/python'))
    worker=Path(__file__).with_name('header_check_worker.py')
    if not python.is_file():return dict(status='not_checked',code='reader_unavailable')
    def read():
        try:
            result=subprocess.run([str(python),'-B','-s',str(worker),str(path)],capture_output=True,text=True,timeout=12,shell=False)
            if result.returncode or len(result.stdout)>10000:return dict(status='not_checked',code='reader_failed')
            return json.loads(result.stdout)
        except (OSError,ValueError,subprocess.TimeoutExpired):return dict(status='not_checked',code='reader_failed')
    return checked_file(path,('image-header-v1',str(python),python.stat().st_mtime_ns,worker.stat().st_mtime_ns),read)

def numeric_table(path):
    if path.stat().st_size>2_000_000:raise ValueError('Gradient table exceeds 2 MB')
    rows=[[float(v) for v in line.split()] for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not rows or any(not math.isfinite(v) for row in rows for v in row):raise ValueError('Empty or non-finite gradient table')
    if len({len(row) for row in rows})!=1:raise ValueError('Ragged gradient table')
    return rows

def scientific_checks(context):
    # Called only after common_preflight authorized every path and provenance.
    from .external_command import ExternalCommandRunner
    rows=[];images=[];gradients={}
    def add(status,code,slot='',**details):
        rows.append(dict(status=status,code=code,slot_id=slot,step_id=context.step.id,details=details))
    for slot,binding in context.step.input_bindings.items():
        if binding.source=='upstream_output':
            if binding.artifact_type in IMAGE_TYPES:add('deferred','upstream_check_deferred',slot)
            continue
        for path in ExternalCommandRunner.binding_paths(binding):
            if binding.artifact_type in IMAGE_TYPES and path.is_file():
                header=image_header(path)
                add(header['status'],header['code'],slot,metadata={k:v for k,v in header.items() if k not in {'status','code'}})
                if header['status']=='passed':images.append((slot,binding.artifact_type,header))
            if binding.artifact_type in {'b_values','b_vectors','gradient_table'} and path.is_file():
                try:
                    table=checked_file(path,'gradient-table-v1',lambda:numeric_table(path))
                    if binding.artifact_type=='b_values':
                        if min(v for row in table for v in row)<0:raise ValueError('Negative b-value')
                        gradients[slot]=sum(map(len,table))
                    elif binding.artifact_type=='b_vectors':
                        if len(table)!=3 and len(table[0])!=3:raise ValueError('b-vectors require 3xN or Nx3')
                        gradients[slot]=len(table[0]) if len(table)==3 else len(table)
                    else:
                        if len(table[0])!=4:raise ValueError('MRtrix gradients require 4 columns')
                        gradients[slot]=len(table)
                    add('passed','gradient_table_readable',slot,count=gradients[slot])
                except (ValueError,UnicodeError,OSError) as exc:add('error','invalid_gradient_table',slot,reason=str(exc))
    counts=set(gradients.values())
    volumes={h['shape'][3] if len(h['shape'])>3 else 1 for _,kind,h in images if kind in {'raw_dwi','preprocessed_dwi'}}
    if len(counts|volumes)>1:add('error','gradient_volume_mismatch',counts=sorted(counts),volumes=sorted(volumes))
    for slot,kind,h in images:
        if kind=='five_tt_image' and (len(h['shape'])!=4 or h['shape'][3]!=5):add('error','five_tt_channels',slot,shape=h['shape'])
        if kind in {'label_image','parcellation_image'} and len(h['shape'])>3 and h['shape'][3]!=1:add('error','label_dimensions',slot,shape=h['shape'])
    if len(images)>1:
        # Registration, ACT and resampling allow differing grids. Do not reject
        # them or claim alignment based only on equal shapes/affines.
        add('review','spatial_alignment_requires_review',slots=[v[0] for v in images])
    if any(kind in {'label_image','parcellation_image','brain_mask','five_tt_image'} for _,kind,_ in images):
        add('review','voxel_values_and_anatomy_not_checked')
    return rows
