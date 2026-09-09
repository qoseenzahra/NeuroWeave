import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { HistoricalInputPicker } from '../components/dataset/historical-input-picker';
import { SampleScopeNotice } from '../components/workflow/sample-scope-notice';
import '../app/globals.css';

function Harness() {
  const [scenario, setScenario] = useState('complete');
  const [selected, setSelected] = useState('');
  return <main className="min-w-0 space-y-4 p-4">
    <h1>历史结果输入 · 合成数据交互验证</h1>
    <div className="flex flex-wrap gap-2">
      <button onClick={() => { setScenario('complete'); setSelected(''); }}>测试完整输出</button>
      <button onClick={() => { setScenario('missing'); setSelected(''); }}>测试缺失输出</button>
      <button onClick={() => { setScenario('empty'); setSelected(''); }}>测试零匹配</button>
    </div>
    <HistoricalInputPicker key={scenario} apiBase="" workflowId={scenario}
      revision={1} stepId="track" slotId="five_tt" slotLabel="已有 5TT 影像"
      disabled={false} onSelected={(runId, groupId, allowPartial) => setSelected(runId + ' / ' + groupId + ' / allow_partial=' + allowPartial)} />
    <output>应用结果：{selected || '尚未应用'}</output>
    {selected && scenario === 'missing' && <SampleScopeNotice scope={{ total: 63,
      eligible_sample_ids: Array.from({ length: 62 }, (_, i) => 'sample-' + i),
      skipped_samples: [{ sample_id: 'sample-62', label: 'Synthetic sample 62', reasons: ['5TT：此样本没有成功的历史输出'] }],
    }} />}
  </main>;
}
createRoot(document.getElementById('root')!).render(<Harness />);
