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
const key = 'neuroweave:pending-chat-turns';
export function pendingTurns(): string[] {
  try {
    return JSON.parse(localStorage.getItem(key) ?? '[]');
  } catch {
    return [];
  }
}
const remember = (id: string, keep: boolean) => {
  try {
    localStorage.setItem(
      key,
      JSON.stringify([
        ...new Set([
          ...pendingTurns().filter((v) => v !== id),
          ...(keep ? [id] : [])
        ])
      ])
    );
  } catch {
    /* server still retains the turn */
  }
};
function progress(turn: Turn) {
  window.dispatchEvent(
    new CustomEvent('neuroweave:chat-progress', { detail: turn })
  );
}
export async function waitForTurn(id: string): Promise<ChatResponse> {
  for (;;) {
    const turn = await request<Turn>(
      `/api/chat/turns/${encodeURIComponent(id)}`
    );
    progress(turn);
    if (turn.status === 'succeeded' && turn.result) {
      remember(id, false);
      return turn.result;
    }
    if (!['queued', 'running'].includes(turn.status))
      throw new Error(turn.error?.message ?? turn.message);
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
}
export async function submitTurn(payload: ChatRequest): Promise<ChatResponse> {
  // Record before POST: a lost acknowledgement can still be recovered by ID.
  remember(payload.client_turn_id, true);
  const turn = await request<Turn>('/api/chat/turns', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  progress(turn);
  return waitForTurn(turn.turn_id);
}
export async function retryTurn(id: string) {
  await request(`/api/chat/turns/${encodeURIComponent(id)}/retry`, {
    method: 'POST'
  });
  return waitForTurn(id);
}
export async function forgetTurn(id: string) {
  remember(id, false);
}
