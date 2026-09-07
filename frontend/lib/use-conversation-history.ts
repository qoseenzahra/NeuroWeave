'use client';

import { useCallback, useEffect, useReducer, useRef } from 'react';

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

type CachedHistory = {
  conversations: ConversationListItem[];
  nextCursor: string | null;
  fetchedAt: number;
};

type HistoryView = {
  conversations: ConversationListItem[];
  isHistoryLoading: boolean;
  nextCursor: string | null;
  historyError: string | null;
};
const EMPTY_VIEW: HistoryView = {
  conversations: [], isHistoryLoading: false, nextCursor: null, historyError: null,
};

export function useConversationHistory(apiBase: string, query: string, archived: boolean, enabled = true) {
  // 一次更新列表视图，避免条目、翻页游标和错误状态分别维护时相互脱节。
  const [view, updateView] = useReducer(
    (previous: HistoryView, patch: Partial<HistoryView>) => ({ ...previous, ...patch }), EMPTY_VIEW,
  );
  const setHistoryError = useCallback((historyError: string | null) => updateView({ historyError }), []);
  const nextCursor = useRef<string | null>(null);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const currentFetchPage = useRef<((append: boolean) => Promise<void>) | null>(null);
  const cache = useRef(new Map<string, CachedHistory>());
  const failedAppend = useRef(false);
  const normalizedQuery = query.trim();
  const cacheKey = JSON.stringify([apiBase, archived, normalizedQuery]);

  const fetchPage = useCallback(async (append: boolean) => {
    if (!enabled || (append && (pending.current || !nextCursor.current))) return;
    pending.current?.abort();
    const controller = new AbortController();
    const requestGeneration = ++generation.current;
    pending.current = controller;
    failedAppend.current = append;
    updateView({ isHistoryLoading: true, historyError: null });
    try {
      const parameters = new URLSearchParams({ limit: '20', archived: String(archived) });
      if (normalizedQuery) parameters.set('q', normalizedQuery);
      if (append && nextCursor.current) parameters.set('cursor', nextCursor.current);
      const response = await fetch(`${apiBase}/api/conversations?${parameters}`, { signal: controller.signal });
      if (!response.ok) throw new Error('无法读取对话列表，请重试');
      const page = (await response.json()) as ConversationPage;
      if (!Array.isArray(page.conversations)) throw new Error('对话列表格式异常，请刷新后重试');
      if (requestGeneration !== generation.current || controller.signal.aborted) return;
      const existing = append ? cache.current.get(cacheKey)?.conversations ?? [] : [];
      const seen = new Set(existing.map((item) => item.conversation_id));
      const merged = [...existing, ...page.conversations.filter((item) => !seen.has(item.conversation_id))];
      nextCursor.current = page.has_more ? page.next_cursor : null;
      cache.current.delete(cacheKey);
      cache.current.set(cacheKey, { conversations: merged, nextCursor: nextCursor.current, fetchedAt: Date.now() });
      // Bound cached search/filter scopes; each retains its loaded pages.
      while (cache.current.size > 6) cache.current.delete(cache.current.keys().next().value!);
      updateView({ conversations: merged, nextCursor: nextCursor.current });
    } catch (error) {
      if (!controller.signal.aborted && requestGeneration === generation.current) {
        updateView({ historyError: error instanceof Error ? error.message : '无法读取对话列表' });
      }
    } finally {
      if (requestGeneration === generation.current) {
        pending.current = null;
        updateView({ isHistoryLoading: false });
      }
    }
  }, [apiBase, archived, cacheKey, enabled, normalizedQuery]);

  useEffect(() => {
    currentFetchPage.current = enabled ? fetchPage : null;
    generation.current += 1;
    pending.current?.abort();
    pending.current = null;
    let timer: number | undefined;
    if (!enabled) {
      updateView({ isHistoryLoading: false });
    } else {
      const saved = cache.current.get(cacheKey);
      nextCursor.current = saved?.nextCursor ?? null;
      const fresh = Boolean(saved && Date.now() - saved.fetchedAt < 30_000);
      updateView({ conversations: saved?.conversations ?? [], nextCursor: nextCursor.current,
        historyError: null, isHistoryLoading: !fresh });
      if (!fresh) {
        // Only search typing is debounced. Opening the list starts immediately.
        if (normalizedQuery) timer = window.setTimeout(() => void fetchPage(false), 250);
        else void fetchPage(false);
      }
    }
    return () => {
      window.clearTimeout(timer);
      generation.current += 1;
      pending.current?.abort();
      pending.current = null;
    };
  }, [cacheKey, enabled, fetchPage, normalizedQuery]);

  // Mutations invalidate all scopes, including message-content search caches.
  // Preserve visible rows during refresh; a hidden list fetches only when opened.
  const loadConversations = useCallback(() => {
    cache.current.clear();
    return currentFetchPage.current?.(false);
  }, []);
  const loadMoreConversations = useCallback(() => currentFetchPage.current?.(true), []);
  const retryConversations = useCallback(() => currentFetchPage.current?.(failedAppend.current), []);

  return {
    ...view, hasMoreConversations: Boolean(view.nextCursor),
    setHistoryError, loadConversations, loadMoreConversations, retryConversations,
  };
}
