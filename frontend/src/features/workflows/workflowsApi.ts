import { workflowReads } from '../../api/requestQueue';
import { request } from '../../api/http';
import { runOperation } from '../../api/operations';
import type { OperationView } from '../../api/operations';
import type {
  DatasetPathPreview,
  SamplePathCoverage,
  SamplePathMatch
} from '../datasets/datasetsApi';
import type {
  ExecutionBackends,
  ExecutionDraft,
  ExecutionOptions,
  ParameterValue,
  Workflow
} from './workflowTypes';

export type HistoryCandidate = {
  run_id: string;
  group_id: string;
  run_title: string;
  run_status: string;
  created_at: string;
  step_title: string;
  label: string;
  sample_count: number;
  artifact_count: number;
};

export type HistoryPage = {
  candidates: HistoryCandidate[];
  has_more: boolean;
  next_offset: number;
};

export type HistoryPreview = {
  run_id: string;
  group_id: string;
  coverage: SamplePathCoverage;
  matches: SamplePathMatch[];
  can_apply: boolean;
  messages: string[];
  partial?: boolean;
};

function workflowPath(workflowId: string): string {
  return `/api/workflows/${encodeURIComponent(workflowId)}`;
}

function stepPath(workflowId: string, stepId: string): string {
  return `${workflowPath(workflowId)}/steps/${encodeURIComponent(stepId)}`;
}

function post(path: string, body: Record<string, unknown>): Promise<Workflow> {
  return request<Workflow>(path, { method: 'POST', body: JSON.stringify(body) });
}

export function fetchWorkflow(workflowId: string, signal?: AbortSignal): Promise<Workflow> {
  return workflowReads(() => request<Workflow>(workflowPath(workflowId), { signal }), signal);
}

export function patchWorkflowDataset(
  workflowId: string,
  datasetId: string,
  expectedRevision: number
): Promise<Workflow> {
  return request<Workflow>(`${workflowPath(workflowId)}/dataset`, {
    method: 'PATCH',
    body: JSON.stringify({ dataset_id: datasetId, expected_revision: expectedRevision })
  });
}

export function patchStepMethod(
  workflowId: string,
  stepId: string,
  methodId: string,
  expectedRevision: number
): Promise<Workflow> {
  return request<Workflow>(`${stepPath(workflowId, stepId)}/method`, {
    method: 'PATCH',
    body: JSON.stringify({ method_id: methodId, expected_revision: expectedRevision })
  });
}

export function patchStepParameters(
  workflowId: string,
  stepId: string,
  parameters: Record<string, ParameterValue>,
  expectedRevision: number
): Promise<Workflow> {
  return request<Workflow>(`${stepPath(workflowId, stepId)}/parameters`, {
    method: 'PATCH',
    body: JSON.stringify({ parameters, expected_revision: expectedRevision })
  });
}

export function bindStepInput(
  workflowId: string,
  stepId: string,
  slotId: string,
  rootId: string,
  relativePath: string,
  expectedRevision: number
): Promise<Workflow> {
  return request<Workflow>(`${stepPath(workflowId, stepId)}/inputs/${encodeURIComponent(slotId)}`, {
    method: 'PATCH',
    body: JSON.stringify({
      root_id: rootId,
      relative_path: relativePath,
      expected_revision: expectedRevision
    })
  });
}

export function bindStepHistoryInput(
  workflowId: string,
  stepId: string,
  slotId: string,
  input: { runId: string; groupId: string; allowPartial: boolean },
  expectedRevision: number
): Promise<Workflow> {
  return post(`${stepPath(workflowId, stepId)}/inputs/${encodeURIComponent(slotId)}/history`, {
    run_id: input.runId,
    group_id: input.groupId,
    allow_partial: input.allowPartial,
    expected_revision: expectedRevision
  });
}

export function previewStepInputPath(
  workflowId: string,
  stepId: string,
  slotId: string,
  rootId: string,
  relativePath: string,
  signal?: AbortSignal
): Promise<DatasetPathPreview> {
  return request<DatasetPathPreview>(
    `${stepPath(workflowId, stepId)}/inputs/${encodeURIComponent(slotId)}/preview`,
    {
      method: 'POST',
      body: JSON.stringify({ root_id: rootId, relative_path: relativePath }),
      signal
    }
  );
}

export function fetchInputHistory(
  workflowId: string,
  stepId: string,
  slotId: string,
  offset: number,
  signal?: AbortSignal
): Promise<HistoryPage> {
  return request<HistoryPage>(
    `${stepPath(workflowId, stepId)}/inputs/${encodeURIComponent(slotId)}/history?offset=${offset}`,
    { signal }
  );
}

export function previewInputHistory(
  workflowId: string,
  stepId: string,
  slotId: string,
  input: { runId: string; groupId: string; expectedRevision: number },
  signal?: AbortSignal
): Promise<HistoryPreview> {
  return request<HistoryPreview>(
    `${stepPath(workflowId, stepId)}/inputs/${encodeURIComponent(slotId)}/history/preview`,
    {
      method: 'POST',
      body: JSON.stringify({
        run_id: input.runId,
        group_id: input.groupId,
        expected_revision: input.expectedRevision
      }),
      signal
    }
  );
}

export function removeStep(
  workflowId: string,
  stepId: string,
  expectedRevision: number
): Promise<Workflow> {
  return post(`${stepPath(workflowId, stepId)}/remove`, {
    expected_revision: expectedRevision
  });
}

export function completeDependencies(
  workflowId: string,
  expectedRevision: number
): Promise<Workflow> {
  return post(`${workflowPath(workflowId)}/complete-dependencies`, {
    expected_revision: expectedRevision
  });
}

export type WorkflowLifecycleAction =
  'replan' | 'lock' | 'unlock' | 'review-parameters' | 'confirm';

export function runWorkflowLifecycleAction(
  workflowId: string,
  action: WorkflowLifecycleAction,
  expectedRevision: number
): Promise<Workflow> {
  return post(`${workflowPath(workflowId)}/${action}`, {
    expected_revision: expectedRevision
  });
}

export function runDryRun(
  workflowId: string,
  expectedRevision: number,
  handlers: {
    onProgress?: (operation: OperationView) => void;
    signal?: AbortSignal;
  } = {}
): Promise<Workflow> {
  return runOperation<Workflow>(
    `${workflowPath(workflowId)}/dry-run-jobs`,
    { method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }) },
    handlers
  );
}

export function fetchExecutionDraft(
  workflowId: string,
  signal?: AbortSignal
): Promise<ExecutionDraft> {
  return request<ExecutionDraft>(`${workflowPath(workflowId)}/execution-draft`, { signal });
}

export function saveExecutionDraft(
  workflowId: string,
  input: {
    expectedRevision: number;
    expectedDraftRevision: number;
    execution: ExecutionOptions;
  }
): Promise<ExecutionDraft> {
  return request<ExecutionDraft>(`${workflowPath(workflowId)}/execution-draft`, {
    method: 'PUT',
    keepalive: true,
    body: JSON.stringify({
      expected_revision: input.expectedRevision,
      expected_draft_revision: input.expectedDraftRevision,
      execution: input.execution
    })
  });
}

export function fetchExecutionBackends(signal?: AbortSignal): Promise<ExecutionBackends> {
  return request<ExecutionBackends>('/api/execution/backends', { signal });
}
