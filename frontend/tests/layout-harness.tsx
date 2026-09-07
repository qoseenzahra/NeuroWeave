import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { DatasetPicker } from '../components/dataset/dataset-picker';
import { ArtifactPathPicker } from '../components/dataset/artifact-path-picker';
import { WorkflowCard } from '../components/workflow/workflow-card';
import Page from '../app/page';
import type { Dataset } from '../lib/dataset';
import type { Workflow, InputSlotSpec } from '../lib/workflow';
import '../app/globals.css';

const fixture = (window as unknown as { fixture: { dataset: Dataset; workflow: Workflow; slot: InputSlotSpec } }).fixture;
function Harness() {
  const [selected, setSelected] = useState<Dataset | null>(null);
  const [workflow, setWorkflow] = useState(fixture.workflow);
  const [path, setPath] = useState('');
  return <main className="mx-auto min-w-0 max-w-5xl space-y-4 p-4">
    <div className="flex flex-wrap gap-2">
      <button onClick={() => setWorkflow({ ...fixture.workflow, status: 'awaiting_method_choice', locked_at: null,
        steps: fixture.workflow.steps.map(step => ({ ...step, selected_method_id: null, status: 'needs_method' })) })}>测试方法选择</button>
      <button onClick={() => setWorkflow({ ...fixture.workflow, status: 'awaiting_parameter_review',
        parameters_reviewed_at: null, can_review_parameters: true, confirmed_at: null })}>测试参数审核</button>
      <button onClick={() => setWorkflow(fixture.workflow)}>测试运行设置</button>
      <button onClick={() => setWorkflow({ ...fixture.workflow, workflow_id: 'other-fixture' })}>测试其他流程</button>
    </div>
    <DatasetPicker apiBase="" selectedDataset={selected} onSelected={setSelected} />
    <ArtifactPathPicker apiBase="" disabled={false} dataset={fixture.dataset} workflowId="fixture"
      stepId="step" slot={fixture.slot} onSelected={(_root, value) => setPath(value)} />
    <output data-testid="selected-path">{path}</output>
    <WorkflowCard apiBase="" workflow={workflow} onChange={setWorkflow} />
  </main>;
}
createRoot(document.getElementById('root')!).render(
  new URLSearchParams(window.location.search).get('surface') === 'app' ? <Page /> : <Harness />,
);
