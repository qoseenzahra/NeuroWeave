import { useMutation, useQueryClient } from '@tanstack/react-query';
import { request } from '../../api/http';
import { sendChat } from './chatApi';
import type { ChatRequest, ChatResponse } from './chatApi';
import type { TurnScope } from './chatTurns';

export function useSendChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ChatRequest): Promise<ChatResponse> => {
      const scope = await request<TurnScope>('/api/chat/scope');
      if (!scope.userId) throw new Error('Authentication required');
      return sendChat(payload, scope);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
    }
  });
}
