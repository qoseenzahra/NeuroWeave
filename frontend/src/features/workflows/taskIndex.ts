import type { Workflow } from './workflowTypes';
import type { AccessInfo } from '../access/authorization';

export type TaskEntry = {
  workflow_id: string;
  title: string;
  status: string;
  updated_at: string;
  run_count: number;
  latest_run_status: string | null;
  source: 'pipeline' | 'conversation';
  dataset_label: string | null;
  workspace_path: string | null;
  /** Server hints for buttons and author/scope labels (Task B). */
  allowed_actions?: string[];
  access?: AccessInfo;
};

/** "My tasks" (managed by me) or "Project tasks" (current project); '' = all visible. */
export type TaskView = '' | 'mine' | 'project';
export function taskFromWorkflow(workflow: Workflow): TaskEntry {
  return {
    workflow_id: workflow.workflow_id, title: workflow.title, status: workflow.status,
    updated_at: workflow.updated_at, run_count: 0, latest_run_status: null,
    source: workflow.planner_source === 'pipeline-library' ? 'pipeline' : 'conversation',
    dataset_label: workflow.dataset?.display_name ?? null,
    workspace_path: workflow.workspace_root_path ?? null
  };
}
export function taskIndexUrl(offset: number, q: string, source: string, status: string, view: TaskView = '') {
  const params = new URLSearchParams({offset: String(offset), q, source, status});
  if (view) params.set('view', view);
  return `/api/workflow-index?${params}`;
}
