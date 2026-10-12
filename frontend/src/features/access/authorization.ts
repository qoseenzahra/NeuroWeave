/**
 * UI helpers for server-provided `allowed_actions`. Buttons follow these
 * hints, but every operation is still re-authorized by the server.
 */
export type ResourceAction =
  | 'read' | 'create' | 'update' | 'delete' | 'restore'
  | 'publish' | 'share' | 'handover' | 'takeover'
  | 'submit' | 'retry' | 'cancel' | 'confirm' | 'export';

export type ResourceScope = 'private' | 'project';

export type AccessInfo = {
  creator_id: string;
  manager_id: string;
  project_id: string | null;
  scope: ResourceScope;
  permission_revision: number;
};

/** Shape returned by business list/detail endpoints (`annotate` on the server). */
export type AuthorizedPayload = {
  allowed_actions?: readonly string[];
  access?: AccessInfo;
};

export function can(resource: AuthorizedPayload | undefined | null, action: ResourceAction): boolean {
  return Boolean(resource?.allowed_actions?.includes(action));
}

export type ScopeLabel = { scope: ResourceScope; owner: 'mine' | 'other'; managerId: string; creatorId: string };

/** Author/scope label for list rows; undefined when the server sent no access info. */
export function scopeLabel(resource: AuthorizedPayload | undefined | null, currentUserId: string | undefined): ScopeLabel | undefined {
  const access = resource?.access;
  if (!access) return undefined;
  return {
    scope: access.scope,
    owner: currentUserId && access.manager_id === currentUserId ? 'mine' : 'other',
    managerId: access.manager_id,
    creatorId: access.creator_id,
  };
}

/**
 * Management actions the policy panel may offer, in display order. Takeover is
 * never part of an object's allowed actions: it is an explicit, audited
 * platform-administrator operation, so it is offered only to them.
 */
export function managementActions(
  resource: AuthorizedPayload | undefined | null,
  options: { platformAdmin?: boolean } = {},
): ResourceAction[] {
  const actions: ResourceAction[] = (['share', 'handover'] as const).filter((action) => can(resource, action));
  if (options.platformAdmin && resource?.access) actions.push('takeover');
  return actions;
}
