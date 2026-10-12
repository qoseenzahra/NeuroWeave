import { request } from '../../api/http';

export type DirectoryGrant = {
  grant_id: string;
  root: string;
  scope: 'read' | 'write';
  revision: number;
  user_id?: string;
  project_id?: string;
  revoked?: number;
};

export type QuotaPolicy = {
  max_concurrent_units: number;
  max_cpus_per_unit: number;
  max_memory_gb_per_unit: number;
  max_gpus_per_unit: number;
  allowed_nodes: string[] | null;
};

export type MyQuota = {
  user: QuotaPolicy;
  user_reserved_units: number;
  project?: QuotaPolicy;
  project_reserved_units?: number;
};

export type ResourceView = {
  resource_type: string;
  resource_id: string;
  creator_id: string;
  manager_id: string;
  project_id: string | null;
  scope: 'private' | 'project';
  permission_revision: number;
  allowed_actions: string[];
};

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) });

export const myGrants = () => request<{ items: DirectoryGrant[] }>('/api/access/directory-grants/mine');

export const projectGrants = (projectId: string) =>
  request<{ items: DirectoryGrant[] }>(`/api/access/directory-grants?${new URLSearchParams({ project_id: projectId })}`);

export const createGrant = (grant: { project_id: string; user_id: string; root: string; scope: 'read' | 'write' }) =>
  request<DirectoryGrant>('/api/access/directory-grants', json(grant));

export const revokeGrant = (grantId: string) =>
  request<DirectoryGrant>(`/api/access/directory-grants/${encodeURIComponent(grantId)}`, { method: 'DELETE' });

export const myQuota = () => request<MyQuota>('/api/access/quotas/mine');

export const saveQuota = (subject: string, policy: QuotaPolicy) =>
  request<QuotaPolicy>(`/api/access/quotas/${encodeURIComponent(subject)}`, {
    method: 'PUT',
    body: JSON.stringify(policy),
  });

const resourcePath = (type: string, id: string) =>
  `/api/access/resources/${encodeURIComponent(type)}/${encodeURIComponent(id)}`;

export const resourceView = (type: string, id: string) => request<ResourceView>(resourcePath(type, id));

export const shareResource = (type: string, id: string, scope: 'private' | 'project', expectedRevision: number) =>
  request<ResourceView>(`${resourcePath(type, id)}/share`, json({ scope, expected_revision: expectedRevision }));

export const handoverResource = (type: string, id: string, newManagerId: string, expectedRevision: number) =>
  request<ResourceView>(`${resourcePath(type, id)}/handover`, json({ new_manager_id: newManagerId, expected_revision: expectedRevision }));

export const takeoverResource = (type: string, id: string, reason: string, expectedRevision: number) =>
  request<ResourceView>(`${resourcePath(type, id)}/takeover`, json({ reason, expected_revision: expectedRevision }));
