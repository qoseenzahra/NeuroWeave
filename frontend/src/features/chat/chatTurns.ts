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

function key(userId: string, projectId: string | null): string {
  return `neuroweave:pending-chat-turns:${userId}:${projectId ?? 'personal'}`;
}

function readIds(userId: string, projectId: string | null): string[] {
  try {
    return JSON.parse(localStorage.getItem(key(userId, projectId)) ?? '[]');
  } catch {
    return [];
  }
}

function remember(userId: string, projectId: string | null, id: string, keep: boolean) {
  try {
    const ids = readIds(userId, projectId).filter((v) => v !== id);
    localStorage.setItem(key(userId, projectId), JSON.stringify(keep ? [...ids, id] : ids));
  } catch {
    /* server still retains the turn */
  }
}

export function clearPendingTurnScope(userId: string, projectId: string | null): void {
  try { localStorage.removeItem(key(userId, projectId)); } catch { /* best effort */ }
}

export function clearAllPendingTurnScopes(): void {
  try {
    for (let i = localStorage.length - 1; i >= 0; i -= 1) {
      const k = localStorage.key(i);
      if (k?.startsWith('neuroweave:pending-chat-turns:')) localStorage.removeItem(k);
    }
  } catch { /* best effort */ }
}

function progress(turn: Turn) {
  window.dispatchEvent(new CustomEvent('neuroweave:chat-progress', { detail: turn }));
}

export async function waitForTurn(
  id: string,
  scope: { userId: string; projectId: string | null },
): Promise<ChatResponse> {
  for (;;) {
    const turn = await request<Turn>(`/api/chat/turns/${encodeURIComponent(id)}`);
    progress(turn);
    if (turn.status === 'succeeded' && turn.result) {
      remember(scope.userId, scope.projectId, id, false);
      return turn.result;
    }
    if (!['queued', 'running'].includes(turn.status))
      throw new Error(turn.error?.message ?? turn.message);
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
}

export async function submitTurn(
  payload: ChatRequest,
  scope: { userId: string; projectId: string | null },
): Promise<ChatResponse> {
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
  scope: { userId: string; projectId: string | null },
) {
  await request(`/api/chat/turns/${encodeURIComponent(id)}/retry`, { method: 'POST' });
  return waitForTurn(id, scope);
}

export function forgetTurn(
  id: string,
  scope: { userId: string; projectId: string | null },
) {
  remember(scope.userId, scope.projectId, id, false);
}
