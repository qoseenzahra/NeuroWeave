'use client';

import { useEffect, useState } from 'react';
import type { RunEvent, RunStep, WorkflowRun } from './workflow';

type MonitorUpdate = { run: Omit<WorkflowRun, 'steps' | 'plan_snapshot'>; steps: RunStep[]; reset: boolean };
type EventPage = { events: RunEvent[]; next_event_id: number; has_more: boolean };

export function mergeRunUpdate(previous: WorkflowRun, update: MonitorUpdate): WorkflowRun {
  const steps = new Map((update.reset ? [] : previous.steps).map(step => [step.step_id, step]));
  update.steps.forEach(step => steps.set(step.step_id, step));
  const ordered = [...steps.values()];
  const artifacts = new Map([...update.run.artifacts, ...ordered.flatMap(step => step.artifacts)]
    .map(artifact => [artifact.artifact_id, artifact]));
  return { ...previous, ...update.run, steps: ordered, artifacts: [...artifacts.values()], plan_snapshot: {} };
}

export function useRunMonitoring(apiBase: string, workflowId: string) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(`${apiBase}/api/runs?workflow_id=${encodeURIComponent(workflowId)}&limit=1&summary=true`,
          { signal: controller.signal });
        if (!response.ok) return;
        const payload = await response.json() as { runs: WorkflowRun[] };
        if (!controller.signal.aborted) setRun(current => current ?? payload.runs[0] ?? null);
      } catch { /* The next conversation visit can retry an unavailable run list. */ }
    })();
    return () => controller.abort();
  }, [apiBase, workflowId]);

  const runId = run?.run_id;
  const active = !!run && ['queued', 'running', 'cancel_requested'].includes(run.status);
  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let revision = -1;
    let cursor = 0;
    let firstEvents = true;
    const refresh = async () => {
      let catchUp = false;
      try {
        const [monitorResponse, eventResponse] = await Promise.all([
          fetch(`${apiBase}/api/runs/${runId}/monitor?after_revision=${revision}`, { signal: controller.signal }),
          fetch(`${apiBase}/api/runs/${runId}/events?after_event_id=${cursor}&tail=${firstEvents}&limit=200`, { signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;
        if (monitorResponse.ok) {
          const update = await monitorResponse.json() as MonitorUpdate;
          revision = update.run.state_revision ?? 0;
          if (!controller.signal.aborted) setRun(current => current?.run_id === runId ? mergeRunUpdate(current, update) : current);
        }
        if (eventResponse.ok) {
          const page = await eventResponse.json() as EventPage;
          const reset = firstEvents;
          cursor = page.next_event_id;
          firstEvents = false;
          catchUp = page.has_more;
          if (!controller.signal.aborted) setRunEvents(previous => {
            const events = new Map((reset ? [] : previous).map(event => [event.event_id, event]));
            page.events.forEach(event => events.set(event.event_id, event));
            return [...events.values()].sort((a, b) => a.event_id - b.event_id).slice(-1000);
          });
        }
      } catch { /* Keep the last persisted state; polling resumes after transient failures. */ }
      finally {
        // Schedule after completion so slow requests never overlap or arrive out of order.
        if (!controller.signal.aborted && (active || catchUp)) timer = setTimeout(() => void refresh(), catchUp ? 100 : 1000);
      }
    };
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [apiBase, runId, active]);
  return { run, setRun, runEvents, setRunEvents };
}
