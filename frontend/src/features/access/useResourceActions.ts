import { useQuery } from '@tanstack/react-query';
import { resourceView } from './accessApi';
import type { ResourceAction } from './authorization';

/**
 * Server-provided `allowed_actions` for one resource (fail-closed).
 *
 * Buttons are hidden or disabled until the server has said the current
 * user/project may perform the action. The server still re-checks every call.
 */
export function useResourceActions(resourceType: string, resourceId: string | null | undefined) {
  const query = useQuery({
    queryKey: ['resource-access', resourceType, resourceId],
    queryFn: () => resourceView(resourceType, resourceId as string),
    enabled: Boolean(resourceId),
    retry: false,
    staleTime: 15_000,
  });
  const actions = query.data?.allowed_actions ?? [];
  return {
    loaded: query.isSuccess,
    allows: (action: ResourceAction) => query.isSuccess && actions.includes(action),
    refresh: () => query.refetch(),
  };
}
