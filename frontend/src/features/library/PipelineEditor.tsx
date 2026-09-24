import { ui } from '../../lib/libraryText';
import { useLanguageStore } from '../../stores/languageStore';
import { Component, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { Dialog } from '../../ui/Dialog';
import { displayedInputSlots, activeOutputSlots, conditionMatches, parameterEnabled, parameterRequired } from '../workflows/workflowConditions';
import type { ParameterValue } from '../workflows/workflowTypes';
import * as api from './libraryApi';
import type { Draft, InputPort, Method, Node, Pipeline } from './libraryApi';
import { PipelineCanvas } from './PipelineCanvas';
import { shareInputs, sharedGroup, retainSharedNodes, detachSharedInput, displayBindings, arrangeNodes, conditionalConnectionIssues, conditionDescription, connectNodes, createNodeId, disconnectInput, orderedSteps, removeNode } from './pipelineGraph';
import type { Point } from './pipelineGraph';

const button='rounded border border-line px-2 py-1 text-xs hover:bg-hover disabled:opacity-40';
const field='w-full min-w-0 rounded border border-line bg-raised p-2 text-xs';
type Props={initial?:Pipeline;onClose:()=>void;onSaved:(p:Pipeline)=>void};

/** An editor failure must not unmount the user's conversation or running-task monitor. */
class EditorBoundary extends Component<{children:ReactNode;onClose:()=>void},{error:string}> {
  state={error:''};
  static getDerivedStateFromError(error:Error){return {error:error.message||ui("未知错误")};}
  render(){return this.state.error?<Dialog title={ui("Pipeline 编辑器遇到错误")} closeLabel={ui("关闭")} onClose={this.props.onClose}>
    <p>{ui("请关闭编辑器后重试。已保存的 Pipeline 和运行中的任务不受影响。")}</p><p className="mt-2 break-words text-xs text-danger">{this.state.error}</p>
  </Dialog>:this.props.children;}
}
export function PipelineEditor(props:Props){return <EditorBoundary onClose={props.onClose}><Editor {...props}/></EditorBoundary>;}

function Editor({initial,onClose,onSaved}:Props){
  const language=useLanguageStore(s=>s.language);
  const [draft,setDraft]=useState<Draft>(initial?.editor??{name:ui("新 Pipeline"),description:'',steps:[]});
  const [showConditionalInputs,setShowConditionalInputs]=useState(false);
  const [selected,setSelected]=useState<string|null>(draft.steps[0]?.id??null);
  const [q,setQ]=useState('');const [cursor,setCursor]=useState(0);
  const client=useQueryClient();const pending=useRef(false);
  const methods=useQuery({queryKey:['library-editor-methods',q,cursor,language],queryFn:()=>api.catalog('method',q,cursor,'','',language)});
  const ids=[...new Set(draft.steps.map(s=>s.method_id))];
  const contracts=useQueries({queries:ids.map(id=>({queryKey:['library-method',id,language],queryFn:()=>api.method(id),staleTime:60000,retry:1}))});
  const definitions:Record<string,Method>=Object.fromEntries(contracts.flatMap(r=>r.data?[[r.data.id,r.data]]:[]));
  const contractError=contracts.find(r=>r.isError)?.error;
  const loading=contracts.some(r=>r.isPending);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [preview,setPreview]=useState<Pipeline|null>(null);
  const [identity,setIdentity]=useState(initial?.editor?initial.id:undefined);
  const [version,setVersion]=useState(initial?.editor?Number(initial.version):undefined);
  const [saved,setSaved]=useState(false);
  const change=(next:Draft)=>{if(pending.current)return;setDraft(next);setPreview(null);setSaved(false);setError('');};
  const update=(id:string,next:Partial<Node>)=>change({...draft,steps:draft.steps.map(s=>s.id===id?{...s,...next}:s)});
  const add=async(id:string,position?:Point)=>{
    if(pending.current)return;pending.current=true;setBusy(true);setError('');
    try{
      await client.fetchQuery({queryKey:['library-method',id,language],queryFn:()=>api.method(id),staleTime:60000});
      // Generate outside React's updater: failures stay inside this try/catch,
      // and StrictMode cannot generate a second identity when replaying an updater.
      const node:Node={id:createNodeId(),method_id:id,parameters:{},inputs:{},position:position??{x:40+(draft.steps.length%4)*40,y:40+(draft.steps.length%4)*60}};
      setDraft(p=>({...p,steps:[...p.steps,node]}));setSelected(node.id);setPreview(null);setSaved(false);
    }catch(e){setError(String(e));}finally{pending.current=false;setBusy(false);}
  };
  const connect=(from:string,output:string,to:string,input:string)=>{
    try{if(sharedGroup(draft.shared_inputs??[],{step_id:to,input_slot_id:input}))throw new Error(ui("该输入正在共享外部文件，请先解除共享，再连接上游输出"));change({...draft,steps:connectNodes(draft.steps,definitions,from,output,to,input)});}catch(e){setError(String(e));}
  };
  const share=(from:InputPort,to:InputPort)=>{try{change(shareInputs(draft,definitions,from,to));}catch(e){setError(String(e));}};
  const detach=(port:InputPort)=>change({...draft,shared_inputs:detachSharedInput(draft.shared_inputs??[],port)});
  const submit=async(persist:boolean)=>{
    if(pending.current)return;pending.current=true;setBusy(true);setError('');
    try{
      const ordered={...draft,steps:orderedSteps(draft.steps)};
      const p=persist?await api.save({...ordered,expected_version:version},identity):await api.validate(ordered);
      setPreview(p);if(persist){setIdentity(p.id);setVersion(Number(p.version));setSaved(true);onSaved(p);if(p.layout_warning)setError(p.layout_warning);}
    }catch(e){setError(String(e));}finally{pending.current=false;setBusy(false);}
  };
  const selectedNode=draft.steps.find(n=>n.id===selected);
  const selectedMethod=selectedNode&&definitions[selectedNode.method_id];
  const values:Record<string,ParameterValue>={...Object.fromEntries(selectedMethod?.parameters.map(p=>[p.id,p.default])??[]),...selectedNode?.parameters};
  const connectionIssues=conditionalConnectionIssues(draft.steps,definitions);
  const canSave=!busy&&!loading&&!contractError&&!connectionIssues.length&&!!draft.steps.length&&!!draft.name.trim();
  const groups=new Map<string,api.Entry[]>();
  for(const m of methods.data?.items??[]){const category=m.category.join(' / ');groups.set(category,[...(groups.get(category)??[]),m]);}
  return <Dialog title={ui("Pipeline 节点编排")} size="xl" closeLabel={ui("关闭")} onClose={onClose} className="!max-w-[96vw] h-[90dvh]"
    contentClassName="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3"
    description={ui("自由摆放节点，从输出端口拖线到输入端口，或连接两个输入以共享文件。执行顺序由连线决定；未连接的输入在运行前选择。节点位置保存在当前浏览器。")}
    footer={<><span className="mr-auto text-xs text-subtle">{busy?ui("正在读取方法或保存… · "):''}{draft.steps.length} {ui("个步骤 · 保存不会启动任务")}{saved?ui(" · 已保存 v{0}",version):ui(" · 未保存")}</span>
      <button className={button} disabled={!canSave} onClick={()=>void submit(false)}>{ui("校验并预览接口")}</button>
      <button className={button} disabled={!canSave} onClick={()=>void submit(true)}>{ui("保存")}{version?ui("新版本"):''}</button></>}>
    <div className="flex shrink-0 flex-wrap gap-3"><label className="min-w-0 flex-1 text-xs">{ui("名称")}<input disabled={busy} className={field} value={draft.name} onChange={e=>change({...draft,name:e.target.value})}/></label>
      <label className="min-w-0 flex-[2] text-xs">{ui("说明")}<input disabled={busy} className={field} value={draft.description} onChange={e=>change({...draft,description:e.target.value})}/></label></div>
    {(error||contractError)&&<div role="alert" className="shrink-0 rounded border border-line p-2 text-sm text-danger">{error||ui("无法加载方法定义：{0}",String(contractError))}
      {contractError&&<button className={button} onClick={()=>{for(const c of contracts)if(c.isError)void c.refetch();}}>{ui("重试加载")}</button>}</div>}
    {!!connectionIssues.length&&<div role="alert" className="max-h-28 shrink-0 overflow-auto rounded border border-line p-2 text-xs text-warning">{ui("连接已保留，请先调整上游参数：")}{connectionIssues.map(issue=><p key={issue}>{issue}</p>)}</div>}
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-[200px_minmax(0,1fr)_280px]">
      <aside className="min-h-0 max-h-[35vh] overflow-auto rounded border border-line p-2 lg:max-h-none">
        <input aria-label={ui("查找 Method")} placeholder={ui("搜索方法或软件")} className={field} value={q} onChange={e=>{setQ(e.target.value);setCursor(0);}}/>
        <p className="my-2 text-xs text-subtle">{ui("拖到画布指定位置，或点击添加")}</p>
        {methods.isError&&<p role="alert">{String(methods.error)}</p>}
        {[...groups].map(([group,entries])=><details key={group} open className="my-2"><summary className="cursor-pointer break-words text-xs font-medium">{group}</summary>
          {entries.map(m=><div key={m.id} draggable={!busy} onDragStart={e=>{e.dataTransfer.setData('application/x-neuroweave-method',m.id);e.dataTransfer.effectAllowed='copy';}} className="my-2 cursor-grab rounded border border-line bg-raised p-2 text-xs">
            <strong className="break-words">{m.label}</strong><p className="my-1 line-clamp-2 break-words text-subtle" title={m.description}>{m.description}</p>
            <button className={button} disabled={busy||draft.steps.length>=50} onClick={()=>void add(m.id)}>{ui("添加节点")}</button>
          </div>)}</details>)}
        <div className="flex justify-between gap-1"><button className={button} disabled={!cursor} onClick={()=>setCursor(Math.max(0,cursor-100))}>{ui("上一页")}</button><button className={button} disabled={!methods.data?.has_more} onClick={()=>setCursor(methods.data?.next_cursor??0)}>{ui("下一页")}</button></div>
      </aside>
      <PipelineCanvas sharedInputs={draft.shared_inputs} onShareInputs={share} onDetachSharedInput={detach} showConditionalInputs={showConditionalInputs} onToggleConditionalInputs={()=>setShowConditionalInputs(v=>!v)} steps={draft.steps} definitions={definitions} selected={selected} disabled={busy} onSelect={setSelected}
        onMove={(id,position)=>update(id,{position})} onAdd={(id,position)=>{if(draft.steps.length>=50)setError(ui("每个 Pipeline 最多 50 个步骤"));else void add(id,position);}}
        onConnect={connect} onDisconnect={(id,input)=>change({...draft,steps:disconnectInput(draft.steps,id,input)})}
        onArrange={()=>{try{change({...draft,steps:arrangeNodes(draft.steps,definitions)});}catch(e){setError(String(e));}}}/>
      <aside aria-label={ui("选中步骤参数")} className="min-h-0 max-h-[50vh] overflow-auto rounded border border-line p-3 lg:max-h-none">
        {!selectedNode?<p className="text-sm text-subtle">{ui("选中画布节点，在这里查看端口和调整参数。")}</p>:<fieldset disabled={busy} className="min-w-0">
          <h3 className="break-words text-sm font-semibold">{selectedMethod?.label??selectedNode.method_id}</h3>
          <button className={button+' my-2'} onClick={()=>{const steps=removeNode(draft.steps,selectedNode.id);change({...draft,steps,shared_inputs:retainSharedNodes(draft.shared_inputs??[],steps)});setSelected(null);}}>{ui("移除节点及连线")}</button>
          {selectedMethod?<>
            <details className="mb-3 text-xs"><summary className="cursor-pointer">{ui("方法说明")}</summary><p className="whitespace-pre-wrap break-words text-subtle">{selectedMethod.description}</p></details>
            {!selectedMethod.runtime_status.available&&<p className="mb-3 text-xs text-warning">{ui("当前环境：")}{selectedMethod.runtime_status.reason??ui("不可用")}{ui("。可编排保存，执行前需满足环境。")}</p>}
            <h4 className="mb-2 text-xs font-semibold">{ui("输入连接")}</h4>
            {displayedInputSlots(selectedMethod,selectedNode.parameters,displayBindings(selectedNode,draft.shared_inputs??[]),showConditionalInputs).map(slot=><label key={slot.id} className="mb-3 block text-xs">{slot.label} · {slot.type} · {slot.requiredNow?ui("必需"):ui("可选")}
              {slot.conditionalOptional&&<span className="block text-subtle">{ui("当前参数下非必需；已有连接会保留。")}</span>}
              {sharedGroup(draft.shared_inputs??[],{step_id:selectedNode.id,input_slot_id:slot.id})&&<span className="my-1 block rounded border border-purple-400 p-2 text-purple-600">{ui("↔ 共享输入：只需选择一次文件")}<button type="button" className={button+' ml-2'} onClick={()=>detach({step_id:selectedNode.id,input_slot_id:slot.id})}>{ui("解除共享")}</button></span>}
              <select disabled={!!sharedGroup(draft.shared_inputs??[],{step_id:selectedNode.id,input_slot_id:slot.id})} className={field} value={selectedNode.inputs[slot.id]?`${selectedNode.inputs[slot.id].step_id}/${selectedNode.inputs[slot.id].output_slot_id}`:''}
                onChange={e=>{if(!e.target.value)change({...draft,steps:disconnectInput(draft.steps,selectedNode.id,slot.id)});else{const [id,output]=e.target.value.split('/');connect(id,output,selectedNode.id,slot.id);}}}>
                <option value="">{ui("整体输入（运行前选择文件）")}</option>
                {draft.steps.filter(s=>s.id!==selectedNode.id).flatMap(s=>(definitions[s.method_id]?definitions[s.method_id].output_slots.filter(o=>o.type===slot.type&&(activeOutputSlots(definitions[s.method_id],s.parameters).some(a=>a.id===o.id)||(selectedNode.inputs[slot.id]?.step_id===s.id&&selectedNode.inputs[slot.id]?.output_slot_id===o.id))):[]).map(o=><option key={s.id+'/'+o.id} value={s.id+'/'+o.id}>{definitions[s.method_id].label} · {s.id.slice(-4)} / {o.label}</option>)??[])}
              </select><span className="block break-words text-subtle">{slot.description}</span>
              {!!Object.keys(slot.required_when??{}).length&&<span className="block text-subtle">{ui("条件必需：")}{conditionDescription(selectedMethod,slot.required_when)}</span>}
            </label>)}
            <h4 className="mt-3 text-xs font-semibold">{ui("步骤参数")}</h4>
            {selectedMethod.parameters.filter(p=>conditionMatches(p.visible_when??{},values)).map(p=><label key={p.id} className="mt-3 block text-xs">{p.label}{parameterRequired(p,values)?' *':''}
              {(p.options??[]).length?<select className={field} disabled={!parameterEnabled(p,values)} value={JSON.stringify(values[p.id]??null)} onChange={e=>update(selectedNode.id,{parameters:{...selectedNode.parameters,[p.id]:JSON.parse(e.target.value)}})}>
                <option value="null">{ui("未指定")}</option>{p.options.map(o=><option key={JSON.stringify(o.value)} value={JSON.stringify(o.value)}>{o.label}</option>)}</select>
                :p.type==='boolean'?<select className={field} disabled={!parameterEnabled(p,values)} value={String(values[p.id]??'')} onChange={e=>update(selectedNode.id,{parameters:{...selectedNode.parameters,[p.id]:e.target.value===''?null:e.target.value==='true'}})}><option value="">{ui("未指定")}</option><option value="true">{ui("是")}</option><option value="false">{ui("否")}</option></select>
                :<input className={field} disabled={!parameterEnabled(p,values)} type={p.type==='string'?'text':'number'} min={p.minimum??undefined} max={p.maximum??undefined} step={p.type==='integer'?1:'any'} value={String(values[p.id]??'')}
                  onChange={e=>update(selectedNode.id,{parameters:{...selectedNode.parameters,[p.id]:e.target.value===''?null:p.type==='string'?e.target.value:Number(e.target.value)}})}/>}
              <span className="block whitespace-pre-wrap break-words text-subtle">{p.description} {p.usage} {p.condition_help}</span>
            </label>)}
          </>:<p className="text-xs">{ui("正在加载参数定义…")}</p>}
        </fieldset>}
      </aside>
    </div>
    {preview&&<details open className="max-h-32 shrink-0 overflow-auto rounded border border-line p-2 text-xs"><summary className="cursor-pointer font-medium">{ui("整体接口 · 已校验")}</summary>
      <p>{ui("输入：")}{displayedInputSlots(preview,{}, {},showConditionalInputs).map(s=>`${s.label} [${s.type}]`).join('；')||ui("无")}</p><p>{ui("输出：")}{preview.output_slots.map(s=>`${s.label} [${s.type}]`).join('；')||ui("无文件输出")}</p>
      <p>{ui("执行顺序：")}{preview.steps.map(s=>s.title||s.method_ref).join(' → ')}</p></details>}
  </Dialog>;
}
