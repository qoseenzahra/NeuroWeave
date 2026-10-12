import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, errorText } from '../../api/http';
import { ui } from '../../lib/libraryText';
import { createGrant, modelPolicy, myGrants, myModelUsage, myQuota, projectGrants, revokeGrant, saveModelPolicy, saveQuota } from './accessApi';
import type { QuotaPolicy } from './accessApi';
import { DirectoryScopeSettings } from './DirectoryScopeSettings';
import { OutputWriteGrantSettings } from './OutputWriteGrantSettings';
import { ResourceLimitsSettings } from './ResourceLimitsSettings';
import { ModelPolicySettings } from './ModelPolicySettings';
import { useBusinessScope } from './useScopeCleanup';

/**
 * Directory scope, output write grants and execution limits for the current
 * personal/project scope. Management controls appear only when the server
 * confirms management permission; it re-checks every change anyway.
 */
export function AccessSettingsSection() {
  const scope = useBusinessScope();
  const client = useQueryClient();
  const projectId = scope?.projectId ?? '';
  const platformAdmin = scope?.platformRole === 'admin';
  const grants = useQuery({ queryKey: ['access', 'grants', 'mine'], queryFn: myGrants, enabled: Boolean(scope) });
  const managed = useQuery({
    queryKey: ['access', 'grants', 'project', projectId],
    queryFn: () => projectGrants(projectId),
    enabled: Boolean(scope) && (platformAdmin || Boolean(projectId)),
    retry: false,
  });
  const quota = useQuery({ queryKey: ['access', 'quota', 'mine'], queryFn: myQuota, enabled: Boolean(scope) });
  const policy = useQuery({ queryKey: ['access', 'model-policy'], queryFn: modelPolicy, enabled: Boolean(scope) });
  const usage = useQuery({ queryKey: ['access', 'model-usage'], queryFn: myModelUsage, enabled: Boolean(scope) });
  const canManage = managed.isSuccess || platformAdmin;
  const forbidden = managed.error instanceof ApiError && managed.error.status === 403;
  const refresh = () => void client.invalidateQueries({ queryKey: ['access'] });
  const create = useMutation({
    mutationFn: (grant: { user_id: string; root: string; scope: 'read' | 'write' }) =>
      createGrant({ ...grant, project_id: projectId }),
    onSuccess: refresh,
  });
  const revoke = useMutation({ mutationFn: revokeGrant, onSuccess: refresh });
  const savePolicy = useMutation({
    mutationFn: (allow: boolean) => saveModelPolicy(policy.data?.subject ?? '', allow),
    onSuccess: refresh,
  });
  const limits = useMutation({
    mutationFn: (policy: QuotaPolicy) => saveQuota(projectId ? `project:${projectId}` : `user:${scope?.userId ?? ''}`, policy),
    onSuccess: refresh,
  });

  if (!scope) {
    return <p className="text-meta text-subtle">{ui('登录后可查看目录与资源权限')}</p>;
  }
  const visible = canManage && managed.data ? managed.data.items.filter((grant) => !grant.revoked) : grants.data?.items ?? [];
  const busy = create.isPending || revoke.isPending || limits.isPending;
  const error = [create.error, revoke.error, limits.error, grants.error].find(Boolean);
  const quotaPolicy = projectId ? quota.data?.project : quota.data?.user;
  const reserved = projectId ? quota.data?.project_reserved_units : quota.data?.user_reserved_units;
  return (
    <div className="space-y-4" data-testid="access-settings">
      <DirectoryScopeSettings projectId={projectId} grants={visible} canManage={canManage && !forbidden}
        onCreate={(grant) => create.mutate(grant)} onRevoke={(id) => revoke.mutate(id)} busy={busy}
        error={error ? errorText(error, ui('权限设置失败')) : undefined} />
      <OutputWriteGrantSettings projectId={projectId} grants={visible} canManage={canManage && !forbidden}
        onCreate={(grant) => create.mutate(grant)} onRevoke={(id) => revoke.mutate(id)} busy={busy} />
      {quotaPolicy && (
        <ResourceLimitsSettings key={JSON.stringify(quotaPolicy)}
          subject={projectId ? `project:${projectId}` : `user:${scope.userId}`}
          policy={quotaPolicy} reservedUnits={reserved}
          canManage={platformAdmin || (Boolean(projectId) && canManage && !forbidden)}
          onSave={(policy) => limits.mutate(policy)} busy={busy} />
      )}
      {policy.data && (
        <ModelPolicySettings policy={policy.data} usage={projectId ? usage.data?.project ?? usage.data?.user : usage.data?.user}
          onChange={(allow) => savePolicy.mutate(allow)} busy={savePolicy.isPending} />
      )}
    </div>
  );
}
