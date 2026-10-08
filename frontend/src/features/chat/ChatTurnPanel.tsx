import { useEffect, useState } from 'react';
import { useQueries, useQueryClient } from '@tanstack/react-query';
import { request, errorText } from '../../api/http';
import { pendingTurns, retryTurn, forgetTurn } from './chatTurns';
import type { Turn, TurnScope } from './chatTurns';
import { ui } from '../../lib/libraryText';

type ChatTurnPanelProps = {
  onOpen: (id: string) => void;
  scope?: TurnScope;
};

export function ChatTurnPanel({ onOpen, scope }: ChatTurnPanelProps) {
  const [ids, setIds] = useState<string[]>(() => pendingTurns(scope));
  const client = useQueryClient();
  const [error, setError] = useState('');

  useEffect(() => {
    const refresh = () => setIds(pendingTurns(scope));
    window.addEventListener('neuroweave:chat-progress', refresh);
    return () => window.removeEventListener('neuroweave:chat-progress', refresh);
  }, [scope]);

  const turns = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['chat-turn', id],
      queryFn: () => request<Turn>(`/api/chat/turns/${encodeURIComponent(id)}`),
      refetchInterval: (query: { state: { data?: Turn } }) =>
        !query.state.data || ['queued', 'running'].includes(query.state.data.status) ? 1000 : false,
      retry: 1,
    })),
  });

  const completed = turns
    .map((t) => (t.data?.status === 'succeeded' ? t.data.conversation_id : ''))
    .filter(Boolean)
    .join(',');

  useEffect(() => {
    if (completed) {
      void client.invalidateQueries({ queryKey: ['conversations'] });
      for (const id of completed.split(',')) {
        void client.invalidateQueries({ queryKey: ['conversation', id] });
      }
    }
  }, [completed, client]);

  if (!ids.length) return null;

  return (
    <div className="max-h-40 shrink-0 space-y-2 overflow-auto border-b border-line p-3 text-xs" aria-live="polite">
      {error && <p className="text-danger">{error}</p>}
      {turns.map((query, i) => {
        const turn = query.data;
        return (
          <div key={ids[i]} className="flex flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1 break-words">
              {turn ? ui(turn.message) : query.isError ? ui('未能恢复请求，请刷新检查或从会话中重新发送。') : ui('正在恢复对话进度…')}
            </span>
            {turn && (
              <button
                className="rounded border border-line px-2 py-1"
                onClick={() => {
                  onOpen(turn.conversation_id);
                  if (turn.status === 'succeeded' && scope) {
                    void forgetTurn(ids[i], scope);
                    setIds(pendingTurns(scope));
                  }
                }}
              >
                {ui('打开会话')}
              </button>
            )}
            {turn && ['failed', 'interrupted', 'cancelled'].includes(turn.status) && scope && (
              <button
                className="rounded border border-line px-2 py-1"
                onClick={() => {
                  void retryTurn(ids[i], scope)
                    .then(() => client.invalidateQueries({ queryKey: ['chat-turn', ids[i]] }))
                    .catch((e) => setError(errorText(e, ui('重试失败'))));
                  void client.invalidateQueries({ queryKey: ['chat-turn', ids[i]] });
                }}
              >
                {ui('重试同一请求')}
              </button>
            )}
            {turn && ['queued', 'running'].includes(turn.status) ? (
              <button
                className="rounded border border-line px-2 py-1"
                onClick={() => void request(`/api/chat/turns/${encodeURIComponent(ids[i])}/cancel`, { method: 'POST' }).catch((e) => setError(errorText(e, ui('停止失败'))))}
              >
                {ui('停止规划')}
              </button>
            ) : (
              <button
                className="rounded border border-line px-2 py-1"
                onClick={() => {
                  if (scope) {
                    void forgetTurn(ids[i], scope);
                    setIds(pendingTurns(scope));
                  }
                }}
              >
                {ui('关闭提示')}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
