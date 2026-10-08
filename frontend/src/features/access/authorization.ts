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
