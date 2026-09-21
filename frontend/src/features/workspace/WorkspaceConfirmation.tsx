import { useEffect, useState } from 'react';
import { useLanguageStore } from '../../stores/languageStore';
import { getTranslations } from '../../lib/i18n';
import type { TranslationKeys } from '../../types/i18n';
import { confirmFsOperation, fetchFsOperation } from './workspaceApi';
import type { WorkspaceOperation } from './workspaceTypes';
import { ServerPath } from './ServerPath';

const ACTION_KEYS: Record<string, keyof TranslationKeys> = {
  mkdir: 'workspaceActionMkdir',
  copy: 'workspaceActionCopy',
  move: 'workspaceActionMove',
  rename: 'workspaceActionRename',
  delete: 'workspaceActionDelete',
  restore: 'workspaceActionRestore',
  'read-sensitive': 'workspaceActionReadSensitive'
};

const STATUS_KEYS: Record<string, keyof TranslationKeys> = {
  pending: 'workspaceStatusPending',
  running: 'workspaceStatusRunning',
  succeeded: 'workspaceStatusSucceeded',
  failed: 'workspaceStatusFailed'
};

export function WorkspaceConfirmation({
  operation,
  conversationId,
  onDone,
  onDismiss
}: {
  operation: WorkspaceOperation;
  conversationId: string | null;
  onDone?: (value: WorkspaceOperation) => void;
  onDismiss?: () => void;
}) {
  const language = useLanguageStore((s) => s.language);
  const t = getTranslations(language);
  const [current, setCurrent] = useState(operation);
  const [dismissedId, setDismissedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    void fetchFsOperation(operation.id)
      .then((value) => {
        if (alive) setCurrent(value);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [operation.id]);
  useEffect(() => {
    if (current.action !== 'mkdir' || current.status !== 'succeeded') return;
    // Hide only transient success UI; the server audit record is retained.
    const timer = setTimeout(() => { setDismissedId(current.id); onDismiss?.(); }, 2500);
    return () => clearTimeout(timer);
  }, [current.id, current.action, current.status, onDismiss]);
  const confirm = async () => {
    setBusy(true);
    setError('');
    try {
      const value = await confirmFsOperation(current.id, current.conversation_id ?? conversationId);
      setCurrent(value);
      onDone?.(value);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  if (dismissedId === current.id) return null;
  return (
    <div className="my-2 min-w-0 rounded-control border border-warning-line bg-warning-quiet p-3 text-xs ">
      <strong>
        {t[ACTION_KEYS[current.action]] ?? current.action} ·{' '}
        {t[STATUS_KEYS[current.status]] ?? current.status}
      </strong>
      {current.action === 'mkdir' && current.status === 'succeeded' &&
        <button className="float-right underline" onClick={() => { setDismissedId(current.id); onDismiss?.(); }}>{t.workspaceDismiss}</button>}
      <p className="mt-2">{t.workspaceConfirmSource}</p>
      <ServerPath path={current.source} />
      {current.target && (
        <>
          <p>{t.workspaceConfirmTarget}</p>
          <ServerPath path={current.target} />
        </>
      )}
      {current.request.permanent && (
        <p className="font-semibold text-danger">{t.workspaceConfirmPermanent}</p>
      )}
      {current.request.overwrite && <p>{t.workspaceConfirmOverwrite}</p>}
      {current.action === 'read-sensitive' && <p>{t.workspaceConfirmSensitive}</p>}
      {current.status === 'pending' && (
        <button
          type="button"
          className="mt-2 rounded-control border border-line px-2 py-1 disabled:opacity-50 "
          disabled={busy}
          onClick={() => void confirm()}
        >
          {busy ? t.workspaceConfirmBusy : t.workspaceConfirmButton}
        </button>
      )}
      {current.status === 'running' && (
        <button
          type="button"
          className="mt-2 rounded-control border border-line px-2 py-1 "
          onClick={() =>
            void fetchFsOperation(current.id)
              .then((value) => { setCurrent(value); onDone?.(value); })
              .catch((failure: unknown) => setError(failure instanceof Error ? failure.message : String(failure)))
          }
        >
          {t.workspaceRefreshStatus}
        </button>
      )}
      {(current.error || error) && (
        <p className="mt-2 break-words text-danger">{current.error || error}</p>
      )}
      {current.status === 'failed' && current.staging_path && (
        <>
          <p>{t.workspaceStaging}</p>
          <ServerPath path={current.staging_path} />
        </>
      )}
      {current.action === 'read-sensitive' && typeof current.result?.text === 'string' && (
        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all">
          {current.result.text}
        </pre>
      )}
    </div>
  );
}
