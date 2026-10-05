import { stateText } from '../../lib/stateText';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request, errorText } from '../../api/http';
import { Dialog } from '../../ui/Dialog';
import { RunHistory } from '../runs/RunHistory';
import { WorkflowCard } from './WorkflowCard';
import { ui } from '../../lib/libraryText';
type Entry={workflow_id:string;title:string;status:string;updated_at:string;run_count:number;latest_run_status:string|null};
export function WorkflowHistory(){
 const [offset,setOffset]=useState(0),[q,setQ]=useState(''),[selected,setSelected]=useState<Entry|null>(null);
 const list=useQuery({queryKey:['workflow-index',offset,q],queryFn:()=>request<{items:Entry[];has_more:boolean}>(`/api/workflow-index?offset=${offset}&q=${encodeURIComponent(q)}`),refetchInterval:15000});
 return <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3 text-xs"><input aria-label={ui('搜索流程')} placeholder={ui('搜索流程')} value={q} onChange={e=>{setQ(e.target.value);setOffset(0);}} className="w-full rounded border border-line bg-raised p-2"/>
 {list.isError&&<p role="alert">{errorText(list.error,ui('读取流程列表失败'))}</p>}{list.data?.items.map(w=><button key={w.workflow_id} className="block w-full rounded border border-line p-3 text-left hover:bg-hover" onClick={()=>setSelected(w)}><strong className="break-words">{w.title}</strong><p>{stateText(w.status)} · {w.run_count} {ui('次运行')} {w.latest_run_status?stateText(w.latest_run_status):''}</p><p>{new Date(w.updated_at).toLocaleString()}</p></button>)}
 {!list.isPending&&!list.data?.items.length&&<p>{ui('暂无流程')}</p>}<div className="flex justify-between"><button disabled={!offset} onClick={()=>setOffset(v=>Math.max(0,v-30))}>{ui('上一页')}</button><button disabled={!list.data?.has_more} onClick={()=>setOffset(v=>v+30)}>{ui('下一页')}</button></div>
 {selected&&<Dialog title={selected.title} size="xl" closeLabel={ui('关闭')} onClose={()=>setSelected(null)}><WorkflowCard workflowId={selected.workflow_id}/><RunHistory key={selected.workflow_id} workflowId={selected.workflow_id}/></Dialog>}
 </div>;
}
