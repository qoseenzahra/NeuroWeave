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
