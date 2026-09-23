import { MethodVerification } from '../skills/MethodVerification';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog } from '../../ui/Dialog';
import { useSkills } from '../skills/useSkills';
import type { Skill } from '../skills/skillsApi';
import { useDatasetStore } from '../../stores/datasetStore';
import { WorkflowCard } from '../workflows/WorkflowCard';
import type { Workflow } from '../workflows/workflowTypes';
import * as api from './libraryApi';
import type { Entry, Method, Pipeline } from './libraryApi';
import { PipelineEditor } from './PipelineEditor';

type Props={selectedSkillIds:string[];disabled:boolean;onAdd:(id:string)=>void;onRemove:(id:string)=>void;
  onDetails:(s:Skill)=>void;onClear:()=>void;workspaceId?:string|null};
const button='rounded border border-line px-2 py-1 text-xs hover:bg-hover disabled:opacity-40';
function Tree({items,depth=0,render}:{items:Entry[];depth?:number;render:(e:Entry)=>React.ReactNode}) {
  const groups=new Map<string,Entry[]>();
  for(const e of items){const key=e.category[depth]??'';groups.set(key,[...(groups.get(key)??[]),e]);}
  return <div className="min-w-0 space-y-2">{[...groups].map(([name,entries])=>name?
    <details key={name} open={depth===0} className="min-w-0 rounded border border-line p-2"><summary className="cursor-pointer text-xs font-medium">{name} · {entries.length}</summary>
      <div className="mt-2"><Tree items={entries} depth={depth+1} render={render}/></div></details>:
    <div key="entries" className="space-y-2">{entries.map(render)}</div>)}</div>;
}
export function LibraryPanel(props:Props) {
  const [kind,setKind]=useState('skill');const [q,setQ]=useState('');const [cursor,setCursor]=useState(0);
  const [editing,setEditing]=useState<Pipeline|'new'|null>(null);
  const [detail,setDetail]=useState<Method|Pipeline|null>(null);const [error,setError]=useState('');
  const [workflow,setWorkflow]=useState<Workflow|null>(null);const [busy,setBusy]=useState(false);
  const datasetId=useDatasetStore(s=>s.selectedDatasetId);const client=useQueryClient();const skills=useSkills();
  const query=useQuery({queryKey:['library',kind,q,cursor],queryFn:()=>api.catalog(kind,q,cursor)});
  const inspect=async(e:Entry)=>{setError('');try{
    if(e.kind==='skill'){const s=skills.data?.skills.find(s=>s.name===e.id);if(s)props.onDetails(s);else throw new Error('Skill 元数据尚未加载');}
    else setDetail(e.kind==='method'?await api.method(e.id):await api.pipeline(e.id));
  }catch(e){setError(String(e));}};
  const use=async(p:Pipeline)=>{setBusy(true);setError('');try{setWorkflow(await api.usePipeline(p.id,datasetId,props.workspaceId??null,p.version));setDetail(null);}catch(e){setError(String(e));}finally{setBusy(false);}};
  return <div className="min-w-0 space-y-3">
    <div role="tablist" aria-label="能力资源目录" className="flex flex-wrap gap-1">{['skill','method','pipeline'].map(k=><button key={k} role="tab" aria-selected={kind===k} className={button+' '+(kind===k?'bg-selected':'')} onClick={()=>{setKind(k);setCursor(0);}}>{k==='skill'?'Skill':k==='method'?'Method':'Pipeline'}</button>)}</div>
    <input className="w-full min-w-0 rounded border border-line bg-raised p-2 text-xs" aria-label="搜索资源" placeholder="搜索名称、功能或软件" value={q} onChange={e=>{setQ(e.target.value);setCursor(0);}}/>
    {kind==='pipeline'&&<button className={button} onClick={()=>setEditing('new')}>＋ 拖拽创建 Pipeline</button>}
    {kind==='skill'&&!!props.selectedSkillIds.length&&<button className={button} disabled={props.disabled} onClick={props.onClear}>清空已选 Skill</button>}
    {(error||query.isError)&&<p role="alert" className="break-words text-xs text-danger">{error||String(query.error)}</p>}
    {query.isPending?<p className="text-xs">加载目录…</p>:<Tree items={query.data?.items??[]} render={e=><div key={e.id} className="min-w-0 rounded border border-line p-2 text-xs">
      <button className="block w-full break-words text-left font-medium" onClick={()=>void inspect(e)}>{e.label}</button>
      <p className="mt-1 break-words text-subtle">{e.description}</p>
      <div className="mt-2 flex flex-wrap gap-1"><button className={button} onClick={()=>void inspect(e)}>查看详情</button>
        {e.kind==='skill'&&<button className={button} disabled={props.disabled} onClick={()=>props.selectedSkillIds.includes(e.id)?props.onRemove(e.id):props.onAdd(e.id)}>{props.selectedSkillIds.includes(e.id)?'移出会话':'加入会话'}</button>}
        {e.kind==='pipeline'&&<span className="text-subtle">{e.step_count} 步 · v{e.version}</span>}</div>
    </div>}/>}
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><button className={button} disabled={!cursor} onClick={()=>setCursor(Math.max(0,cursor-100))}>上一页</button>
      <span>{query.data?.total??0} 项</span><button className={button} disabled={!query.data?.has_more} onClick={()=>setCursor(query.data?.next_cursor??0)}>下一页</button></div>
    {editing&&<PipelineEditor initial={editing==='new'?undefined:editing} onClose={()=>setEditing(null)} onSaved={()=>void client.invalidateQueries({queryKey:['library']})}/>}
    {detail&&<Dialog title={detail.label} closeLabel="关闭" size="xl" onClose={()=>setDetail(null)} footer={'steps' in detail?<>
      {detail.editor&&<button className={button} onClick={()=>{setEditing(detail);setDetail(null);}}>编辑新版本</button>}
      <button className={button} disabled={busy||props.disabled} onClick={()=>void use(detail)}>创建流程并配置运行</button></>:undefined}>
      <p className="whitespace-pre-wrap text-sm">{detail.description}</p>
      {'runtime_status' in detail&&<p className="my-2 text-xs">运行环境：{detail.runtime_status.available?'可用':'尚未满足'} · {detail.runtime_status.reason}</p>}
      {'verification' in detail&&<MethodVerification value={detail.verification}/>}
      {'steps' in detail&&<ol className="my-3 list-inside list-decimal text-xs">{detail.steps.map(s=><li key={s.id}>{s.title||s.method_ref}</li>)}</ol>}
      {'execution' in detail&&detail.execution?.contract?.omitted_options&&<details className="my-3 rounded border border-line p-2 text-xs"><summary>尚未开放的命令选项（请检查覆盖范围）</summary>{Object.entries(detail.execution.contract.omitted_options).map(([flag,reason])=><p key={flag}>-{flag}：{reason}</p>)}</details>}
      <h3 className="mt-3 font-medium">输入</h3>{detail.input_slots.map(s=><p key={s.id} className="break-words text-xs">{s.label} · {s.type} · {s.required?'必需':'可选/条件必需'} — {s.description}</p>)}
      <h3 className="mt-3 font-medium">输出</h3>{detail.output_slots.map(s=><p key={s.id} className="break-words text-xs">{s.label} · {s.type} — {s.description}</p>)}
      <h3 className="mt-3 font-medium">参数与用法</h3>{detail.parameters.map(p=><details key={p.id} className="my-2 rounded border border-line p-2 text-xs"><summary>{p.label} · {p.id} · {p.type}</summary>
        <p className="whitespace-pre-wrap">{p.description}</p><p>{p.usage}</p><p>默认：{String(p.default??'未指定')}；{p.required?'必需':'可选'} {p.condition_help}</p>
        {!!p.options.length&&<p>{p.options.map(o=>`${o.label}=${o.value}`).join('；')}</p>}
        {[['显示条件',p.visible_when],['启用条件',p.enabled_when],['必填条件',p.required_when]].map(([label,value])=>value&&Object.keys(value).length>0?<p key={String(label)}>{String(label)}：{JSON.stringify(value)}</p>:null)}
      </details>)}
      {error&&<p className="text-danger">{error}</p>}
    </Dialog>}
    {workflow&&<Dialog title={workflow.title} closeLabel="关闭" size="xl" onClose={()=>setWorkflow(null)} description="此处仅创建流程；选择文件、输出目录和资源，完成 dry run 和确认后才会提交计算。">
      <WorkflowCard workflowId={workflow.workflow_id} initialWorkflow={workflow}/></Dialog>}
  </div>;
}
