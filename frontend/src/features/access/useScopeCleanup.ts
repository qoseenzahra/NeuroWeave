import { useEffect, useSyncExternalStore } from 'react';
import type { QueryClient } from '@tanstack/react-query';
import { request } from '../../api/http';
import {
  currentScope,
  scopeKey,
  setBusinessScope,
  StaleScopeError,
  subscribeScope,
} from './businessScope';
import type { BusinessScope } from './businessScope';
import { clearAllPendingTurnScopes } from '../chat/chatTurns';

/**
 * Business-context cleanup for an identity or scope switch.
 *
 * Order (A calls this, or mounts `useBusinessScopeSync`, which does it):
 *  1. `setBusinessScope` has already bumped the epoch, aborting old requests
 *     and making late responses throw `StaleScopeError` in `request()`.
 *  2. Cancel in-flight queries, then remove every cached query so no private
 *     data from the previous user/project can be rendered again.
 *  3. Forget pending chat turns and confirmation state of the old scope.
 *  4. Notify feature modules (`neuroweave:business-scope-changed`) so they
 *     drop local state such as open proposals or draft editors.
 * Server authorization remains authoritative; this only protects the browser.
 */
export function cleanupBusinessContext(
  queryClient: Pick<QueryClient, 'cancelQueries' | 'removeQueries'>,
  previous: BusinessScope | null,
  next: BusinessScope | null,
): void {
  void queryClient.cancelQueries();
  queryClient.removeQueries();
  clearAllPendingTurnScopes();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('neuroweave:business-scope-changed', {
        detail: { previous: scopeKey(previous), next: scopeKey(next) },
      }),
    );
  }
}

/** Current verified scope for React components. */
export function useBusinessScope(): BusinessScope | null {
  return useSyncExternalStore(
    (onChange) => subscribeScope(() => onChange()),
    currentScope,
    currentScope,
  );
}

type ScopeResponse = { userId: string; projectId: string | null; platformRole?: string };

/** Verify the scope with the server and install it (null when signed out). */
export async function refreshBusinessScope(): Promise<BusinessScope | null> {
  try {
    const scope = await request<ScopeResponse>('/api/access/scope');
    setBusinessScope(scope.userId ? scope : null);
  } catch (error) {
    if (error instanceof StaleScopeError) return currentScope();
    // 401/403 or network failure: nothing from the old scope may stay visible.
    setBusinessScope(null);
  }
  return currentScope();
}

/**
 * Keep the business scope in sync with A's session and clean up on change.
 * Mounted once at the application root (A wires it next to the identity
 * provider; until then App mounts it directly).
 */
export function useBusinessScopeSync(queryClient: QueryClient, intervalMs = 60_000): BusinessScope | null {
  const scope = useBusinessScope();
  useEffect(() => subscribeScope((next, previous) => cleanupBusinessContext(queryClient, previous, next)), [queryClient]);
  useEffect(() => {
    void refreshBusinessScope();
    const refresh = () => void refreshBusinessScope();
    window.addEventListener('focus', refresh);
    window.addEventListener('neuroweave:identity-changed', refresh);
    const timer = window.setInterval(refresh, intervalMs);
    return () => {
      window.removeEventListener('focus', refresh);
      window.removeEventListener('neuroweave:identity-changed', refresh);
      window.clearInterval(timer);
    };
  }, [intervalMs]);
  return scope;
}

/** @deprecated kept for existing callers; use useBusinessScopeSync. */
export function useScopeCleanup(userId: string | undefined, projectId: string | undefined): void {
  useEffect(() => {
    setBusinessScope(userId ? { userId, projectId: projectId ?? null } : null);
  }, [userId, projectId]);
}
