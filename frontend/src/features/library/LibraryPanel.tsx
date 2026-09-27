import { stateText } from '../../lib/stateText';
import { ui } from '../../lib/libraryText';
import { DefinitionDetails } from './DefinitionDetails';
import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog } from '../../ui/Dialog';
import { useSkills } from '../skills/useSkills';
import type { Skill } from '../skills/skillsApi';
import { useDatasetStore } from '../../stores/datasetStore';
import { WorkflowCard } from '../workflows/WorkflowCard';
import type { Workflow } from '../workflows/workflowTypes';
import * as api from './libraryApi';
import type { Entry, Method, Pipeline } from './libraryApi';
import { PipelineVersions } from './PipelineVersions';
import { PipelineEditor } from './PipelineEditor';
import { LibraryNavigation } from './LibraryNavigation';
import { useLanguageStore } from '../../stores/languageStore';

type Props={selectedSkillIds:string[];disabled:boolean;onAdd:(id:string)=>void;onRemove:(id:string)=>void;
  onDetails:(s:Skill)=>void;onClear:()=>void;workspaceId?:string|null;conversationId?:string|null};
const button='rounded border border-line px-2 py-1 text-xs hover:bg-hover disabled:opacity-40';
export function LibraryPanel(props:Props) {
  const language=useLanguageStore(s=>s.language);
  const [category,setCategory]=useState(''); const [software,setSoftware]=useState('');
  const [search,setSearch]=useState('');
  const [kind,setKind]=useState('skill');const [q,setQ]=useState('');const [cursor,setCursor]=useState(0);
  const [editing,setEditing]=useState<Pipeline|'new'|null>(null);
  const [detail,setDetail]=useState<Method|Pipeline|null>(null);const [error,setError]=useState('');
  const [workflow,setWorkflow]=useState<Workflow|null>(null);const [busy,setBusy]=useState(false);
  const datasetId=useDatasetStore(s=>s.selectedDatasetId);const client=useQueryClient();const skills=useSkills();
  useEffect(()=>{const timer=setTimeout(()=>setSearch(q),200);return()=>clearTimeout(timer);},[q]);
  const draftQuery=useQuery({queryKey:['pipeline-drafts'],queryFn:api.drafts,enabled:kind==='pipeline',refetchOnWindowFocus:true});
  const query=useQuery({queryKey:['library',kind,search,cursor,category,software,language],queryFn:()=>api.catalog(kind,search,cursor,category,software,language)});
  const detailVersion=detail&&'steps' in detail?detail.version:undefined;
  const detailId=detail?.id; const detailKind=detail && 'runtime_status' in detail ? 'method' : 'pipeline';
  useEffect(()=>{let active=true;if(detailId)void (detailKind==='method'?api.method(detailId):api.pipeline(detailId,detailVersion)).then(value=>{if(active)setDetail(value);}).catch(e=>{if(active)setError(String(e));});return()=>{active=false;};},[detailId,detailKind,detailVersion,language]);
  const inspect=async(e:Entry)=>{setError('');try{
    if(e.kind==='skill'){const s=skills.data?.skills.find(s=>s.name===e.id);if(s)props.onDetails(s);else throw new Error(ui("Skill 元数据尚未加载"));}
    else setDetail(e.kind==='method'?await api.method(e.id):await api.pipeline(e.id));
  }catch(e){setError(String(e));}};
  const use=async(p:Pipeline)=>{setBusy(true);setError('');try{setWorkflow(await api.usePipeline(p.id,datasetId,props.workspaceId??null,p.version,props.conversationId));void client.invalidateQueries({queryKey:['conversation']});setDetail(null);}catch(e){setError(String(e));}finally{setBusy(false);}};
  return <div className="min-w-0 space-y-3">
    <div role="tablist" aria-label={ui("能力资源目录")} className="flex flex-wrap gap-1">{['skill','method','pipeline'].map(k=><button key={k} role="tab" aria-selected={kind===k} className={button+' '+(kind===k?'bg-selected':'')} onClick={()=>{setKind(k);setCursor(0);setCategory('');setSoftware('');}}>{k==='skill'?'Skill':k==='method'?'Method':'Pipeline'}</button>)}</div>
    <input className="w-full min-w-0 rounded border border-line bg-raised p-2 text-xs" aria-label={ui("搜索资源")} placeholder={ui("搜索名称、功能或软件")} value={q} onChange={e=>{setQ(e.target.value);setCursor(0);}}/>
    <p className="text-xs text-subtle">{kind==='skill'?ui("Skill：按目标统筹方法与流程"):kind==='method'?ui("Method：可执行的最小命令或库调用"):ui("Pipeline：已定义输入输出的可复用方法组合")}</p>
    <LibraryNavigation facets={query.data?.facets} category={category} software={software} onCategory={value=>{setCategory(value);setCursor(0);}} onSoftware={value=>{setSoftware(value);setCursor(0);}}/>
    {kind==='pipeline'&&<details className="rounded border border-line p-2 text-xs"><summary>{ui('未完成的 Pipeline 草稿')} · {draftQuery.data?.items.length??0}</summary>{draftQuery.data?.items.map(d=><button key={d.id} className="my-2 block w-full break-words text-left hover:text-accent" onClick={()=>setEditing({id:d.pipeline_id??'',version:d.pipeline_version?String(d.pipeline_version):'',label:d.editor.name,description:d.editor.description,editor:d.editor,draft_id:d.id,draft_revision:d.revision,parameters:[],input_slots:[],output_slots:[],steps:[]})}>{d.editor.name||ui('未命名草稿')} · {new Date(d.updated_at).toLocaleString()}</button>)}</details>}
    {kind==='pipeline'&&<button className={button} onClick={()=>setEditing('new')}>{ui("＋ 拖拽创建 Pipeline")}</button>}
    {kind==='skill'&&!!props.selectedSkillIds.length&&<button className={button} disabled={props.disabled} onClick={props.onClear}>{ui("清空已选 Skill")}</button>}
    {(error||query.isError)&&<p role="alert" className="break-words text-xs text-danger">{error||String(query.error)}</p>}
    {query.isPending?<p className="text-xs">{ui("加载目录…")}</p>:<div className="space-y-2">{(query.data?.items??[]).map(e=><div key={e.id} className="min-w-0 rounded border border-line p-2 text-xs">
      <button className="block w-full break-words text-left font-medium" onClick={()=>void inspect(e)}>{e.label}</button>
      <p className="mt-1 line-clamp-3 break-words text-subtle" title={e.description}>{e.description}</p>
      <p className="mt-1 break-words text-[10px] text-subtle">{e.category.join(" / ")}{e.software?.length ? " · "+e.software.join(", ") : ""}</p>
      {e.kind==='method'&&<p className="mt-1 text-subtle">{ui('已开放 {0} 个参数，{1} 个原生命令选项尚未开放',e.parameter_count??0,e.omitted_option_count??0)}</p>}
      <div className="mt-2 flex flex-wrap gap-1"><button className={button} onClick={()=>void inspect(e)}>{ui("查看详情")}</button>
        {e.kind==='skill'&&<button className={button} disabled={props.disabled} onClick={()=>props.selectedSkillIds.includes(e.id)?props.onRemove(e.id):props.onAdd(e.id)}>{props.selectedSkillIds.includes(e.id)?ui("移出会话"):ui("加入会话")}</button>}
        {e.kind==='pipeline'&&<span className="text-subtle">{e.step_count} {ui("步 · v")}{e.version} · {stateText(e.status??'published')}</span>}</div>
    </div>)}</div>}
    {!query.isPending&&!query.data?.items.length&&<p role="status" className="py-3 text-xs text-subtle">{ui("没有匹配条目，请调整搜索或清除筛选。")}</p>}
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><button className={button} disabled={!cursor} onClick={()=>setCursor(Math.max(0,cursor-100))}>{ui("上一页")}</button>
      <span>{query.data?.total??0} {ui("项")}</span><button className={button} disabled={!query.data?.has_more} onClick={()=>setCursor(query.data?.next_cursor??0)}>{ui("下一页")}</button></div>
    {editing&&<PipelineEditor initial={editing==='new'?undefined:editing} onClose={()=>{setEditing(null);void client.invalidateQueries({queryKey:['pipeline-drafts']});}} onSaved={()=>void client.invalidateQueries({queryKey:['library']})}/>}
    {detail&&<Dialog title={detail.label} closeLabel={ui("关闭")} size="xl" onClose={()=>setDetail(null)} footer={'steps' in detail?<>

      <button className={button} disabled={busy||props.disabled||detail.status==='archived'} onClick={()=>void use(detail)}>{ui("创建流程并配置运行")}</button></>:undefined}>
      {'steps' in detail&&<PipelineVersions key={detail.id+':'+detail.version} pipeline={detail} onSelect={setDetail} onEdit={p=>{setEditing(p);setDetail(null);}} onChange={()=>void client.invalidateQueries({queryKey:['library']})}/>}
      {'steps' in detail&&<ol className="my-3 list-inside list-decimal text-xs">{detail.steps.map(s=><li key={s.id}>{s.title||s.method_ref}</li>)}</ol>}
      <DefinitionDetails definition={detail}/>
      {error&&<p className="text-danger">{error}</p>}
    </Dialog>}
    {workflow&&<Dialog title={workflow.title} closeLabel={ui("关闭")} size="xl" onClose={()=>setWorkflow(null)} description={ui("此处仅创建流程；选择文件、输出目录和资源，完成 dry run 和确认后才会提交计算。")}>
      <WorkflowCard workflowId={workflow.workflow_id} initialWorkflow={workflow}/></Dialog>}
  </div>;
}
