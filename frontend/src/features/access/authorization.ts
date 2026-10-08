export type ResourceAction =
  | "read" | "create" | "update" | "delete" | "restore"
  | "publish" | "share" | "handover" | "takeover"
  | "submit" | "retry" | "cancel" | "confirm" | "export";

export type ResourceScope = "private" | "project";

export interface AuthorizedResource {
  id: string;
  projectId?: string;
  scope: ResourceScope;
  allowedActions: readonly ResourceAction[];
}

export function can(resource: AuthorizedResource | undefined, action: ResourceAction): boolean {
  return Boolean(resource?.allowedActions.includes(action));
}

/** Clear stale business-resource state when the authenticated user/scope changes. */
export function scopeKey(userId: string | undefined, projectId: string | undefined): string {
  return [userId ?? "", projectId ?? ""].join(":");
}


export function scopedStorageKey(
  userId: string,
  projectId: string | undefined,
  resource: string,
): string {
  return `neuroweave:${resource}:${scopeKey(userId, projectId)}`;
}

export function clearScopeStorage(
  userId: string,
  projectId: string | undefined,
  prefixes: readonly string[] = ["neuroweave:"],
): void {
  const scope = scopeKey(userId, projectId);
  try {
    for (let i = localStorage.length - 1; i >= 0; i -= 1) {
      const key = localStorage.key(i);
      if (key && prefixes.some((prefix) => key.startsWith(prefix)) && key.includes(scope)) {
        localStorage.removeItem(key);
      }
    }
  } catch {
    /* storage cleanup is best effort; server authorization remains authoritative */
  }
}
