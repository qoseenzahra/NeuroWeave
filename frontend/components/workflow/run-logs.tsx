'use client';

import { useRef, useState } from 'react';
import { ChevronDown, Terminal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { RunEvent } from '@/lib/workflow';

type EventPage = { events: RunEvent[]; has_older: boolean };

/** Keep one historical page in memory; live polling never moves a page being read. */
export function RunLogs({ apiBase, runId, events }: { apiBase?: string; runId: string; events: RunEvent[] }) {
  const [history, setHistory] = useState<EventPage | null>(null);
  const [cursors, setCursors] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(0);
  const displayed = history?.events ?? events.slice(-20);
  const load = async (next: number[]) => {
    const generation = ++request.current;
    if (!next.length) { setHistory(null); setCursors([]); setBusy(false); setError(''); return; }
    setBusy(true);
    setError('');
    try {
      const response = await fetch(`${apiBase}/api/runs/${runId}/events?before_event_id=${next[next.length - 1]}&limit=20`);
      if (!response.ok) throw new Error('无法读取日志，请重试');
      const page = await response.json() as EventPage;
      if (generation !== request.current) return;
      setHistory(page);
      setCursors(next);
    } catch (failure) {
      if (generation === request.current) setError(failure instanceof Error ? failure.message : '读取日志失败');
    } finally { if (generation === request.current) setBusy(false); }
  };
  return <details className="group/log mt-3 min-w-0 rounded-lg border border-slate-800 bg-slate-950 text-slate-200">
    <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-blue-400 [&::-webkit-details-marker]:hidden">
      <Terminal className="size-4 shrink-0" /><span className="flex-1">运行日志{history ? ' · 历史' : ' · 实时'}</span>
      <ChevronDown className="size-4 shrink-0 group-open/log:rotate-180" />
    </summary>
    <div className="max-h-64 space-y-1 overflow-y-auto overscroll-contain border-t border-slate-800 p-3 font-mono text-xs">
      {displayed.map(event => <p className={event.level === 'error' ? 'text-red-300' : ''} key={event.event_id}>
        [{event.event_id}] {event.message}
      </p>)}
      {!displayed.length && <p>当前没有更多日志。</p>}
    </div>
    {apiBase !== undefined && <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 p-2 text-xs">
      <Button size="sm" variant="secondary" disabled={busy || !displayed.length || history?.has_older === false}
        onClick={() => void load([...cursors, displayed[0].event_id])}>更早日志</Button>
      <Button size="sm" variant="secondary" disabled={busy || !history}
        onClick={() => void load(cursors.slice(0, -1))}>较新日志</Button>
      {history && <Button size="sm" variant="secondary" onClick={() => void load([])}>回到实时</Button>}
      {busy && <span>加载中…</span>}
      {error && <span role="alert" className="text-red-300">{error}</span>}
    </div>}
  </details>;
}
