import { useState } from 'react';
import { ui } from '../../lib/libraryText';
import type { DirectoryGrant } from './accessApi';

export interface OutputWriteGrantSettingsProps {
  projectId: string;
  grants: readonly DirectoryGrant[];
  canManage: boolean;
  onCreate?: (grant: { user_id: string; root: string; scope: 'read' | 'write' }) => void;
  onRevoke?: (grantId: string) => void;
  busy?: boolean;
}

/**
 * Output roots with write grants. Revoking a grant immediately invalidates
 * pending file confirmations and blocks new run submissions to that root.
 */
export function OutputWriteGrantSettings({ projectId, grants, canManage, onCreate, onRevoke, busy }: OutputWriteGrantSettingsProps) {
  const [root, setRoot] = useState('');
  const [userId, setUserId] = useState('*');
  const writes = grants.filter((grant) => grant.scope === 'write');
  return (
    <section aria-label={ui('输出写入授权')} className="space-y-1.5">
      <p className="text-meta font-medium text-muted">{ui('输出写入授权')}</p>
      <p className="text-micro text-subtle">{projectId ? ui('项目 {0}', projectId) : ui('个人范围')}</p>
      {writes.length === 0 ? (
        <p className="text-meta text-subtle">{ui('没有可写入的输出目录')}</p>
      ) : (
        <ul className="space-y-1">
          {writes.map((grant) => (
            <li key={grant.grant_id} className="flex items-center justify-between gap-2 text-meta">
              <span className="truncate" title={grant.root}>{grant.root}</span>
              {canManage && onRevoke && (
                <button type="button" className="text-danger hover:underline" disabled={busy} onClick={() => onRevoke(grant.grant_id)}>
                  {ui('撤销写入授权')}
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
            if (root.trim()) onCreate({ user_id: userId.trim() || '*', root: root.trim(), scope: 'write' });
          }}
        >
          <input aria-label={ui('输出根目录')} className="min-w-0 flex-1 rounded-control border border-line bg-raised p-1.5 text-meta"
            placeholder="/data/outputs" value={root} onChange={(event) => setRoot(event.target.value)} />
          <input aria-label={ui('用户（* 表示全部成员）')} className="w-24 rounded-control border border-line bg-raised p-1.5 text-meta"
            value={userId} onChange={(event) => setUserId(event.target.value)} />
          <button type="submit" className="rounded-control border border-line px-2 text-meta" disabled={busy}>{ui('授予写入')}</button>
        </form>
      )}
    </section>
  );
}
