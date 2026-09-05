export type CapabilityRecommendationItem = {
  capability_id: string;
  label: string;
  description: string;
  execution_level: 'advisory' | 'planning' | 'structured';
  skill_ids: string[];
  tree_path: string[];
};

export type CapabilityRecommendation = {
  title: string;
  summary: string;
  plan_kind: 'atomic' | 'composite';
  fully_executable: boolean;
  items: CapabilityRecommendationItem[];
  notice: string;
};

export type CapabilityRoutingLevel = {
  level: number;
  parent_ids: string[];
  candidate_count: number;
  payload_chars: number;
  selected_node_ids: string[];
  source: string;
};

export type CapabilityRoutingTrace = {
  strategy: 'hierarchical' | 'heuristic' | 'semantic';
  levels: CapabilityRoutingLevel[];
  candidates_seen: number;
  payload_chars: number;
  full_tree_payload_chars: number;
  payload_ratio: number;
  selected_paths: string[][];
  intent_source: string;
  normalized_task: string;
  semantic_hints: string[];
  confidence: number;
};
