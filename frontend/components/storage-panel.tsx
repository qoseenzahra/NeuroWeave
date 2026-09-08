'use client';

import { useState } from 'react';
import { Database } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { fetchOperation, cancelOperation, type OperationView } from '@/lib/api-operation';
import { responseError } from '@/lib/api-error';

type Storage = {
  backend_revision?: string;
  database_bytes: number; backup_count: number; retention: string;
  latest_backup: { created_at?: string; restore_verified?: boolean; error?: string } | null;
  volumes: { path: string; free_bytes: number; total_bytes: number; low_space: boolean }[];
};
type Inventory = {
  totals: { files: number; bytes: number; unreadable: number; symlinks_skipped: number };
  run_count: number; largest_runs: { run_id: string; status: string; bytes: number; files: number }[];
};
const size = (bytes: number) => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;

export function StoragePanel({ apiBase }: { apiBase: string }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Storage | null>(null);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [operation, setOperation] = useState<OperationView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = async () => {
    setError('');
    try {
      const response = await fetch(`${apiBase}/api/maintenance/storage`);
      if (!response.ok) throw new Error(await responseError(response));
      setStatus(await response.json() as Storage);
    } catch (failure) { setError(failure instanceof Error ? failure.message : '无法读取存储状态'); }
  };
  const inspect = async () => {
    setBusy(true); setError('');
    try {
      const response = await fetchOperation(apiBase, `${apiBase}/api/maintenance/inventory-jobs`,
        { method: 'POST' }, setOperation);
      if (!response.ok) throw new Error(await responseError(response));
      setInventory(await response.json() as Inventory);
    } catch (failure) { setError(failure instanceof Error ? failure.message : '统计失败'); }
    finally { setBusy(false); setOperation(null); }
  };
  return <>
    <Button className="mt-2 w-full" variant="ghost" size="sm" onClick={() => { setOpen(true); void refresh(); }}>
      <Database />存储与备份
    </Button>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="flex max-h-[85dvh] w-[calc(100vw-2rem)] min-w-0 flex-col overflow-hidden sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>存储与备份</DialogTitle>
          <DialogDescription>检查磁盘余量、备份状态和运行目录占用。</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 space-y-4 overflow-y-auto overscroll-contain text-sm">
          {status && <>
            <p>数据库：{size(status.database_bytes)} · 备份 {status.backup_count} 份</p>
            <p>{status.latest_backup?.created_at
              ? `最近备份：${new Date(status.latest_backup.created_at).toLocaleString()} · ${status.latest_backup.restore_verified ? '恢复校验通过' : '待校验'}`
              : '尚无可读取的备份记录'}</p>
            {status.volumes.map(volume => <div key={volume.path} className="min-w-0 rounded-lg border p-3">
              <p className="break-all font-mono text-xs">{volume.path}</p>
              <p className={volume.low_space ? 'text-red-700' : 'text-slate-600'}>可用 {size(volume.free_bytes)} / 总计 {size(volume.total_bytes)}
                {volume.low_space && ' · 空间不足，请安排清理或扩容'}</p>
            </div>)}
            <p className="text-xs text-slate-500">{status.retention}</p>
            <div className="break-all font-mono text-xs text-slate-500">
              <p>前端版本：{process.env.NEXT_PUBLIC_NEUROWEAVE_REVISION ?? 'development'}</p>
              <p>后端版本：{status.backend_revision ?? '未知'}</p>
            </div>
          </>}
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => void refresh()}>刷新状态</Button>
            <Button size="sm" disabled={busy} onClick={() => void inspect()}>{busy ? '正在统计…' : '统计运行目录'}</Button>
            {operation && <Button size="sm" variant="outline" disabled={operation.status === 'cancel_requested'}
              onClick={() => void cancelOperation(apiBase, operation.operation_id).catch(() => setError('取消请求失败，请重试'))}>取消统计</Button>}
          </div>
          {operation && <p className="text-xs text-slate-500">{operation.message}</p>}
          {error && <p role="alert" className="text-red-700">{error}</p>}
          {inventory && <>
            <p>{inventory.run_count} 个运行目录 · {size(inventory.totals.bytes)} · {inventory.totals.files} 个文件</p>
            {(inventory.totals.unreadable > 0 || inventory.totals.symlinks_skipped > 0) &&
              <p className="text-xs text-amber-700">统计未包含 {inventory.totals.unreadable} 个无法读取的条目和 {inventory.totals.symlinks_skipped} 个符号链接。</p>}
            <div className="max-h-64 overflow-y-auto">
              {inventory.largest_runs.map(run => <div key={run.run_id} className="flex flex-wrap justify-between gap-2 border-b py-2 text-xs">
                <span className="break-all font-mono">{run.run_id}</span><span>{run.status} · {size(run.bytes)} · {run.files} 文件</span>
              </div>)}
            </div>
            <p className="text-xs text-slate-500">按占用显示前 20 个目录。科研结果的归档和删除由管理员核对后操作。</p>
          </>}
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
