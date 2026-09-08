import type { Workflow } from './workflow';

const waiting: Array<() => void> = [];
const pending = new Map<string, Promise<Workflow>>();
let active = 0;

export function loadWorkflow(apiBase: string, workflowId: string): Promise<Workflow> {
  const key = `${apiBase}/api/workflows/${encodeURIComponent(workflowId)}`;
  const existing = pending.get(key);
  if (existing) return existing;
  const request = (async () => {
    if (active >= 2) await new Promise<void>(resolve => waiting.push(resolve));
    else active += 1;
    try {
      const response = await fetch(key);
      if (!response.ok) throw new Error('无法读取流程，请重试');
      return await response.json() as Workflow;
    } finally {
      const next = waiting.shift();
      if (next) next();
      else active -= 1;
      pending.delete(key);
    }
  })();
  pending.set(key, request);
  return request;
}
