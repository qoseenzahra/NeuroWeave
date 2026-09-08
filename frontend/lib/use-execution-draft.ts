'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { responseError } from './api-error';
import type { ExecutionOptions } from './workflow';

type Draft = { execution: ExecutionOptions | null; draft_revision: number; workflow_revision: number | null };

export function useExecutionDraft(apiBase: string, workflowId: string, workflowRevision: number, defaults: ExecutionOptions) {
  const [execution, setExecution] = useState(defaults);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  const revision = useRef(0);
  const saved = useRef('');
  const queue = useRef<Promise<boolean>>(Promise.resolve(true));
  const conflict = useRef(false);
  const flush = useRef<(() => void) | null>(null);
  const url = `${apiBase}/api/workflows/${workflowId}/execution-draft`;

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(await responseError(response, '无法读取运行设置'));
        const draft = await response.json() as Draft;
        if (controller.signal.aborted) return;
        const value = draft.execution ?? defaults;
        revision.current = draft.draft_revision;
        saved.current = JSON.stringify(value);
        conflict.current = false;
        setExecution(value);
        setReady(true);
        setError(null);
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : '无法读取运行设置');
      }
    })();
    return () => controller.abort();
  }, [url, defaults, reload]);

  const persist = useCallback((value: ExecutionOptions) => {
    const serialized = JSON.stringify(value);
    queue.current = queue.current.then(async () => {
      if (conflict.current) return false;
      if (serialized === saved.current) return true;
      setSaving(true);
      try {
        const response = await fetch(url, { method: 'PUT', keepalive: true,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expected_revision: workflowRevision, expected_draft_revision: revision.current, execution: value }) });
        if (!response.ok) {
          if (response.status === 409) conflict.current = true;
          throw new Error(await responseError(response, '运行设置尚未保存，请检查资源参数'));
        }
        const draft = await response.json() as Draft;
        revision.current = draft.draft_revision;
        saved.current = serialized;
        setError(null);
        return true;
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : '运行设置保存失败');
        return false;
      } finally { setSaving(false); }
    });
    return queue.current;
  }, [url, workflowRevision]);

  useEffect(() => {
    if (!ready || JSON.stringify(execution) === saved.current) return;
    const timer = setTimeout(() => void persist(execution), 500);
    return () => clearTimeout(timer);
  }, [execution, persist, ready]);
  useLayoutEffect(() => {
    flush.current = ready ? () => { void persist(execution); } : null;
  }, [execution, persist, ready]);
  useEffect(() => () => flush.current?.(), []);
  return { execution, setExecution, ready, error, saving, save: () => persist(execution),
    reload: () => { setReady(false); setReload(value => value + 1); } };
}
