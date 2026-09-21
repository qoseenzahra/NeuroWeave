import { request } from '../../api/http';

export type Skill = {
  name: string;
  display_name: string;
  description: string;
  layer: string;
  skill_type: string;
  runtime: string;
  status: string;
  summary_en?: string;
  summary_zh?: string;
  dependencies?: string[];
  source?: 'NeuroClaw' | 'LocalFlow';
  script_count?: number;
  has_handler?: boolean;
  executable?: boolean;
  structure_mode?: 'advisory' | 'planning' | 'runner';
  runner_count?: number;
  ready_runner_count?: number;
  planning_method_count?: number;
  execution_state?: 'ready' | 'needs_environment' | 'planning';
  runtime_reasons?: string[];
};

export type CatalogStats = {
  total: number;
  sources: Record<string, number>;
  with_scripts: number;
  with_handlers: number;
  structured?: number;
  planning_structured?: number;
  runner_structured?: number;
  capability_catalog?: {
    capabilities: number;
    methods: number;
    planning_methods: number;
    runner_methods: number;
    evidence_backed_methods: number;
    reference_commands: number;
    artifact_types: number;
  };
  execution_enabled: boolean;
};

export type SkillsResponse = {
  skills: Skill[];
  stats?: CatalogStats | null;
};

export function fetchSkills(signal?: AbortSignal): Promise<SkillsResponse> {
  return request<SkillsResponse>('/api/skills', { signal });
}

export type SkillDetails = Skill & {
  instructions: string;
  files: string[];
  complementary_skills?: string[];
};

export function fetchSkill(name: string, signal?: AbortSignal): Promise<SkillDetails> {
  return request<SkillDetails>(`/api/skills/${encodeURIComponent(name)}`, { signal });
}

export type SkillMethodSummary = {
  capability:string; method_id:string; skill_id:string; label:string; description:string;
  runner_id:string; execution_mode:'runner'|'planning'; parameter_count:number; input_count:number; output_count:number;
};
export type SkillMethodPage = {items:SkillMethodSummary[]; total:number; has_more:boolean; next_cursor:string|null};
export type SkillMethodDetail = SkillMethodSummary & {
  definition_revision:string;
  runtime_status:{available:boolean;reason?:string};
  parameters:import('../workflows/workflowTypes').ParameterSpec[];
  input_slots:import('../workflows/workflowTypes').InputSlotSpec[];
  output_slots:import('../workflows/workflowTypes').OutputSlotSpec[];
  source_references:import('../workflows/workflowTypes').MethodSourceReference[];
  command_coverage?:{total:number;exposed:number;omitted:string[]};
};
export function fetchSkillMethods(skill:string,q:string,cursor:string,signal?:AbortSignal) {
  return request<SkillMethodPage>(`/api/skills/${encodeURIComponent(skill)}/methods?${new URLSearchParams({q,cursor,limit:'20'})}`,{signal});
}
export function fetchSkillMethod(capability:string,method:string,signal?:AbortSignal) {
  return request<SkillMethodDetail>(`/api/skill-methods/${encodeURIComponent(capability)}/${encodeURIComponent(method)}`,{signal});
}
export function fetchSkillReference(skill:string,offset:number,signal?:AbortSignal) {
  return request<{text:string;total_chars:number;truncated:boolean;next_offset:number|null}>(`/api/skills/${encodeURIComponent(skill)}/reference?offset=${offset}&max_chars=6000`,{signal});
}
