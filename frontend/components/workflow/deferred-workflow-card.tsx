'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { WorkflowCard } from './workflow-card';
import { loadWorkflow } from '@/lib/load-workflow';
import type { Workflow } from '@/lib/workflow';

export function DeferredWorkflowCard({ apiBase, workflowId, disabled, onChange, onBusyChange }: {
  apiBase: string; workflowId: string; disabled?: boolean;
  onChange: (workflow: Workflow) => void; onBusyChange: (id: string, busy: boolean) => void;
}) {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const open = async () => {
    setLoading(true);
    setError('');
    try { setWorkflow(await loadWorkflow(apiBase, workflowId)); setExpanded(true); }
    catch (failure) { setError(failure instanceof Error ? failure.message : '无法读取流程'); }
    finally { setLoading(false); }
  };
  return <div className="mt-3 min-w-0">
    <Button size="sm" variant="outline" disabled={loading || busy || disabled}
      onClick={() => expanded ? setExpanded(false) : void open()}>
      {loading ? '正在读取流程…' : expanded ? '收起历史流程' : '展开历史流程'}
    </Button>
    {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    {expanded && workflow && <WorkflowCard apiBase={apiBase} workflow={workflow} disabled={disabled}
      onChange={value => { setWorkflow(value); onChange(value); }}
      onBusyChange={(id, value) => { setBusy(value); onBusyChange(id, value); }} />}
  </div>;
}
