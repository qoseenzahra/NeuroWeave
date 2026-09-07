"""Cross-validated NPZ adapter for the upstream dense-connectome neural networks."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset
from models.common.artifacts import RunArtifacts
from models.common.data import make_splits
from models.common.metrics import classification_metrics, regression_metrics


def network(args,n_roi,nclass,blob):
    if args.model=='brainnetcnn':
        from models.brainnetcnn.net.brainnetcnn import BrainNetCNN
        return BrainNetCNN(n_roi,nclass=nclass,task=args.task)
    if args.model=='bnt':
        from models.bnt.net.bnt import BrainNetworkTransformer
        return BrainNetworkTransformer(n_roi,sizes=[max(2,n_roi//2),max(2,n_roi//4)],
            pos_embed_dim=8,hidden_size=args.hidden_size,nhead=args.nhead,nclass=nclass,task=args.task)
    from models.combraintf.net.combraintf import ComBrainTF
    if 'community_ids' not in blob: raise ValueError('ComBrainTF requires explicit atlas community_ids in the NPZ')
    communities=blob['community_ids'].astype(int)
    if len(communities)!=n_roi or set(communities)!=set(range(len(set(communities)))):
        raise ValueError('community_ids must match ROIs and use contiguous indices from zero')
    return ComBrainTF(n_roi,nclass,community_ids=communities.tolist(),n_clusters=min(8,n_roi),hidden_size=args.hidden_size,nhead=args.nhead,task=args.task)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--model',choices=['brainnetcnn','bnt','combraintf'],required=True)
    parser.add_argument('--task',choices=['classification','regression'],default='classification')
    parser.add_argument('--epochs',type=int,default=30)
    parser.add_argument('--batch-size',type=int,default=8)
    parser.add_argument('--folds',type=int,default=5)
    parser.add_argument('--seed',type=int,default=123)
    parser.add_argument('--lr',type=float,default=.001)
    parser.add_argument('--hidden-size',type=int,default=128)
    parser.add_argument('--nhead',type=int,default=1)
    parser.add_argument('--dec-weight',type=float,default=.01)
    parser.add_argument('--device',choices=['auto','cpu','cuda'],default='auto')
    args=parser.parse_args(argv)
    device='cuda' if args.device=='auto' and torch.cuda.is_available() else 'cpu' if args.device=='auto' else args.device
    blob=np.load(args.input,allow_pickle=False)
    X=blob['X'].astype(np.float32); y=blob['y']
    if X.ndim!=3 or X.shape[1]!=X.shape[2] or X.shape[1]<4 or len(y)!=len(X) or not np.isfinite(X).all():
        raise ValueError('Expected finite X[N,ROI,ROI], ROI >=4 and matching y[N]')
    if not np.allclose(X,X.transpose(0,2,1),atol=1e-5): raise ValueError('Connectomes must be symmetric')
    ids=blob['subject_id'].astype(str) if 'subject_id' in blob else np.arange(len(y)).astype(str)
    if len(set(ids))!=len(ids):raise ValueError('Subject identifiers must be unique')
    classes=np.unique(y) if args.task=='classification' else None
    nclass=len(classes) if classes is not None else 1
    encoded=np.searchsorted(classes,y) if classes is not None else y.astype(float)
    predictions=np.zeros(len(y)); scores=np.zeros((len(y),nclass)); folds=np.full(len(y),-1)
    saved=[]
    for fold,(train,test) in enumerate(make_splits(encoded,args.task,args.folds,args.seed)):
        torch.manual_seed(args.seed+fold)
        net=network(args,X.shape[1],nclass,blob).to(device)
        optimizer=torch.optim.AdamW(net.parameters(),lr=args.lr,weight_decay=.0001)
        target_mean=float(np.mean(encoded[train])) if classes is None else 0.
        target_std=max(float(np.std(encoded[train])),1e-6) if classes is None else 1.
        targets=(encoded[train]-target_mean)/target_std
        dataset=TensorDataset(torch.from_numpy(X[train]),torch.tensor(targets,dtype=torch.long if classes is not None else torch.float32))
        loader=DataLoader(dataset,batch_size=args.batch_size,shuffle=True,generator=torch.Generator().manual_seed(args.seed+fold))
        net.train()
        for _ in range(args.epochs):
            for x,target in loader:
                optimizer.zero_grad(); result=net(x.to(device)); logits=result[0] if isinstance(result,tuple) else result
                loss=torch.nn.functional.cross_entropy(logits,target.to(device)) if classes is not None else torch.nn.functional.mse_loss(logits[:,0],target.to(device))
                if isinstance(result,tuple): loss=loss+args.dec_weight*net.dec_loss(result[1])
                if not torch.isfinite(loss):raise ValueError('Training produced a non-finite loss')
                loss.backward(); optimizer.step()
        net.eval()
        with torch.no_grad():
            chunks=[]
            for begin in range(0,len(test),args.batch_size):
                result=net(torch.from_numpy(X[test[begin:begin+args.batch_size]]).to(device))
                chunks.append((result[0] if isinstance(result,tuple) else result).cpu())
            logits=torch.cat(chunks)
            if classes is not None:
                scores[test]=torch.softmax(logits,dim=1).numpy(); predictions[test]=scores[test].argmax(axis=1)
            else: predictions[test]=logits[:,0].numpy()*target_std+target_mean
        folds[test]=fold
        saved.append({'state_dict':{k:v.detach().cpu() for k,v in net.state_dict().items()},'target_mean':target_mean,'target_std':target_std})
        del net
        print('Completed fold',fold,flush=True)
    metrics=classification_metrics(encoded,predictions.astype(int),scores[:,1] if nclass==2 else scores) if classes is not None else regression_metrics(encoded,predictions)
    metrics['device']=device
    artifacts=RunArtifacts(args.output_dir,vars(args)); artifacts.write_config(); artifacts.write_metrics(metrics)
    artifacts.write_predictions({'subject_id':ids,'fold':folds,'target':y,'prediction':classes[predictions.astype(int)] if classes is not None else predictions})
    artifacts.write_folds({'subject_id':ids,'fold':folds})
    torch.save({'folds':saved,'classes':classes.tolist() if classes is not None else None,'n_roi':X.shape[1]},Path(args.output_dir)/'checkpoint.pt')
    artifacts.write_manifest(); print(metrics)


if __name__=='__main__': main()
