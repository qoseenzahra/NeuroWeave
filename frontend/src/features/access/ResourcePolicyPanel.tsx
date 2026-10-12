import { useState } from 'react';
import { ui } from '../../lib/libraryText';
import { managementActions, scopeLabel } from './authorization';
import type { AuthorizedPayload, ResourceAction } from './authorization';

export interface ResourcePolicyPanelProps {
  resource: AuthorizedPayload;
  currentUserId?: string;
  platformAdmin?: boolean;
  onShare?: (scope: 'private' | 'project') => void;
  onHandover?: (newManagerId: string) => void;
  onTakeover?: (reason: string) => void;
  busy?: boolean;
  error?: string;
}

/** Author/scope label plus sharing, handover and audited takeover controls. */
export function ResourcePolicyPanel({ resource, currentUserId, platformAdmin, onShare, onHandover, onTakeover, busy, error }: ResourcePolicyPanelProps) {
  const [recipient, setRecipient] = useState('');
  const [reason, setReason] = useState('');
  const label = scopeLabel(resource, currentUserId);
  const actions = managementActions(resource, { platformAdmin });
  const has = (action: ResourceAction) => actions.includes(action);
  return (
    <section aria-label={ui('资源权限')} className="space-y-1.5 text-meta">
      {label && (
        <p>
          <strong>{label.scope === 'project' ? ui('项目共享') : ui('私有')}</strong>
          {' · '}
          {label.owner === 'mine' ? ui('由我管理') : ui('管理者：{0}', label.managerId)}
          {label.creatorId !== label.managerId && <span className="text-subtle">{' · '}{ui('创建者：{0}', label.creatorId)}</span>}
        </p>
      )}
      {has('share') && onShare && label && (
        <button type="button" className="rounded-control border border-line px-2 py-1" disabled={busy}
          onClick={() => onShare(label.scope === 'project' ? 'private' : 'project')}>
          {label.scope === 'project' ? ui('撤回共享') : ui('共享到项目')}
        </button>
      )}
      {has('handover') && onHandover && (
        <form className="flex gap-1.5" onSubmit={(event) => { event.preventDefault(); if (recipient.trim()) onHandover(recipient.trim()); }}>
          <input aria-label={ui('接收人')} className="min-w-0 flex-1 rounded-control border border-line bg-raised p-1.5"
            value={recipient} onChange={(event) => setRecipient(event.target.value)} />
          <button type="submit" className="rounded-control border border-line px-2" disabled={busy}>{ui('移交管理')}</button>
        </form>
      )}
      {has('takeover') && onTakeover && (
        <form className="flex gap-1.5" onSubmit={(event) => { event.preventDefault(); if (reason.trim().length >= 8) onTakeover(reason.trim()); }}>
          <input aria-label={ui('接管原因（将记入审计）')} className="min-w-0 flex-1 rounded-control border border-line bg-raised p-1.5"
            value={reason} onChange={(event) => setReason(event.target.value)} />
          <button type="submit" className="rounded-control border border-danger px-2 text-danger" disabled={busy || reason.trim().length < 8}>
            {ui('接管私有资源')}
          </button>
        </form>
      )}
      {error && <p role="alert" className="text-danger">{error}</p>}
    </section>
  );
}
