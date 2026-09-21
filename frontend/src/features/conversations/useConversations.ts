import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { InfiniteData, QueryClient } from '@tanstack/react-query';
import {
  fetchConversationSnapshot,
  fetchConversations,
  patchConversation,
  removeConversation
} from './conversationsApi';
import { nextConversationRead, restoreConversationContext } from './conversationContext';
import type { ConversationPage } from './conversationTypes';
import { prependUniqueMessages, toChatMessages } from '../chat/chatMessages';
import type { ChatMessage } from '../chat/chatMessages';

export type ConversationScope = 'active' | 'archived';

export function conversationListKey(
  scope: ConversationScope,
  query: string
): [string, ConversationScope, string] {
  return ['conversations', scope, query.trim()];
}

export function useConversationList(scope: ConversationScope, search: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: conversationListKey(scope, search),
    enabled,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      fetchConversations({
        archived: scope === 'archived',
        query: search,
        cursor: pageParam,
        signal
      }),
    getNextPageParam: (lastPage: ConversationPage) =>
      lastPage.has_more ? lastPage.next_cursor : undefined,
    staleTime: 15_000
  });
}

export type ConversationDetailState = {
  readGeneration: number;
  workspaceId: string | null;
  title: string;
  archived: boolean;
  messages: ChatMessage[];
  hasMoreOlder: boolean;
  beforeSequence: number | null;
  context: Record<string, unknown>;
};

export function useConversationDetail(conversationId: string | null) {
  return useQuery({
    queryKey: ['conversation', conversationId],
    enabled: conversationId !== null,
    staleTime: 10_000,
    queryFn: async ({ signal }): Promise<ConversationDetailState> => {
      if (!conversationId) throw new Error('No conversation selected');
      const readGeneration = nextConversationRead();
      const snapshot = await fetchConversationSnapshot(conversationId, {
        limit: 40,
        signal
      });
      return {
        readGeneration,
        workspaceId: snapshot.conversation.workspace_id ?? null,
        title: snapshot.conversation.title,
        archived: snapshot.conversation.archived,
        messages: toChatMessages(snapshot.messages),
        hasMoreOlder: Boolean(snapshot.has_more),
        beforeSequence:
          snapshot.has_more && snapshot.before_sequence != null ? snapshot.before_sequence : null,
        context: restoreConversationContext(snapshot)
      };
    }
  });
}

export function useLoadOlderMessages(
  conversationId: string | null,
  options: {
    onSettledScroll?: (info: { top: number; height: number } | null) => void;
  } = {}
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      beforeSequence: number;
      anchor: { top: number; height: number } | null;
    }) => {
      if (!conversationId) throw new Error('No conversation selected');
      const snapshot = await fetchConversationSnapshot(conversationId, {
        limit: 40,
        beforeSequence: input.beforeSequence
      });
      return { snapshot, anchor: input.anchor };
    },
    onSuccess: ({ snapshot, anchor }) => {
      if (!conversationId) return;
      queryClient.setQueryData<ConversationDetailState>(
        ['conversation', conversationId],
        (previous) => {
          if (!previous) return previous;
          const older = toChatMessages(snapshot.messages);
          return {
            ...previous,
            title: snapshot.conversation.title,
            archived: snapshot.conversation.archived,
            messages: prependUniqueMessages(previous.messages, older),
            hasMoreOlder: Boolean(snapshot.has_more),
            beforeSequence:
              snapshot.has_more && snapshot.before_sequence != null
                ? snapshot.before_sequence
                : null,
            context: previous.context
          };
        }
      );
      requestAnimationFrame(() => options.onSettledScroll?.(anchor));
    },
    onError: () => {
      options.onSettledScroll?.(null);
    }
  });
}

function invalidateConversationLists(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: ['conversations'] });
}

export function useRenameConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; title: string }) =>
      patchConversation(input.id, { title: input.title }),
    onSuccess: (_data, variables) => {
      queryClient.setQueryData<ConversationDetailState>(
        ['conversation', variables.id],
        (previous) => (previous ? { ...previous, title: variables.title } : previous)
      );
      invalidateConversationLists(queryClient);
    }
  });
}

export function useArchiveConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; archived: boolean }) =>
      patchConversation(input.id, { archived: input.archived }),
    onSuccess: (_data, variables) => {
      queryClient.setQueryData<ConversationDetailState>(
        ['conversation', variables.id],
        (previous) => (previous ? { ...previous, archived: variables.archived } : previous)
      );
      invalidateConversationLists(queryClient);
    }
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => removeConversation(id),
    onSuccess: async (_data, id) => {
      await queryClient.cancelQueries({ queryKey: ['conversation', id] });
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      queryClient.removeQueries({ queryKey: ['conversation', id] });
      queryClient.setQueriesData<InfiniteData<ConversationPage>>(
        { queryKey: ['conversations'] },
        (previous) =>
          previous
            ? {
                ...previous,
                pages: previous.pages.map((page) => ({
                  ...page,
                  conversations: page.conversations.filter((item) => item.conversation_id !== id)
                }))
              }
            : previous
      );
      invalidateConversationLists(queryClient);
    }
  });
}
