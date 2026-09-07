"""Compare explicitly aligned maps under a recorded exchangeability assumption."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
from models.connectome_discovery.mapping import cosine_similarity_map, permutation_pvalue, rank_targets


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--atlas',required=True);parser.add_argument('--space',required=True)
    parser.add_argument('--permutations',type=int,default=1000);parser.add_argument('--seed',type=int,default=123)
    parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    data=np.load(args.input,allow_pickle=False);reference=data['reference'];candidates=data['candidates'];names=data['target_names']
    if reference.ndim!=1 or candidates.ndim!=2 or candidates.shape[1]!=reference.size or len(names)!=len(candidates):raise ValueError('NPZ requires reference[F], candidates[N,F], target_names[N]')
    if not np.isfinite(reference).all() or not np.isfinite(candidates).all():raise ValueError('Maps contain non-finite values')
    if np.linalg.norm(reference)==0 or (np.linalg.norm(candidates,axis=1)==0).any():raise ValueError('Cosine similarity is undefined for zero maps')
    pvalues={str(name):permutation_pvalue(reference,map,args.permutations,args.seed) for name,map in zip(names,candidates)}
    frame=rank_targets(reference,candidates,list(map(str,names)))
    frame['permutation_p']=frame.target.map(pvalues)
    args.output_dir.mkdir(parents=True,exist_ok=True);frame.to_csv(args.output_dir/'ranking.csv',index=False)
    (args.output_dir/'method.json').write_text(json.dumps({'atlas':args.atlas,'space':args.space,'permutations':args.permutations,'seed':args.seed,
        'null_model':'unrestricted feature permutation; requires exchangeability; does not preserve spatial autocorrelation',
        'p_values':'two-sided, uncorrected; plus-one correction'},indent=2))


if __name__=='__main__':main()
