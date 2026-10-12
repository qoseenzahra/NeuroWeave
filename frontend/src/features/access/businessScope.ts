/**
 * Business scope and epoch for Task B (no React, so it is unit-testable).
 *
 * The *verified* scope (user + personal/project) comes only from the backend
 * (`/api/access/scope`). Every change bumps `epoch` and aborts the previous
 * epoch's AbortSignal, so requests started for an old user/project cannot
 * deliver late private results or progress events into the new one.
 *
 * Developer A's identity module calls `selectProject` from the project
 * selector and `setBusinessScope(null)` on logout; B's modules read the rest.
 */

export type BusinessScope = {
  userId: string;
  projectId: string | null;
  platformRole?: string;
};

export const PROJECT_HEADER = 'X-NeuroWeave-Project';

type Listener = (next: BusinessScope | null, previous: BusinessScope | null) => void;

let current: BusinessScope | null = null;
let requestedProject: string | null = null;
let epoch = 0;
let controller = new AbortController();
const listeners = new Set<Listener>();

export class StaleScopeError extends Error {
  constructor() {
    super('The user or project changed; this response was discarded.');
    this.name = 'StaleScopeError';
  }
}

export function scopeKey(scope: BusinessScope | null | undefined): string {
  return scope?.userId ? `${scope.userId}:${scope.projectId ?? 'personal'}` : 'anonymous';
}

export function currentScope(): BusinessScope | null {
  return current;
}

export function currentEpoch(): number {
  return epoch;
}

export function currentScopeKey(): string {
  return scopeKey(current);
}

/** Abort signal for the current epoch; it aborts as soon as the scope changes. */
export function scopeSignal(): AbortSignal {
  return controller.signal;
}

export function isCurrentEpoch(value: number): boolean {
  return value === epoch;
}

export function assertCurrentEpoch(value: number): void {
  if (value !== epoch) throw new StaleScopeError();
}

function sameScope(a: BusinessScope | null, b: BusinessScope | null): boolean {
  return scopeKey(a) === scopeKey(b);
}

/** Install a newly verified scope. Returns true when it actually changed. */
export function setBusinessScope(next: BusinessScope | null): boolean {
  const normalized = next?.userId ? { ...next, projectId: next.projectId ?? null } : null;
  if (sameScope(current, normalized)) {
    current = normalized;
    return false;
  }
  const previous = current;
  current = normalized;
  epoch += 1;
  controller.abort(new StaleScopeError());
  controller = new AbortController();
  for (const listener of [...listeners]) {
    try {
      listener(current, previous);
    } catch {
      /* one failing cleanup must not block the others */
    }
  }
  return true;
}

/** Project chosen in A's selector; the server still verifies membership. */
export function selectProject(projectId: string | null): void {
  requestedProject = projectId || null;
  if (current && (current.projectId ?? null) !== requestedProject) {
    // Until the server confirms the new scope nothing from the old one may
    // be shown, so the old epoch ends immediately.
    setBusinessScope(null);
  }
}

export function requestedProjectId(): string | null {
  return requestedProject;
}

/** Scope header for the shared HTTP client (A wires it in api/http.ts). */
export function scopeHeaders(): Record<string, string> {
  return requestedProject ? { [PROJECT_HEADER]: requestedProject } : {};
}

export function subscribeScope(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Combine a caller's signal with the epoch signal. */
export function withScopeSignal(signal?: AbortSignal | null): AbortSignal {
  const epochSignal = scopeSignal();
  if (!signal) return epochSignal;
  const any = (AbortSignal as unknown as { any?: (signals: AbortSignal[]) => AbortSignal }).any;
  if (typeof any === 'function') return any([signal, epochSignal]);
  const combined = new AbortController();
  const abort = (source: AbortSignal) => () => combined.abort(source.reason);
  if (signal.aborted) combined.abort(signal.reason);
  else if (epochSignal.aborted) combined.abort(epochSignal.reason);
  else {
    signal.addEventListener('abort', abort(signal), { once: true });
    epochSignal.addEventListener('abort', abort(epochSignal), { once: true });
  }
  return combined.signal;
}

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.keys(value as Record<string, unknown>)
      .sort()
      .filter((key) => (value as Record<string, unknown>)[key] !== undefined)
      .map((key) => `${JSON.stringify(key)}:${stable((value as Record<string, unknown>)[key])}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
}

/**
 * Query hash that always includes the user and effective scope, so cached
 * business data can never be served across accounts or projects even when a
 * feature's query key omits them.
 */
export function scopedQueryHash(queryKey: readonly unknown[]): string {
  return stable([currentScopeKey(), ...queryKey]);
}

/** Browser draft keys are bound to the user and scope; null when signed out. */
export function scopedStorageKey(resource: string, id: string): string | null {
  return current?.userId ? `neuroweave:${resource}:${scopeKey(current)}:${id}` : null;
}

export function scopedStoragePrefix(resource: string): string | null {
  return current?.userId ? `neuroweave:${resource}:${scopeKey(current)}:` : null;
}

/** Test helper: reset module state between cases. */
export function resetBusinessScopeForTests(): void {
  current = null;
  requestedProject = null;
  epoch = 0;
  controller = new AbortController();
  listeners.clear();
}
