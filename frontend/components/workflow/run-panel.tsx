'use client';

import { useMemo, useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleAlert, FileText, LoaderCircle, Terminal, TriangleAlert } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';
import { filterRunGroups, groupRunSteps, monitorPage, STEP_STATUS_COPY } from '@/lib/run-monitor';
import type { MonitorFilter, MonitorStatus } from '@/lib/run-monitor';
import type { RunArtifact, RunEvent, RunStep, WorkflowRun } from '@/lib/workflow';

const RUN_STATUS_COPY: Record<WorkflowRun['status'], string> = {
  queued: '等待运行', running: '正在运行', cancel_requested: '正在取消',
  cancelled: '已取消', succeeded: '运行成功', failed: '运行失败',
};
const SCHEDULER_STATUS_COPY: Record<string, string> = {
  PENDING: '排队中', CONFIGURING: '正在分配资源', RUNNING: '正在计算',
  COMPLETING: '正在结束', COMPLETED: '已完成', CANCELLED: '已取消',
  FAILED: '失败', TIMEOUT: '超出时限', OUT_OF_MEMORY: '内存不足',
  NODE_FAIL: '节点故障', PREEMPTED: '被抢占', SUSPENDED: '已暂停',
};
const STATUS_STYLE: Record<MonitorStatus, string> = {
  queued: 'bg-slate-100 text-slate-600', running: 'bg-blue-100 text-blue-800',
  succeeded: 'bg-emerald-100 text-emerald-800', failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-amber-100 text-amber-800',
};
const FILTERS: MonitorFilter[] = ['all', 'running', 'failed', 'queued', 'succeeded', 'cancelled'];

function Pagination({ page, pages, total, label, onChange }: {
  page: number; pages: number; total: number; label: string; onChange: (page: number) => void;
}) {
  return <nav aria-label={label} className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
    <span>共 {total} 项 · 第 {page + 1} / {pages} 页</span>
    <div className="flex gap-1">
      <Button aria-label={`${label}上一页`} disabled={page === 0} onClick={() => onChange(page - 1)} size="sm" variant="outline">
        <ChevronLeft />上一页
      </Button>
      <Button aria-label={`${label}下一页`} disabled={page + 1 >= pages} onClick={() => onChange(page + 1)} size="sm" variant="outline">
        下一页<ChevronRight />
      </Button>
    </div>
  </nav>;
}

function StepDetails({ step }: { step: RunStep }) {
  return <div className="min-w-0 border-t border-slate-100 px-3 py-2 text-xs">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="font-medium text-slate-800">{step.title}</span>
      <span className="text-slate-600">{STEP_STATUS_COPY[step.status]} · {Math.round(step.progress)}%</span>
    </div>
    {step.message && <p className="mt-1 text-slate-600">{step.message}</p>}
    {step.scheduler?.job_id && <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-blue-700">
      <span className="font-mono">Job {step.scheduler.job_id}</span>
      {step.scheduler.state && <span>{SCHEDULER_STATUS_COPY[step.scheduler.state.toUpperCase()] ?? step.scheduler.state}</span>}
      {(step.scheduler.node_list || step.node_name) && <span>节点：{step.scheduler.node_list || step.node_name}</span>}
      {step.scheduler.reason && <span>原因：{step.scheduler.reason}</span>}
    </div>}
    {step.error_message && <p className="mt-1 text-red-700">{step.error_message}</p>}
  </div>;
}

function OutputFiles({ artifacts }: { artifacts: RunArtifact[] }) {
  const [query, setQuery] = useState('');
  const [requestedPage, setPage] = useState(0);
  const term = query.trim().toLocaleLowerCase();
  const matches = artifacts.filter(item => !term ||
    `${item.label} ${item.absolute_path}`.toLocaleLowerCase().includes(term));
  const { items, page, pages } = monitorPage(matches, requestedPage);
  return <details className="group/output mt-3 min-w-0 rounded-lg border border-emerald-200 bg-emerald-50">
    <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium text-emerald-800 focus-visible:outline-2 focus-visible:outline-blue-500 [&::-webkit-details-marker]:hidden">
      <FileText className="size-4 shrink-0" />
      <span className="min-w-0 flex-1">输出文件（{artifacts.length}）</span>
      <ChevronDown className="size-4 shrink-0 group-open/output:rotate-180" />
    </summary>
    <div className="min-w-0 border-t border-emerald-200 p-3">
      <Input aria-label="筛选输出文件" placeholder="搜索文件名称或路径" value={query}
        onChange={event => { setQuery(event.target.value); setPage(0); }} />
      <div className="mt-2 max-h-64 overflow-y-auto overscroll-contain">
        {items.map(artifact => <div className="min-w-0 border-b border-emerald-100 py-2 last:border-0" key={artifact.artifact_id}>
          <p className="text-sm font-medium text-slate-800">{artifact.label}</p>
          <p className="break-all font-mono text-xs text-slate-600">{artifact.absolute_path}</p>
          {artifact.sha256 && <p className="break-all font-mono text-xs text-slate-500">SHA-256 {artifact.sha256}</p>}
        </div>)}
        {!items.length && <p className="py-3 text-sm text-slate-500">没有匹配的输出文件。</p>}
      </div>
      <Pagination page={page} pages={pages} total={matches.length} label="输出文件分页" onChange={setPage} />
    </div>
  </details>;
}

export function RunPanel({ events, run }: { events: RunEvent[]; run: WorkflowRun }) {
  return <RunPanelContent key={run.run_id} events={events} run={run} />;
}

function RunPanelContent({ events, run }: { events: RunEvent[]; run: WorkflowRun }) {
  const active = ['queued', 'running', 'cancel_requested'].includes(run.status);
  const groups = useMemo(() => groupRunSteps(run.steps), [run.steps]);
  // Pick the initial view once. Polling must not reset the user's filter or page.
  const [filter, setFilter] = useState<MonitorFilter>(() =>
    groups.some(group => group.status === 'failed') ? 'failed'
      : groups.some(group => group.status === 'running') ? 'running' : 'all');
  const [query, setQuery] = useState('');
  const [requestedPage, setPage] = useState(0);
  const counts = { all: groups.length, running: 0, failed: 0, queued: 0, succeeded: 0, cancelled: 0 };
  groups.forEach(group => { counts[group.status] += 1; });
  const filtered = filterRunGroups(groups, filter, query);
  const { items, page, pages } = monitorPage(filtered, requestedPage);
  // A shrinking live filter can remove the last page. Keep the clamped page
  // instead of jumping back when more samples enter this filter later.
  if (page !== requestedPage) setPage(page);
  const samples = groups.some(group => group.sampleId);
  const recentEvents = events.filter(event => event.message).slice(-8);

  return <section aria-label="运行监控" className="min-w-0 wrap-anywhere rounded-xl border border-blue-100 bg-blue-50/40 p-3 sm:p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {active ? <LoaderCircle className="size-4 animate-spin text-blue-600" />
          : run.status === 'succeeded' ? <CheckCircle2 className="size-4 text-emerald-600" />
            : <CircleAlert className="size-4 text-amber-600" />}
        <h3 className="text-sm font-semibold text-slate-900">{RUN_STATUS_COPY[run.status]}</h3>
        <Badge variant="outline" className="rounded-md bg-white font-mono text-xs">{run.run_id.slice(0, 12)}</Badge>
        {run.execution?.backend === 'slurm' && <Badge variant="outline" className="rounded-md bg-white text-xs">
          Slurm · {run.execution.partition}
        </Badge>}
      </div>
      <span className="text-xs tabular-nums text-slate-600">
        {counts.succeeded} / {groups.length} {samples ? '样本' : '步骤'}已完成
      </span>
    </div>
    {run.execution?.sample_mode === 'per_sample' && <p className="mt-2 text-xs text-slate-600">
      并行样本上限：{run.execution.nodes?.map(node => `${node.node}：${node.parallel_samples ?? 1}`).join(' · ')}
    </p>}
    <Progress className="mt-3" value={run.progress}>
      <ProgressLabel className="text-xs text-slate-600">流程进度</ProgressLabel>
      <ProgressValue className="text-xs" />
    </Progress>

    <fieldset aria-label={samples ? '样本状态筛选' : '步骤状态筛选'} className="mt-3 flex min-w-0 flex-wrap gap-1.5">
      {FILTERS.map(status => <Button key={status} aria-pressed={filter === status}
        className={status === 'failed' && counts.failed > 0 ? 'border-red-200 text-red-700' : ''}
        onClick={() => { setFilter(status); setPage(0); }} size="sm" variant={filter === status ? 'secondary' : 'outline'}>
        {status === 'all' ? '全部' : STEP_STATUS_COPY[status]} {counts[status]}
      </Button>)}
    </fieldset>
    <Input className="mt-2" aria-label="筛选运行任务" placeholder={samples ? '搜索样本、节点或 Job ID' : '搜索步骤、节点或 Job ID'}
      value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} />

    <section aria-label={samples ? '样本任务列表' : '步骤任务列表'}
      className="mt-2 max-h-96 min-w-0 space-y-1.5 overflow-y-auto overscroll-contain rounded-lg">
      {items.map(group => {
        const current = group.steps.find(step => step.status === 'failed')
          || group.steps.find(step => step.status === 'running')
          || group.steps.find(step => step.status === 'queued')
          || group.steps[group.steps.length - 1];
        const completed = group.steps.filter(step => step.status === 'succeeded').length;
        return <details key={group.id} className="group/sample min-w-0 rounded-lg border border-slate-200 bg-white">
          <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2 focus-visible:outline-2 focus-visible:outline-blue-500 [&::-webkit-details-marker]:hidden">
            <ChevronRight className="size-4 shrink-0 text-slate-400 group-open/sample:rotate-90" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-slate-800" title={group.label}>{group.label}</span>
              <span className="block truncate text-xs text-slate-500" title={`${group.nodes.join('、')} · ${current.title}`}>
                {group.nodes.join('、') || '未分配节点'} · {completed}/{group.steps.length} 步
                {group.status !== 'succeeded' && ` · ${current.title}`}
              </span>
            </span>
            <span className="flex shrink-0 flex-col items-end gap-0.5">
              <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[group.status]}`}>{STEP_STATUS_COPY[group.status]}</span>
              <span className="text-xs tabular-nums text-slate-600">{Math.round(group.progress)}%</span>
            </span>
          </summary>
          <div className="min-w-0 wrap-anywhere">
            <p className="border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
              {group.label}{group.sampleId && group.sampleId !== group.label && ` · 样本 ID：${group.sampleId}`}
              {group.nodes.length > 0 && ` · 节点：${group.nodes.join('、')}`}
            </p>
            {group.steps.map(step => <StepDetails step={step} key={step.step_id} />)}
          </div>
        </details>;
      })}
      {!items.length && <p className="rounded-lg bg-white p-4 text-sm text-slate-500">
        {groups.length ? '当前筛选下没有任务，可切换“全部”或清空搜索。' : '任务列表准备中。'}
      </p>}
    </section>
    <Pagination page={page} pages={pages} total={filtered.length} label="运行任务分页" onChange={setPage} />

    {recentEvents.length > 0 && <details className="group/log mt-3 rounded-lg border border-slate-800 bg-slate-950 text-slate-200">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-blue-400 [&::-webkit-details-marker]:hidden">
        <Terminal className="size-4 shrink-0" /><span className="flex-1">运行日志</span>
        <ChevronDown className="size-4 shrink-0 group-open/log:rotate-180" />
      </summary>
      <div className="max-h-48 space-y-1 overflow-y-auto overscroll-contain border-t border-slate-800 p-3 font-mono text-xs">
        {recentEvents.map(event => <p className={event.level === 'error' ? 'text-red-300' : ''} key={event.event_id}>
          [{event.event_id}] {event.message}
        </p>)}
      </div>
    </details>}
    {run.artifacts.length > 0 && <OutputFiles artifacts={run.artifacts} />}
    {run.error_message && <Alert variant="destructive" className="mt-3">
      <TriangleAlert /><AlertDescription className="max-h-32 overflow-y-auto overscroll-contain">{run.error_message}</AlertDescription>
    </Alert>}
    <details className="mt-2 text-xs text-slate-500">
      <summary className="cursor-pointer py-1">输出目录</summary>
      <p className="mt-1 break-all font-mono">{run.output_directory}</p>
    </details>
  </section>;
}
