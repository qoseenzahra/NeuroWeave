import { request } from '../../api/http';
import {
  assertCurrentEpoch,
  currentEpoch,
  currentScope,
  isCurrentEpoch,
  setBusinessScope,
  StaleScopeError,
} from '../access/businessScope';
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

/** Forget every pending turn of one user (sign-out or a different account). */
export function clearPendingTurnsForUser(userId: string): void {
  try {
    const prefix = `neuroweave:pending-chat-turns:${userId}:`;
    for (let i = localStorage.length - 1; i >= 0; i -= 1) {
      const k = localStorage.key(i);
      if (k?.startsWith(prefix)) localStorage.removeItem(k);
    }
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

/** The server says this turn is not (or no longer) visible to this user. */
export function isGoneForThisUser(error: unknown): boolean {
  const status = (error as { status?: number })?.status;
  return status === 403 || status === 404;
}

/** Progress events belong to the epoch that started the turn. */
function progress(turn: Turn, epoch: number): void {
  if (!isCurrentEpoch(epoch) || typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('neuroweave:chat-progress', { detail: turn }));
}

function sameScope(a: TurnScope | null | undefined, b: TurnScope): boolean {
  return Boolean(a?.userId) && a?.userId === b.userId && (a?.projectId ?? null) === (b.projectId ?? null);
}

async function requireCurrentScope(scope: TurnScope, epoch: number): Promise<void> {
  assertCurrentEpoch(epoch);
  const local = currentScope();
  if (local && !sameScope(local, scope)) throw new StaleScopeError();
  const current = await request<TurnScope>('/api/chat/scope');
  if (!sameScope(current, scope)) {
    throw new StaleScopeError();
  }
}

/**
 * The authenticated scope for a chat submission: the verified business scope
 * when present, otherwise the server's answer (which then becomes current).
 */
export async function resolveChatScope(): Promise<TurnScope> {
  const local = currentScope();
  if (local?.userId) return { userId: local.userId, projectId: local.projectId ?? null };
  const scope = await request<TurnScope>('/api/chat/scope');
  if (!scope.userId) throw new Error('Authentication required');
  setBusinessScope(scope);
  return { userId: scope.userId, projectId: scope.projectId ?? null };
}

export async function waitForTurn(id: string, scope: TurnScope, epoch = currentEpoch()): Promise<ChatResponse> {
  for (;;) {
    await requireCurrentScope(scope, epoch);
    let turn: Turn;
    try {
      turn = await request<Turn>(`/api/chat/turns/${encodeURIComponent(id)}`);
    } catch (error) {
      // 403/404: the turn is no longer ours to see (revoked, other account).
      if (isGoneForThisUser(error)) remember(scope.userId, scope.projectId, id, false);
      throw error;
    }
    await requireCurrentScope(scope, epoch);
    progress(turn, epoch);
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
  // Normal submission resolves the trusted scope itself, so a caller that has
  // not loaded it yet no longer fails before sending the request (issue 03).
  const effective = scope?.userId ? scope : await resolveChatScope();
  const epoch = currentEpoch();
  remember(effective.userId, effective.projectId, payload.client_turn_id, true);
  let turn: Turn;
  try {
    turn = await request<Turn>('/api/chat/turns', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  } catch (error) {
    // The server rejected the turn (validation, permission, conflict): there
    // is nothing to recover. Network failures keep it for recovery.
    const status = (error as { status?: number })?.status;
    if (typeof status === 'number' && status >= 400 && status < 500) {
      remember(effective.userId, effective.projectId, payload.client_turn_id, false);
    }
    throw error;
  }
  // Do not emit even the initial response if the authenticated scope changed
  // while the submit request was in flight.
  await requireCurrentScope(effective, epoch);
  progress(turn, epoch);
  return waitForTurn(turn.turn_id, effective, epoch);
}

export async function retryTurn(
  id: string,
  scope: TurnScope,
): Promise<ChatResponse> {
  const epoch = currentEpoch();
  await request(`/api/chat/turns/${encodeURIComponent(id)}/retry`, { method: 'POST' });
  return waitForTurn(id, scope, epoch);
}

export function forgetTurn(id: string, scope: TurnScope): void {
  remember(scope.userId, scope.projectId, id, false);
}
