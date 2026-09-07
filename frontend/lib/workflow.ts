import type { Dataset, SamplePathCoverage, SamplePathMatch } from '@/lib/dataset';

export type WorkflowStatus =
  | 'awaiting_method_choice'
  | 'awaiting_input_binding'
  | 'chain_ready'
  | 'awaiting_parameter_review'
  | 'awaiting_dry_run'
  | 'ready'
  | 'confirmed';

export type ParameterValue = string | number | boolean | null;

export type ParameterOption = {
  value: ParameterValue;
  label: string;
  description?: string;
};

export type MethodSourceReference = {
  path: string;
  label: string;
  kind: 'skill' | 'script' | 'command';
  line_start: number | null;
  line_end: number | null;
};

export type CommandReference = {
  command: string;
  language: string;
  source_path: string;
  line_start: number | null;
  kind: 'operation' | 'setup' | 'environment' | 'example';
  executable: boolean;
};

export type ParameterSpec = {
  id: string;
  argument: string;
  label: string;
  description: string;
  type: 'string' | 'integer' | 'number' | 'boolean';
  control?: 'auto' | 'select' | 'number' | 'text' | 'switch';
  level?: 'basic' | 'advanced';
  group?: string;
  unit: string;
  required: boolean;
  default: ParameterValue | null;
  options: ParameterOption[];
  minimum?: number | null;
  maximum?: number | null;
  step?: number | null;
  placeholder?: string;
  visible_when?: Record<string, ParameterValue[]>;
};

export type InputSlotSpec = {
  id: string;
  type: string;
  label: string;
  description: string;
  required: boolean;
  required_when: Record<string, ParameterValue[]>;
  cardinality: 'one' | 'many';
  binding: 'file' | 'folder' | 'file_bundle' | 'artifact';
  formats: string[];
  companions: string[];
  source_options: Array<'dataset' | 'existing_path' | 'upstream_output'>;
  validation: string[];
};

export type OutputSlotSpec = {
  id: string;
  type: string;
  label: string;
  description: string;
  format: string;
  primary: boolean;
  path_template: string;
  generated_when: Record<string, ParameterValue[]>;
};

export type InputBinding = {
  slot_id: string;
  artifact_type: string;
  source: 'dataset' | 'existing_path' | 'upstream_output';
  label: string;
  root_id: string | null;
  relative_path: string | null;
  absolute_path: string | null;
  upstream_step_id: string | null;
  output_slot_id: string | null;
  binding_mode: 'single' | 'per_sample' | 'dataset';
  dataset_id: string | null;
  path_template: string;
  variables: string[];
  coverage: SamplePathCoverage | null;
  sample_matches: SamplePathMatch[];
  status: 'validated' | 'selected' | 'planned';
  messages: string[];
};

export type ExecutionRecipe = {
  recipe_id: string;
  label: string;
  operation_value: string;
  interface_capability: string;
  interface_method_id: string;
  exposed_parameters: string[];
  steps: Array<{
    id: string;
    title: string;
    capability: string;
    method_id: string;
    fixed_parameters: Record<string, ParameterValue>;
    workspace: string;
  }>;
};

export type MethodOption = {
  id: string;
  skill_id: string;
  label: string;
  description: string;
  runner_id: string;
  execution_mode: 'planning' | 'runner';
  input_types: string[];
  output_types: string[];
  requires_features: string[];
  compatible: boolean;
  blocked_reasons: string[];
  input_warnings?: string[];
  scope_warnings?: string[];
  recommended: boolean;
  recommendation_reason: string;
  parameters: ParameterSpec[];
  input_slots?: InputSlotSpec[];
  output_slots?: OutputSlotSpec[];
  structure_level?: 'profile' | 'evidence' | 'reviewed';
  source_references?: MethodSourceReference[];
  command_references?: CommandReference[];
  delegate_skill_ids?: string[];
  execution_recipe?: ExecutionRecipe | null;
  included_capabilities?: string[];
};

export type WorkflowStep = {
  id: string;
  order: number;
  title: string;
  description: string;
  capability: string;
  origin?: 'requested' | 'dependency';
  selection: 'auto' | 'user';
  depends_on: string[];
  status:
    | 'configured'
    | 'needs_method'
    | 'method_selected'
    | 'parameters_ready'
    | 'parameters_reviewed'
    | 'confirmed';
  method_options: MethodOption[];
  selected_method_id: string | null;
  selected_parameters: Record<string, ParameterValue>;
  input_bindings?: Record<string, InputBinding>;
  manual_input_types?: string[];
  missing_required_inputs?: string[];
  command_preview: string | null;
};

export type DryRunReport = {
  valid: boolean;
  execution_enabled: boolean;
  dataset_path_validated: boolean;
  commands: Array<{
    step_id: string;
    runner_id: string;
    command_preview: string;
    execution_mode: 'planning' | 'runner';
    valid: boolean;
    messages: string[];
  }>;
  warnings: string[];
  checked_at: string;
};

export type Workflow = {
  workflow_id: string;
  template_id: string;
  revision: number;
  title: string;
  summary: string;
  original_request: string;
  status: WorkflowStatus;
  dataset_id: string | null;
  dataset: Dataset | null;
  planner_source: string;
  execution_mode: 'planning' | 'runner' | 'mixed';
  plan_kind: 'atomic' | 'composite';
  requested_capabilities: string[];
  excluded_capabilities?: string[];
  input_capabilities?: string[];
  dependency_policy?: 'target_only' | 'complete';
  steps: WorkflowStep[];
  warnings: string[];
  can_lock: boolean;
  can_unlock: boolean;
  can_review_parameters: boolean;
  can_dry_run: boolean;
  can_confirm: boolean;
  locked_at: string | null;
  parameters_reviewed_at: string | null;
  dry_run_report: DryRunReport | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RunStatus =
  | 'queued'
  | 'running'
  | 'cancel_requested'
  | 'cancelled'
  | 'succeeded'
  | 'failed';

export type RunArtifact = {
  artifact_id: string;
  step_id: string;
  artifact_type: string;
  label: string;
  absolute_path: string;
  relative_path: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  metadata: Record<string, unknown>;
};

export type ExecutionOptions = {
  backend: 'local' | 'slurm';
  partition: string;
  cpus: number;
  memory_gb: number;
  gpus: number;
  time_minutes: number;
  node?: string | null;
  nodes?: NodeAllocation[];
  sample_mode?: 'single' | 'per_sample';
};

export type NodeAllocation = Pick<ExecutionOptions, 'cpus' | 'memory_gb' | 'gpus' | 'time_minutes'> & { node: string };
export type SlurmNode = {
  name: string;
  partition: string;
  state: string;
  schedulable: boolean;
  cpus?: number;
  allocated_cpus?: number;
  memory_mb?: number;
  free_memory_mb?: number;
  gpus: number;
};

export type ExecutionBackends = {
  local: { available: boolean };
  slurm: {
    enabled: boolean;
    available: boolean;
    reason?: string;
    partitions: string[];
    gpu_available: boolean;
    nodes?: SlurmNode[];
  };
};

export type RunStep = {
  step_id: string;
  title: string;
  runner_id: string;
  method_id: string;
  sample_id?: string | null;
  sample_label?: string;
  node_name?: string | null;
  status: 'queued' | 'running' | 'cancelled' | 'succeeded' | 'failed';
  progress: number;
  message: string;
  artifacts: RunArtifact[];
  error_code: string;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  scheduler?: {
    job_id?: string | number;
    state?: string;
    node_list?: string;
    reason?: string;
    [key: string]: unknown;
  };
};

export type WorkflowRun = {
  run_id: string;
  workflow_id: string;
  workflow_revision: number;
  execution?: ExecutionOptions;
  status: RunStatus;
  progress: number;
  current_step_id: string | null;
  output_directory: string;
  plan_snapshot: Record<string, unknown>;
  steps: RunStep[];
  artifacts: RunArtifact[];
  error_code: string;
  error_message: string;
  cancellation_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
};

export type RunEvent = {
  event_id: number;
  event_type: string;
  level: 'info' | 'warning' | 'error';
  message: string;
  progress: number | null;
  step_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};
