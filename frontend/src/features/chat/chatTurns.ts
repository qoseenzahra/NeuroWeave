import { request } from '../../api/http';
import type { ChatRequest, ChatResponse } from './chatApi';

export type Turn = {
  turn_id: string;
  conversation_id: string;
  status: string;
  message: string;
  result: ChatResponse | null;
  error: { message: string } | null;
};

export type TurnScope = { userId: string; projectId: string | null };

function key(userId: string, projectId: string | null): string {
  return `neuroweave:pending-chat-turns:${userId}:${projectId ?? 'personal'}`;
}

function readIds(userId: string, projectId: string | null): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(key(userId, projectId)) ?? '[]');
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];
  } catch {
    return [];
  }
}

/** Compatibility accessor for existing callers; new code should pass an explicit scope. */
export function pendingTurns(scope?: TurnScope): string[] {
  if (!scope?.userId) return [];
  return readIds(scope.userId, scope.projectId);
}

function remember(userId: string, projectId: string | null, id: string, keep: boolean): void {
  try {
    const ids = readIds(userId, projectId).filter((v) => v !== id);
    localStorage.setItem(key(userId, projectId), JSON.stringify(keep ? [...ids, id] : ids));
  } catch {
    /* server still retains the turn */
  }
}

export function clearPendingTurnScope(userId: string, projectId: string | null): void {
  try {
    localStorage.removeItem(key(userId, projectId));
  } catch {
    /* best effort */
  }
}

export function clearAllPendingTurnScopes(): void {
  try {
    for (let i = localStorage.length - 1; i >= 0; i -= 1) {
      const k = localStorage.key(i);
      if (k?.startsWith('neuroweave:pending-chat-turns:')) localStorage.removeItem(k);
    }
  } catch {
    /* best effort */
  }
}

function progress(turn: Turn): void {
  window.dispatchEvent(new CustomEvent('neuroweave:chat-progress', { detail: turn }));
}

async function requireCurrentScope(scope: TurnScope): Promise<void> {
  const current = await request<TurnScope>('/api/chat/scope');
  if (
    !current.userId ||
    current.userId !== scope.userId ||
    (current.projectId ?? null) !== (scope.projectId ?? null)
  ) {
    throw new Error('Chat scope changed; discard the stale response.');
  }
}

export async function waitForTurn(id: string, scope: TurnScope): Promise<ChatResponse> {
  for (;;) {
    await requireCurrentScope(scope);
    const turn = await request<Turn>(`/api/chat/turns/${encodeURIComponent(id)}`);
    await requireCurrentScope(scope);
    progress(turn);
    if (turn.status === 'succeeded' && turn.result) {
      remember(scope.userId, scope.projectId, id, false);
      return turn.result;
    }
    if (!['queued', 'running'].includes(turn.status)) {
      throw new Error(turn.error?.message ?? turn.message);
    }
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
}

export async function submitTurn(
  payload: ChatRequest,
  scope?: TurnScope,
): Promise<ChatResponse> {
  if (!scope?.userId) {
    throw new Error('An authenticated user scope is required for chat turns.');
  }
  remember(scope.userId, scope.projectId, payload.client_turn_id, true);
  const turn = await request<Turn>('/api/chat/turns', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  progress(turn);
  return waitForTurn(turn.turn_id, scope);
}

export async function retryTurn(
  id: string,
  scope: TurnScope,
): Promise<ChatResponse> {
  await request(`/api/chat/turns/${encodeURIComponent(id)}/retry`, { method: 'POST' });
  return waitForTurn(id, scope);
}

export function forgetTurn(id: string, scope: TurnScope): void {
  remember(scope.userId, scope.projectId, id, false);
}
