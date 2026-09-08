'use client';

import { useEffect, useRef, useState } from 'react';
import { History, LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { responseError } from '@/lib/api-error';
import type { SamplePathCoverage, SamplePathMatch } from '@/lib/dataset';

type Candidate = {
  run_id: string; group_id: string; run_title: string; run_status: string; created_at: string;
  step_title: string; label: string; sample_count: number; artifact_count: number;
};
type Preview = {
  run_id: string; group_id: string; coverage: SamplePathCoverage;
  matches: SamplePathMatch[]; can_apply: boolean; messages: string[];
};
type Props = {
  apiBase: string; workflowId: string; revision: number; stepId: string; slotId: string;
  slotLabel: string; disabled: boolean; onSelected: (runId: string, groupId: string) => void;
};

export function HistoricalInputPicker(props: Props) {
  const [open, setOpen] = useState(false);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  useEffect(() => () => { sequence.current += 1; pending.current?.abort(); }, []);
  const base = `${props.apiBase}/api/workflows/${props.workflowId}/steps/${props.stepId}/inputs/${props.slotId}/history`;

  const request = async (url: string, init: RequestInit, apply: (value: unknown) => void) => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const token = ++sequence.current;
    setBusy(true); setError('');
    try {
      const response = await fetch(url, { ...init, signal: controller.signal });
      if (!response.ok) throw new Error(await responseError(response));
      const value: unknown = await response.json();
      if (token === sequence.current) apply(value);
    } catch (failure) {
      if (token === sequence.current && !controller.signal.aborted)
        setError(failure instanceof Error ? failure.message : '无法读取历史输出');
    } finally { if (token === sequence.current) setBusy(false); }
  };
  const load = (position: number) => {
    setPreview(null); setCandidates([]); setOffset(position); setMore(false); setPage(0);
    void request(`${base}?offset=${position}`, {}, value => {
      const result = value as { candidates: Candidate[]; has_more: boolean; next_offset: number };
      setCandidates(result.candidates); setMore(result.has_more); setNextOffset(result.next_offset);
    });
  };
  const choose = (candidate: Candidate) => {
    setPreview(null); setPage(0);
    void request(`${base}/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: candidate.run_id, group_id: candidate.group_id, expected_revision: props.revision }) },
      value => setPreview(value as Preview));
  };
  const rows = preview?.matches.slice(page * 20, (page + 1) * 20) ?? [];
  const pageCount = Math.max(1, Math.ceil((preview?.matches.length ?? 0) / 20));

  return <Dialog open={open} onOpenChange={value => {
    setOpen(value);
    if (value) load(0);
    else { pending.current?.abort(); sequence.current += 1; setBusy(false); }
  }}>
    <DialogTrigger render={<Button size="sm" variant="outline" disabled={props.disabled} className="max-w-full whitespace-normal" />}>
      <History className="shrink-0" />从历史运行结果选择
    </DialogTrigger>
    <DialogContent className="flex max-h-[85dvh] w-[calc(100vw-2rem)] min-w-0 flex-col overflow-hidden sm:max-w-3xl">
      <DialogHeader className="shrink-0">
        <DialogTitle>选择历史输出 · {props.slotLabel}</DialogTitle>
        <DialogDescription>按原数据集和样本标识匹配。文件保留在原位置，无需复制。</DialogDescription>
      </DialogHeader>
      <div className="min-h-0 space-y-3 overflow-y-auto overscroll-contain text-sm">
        <p className="text-xs text-slate-500">只显示同一原始数据集、符合当前输入类型的成功步骤输出。运行失败时，已成功步骤的输出仍可选择。</p>
        <div className="max-h-52 space-y-2 overflow-y-auto rounded-lg border p-2" aria-label="历史运行候选">
          {candidates.map(candidate => <button type="button" key={candidate.run_id + candidate.group_id}
            disabled={busy} onClick={() => choose(candidate)}
            aria-pressed={preview?.run_id === candidate.run_id && preview.group_id === candidate.group_id}
            className="w-full rounded-md border p-3 text-left hover:bg-blue-50 aria-pressed:border-blue-500 aria-pressed:bg-blue-50 disabled:opacity-60">
            <span className="block break-words font-medium">{candidate.run_title} · {candidate.step_title}</span>
            <span className="mt-1 block break-words text-xs text-slate-600">{candidate.label} · {candidate.sample_count} 个已记录样本 · {new Date(candidate.created_at).toLocaleString()}</span>
            <span className="mt-1 block break-all font-mono text-[10px] text-slate-500">{candidate.run_id}</span>
          </button>)}
          {!busy && candidates.length === 0 && <p className="p-3 text-slate-500">这一页没有符合条件的历史输出。可查看更早运行；没有记录的已有文件仍可从数据集选择。</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy || offset === 0} onClick={() => load(Math.max(0, offset - 10))}>较新运行</Button>
          <Button size="sm" variant="outline" disabled={busy || !more} onClick={() => load(nextOffset)}>更早运行</Button>
          {busy && <output className="flex items-center gap-2 text-xs"><LoaderCircle className="size-4 animate-spin" />正在核对…</output>}
        </div>
        {error && <p role="alert" className="break-words text-red-700">{error}</p>}
        {preview && <div className="min-w-0 space-y-2 rounded-lg border p-3">
          <p className="font-medium">样本匹配预览：匹配 {preview.coverage.matched} / {preview.coverage.total} · 缺失 {preview.coverage.missing} · 无效 {preview.coverage.invalid}</p>
          <div className="max-h-60 space-y-2 overflow-y-auto" aria-label="历史输出样本匹配">
            {rows.map(match => <div key={match.sample_id} className="min-w-0 rounded border p-2 text-xs">
              <p className={match.status === 'matched' ? 'text-emerald-700' : 'text-red-700'}>{match.label} · {match.message}</p>
              <p className="mt-1 break-all font-mono text-slate-500">{match.absolute_path || '无对应输出'}</p>
            </div>)}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>上一页样本</Button>
            <span className="text-xs">{page + 1} / {pageCount}</span>
            <Button size="sm" variant="ghost" disabled={page + 1 >= pageCount} onClick={() => setPage(page + 1)}>下一页样本</Button>
          </div>
          {preview.messages.map(message => <p key={message} className="text-xs text-slate-500">{message}</p>)}
          {!preview.can_apply && <p role="alert" className="text-sm text-amber-800">未能唯一覆盖全部样本，请选择其他历史输出或使用已有文件输入。</p>}
        </div>}
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t pt-3">
        <Button size="sm" variant="outline" onClick={() => setOpen(false)}>关闭</Button>
        <Button size="sm" disabled={busy || props.disabled || !preview?.can_apply} onClick={() => {
          if (!preview?.can_apply) return;
          props.onSelected(preview.run_id, preview.group_id); setOpen(false);
        }}>应用到 {preview?.coverage.matched ?? 0} 个样本</Button>
      </div>
    </DialogContent>
  </Dialog>;
}
