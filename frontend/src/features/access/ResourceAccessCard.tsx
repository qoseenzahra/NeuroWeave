import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { errorText } from '../../api/http';
import { ui } from '../../lib/libraryText';
import { handoverResource, resourceView, shareResource, takeoverResource } from './accessApi';
import type { ResourceView } from './accessApi';
import { ResourcePolicyPanel } from './ResourcePolicyPanel';
import { useBusinessScope } from './useScopeCleanup';

/** Sharing, handover and audited takeover for one data/output/task/Pipeline. */
export function ResourceAccessCard({ resourceType, resourceId }: { resourceType: string; resourceId: string }) {
  const scope = useBusinessScope();
  const client = useQueryClient();
  const queryKey = ['access', 'resource', resourceType, resourceId];
  const view = useQuery({ queryKey, queryFn: () => resourceView(resourceType, resourceId), retry: false });
  const onDone = (next: ResourceView) => {
    client.setQueryData(queryKey, next);
    void client.invalidateQueries({ queryKey: ['workflow-index'] });
  };
  const revision = view.data?.permission_revision ?? 0;
  const share = useMutation({ mutationFn: (target: 'private' | 'project') => shareResource(resourceType, resourceId, target, revision), onSuccess: onDone });
  const handover = useMutation({ mutationFn: (recipient: string) => handoverResource(resourceType, resourceId, recipient, revision), onSuccess: onDone });
  const takeover = useMutation({ mutationFn: (reason: string) => takeoverResource(resourceType, resourceId, reason, revision), onSuccess: onDone });
  if (!view.data) return null;
  const payload = {
    allowed_actions: view.data.allowed_actions,
    access: {
      creator_id: view.data.creator_id, manager_id: view.data.manager_id, project_id: view.data.project_id,
      scope: view.data.scope, permission_revision: view.data.permission_revision,
    },
  };
  const error = share.error ?? handover.error ?? takeover.error;
  return (
    <div className="rounded-card border border-line bg-raised p-3">
      <ResourcePolicyPanel resource={payload} currentUserId={scope?.userId} platformAdmin={scope?.platformRole === 'admin'}
        onShare={(target) => share.mutate(target)} onHandover={(recipient) => handover.mutate(recipient)}
        onTakeover={(reason) => takeover.mutate(reason)}
        busy={share.isPending || handover.isPending || takeover.isPending}
        error={error ? errorText(error, ui('权限操作失败')) : undefined} />
    </div>
  );
}
