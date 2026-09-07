"""Explicit image inspection and frequency-domain zALFF summaries."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import nibabel as nib
import numpy as np
import pandas as pd
from scipy.signal import detrend


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--operation',choices=['zalff','inspect','surface'],required=True)
    parser.add_argument('--image',type=Path)
    parser.add_argument('--bold',type=Path)
    parser.add_argument('--atlas',type=Path)
    parser.add_argument('--labels',type=Path)
    parser.add_argument('--mask',type=Path)
    parser.add_argument('--surf',type=Path)
    parser.add_argument('--annot',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--tr',type=float,default=2.)
    parser.add_argument('--top-n',type=int,default=10)
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    if args.operation=='inspect':
        img=nib.load(args.image)
        info={'shape':list(img.shape),'zooms':list(map(float,img.header.get_zooms())),
              'affine':img.affine.tolist(),'orientation':list(nib.aff2axcodes(img.affine)),'dtype':str(img.get_data_dtype())}
        (out/'inspection.json').write_text(json.dumps(info,indent=2));return
    if args.operation=='surface':
        vertices,faces=nib.freesurfer.read_geometry(args.surf)
        labels,colors,names=nib.freesurfer.read_annot(args.annot)
        if len(vertices)!=len(labels):raise ValueError('Annotation and surface vertex counts differ')
        np.savez_compressed(out/'surface.npz',vertices=vertices,faces=faces,labels=labels,colors=colors,names=np.array([n.decode() for n in names]));return
    bold,atlas,mask=[nib.load(p) for p in (args.bold,args.atlas,args.mask)]
    if len(bold.shape)!=4 or bold.shape[3]<20 or args.tr<=0 or .1>=.5/args.tr:
        raise ValueError('zALFF requires a 4D series with >=20 volumes and Nyquist frequency >0.1 Hz')
    if any(img.shape!=bold.shape[:3] or not np.allclose(img.affine,bold.affine) for img in (atlas,mask)):
        raise ValueError('BOLD, mask and atlas must already be registered on the same grid')
    selected=mask.get_fdata()>0
    values=bold.get_fdata()[selected]
    if not len(values) or not np.isfinite(values).all():raise ValueError('Empty mask or non-finite BOLD')
    values=detrend(values,axis=-1)
    frequencies=np.fft.rfftfreq(values.shape[1],d=args.tr)
    band=(frequencies>=.01)&(frequencies<=.1)
    if not band.any():raise ValueError('No frequency bins in 0.01–0.1 Hz')
    amplitude=np.abs(np.fft.rfft(values,axis=-1))*2/values.shape[1]
    alff=amplitude[:,band].mean(axis=1)
    if alff.std()==0:raise ValueError('ALFF has zero spatial variance')
    image=np.zeros(bold.shape[:3],dtype=np.float32);image[selected]=(alff-alff.mean())/alff.std()
    nib.save(nib.Nifti1Image(image,bold.affine),out/'zalff.nii.gz')
    atlas_data=atlas.get_fdata();ids=np.unique(atlas_data);ids=ids[ids>0]
    names=[line.strip() for line in args.labels.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(names)!=len(ids):raise ValueError('Label names must match positive atlas IDs in ascending order')
    rows=[]
    for roi,name in zip(ids,names):
        include=(atlas_data==roi)&selected
        if not include.any():continue
        xyz=nib.affines.apply_affine(atlas.affine,np.median(np.argwhere(include),axis=0))
        rows.append({'region_id':int(roi),'region':name,'x_mm':xyz[0],'y_mm':xyz[1],'z_mm':xyz[2],'zalff':float(image[include].mean())})
    if not rows:raise ValueError('Atlas does not overlap the analysis mask')
    frame=pd.DataFrame(rows).sort_values('zalff',ascending=False)
    frame.to_csv(out/'all_regions.csv',index=False);frame.head(args.top_n).to_csv(out/'top_regions.csv',index=False)
    (out/'method.json').write_text(json.dumps({'method':'mean Fourier amplitude, 0.01–0.1 Hz; spatial z-score within mask','tr':args.tr,'coordinates':'input affine (no registration inferred)'}))


if __name__=='__main__':main()
