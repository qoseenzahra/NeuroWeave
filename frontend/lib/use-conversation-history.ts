'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

export type ConversationListItem = {
  conversation_id: string;
  title: string;
  archived: boolean;
  message_count: number;
  last_message_preview: string;
  last_message_role?: 'user' | 'assistant' | null;
  created_at: string;
  updated_at: string;
};

type ConversationPage = {
  conversations: ConversationListItem[];
  next_cursor: string | null;
  has_more: boolean;
};

export function useConversationHistory(apiBase: string, query: string, archived: boolean) {
  const [conversations, setConversations] = useState<ConversationListItem[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [hasMoreConversations, setHasMoreConversations] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const nextCursor = useRef<string | null>(null);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const currentFetchPage = useRef<((append: boolean) => Promise<void>) | null>(null);

  const fetchPage = useCallback(async (append: boolean) => {
    // Synchronous guard prevents repeated intersection events requesting the same page.
    if (append && (pending.current || !nextCursor.current)) return;
    pending.current?.abort();
    const controller = new AbortController();
    const requestGeneration = ++generation.current;
    pending.current = controller;
    if (!append) {
      nextCursor.current = null;
      setHasMoreConversations(false);
    }
    setIsHistoryLoading(true);
    setHistoryError(null);
    try {
      const parameters = new URLSearchParams({ limit: '20', archived: String(archived) });
      if (query.trim()) parameters.set('q', query.trim());
      if (append && nextCursor.current) parameters.set('cursor', nextCursor.current);
      const response = await fetch(`${apiBase}/api/conversations?${parameters}`, {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error('无法读取对话列表，请重试');
      const page = (await response.json()) as ConversationPage;
      if (!Array.isArray(page.conversations)) throw new Error('对话列表格式异常，请刷新后重试');
      if (requestGeneration !== generation.current) return;
      setConversations((current) => {
        if (requestGeneration !== generation.current) return current;
        if (!append) return page.conversations;
        const seen = new Set(current.map((item) => item.conversation_id));
        return [...current, ...page.conversations.filter((item) => !seen.has(item.conversation_id))];
      });
      nextCursor.current = page.has_more ? page.next_cursor : null;
      setHasMoreConversations(Boolean(nextCursor.current));
    } catch (error) {
      if (!controller.signal.aborted && requestGeneration === generation.current) {
        setHistoryError(error instanceof Error ? error.message : '无法读取对话列表');
      }
    } finally {
      if (requestGeneration === generation.current) {
        pending.current = null;
        setIsHistoryLoading(false);
      }
    }
  }, [apiBase, archived, query]);

  useEffect(() => {
    currentFetchPage.current = fetchPage;
    // Invalidate old responses immediately, including during the search debounce.
    generation.current += 1;
    pending.current?.abort();
    pending.current = null;
    nextCursor.current = null;
    setConversations([]);
    setHasMoreConversations(false);
    setHistoryError(null);
    setIsHistoryLoading(true);
    const timer = window.setTimeout(() => void fetchPage(false), 250);
    return () => {
      window.clearTimeout(timer);
      generation.current += 1;
      pending.current?.abort();
      pending.current = null;
    };
  }, [fetchPage]);

  // A slow chat reply or edit may finish after the user changes filters. These
  // stable callbacks always refresh the current view, never the captured old one.
  const loadConversations = useCallback(() => currentFetchPage.current?.(false), []);
  const loadMoreConversations = useCallback(() => currentFetchPage.current?.(true), []);
  const retryConversations = useCallback(() => currentFetchPage.current?.(Boolean(nextCursor.current)), []);

  return {
    conversations, isHistoryLoading, hasMoreConversations, historyError,
    setHistoryError, loadConversations, loadMoreConversations, retryConversations,
  };
}
