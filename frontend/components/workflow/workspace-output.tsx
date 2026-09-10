'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ServerPath, WorkspacePanel, workspaceApi } from '@/components/workspace-panel';
import type { Workflow } from '@/lib/workflow';

export function WorkspaceOutput({ apiBase, workflow, onChange, disabled }: {
  apiBase: string; workflow: Workflow; onChange: (workflow: Workflow) => void; disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [path, setPath] = useState(workflow.output_relative_path ?? 'outputs');
  const [picker, setPicker] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!workflow.workspace_id || !workflow.workspace_root_path) return null;
  return <div className="mt-2 min-w-0 rounded border border-blue-100 bg-blue-50/60 p-2 text-xs">
    <div className="flex flex-wrap items-center justify-between gap-1"><span>工作区输出（每次运行创建独立子目录）</span>
      <Button size="sm" variant="ghost" disabled={disabled || workflow.status === 'confirmed'} onClick={() => { setPath(workflow.output_relative_path ?? 'outputs'); setEditing(v => !v); }}>调整</Button></div>
    <ServerPath path={`${workflow.workspace_root_path}/${workflow.output_relative_path ?? 'outputs'}`} label={`${workflow.output_relative_path ?? 'outputs'}/<运行 ID>`} />
    {editing && <form className="space-y-2" onSubmit={e => { e.preventDefault(); setBusy(true); setError('');
      void workspaceApi<Workflow>(apiBase, `/api/workflows/${workflow.workflow_id}/output`, {
        expected_revision: workflow.revision, relative_path: path,
      }, 'PATCH').then(value => { onChange(value); setEditing(false); }).catch(err => setError(String(err))).finally(() => setBusy(false));
    }}>
      <input aria-label="工作区相对输出目录" className="w-full min-w-0 rounded border bg-white p-2" value={path} onChange={e => setPath(e.target.value)} />
      <div className="flex flex-wrap gap-2"><Button size="sm" type="button" variant="outline" onClick={() => setPicker(true)}>浏览工作区目录</Button><Button size="sm" type="submit" disabled={busy || disabled}>保存</Button></div>
    </form>}
    {error && <p role="alert" className="break-words text-red-700">{error}</p>}
    {picker && <WorkspacePanel apiBase={apiBase} workspaceId={workflow.workspace_id} conversationId={null}
      onSelect={async () => {}} onClose={() => setPicker(false)} onPick={entry => {
        if (entry.type !== 'directory') { setError('请选择文件夹'); return; }
        setPath(entry.relative_path); setPicker(false);
      }} />}
  </div>;
}
