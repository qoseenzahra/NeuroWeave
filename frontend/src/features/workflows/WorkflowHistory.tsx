import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request, errorText } from '../../api/http';
import { stateText } from '../../lib/stateText';
import { ui } from '../../lib/libraryText';
import { taskIndexUrl } from './taskIndex';
import type { TaskEntry } from './taskIndex';

export function WorkflowHistory({selectedId, onSelect}: {
  selectedId: string | null; onSelect: (task: TaskEntry) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState('');
  const [source, setSource] = useState('');
  const [status, setStatus] = useState('');
  const list = useQuery({queryKey: ['workflow-index', offset, q, source, status],
    queryFn: () => request<{items: TaskEntry[]; has_more: boolean}>(taskIndexUrl(offset,q,source,status)),
    refetchInterval: 5000});
  const field = 'w-full min-w-0 rounded border border-line bg-raised p-2';
  return <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3 text-xs">
    <input aria-label={ui('搜索任务')} placeholder={ui('搜索任务')} value={q}
      onChange={e => {setQ(e.target.value);setOffset(0);}} className={field}/>
    <div className="grid grid-cols-2 gap-2">
      <select aria-label={ui('任务来源')} className={field} value={source}
        onChange={e => {setSource(e.target.value);setOffset(0);}}>
        <option value="">{ui('全部来源')}</option>
        <option value="conversation">{ui('对话')}</option><option value="pipeline">Pipeline</option>
      </select>
      <select aria-label={ui('任务状态')} className={field} value={status}
        onChange={e => {setStatus(e.target.value);setOffset(0);}}>
        <option value="">{ui('全部状态')}</option><option value="draft">{ui('待执行')}</option>
        <option value="active">{ui('执行中')}</option><option value="succeeded">{stateText('succeeded')}</option>
        <option value="failed">{stateText('failed')}</option><option value="cancelled">{stateText('cancelled')}</option>
      </select>
    </div>
    {list.isError && <p role="alert" className="text-danger">{errorText(list.error,ui('读取任务列表失败'))}</p>}
    {list.isPending && <p role="status">{ui('正在读取任务…')}</p>}
    {list.data?.items.map(task => <button key={task.workflow_id} aria-current={selectedId===task.workflow_id ? 'true' : undefined}
      className={`block w-full space-y-1 rounded border p-3 text-left hover:bg-hover ${selectedId===task.workflow_id?'border-accent-line bg-selected':'border-line'}`}
      onClick={() => onSelect(task)}>
      <strong className="break-words">{task.title}</strong>
      <p>{task.source==='pipeline'?'Pipeline':ui('对话')} · {stateText(task.latest_run_status ?? task.status)}</p>
      {task.dataset_label && <p className="truncate text-subtle">{task.dataset_label}</p>}
      <p className="text-subtle">{task.run_count} {ui('次运行')} · {new Date(task.updated_at).toLocaleString()}</p>
    </button>)}
    {!list.isPending && !list.isError && !list.data?.items.length && <p>{ui('暂无任务')}</p>}
    <div className="flex justify-between">
      <button disabled={!offset || list.isFetching} onClick={()=>setOffset(v=>Math.max(0,v-30))}>{ui('上一页')}</button>
      <button disabled={!list.data?.has_more || list.isFetching} onClick={()=>setOffset(v=>v+30)}>{ui('下一页')}</button>
    </div>
  </div>;
}
