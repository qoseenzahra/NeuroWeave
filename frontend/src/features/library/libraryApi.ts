import { request } from '../../api/http';
import { executionDraft } from './pipelineGraph';
import { rememberLayout, restoreLayout } from './pipelineLayout';
import type { ParameterSpec, InputSlotSpec, OutputSlotSpec, ParameterValue, Workflow } from '../workflows/workflowTypes';
export type Entry = {id:string;label:string;description:string;kind:string;category:string[];category_ids?:string[];software?:string[];method_count?:number;pipeline_count?:number;version?:string;step_count?:number;status?:string;omitted_option_count?:number;parameter_count?:number};
export type Facets = {categories:Array<{path:string[];label:string;count:number}>;software:Array<{id:string;label:string;count:number}>};
export type Page = {facets?:Facets;items:Entry[];total:number;has_more:boolean;next_cursor:number|null};
export type Method = Entry & {parameters:ParameterSpec[];input_slots:InputSlotSpec[];output_slots:OutputSlotSpec[];
  execution?:{contract?:{total_options?:number;omitted_options?:Record<string,string>}};
  verification?:import('../skills/MethodVerification').Verification;
  option_coverage?: {flag:string;description:string}[]; runtime_status:{available:boolean;reason?:string};command_references?:Array<{command:string;description?:string}>};
export type SourceLink = {step_id:string;output_slot_id:string};
export type Link = SourceLink & {additional_sources?:SourceLink[]};
export type Node = {position?:{x:number;y:number};id:string;method_id:string;parameters:Record<string,ParameterValue>;inputs:Record<string,Link>};
export type InputPort = {step_id:string;input_slot_id:string};
export type Draft = {shared_inputs?:InputPort[][];name:string;description:string;steps:Node[];expected_version?:number};
export type Pipeline = {draft_id?:string;draft_revision?:number;status?:string;layout_warning?:string;id:string;version:string;label:string;description:string;editor?:Draft;
  parameters:ParameterSpec[];input_slots:InputSlotSpec[];output_slots:OutputSlotSpec[];
  steps:Array<{id:string;method_ref:string;method_id?:string;title:string}>};
export const catalog = (kind:string,q:string,cursor=0,category='',software='',language='zh') => request<Page>(`/api/library?${new URLSearchParams({kind,q,cursor:String(cursor),limit:'100',category,software,language})}`);
export const method = (id:string,signal?:AbortSignal) => request<Method>(`/api/library/methods/${encodeURIComponent(id)}`,{signal});
export const pipeline = async (id:string,version?:string) => restoreLayout(await request<Pipeline>(`/api/library/pipelines/${encodeURIComponent(id)}${version?'?version='+version:''}`));
export const validate = (draft:Draft) => request<Pipeline>('/api/library/pipelines/validate',{method:'POST',body:JSON.stringify(executionDraft(draft))});
export const save = async (draft:Draft,id?:string) => {
  const value=await request<Pipeline>(`/api/library/pipelines${id?'/'+encodeURIComponent(id):''}`,{method:id?'PUT':'POST',body:JSON.stringify(executionDraft(draft))});
  return rememberLayout(value,draft);
};
export const usePipeline = (id:string,dataset_id:string|null,workspace_id:string|null,version?:string,conversation_id?:string|null) => request<Workflow>(`/api/library/pipelines/${encodeURIComponent(id)}/workflows`,{method:'POST',body:JSON.stringify({dataset_id,workspace_id,conversation_id,version:version?Number(version):null})});

export const describe = (draft:Draft,language:string,signal?:AbortSignal) => request<{description:string;source:string;warning:string;fingerprint:string}>(`/api/library/pipelines/describe?language=${language}`,{method:'POST',body:JSON.stringify(executionDraft(draft)),signal});
export type SavedDraft={id:string;revision:number;updated_at:string;editor:Draft;pipeline_id:string|null;pipeline_version:number|null};
export const drafts=async()=>{
  const server=await request<{items:SavedDraft[]}>('/api/library/drafts');
  const items=new Map(server.items.map(v=>[v.id,v]));
  try{for(let i=0;i<localStorage.length;i++){
    const key=localStorage.key(i);if(!key?.startsWith('neuroweave:pipeline-draft:'))continue;
    const value=JSON.parse(localStorage.getItem(key)??'null') as SavedDraft|null;
    if(value?.id&&value.editor&&(!items.has(value.id)||value.revision>=(items.get(value.id)?.revision??0)))items.set(value.id,value);
  }}catch{/* Server drafts remain visible. */}
  return {items:[...items.values()].sort((a,b)=>b.updated_at.localeCompare(a.updated_at)).slice(0,100)};
};
export const lifecycle=(id:string,version:string,status:string)=>request(`/api/library/pipelines/${encodeURIComponent(id)}/versions/${version}?status=${status}`,{method:'PATCH'});
export const versions=(id:string)=>request<{items:Array<{version:string;status?:string}>}>(`/api/library/pipelines/${encodeURIComponent(id)}/versions`);
export const migration=(id:string,version?:string)=>request<{changes:Array<{step_id:string;method_id:string;from_version:string;to_version:string}>;errors:string[];editor?:Draft}>(`/api/library/pipelines/${encodeURIComponent(id)}/migration${version?'?version='+version:''}`);
