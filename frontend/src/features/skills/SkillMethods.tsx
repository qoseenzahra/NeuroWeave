import { useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { Button } from '../../ui/Button';
import { useLanguageStore } from '../../stores/languageStore';
import { fetchSkillMethods, fetchSkillMethod, fetchSkillReference } from './skillsApi';
import type { SkillMethodSummary } from './skillsApi';

export function SkillMethods({ skillId }: { skillId: string }) {
  const zh = useLanguageStore(s => s.language) === 'zh';
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<SkillMethodSummary | null>(null);
  const query = useInfiniteQuery({ queryKey: ['skill-methods', skillId, search], initialPageParam: '',
    queryFn: ({ pageParam, signal }) => fetchSkillMethods(skillId, search, pageParam, signal),
    getNextPageParam: page => page.next_cursor ?? undefined, staleTime: 60_000 });
  if (selected) return <SkillMethodDetail method={selected} onBack={() => setSelected(null)} />;
  return <section className="mt-3 min-w-0 space-y-3">
    <p className="text-meta text-muted">{zh ? '按需查看方法，不一次加载全部参数。具有执行契约不代表当前环境可用；详情列出实际支持范围。' : 'Open one method at a time. An execution contract does not guarantee runtime availability; details show the supported scope.'}</p>
    <input aria-label={zh ? '搜索命令或方法' : 'Search commands or methods'} value={search} onChange={e => setSearch(e.target.value)}
      placeholder={zh ? '命令名、方法名或用途' : 'Command, method or purpose'} className="w-full rounded-control border border-line px-3 py-2" />
    {query.isPending && <p role="status">{zh ? '正在读取方法目录…' : 'Loading methods…'}</p>}
    {query.isError && <p role="alert">{query.error.message}<Button onClick={() => void query.refetch()}>{zh ? '重试' : 'Retry'}</Button></p>}
    {query.data && <p className="text-meta text-subtle">{query.data.pages[0].total} {zh ? '个方法' : 'methods'}</p>}
    <ul className="space-y-2">{query.data?.pages.flatMap(page => page.items).map(method => <li key={`${method.capability}/${method.method_id}`}>
      <button type="button" onClick={() => setSelected(method)} className="w-full min-w-0 rounded-control border border-line p-3 text-left hover:bg-well focus-visible:outline-2">
        <span className="block break-words font-medium">{method.label}</span>
        <code className="block break-all text-meta text-subtle">{method.runner_id}</code>
        <span className="mt-1 block text-meta">{method.execution_mode === 'runner' ? (zh ? '已登记执行入口' : 'Registered runner') : (zh ? '规划条目' : 'Planning entry')}
          {' · '}{method.input_count} {zh ? '输入' : 'inputs'} · {method.output_count} {zh ? '输出' : 'outputs'} · {method.parameter_count} {zh ? '参数' : 'parameters'}</span>
        <span className="mt-1 block break-words text-meta text-muted">{method.description}</span>
      </button>
    </li>)}</ul>
    {query.hasNextPage && <Button onClick={() => void query.fetchNextPage()} loading={query.isFetchingNextPage}>{zh ? '加载更多' : 'Load more'}</Button>}
  </section>;
}

function SkillMethodDetail({ method, onBack }: { method: SkillMethodSummary; onBack: () => void }) {
  const zh = useLanguageStore(s => s.language) === 'zh';
  const [filter, setFilter] = useState('');
  const query = useQuery({queryKey:['skill-method', method.capability, method.method_id],
    queryFn: ({signal}) => fetchSkillMethod(method.capability, method.method_id, signal), staleTime:60_000});
  const data = query.data;
  return <section className="mt-3 min-w-0 space-y-3">
    <Button variant="outline" onClick={onBack}><ArrowLeft aria-hidden="true"/>{zh ? '返回方法目录' : 'Back to methods'}</Button>
    {query.isPending && <p role="status">{zh ? '读取方法详情…' : 'Loading method…'}</p>}
    {query.isError && <p role="alert">{query.error.message}<Button onClick={() => void query.refetch()}>{zh ? '重试' : 'Retry'}</Button></p>}
    {data && <>
      <p className="font-semibold">{data.label}</p><p className="break-words text-meta">{data.description}</p>
      <p className="rounded-control bg-well p-3 text-meta">{data.runtime_status.available ? (zh ? '当前入口探测可用' : 'Runtime probe available') : (zh ? '当前入口不可用' : 'Runtime unavailable')}：{data.runtime_status.reason || '—'}</p>
      <p className="text-meta text-muted">{zh ? '以下为平台已登记的参数与输入输出，不代表原软件全部选项。实际运行前仍须检查数据、计算节点和 Dry-run。' : 'These are registered parameters and ports, not necessarily every upstream option. Data, target nodes and dry-run still require validation.'}</p>
      {data.command_coverage && <p className="text-meta">{zh ? '命令选项覆盖' : 'Command option coverage'}：{data.command_coverage.exposed} {zh ? '已开放' : 'exposed'} / {data.command_coverage.total} {zh ? '原始选项' : 'upstream options'}
        {data.command_coverage.omitted.length > 0 && <span className="block break-words">{zh ? '由平台管理或尚未接入：' : 'Managed or unsupported: '}{data.command_coverage.omitted.join(', ')}</span>}</p>}
      {[{title: zh ? '输入' : 'Inputs', items:data.input_slots}, {title:zh ? '输出' : 'Outputs',items:data.output_slots}].map(group =>
        <div key={group.title}><p className="mb-2 font-medium">{group.title}</p><ul className="space-y-2">{group.items.map(slot => <li key={slot.id} className="rounded-control border border-line p-2 text-meta">
          <b>{slot.label}</b> <code>{slot.id}</code><p className="break-words">{slot.description}</p><p>{slot.type}</p>
          {'required' in slot && <p>{slot.required ? (zh ? '必填' : 'Required') : (zh ? '可选 / 按条件启用' : 'Optional / conditional')}</p>}
          {'required_when' in slot && Object.keys(slot.required_when).length > 0 && <p>{zh ? '必填条件：' : 'Required when: '}{JSON.stringify(slot.required_when)}</p>}
          {'generated_when' in slot && Object.keys(slot.generated_when).length > 0 && <p>{zh ? '生成条件：' : 'Generated when: '}{JSON.stringify(slot.generated_when)}</p>}
        </li>)}</ul></div>)}
      <input aria-label={zh ? '筛选参数' : 'Filter parameters'} value={filter} onChange={e => setFilter(e.target.value)}
        placeholder={zh ? '搜索参数名或说明' : 'Search parameter name or description'} className="w-full rounded-control border border-line px-3 py-2"/>
      {data.parameters.filter(p => `${p.id} ${p.argument} ${p.label} ${p.description}`.toLowerCase().includes(filter.toLowerCase())).map(p => <details key={p.id} className="min-w-0 rounded-control border border-line p-3">
        <summary className="cursor-pointer break-words">{p.label} <code className="text-meta">{p.argument}</code> · {p.required ? (zh ? '必填' : 'Required') : Object.keys(p.required_when ?? {}).length ? (zh ? '条件必填' : 'Conditionally required') : (zh ? '可选' : 'Optional')}</summary>
        <div className="mt-2 space-y-2 break-words text-meta"><p>{p.description || (zh ? '使用说明待补充；请核对原始参考文档。' : 'Usage needs review; consult the original reference.')}</p>
          <p>{p.type}{p.unit ? ` · ${p.unit}` : ''} · {zh ? '平台默认值：' : 'Platform default: '}{p.default === null ? (zh ? '不显式传入' : 'Not passed') : String(p.default)}</p>
          {p.software_default && <p>{zh ? '软件默认行为：' : 'Software default: '}{p.software_default}</p>}
          {(p.minimum != null || p.maximum != null) && <p>{zh ? '允许范围：' : 'Allowed range: '}{p.minimum ?? '−∞'} … {p.maximum ?? '∞'}</p>}
          {p.options.length > 0 && <ul>{p.options.map(o => <li key={String(o.value)}><code>{String(o.value)}</code>：{o.description || o.label}</li>)}</ul>}
          {p.condition_help && <p>{p.condition_help}</p>}{p.usage && <p className="whitespace-pre-wrap">{p.usage}</p>}
          {(['visible_when','required_when','enabled_when'] as const).map(key => p[key] && Object.keys(p[key]!).length > 0 && <p key={key}><code>{key}</code>：{JSON.stringify(p[key])}</p>)}
          {!!p.conflicts_with?.length && <p>{zh ? '不能同时设置：' : 'Conflicts with: '}{p.conflicts_with.join(', ')}</p>}
          {p.documentation_url && /^https?:\/\//.test(p.documentation_url) && <a className="text-accent underline" href={p.documentation_url} target="_blank" rel="noreferrer">{zh ? '官方文档' : 'Official documentation'}</a>}
        </div>
      </details>)}
      <details><summary className="cursor-pointer text-meta">{zh ? '定义来源与版本' : 'Definition sources and revision'}</summary>
        <code className="block break-all text-micro">{data.definition_revision}</code>
        <ul className="text-meta">{data.source_references.map((s,i) => <li className="break-all" key={i}>{s.label}：{s.path}</li>)}</ul>
      </details>
    </>}
  </section>;
}

export function SkillReference({skillId}: {skillId:string}) {
  const zh = useLanguageStore(s => s.language) === 'zh';
  const [offset,setOffset] = useState(0);
  const query = useQuery({queryKey:['skill-reference',skillId,offset],
    queryFn:({signal})=>fetchSkillReference(skillId,offset,signal),staleTime:60_000});
  return <section className="mt-3 space-y-3">
    {query.isPending && <p role="status">{zh ? '读取参考文档…' : 'Loading reference…'}</p>}
    {query.isError && <p role="alert">{query.error.message}<Button onClick={()=>void query.refetch()}>{zh?'重试':'Retry'}</Button></p>}
    {query.data && <><p className="text-meta text-subtle">{offset}–{offset+query.data.text.length} / {query.data.total_chars}</p>
      <pre className="whitespace-pre-wrap break-words rounded-control border border-line bg-well p-3 text-meta leading-6">{query.data.text}</pre>
      <div className="flex flex-wrap gap-2"><Button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-6000))}>{zh?'上一页':'Previous'}</Button>
        <Button disabled={!query.data.truncated} onClick={()=>setOffset(query.data!.next_offset!)}>{zh?'下一页':'Next'}</Button></div></>}
  </section>;
}
