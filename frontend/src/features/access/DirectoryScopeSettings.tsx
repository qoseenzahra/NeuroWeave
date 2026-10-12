import { useState } from 'react';
import { ui } from '../../lib/libraryText';
import type { DirectoryGrant } from './accessApi';

export interface DirectoryScopeSettingsProps {
  /** Project being administered; empty string for personal grants. */
  projectId: string;
  /** Grants that apply to the current user in the current scope. */
  grants: readonly DirectoryGrant[];
  /** Server-confirmed management permission (project or platform administrator). */
  canManage: boolean;
  onCreate?: (grant: { user_id: string; root: string; scope: 'read' | 'write' }) => void;
  onRevoke?: (grantId: string) => void;
  busy?: boolean;
  error?: string;
}

/** Data roots and read grants. Without a grant nothing is browsable. */
export function DirectoryScopeSettings({ projectId, grants, canManage, onCreate, onRevoke, busy, error }: DirectoryScopeSettingsProps) {
  const [root, setRoot] = useState('');
  const [userId, setUserId] = useState('*');
  const reads = grants.filter((grant) => grant.scope === 'read');
  return (
    <section aria-label={ui('目录访问范围')} className="space-y-1.5">
      <p className="text-meta font-medium text-muted">{ui('目录访问范围')}</p>
      <p className="text-micro text-subtle">{projectId ? ui('项目 {0}', projectId) : ui('个人范围')}</p>
      {reads.length === 0 ? (
        <p className="text-meta text-subtle">{ui('尚未授权任何数据目录')}</p>
      ) : (
        <ul className="space-y-1">
          {reads.map((grant) => (
            <li key={grant.grant_id} className="flex items-center justify-between gap-2 text-meta">
              <span className="truncate" title={grant.root}>{grant.root}</span>
              {canManage && onRevoke && (
                <button type="button" className="text-danger hover:underline" disabled={busy} onClick={() => onRevoke(grant.grant_id)}>
                  {ui('撤销')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && onCreate && (
        <form
          className="flex flex-wrap gap-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            if (root.trim()) onCreate({ user_id: userId.trim() || '*', root: root.trim(), scope: 'read' });
          }}
        >
          <input aria-label={ui('服务器目录')} className="min-w-0 flex-1 rounded-control border border-line bg-raised p-1.5 text-meta"
            placeholder="/data/project" value={root} onChange={(event) => setRoot(event.target.value)} />
          <input aria-label={ui('用户（* 表示全部成员）')} className="w-24 rounded-control border border-line bg-raised p-1.5 text-meta"
            value={userId} onChange={(event) => setUserId(event.target.value)} />
          <button type="submit" className="rounded-control border border-line px-2 text-meta" disabled={busy}>{ui('授权读取')}</button>
        </form>
      )}
      {error && <p role="alert" className="text-meta text-danger">{error}</p>}
    </section>
  );
}
