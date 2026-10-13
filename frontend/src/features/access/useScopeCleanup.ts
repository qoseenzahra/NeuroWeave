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
import { clearPendingTurnsForUser } from '../chat/chatTurns';

/**
 * Business-context cleanup for an identity or scope switch.
 *
 * Order (A calls this, or mounts `useBusinessScopeSync`, which does it):
 *  1. `setBusinessScope` has already bumped the epoch, aborting old requests
 *     and making late responses throw `StaleScopeError` in `request()`.
 *  2. Cancel in-flight queries, then remove every cached query so no private
 *     data from the previous user/project can be rendered again.
 *  3. Forget the previous user's pending chat turns on sign-out or account
 *     switch (project switches keep each scope's own recovery list).
 *  4. Notify feature modules (`neuroweave:business-scope-changed`) so they
 *     drop local state such as open proposals or draft editors.
 * Server authorization remains authoritative; this only protects the browser.
 */
let lastVerifiedUser: string | null = null;

/** The server confirmed nobody is signed in: forget the last user's turns. */
function signedOut(): void {
  if (lastVerifiedUser) clearPendingTurnsForUser(lastVerifiedUser);
  lastVerifiedUser = null;
}

export function cleanupBusinessContext(
  queryClient: Pick<QueryClient, 'cancelQueries' | 'removeQueries'>,
  previous: BusinessScope | null,
  next: BusinessScope | null,
): void {
  void queryClient.cancelQueries();
  queryClient.removeQueries();
  // Pending chat turns are stored per user *and* project, so switching
  // projects keeps each scope's recovery list. Only a sign-out or a different
  // account forgets the previous user's turns.
  // (A project switch passes through a short "unverified" null scope, which
  // must not count as a sign-out.)
  if (next?.userId) {
    for (const user of new Set([lastVerifiedUser, previous?.userId])) {
      if (user && user !== next.userId) clearPendingTurnsForUser(user);
    }
    lastVerifiedUser = next.userId;
  } else if (previous?.userId) {
    lastVerifiedUser = previous.userId;
  }
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
    if (!scope.userId) signedOut();
    setBusinessScope(scope.userId ? scope : null);
  } catch (error) {
    if (error instanceof StaleScopeError) return currentScope();
    if ((error as { status?: number })?.status === 401) signedOut();
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
