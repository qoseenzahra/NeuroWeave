import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { adoptConflict } from '../workflows/useWorkflows';
import { useLanguageStore } from '../../stores/languageStore';
import { getTranslations } from '../../lib/i18n';
import type { Workflow } from '../workflows/workflowTypes';
import { saveWorkflowOutput } from './workspaceApi';
import type { FsEntry } from './workspaceTypes';
import { ServerPath } from './ServerPath';
import { WorkspacePanel } from './WorkspacePanel';

export function WorkspaceOutput({
  workflow,
  onChange,
  disabled
}: {
  workflow: Workflow;
  onChange: (workflow: Workflow) => void;
  disabled?: boolean;
}) {
  const language = useLanguageStore((s) => s.language);
  const t = getTranslations(language);
  const [editing, setEditing] = useState(false);
  const [path, setPath] = useState(workflow.output_relative_path ?? 'outputs');
  const [picker, setPicker] = useState(false);
  const [error, setError] = useState('');
  const client = useQueryClient();
  const save = useMutation({
    mutationKey: ['workflow-change', workflow.workflow_id, 'output'],
    mutationFn: () => saveWorkflowOutput(workflow.workflow_id, path, workflow.revision),
    onSuccess: value => { onChange(value); setEditing(false); },
    onError: error => { adoptConflict(client, error); setError(String(error)); },
  });
  const busy = save.isPending;
  if (!workflow.workspace_id || !workflow.workspace_root_path) return null;
  return (
    <div className="mt-2 min-w-0 rounded border border-accent-line bg-accent-quiet p-2 text-xs dark:border-accent-line ">
      <div className="flex flex-wrap items-center justify-between gap-1">
        <span>{t.workspaceOutputTitle}</span>
        <button
          type="button"
          className="rounded-control border border-line px-2 py-1 "
          disabled={disabled || workflow.status === 'confirmed'}
          onClick={() => {
            setPath(workflow.output_relative_path ?? 'outputs');
            setEditing((v) => !v);
          }}
        >
          {t.workspaceOutputAdjust}
        </button>
      </div>
      <ServerPath
        path={`${workflow.workspace_root_path}/${workflow.output_relative_path ?? 'outputs'}`}
        label={`${workflow.output_relative_path ?? 'outputs'}/<run_id>`}
      />
      {editing && (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (disabled || workflow.status === 'confirmed' || busy) return;
            setError('');
            save.mutate();
          }}
        >
          <input
            aria-label={t.workspaceOutputAria}
            className="w-full min-w-0 rounded border border-line bg-raised p-2 "
            value={path}
            onChange={(e) => setPath(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-control border border-line px-2.5 py-1.5 text-xs "
              onClick={() => setPicker(true)}
            >
              {t.workspaceOutputBrowse}
            </button>
            <button
              type="submit"
              disabled={busy || disabled}
              className="rounded-control bg-accent-solid px-2.5 py-1.5 text-xs font-medium text-on-accent hover:bg-accent-solid-hover disabled:opacity-50"
            >
              {t.workspaceOutputSave}
            </button>
          </div>
        </form>
      )}
      {error && (
        <p role="alert" className="break-words text-danger">
          {error}
        </p>
      )}
      {picker && (
        <WorkspacePanel
          workspaceId={workflow.workspace_id}
          conversationId={null}
          onSelect={async () => undefined}
          onClose={() => setPicker(false)}
          onPick={(entry: FsEntry) => {
            if (entry.type !== 'directory') {
              setError(t.workspacePickMustBeFolder);
              return;
            }
            setPath(entry.relative_path);
            setPicker(false);
          }}
        />
      )}
    </div>
  );
}
