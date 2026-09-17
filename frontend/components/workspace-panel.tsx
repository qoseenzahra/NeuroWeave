'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';

export type Workspace = { id: string; name: string; root_path: string; status: string; description: string; manageable: boolean; permission_reason: string };
export type WorkspaceOperation = { id: string; action: string; source: string; target: string | null;
  conversation_id: string | null; status: string; error?: string; result?: Record<string, unknown>;
  staging_path?: string;
  request: { permanent?: boolean; overwrite?: boolean; root_path?: string } };
export type WorkspaceEvent = { tool: string; status: string; count?: number; error?: string;
  operation?: WorkspaceOperation; arguments?: Record<string, unknown>; time?: string };
type Entry = { name: string; path: string; relative_path: string; type: string; size: number;
  modified_at: string; permissions: string; readable: boolean; writable: boolean };
type Listing = { root_path: string; path: string; relative_path: string; items: Entry[];
  has_more: boolean; next_cursor: string | null };

const field = 'min-w-0 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm';
const actionLabels: Record<string, string> = { mkdir: '新建文件夹', copy: '复制', move: '移动', rename: '重命名', delete: '删除', restore: '恢复', 'read-sensitive': '敏感文本预览' };
const statusLabels: Record<string, string> = { pending: '待确认，尚未执行', running: '正在执行', succeeded: '已完成', failed: '失败' };
export async function workspaceApi<T>(base: string, path: string, body?: unknown, method?: string): Promise<T> {
  const response = await fetch(`${base}${path}`, { method: method ?? (body ? 'POST' : 'GET'),
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined });
  const payload = await response.json() as { detail?: unknown };
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail));
  return payload as T;
}

export function ServerPath({ path, label }: { path: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  return <div className="flex min-w-0 items-center gap-1 text-xs">
    <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap py-1" title={path}>{label ?? path}</code>
    <button className="shrink-0 rounded border px-1.5 py-1 hover:bg-slate-100" title={path} onClick={async () => {
      setCopyError(false);
      try {
        if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(path);
        else {
          // The existing LAN deployment uses HTTP, where Clipboard API is absent.
          const field = document.createElement('textarea');
          const focused = document.activeElement as HTMLElement | null;
          field.value = path; field.style.position = 'fixed'; field.style.opacity = '0';
          document.body.appendChild(field);
          try {
            field.select();
            // HTTP has no modern clipboard alternative; retain this narrow fallback.
            // oxlint-disable-next-line typescript/no-deprecated
            if (!document.execCommand('copy')) throw new Error('copy denied');
          }
          finally { field.remove(); focused?.focus(); }
        }
        setCopied(true);
      } catch { setCopied(false); setCopyError(true); }
    }}>{copied ? '已复制' : copyError ? '请选中路径复制' : '复制路径'}</button>
  </div>;
}

const toolLabels: Record<string, string> = {
  list_workspace_directory: '读取目录', inspect_workspace_path: '检查文件', search_workspace_files: '检索文件',
  read_workspace_text: '读取文本', create_workspace_directory: '创建目录', copy_workspace_path: '复制',
  move_workspace_path: '移动', rename_workspace_path: '重命名', delete_workspace_path: '删除',
};
for (const [name, label] of Object.entries(toolLabels)) {
  toolLabels[name.replace('_workspace_', '_output_')] = `输出目录 · ${label}`;
  if (/^(list|inspect|search|read)_/.test(name)) toolLabels[name.replace('_workspace_', '_dataset_')] = `数据集（只读）· ${label}`;
}

export function WorkspaceConfirmation({ apiBase, operation, onDone, onDismiss }: {
  apiBase: string; operation: WorkspaceOperation; onDone?: (value: WorkspaceOperation) => void; onDismiss?: () => void;
}) {
  const [current, setCurrent] = useState(operation);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    let alive = true;
    void workspaceApi<WorkspaceOperation>(apiBase, `/api/fs/operations/${operation.id}`).then(value => {
      if (alive) setCurrent(value);
    }).catch(e => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [apiBase, operation.id]);
  useEffect(() => {
    if (current.action !== 'mkdir' || current.status !== 'succeeded') return;
    // Keep the audit record; only retire the transient success UI.
    const timer = setTimeout(() => { setDismissed(true); onDismiss?.(); }, 2500);
    return () => clearTimeout(timer);
  }, [current.action, current.status, onDismiss]);
  const confirm = async () => {
    setBusy(true); setError('');
    try {
      const value = await workspaceApi<WorkspaceOperation>(apiBase, `/api/fs/operations/${current.id}/confirm`, {
        confirmed: true, conversation_id: current.conversation_id,
      });
      setCurrent(value); onDone?.(value);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  if (dismissed) return null;
  return <div className="my-2 min-w-0 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs">
    <strong>{actionLabels[current.action] ?? current.action} · {statusLabels[current.status] ?? current.status}</strong>
    {current.action === 'mkdir' && current.status === 'succeeded' && <button className="float-right ml-2 underline"
      aria-label="收起新建文件夹完成提示" onClick={() => { setDismissed(true); onDismiss?.(); }}>收起</button>}
    <p className="mt-2">源路径</p><ServerPath path={current.source} />
    {current.target && <><p>目标路径</p><ServerPath path={current.target} /></>}
    {current.request.permanent && <p className="font-semibold text-red-700">永久删除：不会进入回收站。</p>}
    {current.request.overwrite && <p>将替换目标；旧目标先移入回收站。</p>}
    {current.action === 'read-sensitive' && <p>确认后仅在此面板显示敏感文本，不发送给模型。</p>}
    {current.status === 'pending' && <Button className="mt-2" size="sm" variant="outline" disabled={busy}
      onClick={() => void confirm()}>{busy ? '正在执行…' : '确认以上准确路径并执行'}</Button>}
    {current.status === 'running' && <Button size="sm" variant="outline" onClick={() => {
      void workspaceApi<WorkspaceOperation>(apiBase, `/api/fs/operations/${current.id}`).then(setCurrent);
    }}>刷新操作状态</Button>}
    {(current.error || error) && <p className="mt-2 break-words text-red-700">{current.error || error}</p>}
    {current.status === 'failed' && current.staging_path && <><p>保留的复制暂存路径（可能未完整复制）</p><ServerPath path={current.staging_path} /></>}
    {current.action === 'read-sensitive' && typeof current.result?.text === 'string' &&
      <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all">{current.result.text}</pre>}
  </div>;
}

export function WorkspaceTimeline({ apiBase, events }: { apiBase: string; events: WorkspaceEvent[] }) {
  return <div className="min-w-0 space-y-1 text-xs text-slate-600" aria-live="polite">
    {events.map((event, index) => <div key={`${event.time}-${index}`} className="min-w-0 rounded-md border bg-slate-50 px-2 py-1.5">
      <span>{toolLabels[event.tool] ?? event.tool} · {event.status === 'running' ? '正在执行' :
        event.status === 'succeeded' ? '完成' : event.status === 'pending' ? '等待确认' : '失败'}</span>
      {event.count != null && <span> · 找到 {event.count} 项</span>}
      {typeof event.arguments?.path === 'string' && <code className="ml-2 break-all">{event.arguments.path}</code>}
      {event.error && <p className="break-words text-red-700">{event.error}</p>}
      {event.operation && <WorkspaceConfirmation apiBase={apiBase} operation={event.operation} />}
    </div>)}
  </div>;
}

export function WorkspacePanel({ apiBase, workspaceId, conversationId, onSelect, onClose, locked = false,
  onPick, initialPath, datasetId, datasetOnly = false }: { apiBase: string; workspaceId: string | null; conversationId: string | null;
  onSelect: (workspace: Workspace | null) => Promise<void>; onClose: () => void; locked?: boolean;
  onPick?: (entry: Entry) => void; initialPath?: string; datasetId?: string | null; datasetOnly?: boolean;
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [roots, setRoots] = useState<string[]>([]);
  const [root, setRoot] = useState(datasetOnly ? 'dataset' : '');
  const [registerMode, setRegisterMode] = useState(!workspaceId);
  const [directory, setDirectory] = useState(initialPath ?? '.');
  const [jump, setJump] = useState('');
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState('name');
  const [hidden, setHidden] = useState(false);
  const [listing, setListing] = useState<Listing | null>(null);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{ text: string; truncated: boolean; next_offset: number } | null>(null);
  const [editor, setEditor] = useState<string | null>(null);
  const [destination, setDestination] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [permanent, setPermanent] = useState(false);
  const [pending, setPending] = useState<WorkspaceOperation | null>(null);
  const dismissPending = useCallback(() => setPending(null), []);
  const [trash, setTrash] = useState<{ id: string; original_path: string; deleted_at: string; status: string }[] | null>(null);
  const [restorePaths, setRestorePaths] = useState<Record<string, string>>({});
  const [width, setWidth] = useState(540);
  const [refresh, setRefresh] = useState(0);
  const requestVersion = useRef(0);
  const loading = useRef(false);
  const previewVersion = useRef(0);
  const selectedWorkspace = workspaces.find(item => item.id === workspaceId);
  const boundId = registerMode || datasetOnly ? null : workspaceId;
  const canManage = !datasetOnly && !!selectedWorkspace?.manageable;
  const filesBase = datasetOnly ? `/api/datasets/${datasetId}/files` : '/api/fs';

  const loadWorkspaces = useCallback(async () => setWorkspaces(await workspaceApi<Workspace[]>(apiBase, '/api/output-directories')), [apiBase]);
  useEffect(() => {
    if (datasetOnly) return;
    void workspaceApi<Workspace[]>(apiBase, '/api/output-directories').then(setWorkspaces).catch(e => setError(String(e)));
    void workspaceApi<{ roots: string[]; default_root: string }>(apiBase, '/api/fs/roots').then(value => {
      setRoots(value.roots); setRoot(value.default_root);
    }).catch(e => setError(String(e)));
  }, [apiBase, loadWorkspaces, datasetOnly]);
  const load = useCallback(async (cursor?: string) => {
    if (!root || (cursor && loading.current)) return;
    const version = cursor ? requestVersion.current : ++requestVersion.current;
    loading.current = true; setBusy(true); setError('');
    const query = new URLSearchParams({ path: directory, sort, filter, show_hidden: String(hidden), limit: '80' });
    if (!datasetOnly) { if (boundId) query.set('workspace_id', boundId); else query.set('root_path', root); }
    if (cursor) query.set('cursor', cursor);
    try {
      const result = await workspaceApi<Listing>(apiBase, `${filesBase}/list?${query}`);
      if (version !== requestVersion.current) return;
      setListing(previous => cursor && previous ? { ...result, items: [...previous.items, ...result.items] } : result);
      setJump(result.path);
    } catch (e) { if (version === requestVersion.current) setError(String(e)); }
    finally { if (version === requestVersion.current) { setBusy(false); loading.current = false; } }
  }, [apiBase, boundId, directory, root, filter, hidden, sort, datasetOnly, filesBase]);
  useEffect(() => {
    const timer = setTimeout(() => {
      previewVersion.current += 1;
      setListing(null); setSelected(null); setPreview(null); void load();
    }, 180);
    return () => { clearTimeout(timer); requestVersion.current += 1; loading.current = false; };
  }, [load, refresh]);

  const perform = async () => {
    if (!editor || datasetOnly || (editor !== 'mkdir' && !boundId) || !listing) return;
    setBusy(true); setError('');
    try {
      const path = editor === 'mkdir' ? `${listing.path}/${destination.trim()}` : selected?.path;
      const value = await workspaceApi<WorkspaceOperation>(apiBase, `/api/fs/${editor}`, {
        workspace_id: boundId, ...(!boundId && editor === 'mkdir' ? { root_path: listing.path } : {}),
        conversation_id: conversationId, path,
        destination: ['copy', 'move', 'rename'].includes(editor) ? destination : null,
        overwrite: ['copy', 'move', 'rename'].includes(editor) && overwrite, permanent: editor === 'delete' && permanent,
      });
      setPending(value); setEditor(null);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  const read = async (append = false) => {
    if (!selected || (!boundId && !datasetOnly)) return;
    const version = ++previewVersion.current;
    try {
      const query = new URLSearchParams({ path: selected.path,
        offset: String(append ? preview?.next_offset ?? 0 : 0) });
      if (boundId) query.set('workspace_id', boundId);
      const value = await workspaceApi<{ text: string; truncated: boolean; next_offset: number }>(apiBase, `${filesBase}/read-text?${query}`);
      // Keep only the current bounded page, even when a huge text file is opened.
      if (version === previewVersion.current) setPreview(value);
    } catch (e) { setError(String(e)); }
  };
  const relativeParts = listing?.relative_path === '.' ? [] : (listing?.relative_path.split(/[\\/]/).filter(Boolean) ?? []);
  return <dialog open aria-label={datasetOnly ? '数据集文件（只读）' : '服务器输出目录文件管理'} className="fixed inset-y-0 right-0 left-auto z-50 m-0 flex h-dvh min-w-0 flex-col border-l bg-white p-0 shadow-2xl"
    style={{ width, maxWidth: 'calc(100vw - 12px)' }}>
    <button type="button" aria-label="调整输出目录面板宽度"
      className="absolute inset-y-0 left-0 z-10 w-2 cursor-col-resize touch-none hover:bg-blue-200/50"
      onKeyDown={e => { if (e.key === 'ArrowLeft') setWidth(w => Math.min(window.innerWidth - 12, w + 32)); if (e.key === 'ArrowRight') setWidth(w => Math.max(320, w - 32)); }}
      onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); }}
      onPointerMove={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) setWidth(Math.max(320, Math.min(window.innerWidth - 12, window.innerWidth - e.clientX))); }} />
    <div className="flex shrink-0 items-center justify-between border-b p-3 pl-5"><strong>{datasetOnly ? '数据集文件（只读）' : '服务器输出目录'}</strong><Button size="sm" variant="ghost" onClick={onClose}>关闭</Button></div>
    <div className="shrink-0 space-y-2 border-b p-3 pl-5">
      <div className="flex flex-wrap gap-2">
        {!datasetOnly && <select aria-label="选择输出目录" className={`${field} flex-1`} disabled={locked || !!onPick} value={registerMode ? '' : workspaceId ?? ''}
          onChange={e => { const value = workspaces.find(item => item.id === e.target.value) ?? null;
            void onSelect(value).then(() => { setRegisterMode(!value); setDirectory('.'); setTrash(null); }).catch(err => setError(String(err))); }}>
          <option value="">选择或登记输出目录</option>{workspaces.filter(item => item.status === 'active').map(item => <option key={item.id} value={item.id} disabled={!item.manageable}>{item.name}{item.manageable ? '' : '（仅浏览）'}</option>)}
        </select>}
        {!datasetOnly && !onPick && <Button size="sm" variant="outline" disabled={locked} onClick={() => { setRegisterMode(true); setDirectory('.'); }}>浏览服务器</Button>}
        <Button size="sm" variant="outline" onClick={() => setRefresh(v => v + 1)}>刷新</Button>
      </div>
      <p className="text-xs text-slate-500">{datasetOnly ? '模型可按需读取此数据集。原始文件只读，不提供改名、移动、覆盖或删除。' : '选择后端账户有读写和进入权限的目录，数据集目录不能作为可管理输出目录。'}{locked ? '流程已锁定，当前输出目录不可切换。' : ''}</p>
      {!datasetOnly && selectedWorkspace && !registerMode && <p className="text-xs text-slate-600">{selectedWorkspace.permission_reason}</p>}
      {registerMode && !datasetOnly && <select aria-label="允许访问的服务器根目录" value={root} className={`${field} w-full`} onChange={e => { setRoot(e.target.value); setDirectory('.'); }}>
        {!roots.includes(root) && <option value={root}>{root}</option>}{roots.map(item => <option key={item}>{item}</option>)}
      </select>}
      <form className="flex min-w-0 gap-2" onSubmit={e => { e.preventDefault(); setDirectory(jump); }}>
        <input aria-label="服务器绝对路径" className={`${field} flex-1`} value={jump} title={jump} onChange={e => setJump(e.target.value)} />
        <Button size="sm" variant="outline" type="submit">转到</Button>
        <Button size="sm" variant="outline" type="button" onClick={() => {
          const query = new URLSearchParams({ path: jump });
          if (!datasetOnly) { if (boundId) query.set('workspace_id', boundId); else query.set('root_path', root); }
          void workspaceApi<Entry & { exists: boolean }>(apiBase, `${filesBase}/inspect?${query}`).then(value => {
            if (!value.exists) { setError('路径不存在'); return; }
            previewVersion.current += 1; setSelected(value); setPreview(null); setError('');
          }).catch(e => setError(String(e)));
        }}>详情</Button>
      </form>
      {listing && <><ServerPath path={listing.path} /><nav aria-label="目录面包屑" className="flex gap-1 overflow-x-auto whitespace-nowrap text-xs text-blue-700">
        <button onClick={() => setDirectory('.')}>{selectedWorkspace && !registerMode ? selectedWorkspace.name : listing.root_path}</button>
        {relativeParts.map((part, index) => <button key={index} title={relativeParts.slice(0, index + 1).join('/')} onClick={() => setDirectory(relativeParts.slice(0, index + 1).join('/'))}> / {part}</button>)}
      </nav></>}
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <input className={`${field} min-w-[100px] flex-1`} aria-label="筛选文件名" placeholder="筛选当前目录文件名" value={filter} onChange={e => setFilter(e.target.value)} />
        <select aria-label="排序" className={field} value={sort} onChange={e => setSort(e.target.value)}><option value="name">名称</option><option value="modified">修改时间</option><option value="size">大小</option></select>
        <label className="text-xs"><input type="checkbox" checked={hidden} onChange={e => setHidden(e.target.checked)} /> 隐藏文件</label>
      </div>
      <div className="flex flex-wrap gap-1">
        <Button size="sm" variant="outline" disabled={!relativeParts.length} onClick={() => setDirectory(relativeParts.slice(0, -1).join('/') || '.')}>上级目录</Button>
        {!datasetOnly && !onPick && <Button size="sm" variant="outline" disabled={!listing || busy || (registerMode ? locked : !canManage)}
          onClick={() => { setEditor('mkdir'); setDestination(''); }}>新建文件夹</Button>}
        {!datasetOnly && (registerMode ? <Button size="sm" disabled={!listing || locked} onClick={() => { setEditor('register'); setDestination(listing?.path.split(/[\\/]/).pop() || '输出目录'); }}>当前目录作为输出目录</Button> : !onPick && <>
          <Button size="sm" variant="outline" onClick={() => { void workspaceApi<typeof trash>(apiBase, `/api/output-directories/${workspaceId}/trash`).then(setTrash).catch(e => setError(String(e))); }}>回收站</Button>
          <Button size="sm" variant="ghost" disabled={locked} onClick={() => { setEditor('workspace-edit'); setDestination(selectedWorkspace?.name ?? ''); }}>管理</Button>
        </>)}
      </div>
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3 pl-5" onScroll={e => {
      const element = e.currentTarget;
      if (element.scrollHeight - element.scrollTop - element.clientHeight < 140 && listing?.next_cursor) void load(listing.next_cursor);
    }}>
      {error && <p role="alert" className="mb-2 break-words rounded border border-red-200 p-2 text-xs text-red-700">{error}</p>}
      {error.includes('敏感') && boundId && canManage && <Button size="sm" variant="outline" onClick={() => {
        void workspaceApi<WorkspaceOperation>(apiBase, '/api/fs/read-sensitive', { workspace_id: boundId,
          conversation_id: conversationId, path: jump }).then(setPending).catch(e => setError(String(e)));
      }}>提出对此路径的敏感文本读取确认</Button>}
      {editor && editor !== 'workspace-remove' && <form className="mb-3 space-y-2 rounded-lg border bg-slate-50 p-3 text-xs" onSubmit={e => { e.preventDefault();
        if (editor === 'register') {
          void workspaceApi<Workspace>(apiBase, '/api/output-directories', { name: destination, root_path: listing?.path }).then(async value => {
            await loadWorkspaces(); await onSelect(value); setRegisterMode(false); setDirectory('.'); setEditor(null);
          }).catch(err => setError(String(err)));
        } else if (editor === 'workspace-edit') {
          void workspaceApi(apiBase, `/api/output-directories/${workspaceId}`, { name: destination }, 'PATCH').then(() => { void loadWorkspaces(); setEditor(null); }).catch(err => setError(String(err)));
        } else void perform();
      }}>
        <strong>{editor === 'register' ? '输出目录名称' : editor === 'workspace-edit' ? '修改输出目录名称' : actionLabels[editor] ?? editor}</strong>
        {selected && !['mkdir', 'register', 'workspace-edit'].includes(editor) && <ServerPath path={selected.path} />}
        {!['delete', 'read-sensitive'].includes(editor) && <input required className={`${field} w-full`} aria-label="名称或准确目标路径" value={destination} placeholder="目标路径必须包含最终文件或文件夹名称" onChange={e => setDestination(e.target.value)} />}
        {['copy', 'move', 'rename'].includes(editor) && <label className="block"><input type="checkbox" checked={overwrite} onChange={e => setOverwrite(e.target.checked)} /> 允许覆盖已有目标（先移入回收站）</label>}
        {editor === 'delete' && <label className="block text-red-700"><input type="checkbox" checked={permanent} onChange={e => setPermanent(e.target.checked)} /> 明确要求永久删除，不保留回收站副本</label>}
        <div className="flex flex-wrap gap-2"><Button size="sm" type="submit" disabled={busy}>继续</Button><Button size="sm" type="button" variant="outline" onClick={() => setEditor(null)}>取消</Button>
          {editor === 'workspace-edit' && <Button size="sm" type="button" variant="outline" onClick={() => setEditor('workspace-remove')}>移除输出目录记录</Button>}
        </div>
      </form>}
      {editor === 'workspace-remove' && <div className="mb-3 rounded border border-amber-200 p-3 text-xs"><p>只移除输出目录记录，服务器目录、文件、历史对话与运行输出全部保留。</p>
        <Button size="sm" variant="outline" onClick={() => { void workspaceApi(apiBase, `/api/output-directories/${workspaceId}`, undefined, 'DELETE').then(async () => { await onSelect(null); await loadWorkspaces(); setRegisterMode(true); setDirectory('.'); setEditor(null); }).catch(e => setError(String(e))); }}>确认移除记录</Button></div>}
      {pending && <WorkspaceConfirmation key={pending.id} apiBase={apiBase} operation={pending} onDismiss={dismissPending} onDone={value => {
        if (value.status !== 'succeeded') return;
        // In the chooser, enter the newly created folder so it can be selected
        // immediately. Do not redirect if the user has since browsed elsewhere.
        if (registerMode && value.action === 'mkdir' && value.request.root_path === listing?.path) {
          setDirectory(value.source); setFilter('');
        }
        setRefresh(v => v + 1);
      }} />}
      {trash && <div className="mb-3 space-y-2 rounded border p-2 text-xs"><div className="flex justify-between"><strong>回收站（最多最近 500 项）</strong><button onClick={() => setTrash(null)}>关闭</button></div>
        {!trash.length && <p>回收站为空</p>}{trash.map(item => <div key={item.id}><ServerPath path={item.original_path} /><p>{item.deleted_at}</p>
          <input className={`${field} my-1 w-full`} aria-label="恢复目标路径" placeholder={item.original_path} value={restorePaths[item.id] ?? ''} onChange={e => setRestorePaths(value => ({ ...value, [item.id]: e.target.value }))} />
          <Button size="sm" variant="outline" onClick={() => { void workspaceApi<WorkspaceOperation>(apiBase, `/api/fs/trash/${item.id}/restore`, { conversation_id: conversationId, destination: restorePaths[item.id] || null }).then(setPending).catch(e => setError(String(e))); }}>恢复（可填写其他目标路径）</Button>
        </div>)}</div>}
      {listing?.items.map(item => <button key={item.path} className={`mb-1 flex w-full min-w-0 items-start gap-2 rounded-lg border p-2 text-left ${selected?.path === item.path ? 'border-blue-400 bg-blue-50' : 'border-transparent hover:bg-slate-50'}`}
        onClick={() => { previewVersion.current += 1; setSelected(item); setPreview(null); }} onDoubleClick={() => { if (item.type === 'directory') setDirectory(item.path); }} title={item.path}>
        <span className="shrink-0">{item.type === 'directory' ? '📁' : '📄'}</span><span className="min-w-0 flex-1">
          <span className="block break-all text-sm">{item.name}</span>
          <span className="block text-[11px] text-slate-500">{item.type === 'directory' ? '目录' : `${item.size.toLocaleString()} B`} · {new Date(item.modified_at).toLocaleString()} · {item.permissions}</span>
        </span>{item.type === 'directory' && <span className="shrink-0 text-xs">双击打开 →</span>}
      </button>)}
      {!busy && listing && !listing.items.length && <p className="p-3 text-xs text-slate-500">当前目录没有可显示的条目。</p>}
      {busy && <output className="block p-3 text-xs">正在读取目录…</output>}
      {listing?.has_more && <Button variant="outline" size="sm" disabled={busy} onClick={() => void load(listing.next_cursor!)}>继续加载</Button>}
    </div>
    {selected && <div className="max-h-[40vh] shrink-0 space-y-2 overflow-auto border-t p-3 pl-5 text-xs">
      <ServerPath path={selected.path} label={selected.relative_path} /><p>{selected.type} · {selected.size.toLocaleString()} B · {selected.permissions} · {selected.writable ? '可写' : '只读'}</p>
      <div className="flex flex-wrap gap-1">
        {selected.type === 'directory' && <Button size="sm" variant="outline" onClick={() => setDirectory(selected.path)}>打开目录</Button>}
        {onPick && <Button size="sm" onClick={() => onPick(selected)}>选择此路径</Button>}
        {selected.type === 'file' && (boundId || datasetOnly) && <Button size="sm" variant="outline" onClick={() => void read()}>文本预览</Button>}
        {!registerMode && !onPick && canManage && ['rename', 'copy', 'move', 'delete'].map((action, i) => <Button key={action} size="sm" variant="outline" onClick={() => { setEditor(action); setDestination(action === 'rename' ? selected.name : ''); setOverwrite(false); setPermanent(false); }}>{['重命名', '复制', '移动', '删除'][i]}</Button>)}
      </div>
      {preview && <><pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-50 p-2">{preview.text}</pre>{preview.truncated && <Button size="sm" variant="outline" onClick={() => void read(true)}>读取下一段（当前预览已截断）</Button>}</>}
    </div>}
  </dialog>;
}
